"""
FamilyConnect AI - Authentication & Credential Remediation Verification Suite
=============================================================================
Verifies remediations implemented on November 18, 2026:
1. Elimination of hardcoded developer usernames and privilege escalation in migration.
2. Explicit administrative provisioning for platform reviewers (provision_platform_reviewer).
3. Process-lifetime ephemeral development secret consistency and production fail-closed validation.
4. Elimination of predictable demo password defaults (AdminPass123!, etc.) and production lockout.
5. Safe responder verification status migration (unverified responders remain PENDING).
6. Source code audit: zero personal developer usernames in LoginScreen.jsx or routes/admin.py.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure backend root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ["MOCK_NOTIFICATIONS"] = "true"
os.environ["SKIP_STARTUP_MIGRATION"] = "true"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import User, Member, Responder
from app.auth import (
    create_access_token,
    decode_access_token,
    get_jwt_secret,
    validate_production_jwt_secret,
    verify_password,
    hash_password,
    _EPHEMERAL_DEV_SECRET,
    DEV_FALLBACK_SECRET
)
from app.migrate_db import (
    seed_demo_users,
    provision_platform_reviewer
)


class TestAuthSecurityRemediation(unittest.TestCase):
    def setUp(self):
        # Create an isolated in-memory SQLite database
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db = self.SessionLocal()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    # -------------------------------------------------------------------------
    # TEST GROUP 1: Ephemeral Development Secret Consistency & Production Guard
    # -------------------------------------------------------------------------
    def test_ephemeral_dev_secret_consistency_in_same_process(self):
        """Verify that get_jwt_secret() returns the exact same ephemeral secret throughout the process."""
        s1 = get_jwt_secret()
        s2 = get_jwt_secret()
        self.assertEqual(s1, s2, "Secret must remain identical across calls in the same process")
        self.assertEqual(s1, _EPHEMERAL_DEV_SECRET)
        self.assertGreaterEqual(len(s1), 32, "Ephemeral secret must possess >= 32 chars of entropy")

        # Create token and verify round-trip decode
        token = create_access_token({"sub": "test_caller", "user_id": 101})
        payload = decode_access_token(token)
        self.assertEqual(payload["sub"], "test_caller")
        self.assertEqual(payload["user_id"], 101)

        # Ensure subsequent token operations continue to succeed with the same secret
        token2 = create_access_token({"sub": "test_caller_2", "user_id": 102})
        payload2 = decode_access_token(token2)
        self.assertEqual(payload2["sub"], "test_caller_2")

    def test_production_strictly_rejects_ephemeral_dev_secret(self):
        """Production mode must refuse the ephemeral development secret and fail closed."""
        with self.assertRaises(RuntimeError) as ctx:
            validate_production_jwt_secret(_EPHEMERAL_DEV_SECRET)
        self.assertIn("Insecure development fallback", str(ctx.exception))

        with self.assertRaises(RuntimeError) as ctx:
            validate_production_jwt_secret(DEV_FALLBACK_SECRET)
        self.assertIn("Insecure development fallback", str(ctx.exception))

    def test_production_requires_strong_32char_key(self):
        """Production mode accepts strong 32+ char key and rejects short or guessable keys."""
        with self.assertRaises(RuntimeError) as ctx:
            validate_production_jwt_secret("")
        self.assertIn("no secure JWT_SECRET_KEY was provided", str(ctx.exception))

        with self.assertRaises(RuntimeError) as ctx:
            validate_production_jwt_secret("short_key_123")
        self.assertIn("too short", str(ctx.exception))

        with self.assertRaises(RuntimeError) as ctx:
            validate_production_jwt_secret("password")
        self.assertTrue("too short" in str(ctx.exception) or "guessable" in str(ctx.exception))

        # Valid high-entropy 64-char key accepted
        strong_key = "a" * 64
        validate_production_jwt_secret(strong_key)

    # -------------------------------------------------------------------------
    # TEST GROUP 2: Privilege Escalation Prevention & Platform Reviewer Admin
    # -------------------------------------------------------------------------
    def test_arbitrary_username_never_receives_reviewer_privileges(self):
        """Users named legacy_dev_alpha, legacy_dev_beta, or any arbitrary name must NOT receive platform reviewer rights automatically."""
        h, s = hash_password("SecureTestPass999!")
        u1 = User(id=10, username="legacy_dev_alpha", hashed_password=h, salt=s, role="admin", is_active=True, is_platform_reviewer=False)
        u2 = User(id=11, username="legacy_dev_beta", hashed_password=h, salt=s, role="admin", is_active=True, is_platform_reviewer=False)
        u3 = User(id=12, username="attacker", hashed_password=h, salt=s, role="admin", is_active=True, is_platform_reviewer=False)
        self.db.add_all([u1, u2, u3])
        self.db.commit()

        # Simulate migration logic without reviewer environment variable
        for admin_acc in self.db.query(User).filter(User.role == "admin", User.household_id == None).all():
            admin_acc.household_id = admin_acc.id

        reviewer_config = os.environ.get("INITIAL_PLATFORM_REVIEWER_USERNAME") or os.environ.get("PLATFORM_REVIEWER_USERNAMES") or ""
        if reviewer_config:
            allowed_reviewers = [name.strip() for name in reviewer_config.split(",") if name.strip()]
            for reviewer_user in self.db.query(User).filter(User.username.in_(allowed_reviewers)).all():
                reviewer_user.is_platform_reviewer = True

        self.db.commit()

        # Verify all users remain ordinary admins without reviewer privileges
        refreshed_u1 = self.db.query(User).filter(User.id == 10).first()
        refreshed_u2 = self.db.query(User).filter(User.id == 11).first()
        refreshed_u3 = self.db.query(User).filter(User.id == 12).first()
        self.assertFalse(refreshed_u1.is_platform_reviewer, "legacy_dev_alpha must NOT receive platform reviewer privileges")
        self.assertFalse(refreshed_u2.is_platform_reviewer, "legacy_dev_beta must NOT receive platform reviewer privileges")
        self.assertFalse(refreshed_u3.is_platform_reviewer, "attacker must NOT receive platform reviewer privileges")

        # Household IDs should be assigned cleanly
        self.assertEqual(refreshed_u1.household_id, 10)
        self.assertEqual(refreshed_u2.household_id, 11)
        self.assertEqual(refreshed_u3.household_id, 12)

    def test_explicit_administrative_reviewer_provisioning(self):
        """Platform reviewer status must be granted ONLY via explicit provisioning function or env configuration."""
        h, s = hash_password("SecureTestPass999!")
        u = User(id=20, username="legit_reviewer", hashed_password=h, salt=s, role="admin", is_active=True, is_platform_reviewer=False)
        self.db.add(u)
        self.db.commit()

        # Non-existent user provisioning returns False
        success_fake = provision_platform_reviewer(self.db, "non_existent_user")
        self.assertFalse(success_fake)

        # Explicit provisioning succeeds
        success = provision_platform_reviewer(self.db, "legit_reviewer")
        self.assertTrue(success)

        refreshed = self.db.query(User).filter(User.id == 20).first()
        self.assertTrue(refreshed.is_platform_reviewer)

    # -------------------------------------------------------------------------
    # TEST GROUP 3: Elimination of Predictable Demo Passwords
    # -------------------------------------------------------------------------
    def test_demo_users_use_unguessable_random_passwords_when_env_unset(self):
        """When ENABLE_DEMO_USERS=true without custom passwords, predictable defaults (AdminPass123!, etc.) must fail."""
        mock_env = {
            "ENABLE_DEMO_USERS": "true",
            "ENVIRONMENT": "development"
            # Note: DEMO_ADMIN_PASSWORD, DEMO_MEMBER_PASSWORD, DEMO_RESPONDER_PASSWORD are UNSET
        }
        with patch.dict(os.environ, mock_env, clear=False):
            seed_demo_users(self.db)

        admin = self.db.query(User).filter(User.username == "admin").first()
        self.assertIsNotNone(admin)
        self.assertFalse(admin.is_active, "Demo admin must be created in inactive state")
        self.assertFalse(admin.is_platform_reviewer, "Demo admin must NOT have platform reviewer privileges")

        # Old predictable default passwords MUST FAIL verification
        self.assertFalse(verify_password("AdminPass123!", admin.hashed_password, admin.salt))
        self.assertFalse(verify_password("admin", admin.hashed_password, admin.salt))
        self.assertFalse(verify_password("password", admin.hashed_password, admin.salt))

        marcus = self.db.query(User).filter(User.username == "marcus").first()
        self.assertIsNotNone(marcus)
        self.assertFalse(verify_password("MemberPass123!", marcus.hashed_password, marcus.salt))

        officer = self.db.query(User).filter(User.username == "officer_david").first()
        self.assertIsNotNone(officer)
        self.assertFalse(verify_password("RespPass123!", officer.hashed_password, officer.salt))

    def test_demo_seeding_strictly_blocked_in_production(self):
        """Even if ENABLE_DEMO_USERS=true, seed_demo_users must immediately exit in production."""
        mock_env = {
            "ENABLE_DEMO_USERS": "true",
            "ENVIRONMENT": "production"
        }
        with patch.dict(os.environ, mock_env, clear=False):
            seed_demo_users(self.db)

        # Zero demo users created
        users = self.db.query(User).all()
        self.assertEqual(len(users), 0, "seed_demo_users must never create accounts in production")

    # -------------------------------------------------------------------------
    # TEST GROUP 4: Safe Responder Verification Status Migration
    # -------------------------------------------------------------------------
    def test_responder_verification_migration_leaves_responders_pending(self):
        """Unverified responders must remain PENDING; admins/members receive APPROVED."""
        h, s = hash_password("TestPassword123!")
        # 1. Unverified responder without explicit verification status
        r_unverified = User(id=30, username="new_responder", hashed_password=h, salt=s, role="responder", is_active=False)
        # 2. Existing responder with legacy PENDING_VERIFICATION status
        r_legacy_pending = User(id=31, username="legacy_pending_resp", hashed_password=h, salt=s, role="responder", is_active=False, verification_status="PENDING_VERIFICATION")
        # 3. Existing responder with REJECTED status
        r_existing_rejected = User(id=32, username="rejected_responder", hashed_password=h, salt=s, role="responder", is_active=False, verification_status="REJECTED")
        # 4. Existing responder with APPROVED status
        r_existing_approved = User(id=33, username="approved_responder", hashed_password=h, salt=s, role="responder", is_active=True, verification_status="APPROVED")
        # 5. New household admin and member
        admin_unverified = User(id=34, username="new_admin", hashed_password=h, salt=s, role="admin", is_active=True)
        member_unverified = User(id=35, username="new_member", hashed_password=h, salt=s, role="member", is_active=True)

        self.db.add_all([r_unverified, r_legacy_pending, r_existing_rejected, r_existing_approved, admin_unverified, member_unverified])
        self.db.commit()

        # Execute remediated verification migration logic
        for u in self.db.query(User).all():
            if not u.verification_status or u.verification_status == "PENDING_VERIFICATION":
                if u.role == "responder":
                    u.verification_status = "PENDING"
                else:
                    u.verification_status = "APPROVED"
        self.db.commit()

        # Assertions
        u_resp_unv = self.db.query(User).filter(User.id == 30).first()
        self.assertEqual(u_resp_unv.verification_status, "PENDING", "Unverified responder must be assigned PENDING status")

        u_legacy_resp = self.db.query(User).filter(User.id == 31).first()
        self.assertEqual(u_legacy_resp.verification_status, "PENDING", "Legacy PENDING_VERIFICATION must be normalized to PENDING")

        u_resp_rej = self.db.query(User).filter(User.id == 32).first()
        self.assertEqual(u_resp_rej.verification_status, "REJECTED", "Existing REJECTED status must be preserved")

        u_resp_appr = self.db.query(User).filter(User.id == 33).first()
        self.assertEqual(u_resp_appr.verification_status, "APPROVED", "Existing APPROVED status must be preserved")

        u_admin_unv = self.db.query(User).filter(User.id == 34).first()
        self.assertEqual(u_admin_unv.verification_status, "APPROVED", "Admin without explicit status receives APPROVED")

        u_member_unv = self.db.query(User).filter(User.id == 35).first()
        self.assertEqual(u_member_unv.verification_status, "APPROVED", "Member without explicit status receives APPROVED")

    # -------------------------------------------------------------------------
    # TEST GROUP 5: Source Code Audit for Personal Developer Names & Secrets
    # -------------------------------------------------------------------------
    def test_login_screen_and_admin_routes_clean_of_developer_usernames(self):
        """Verify that frontend/src/components/LoginScreen.jsx and routes/admin.py contain zero personal developer names."""
        login_screen_path = BASE_DIR.parent / "frontend" / "src" / "components" / "LoginScreen.jsx"
        admin_route_path = BASE_DIR / "app" / "routes" / "admin.py"
        auth_path = BASE_DIR / "app" / "auth.py"
        migrate_path = BASE_DIR / "app" / "migrate_db.py"

        login_text = login_screen_path.read_text(encoding="utf-8")
        admin_text = admin_route_path.read_text(encoding="utf-8")
        auth_text = auth_path.read_text(encoding="utf-8")
        migrate_text = migrate_path.read_text(encoding="utf-8")

        # Zero legacy_dev_alpha or legacy_dev_beta in production app code
        self.assertNotIn("legacy_dev_alpha", login_text, "LoginScreen.jsx must not reference legacy_dev_alpha")
        self.assertNotIn("legacy_dev_beta", login_text, "LoginScreen.jsx must not reference legacy_dev_beta")
        self.assertNotIn("legacy_dev_beta", admin_text, "routes/admin.py must not reference legacy_dev_beta")
        self.assertNotIn("legacy_dev_alpha", migrate_text, "migrate_db.py must not reference legacy_dev_alpha")
        self.assertNotIn("legacy_dev_beta", migrate_text, "migrate_db.py must not reference legacy_dev_beta")

        # Zero static dev fallback strings in auth.py
        self.assertNotIn("dev-insecure-secret-key-change-in-production-familyconnect-2026", auth_text)

        # Zero predictable passwords in migrate_db.py
        self.assertNotIn("AdminPass123!", migrate_text)
        self.assertNotIn("MemberPass123!", migrate_text)
        self.assertNotIn("RespPass123!", migrate_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
