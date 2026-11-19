"""
FamilyConnect AI - Phase 3B Test Suite
Comprehensive Automated Verification for:
1. Household Invitations (Creation, Hashing, Expiration, Scoping, Revocation, Single-Use Acceptance)
2. First-Responder Onboarding (Application, Pending Status, Login Block, Reviewer RBAC, Approval/Rejection Lifecycle)
"""

import os
import sys
import json
import hashlib
import datetime
import urllib.request
import urllib.error

# Ensure MOCK_NOTIFICATIONS is set to strictly prevent any external email delivery
os.environ["MOCK_NOTIFICATIONS"] = "true"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app import models
from app.services.notifications import get_captured_dispatches, clear_captured_dispatches

import threading
import time
import uvicorn

BASE_URL = "http://127.0.0.1:8000"


def ensure_server_running():
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=1):
            return None
    except Exception:
        pass

    from app.main import app
    config = uvicorn.Config(app=app, host="127.0.0.1", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=1):
                break
        except Exception:
            time.sleep(0.1)
    return server


class HttpClient:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip("/")

    def request(self, method: str, path: str, json_body=None, token=None):
        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = json.dumps(json_body).encode("utf-8") if json_body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                code = resp.status
                body = resp.read().decode("utf-8")
                return code, json.loads(body) if body else {}
        except urllib.error.HTTPError as err:
            code = err.code
            body = err.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = {"detail": body}
            return code, parsed


client = HttpClient(BASE_URL)
test_created_user_ids = []
test_created_invitation_ids = []
test_created_app_ids = []
test_created_responder_ids = []
test_created_member_ids = []


def cleanup():
    db = SessionLocal()
    try:
        if test_created_invitation_ids:
            db.query(models.HouseholdInvitation).filter(
                models.HouseholdInvitation.id.in_(test_created_invitation_ids)
            ).delete(synchronize_session=False)

        if test_created_app_ids:
            db.query(models.ResponderApplication).filter(
                models.ResponderApplication.id.in_(test_created_app_ids)
            ).delete(synchronize_session=False)

        if test_created_responder_ids:
            db.query(models.Responder).filter(
                models.Responder.id.in_(test_created_responder_ids)
            ).delete(synchronize_session=False)

        if test_created_user_ids:
            users_to_clean = db.query(models.User).filter(models.User.id.in_(test_created_user_ids)).all()
            for u in users_to_clean:
                u.member_id = None
                u.household_id = None
            db.commit()

        if test_created_member_ids:
            db.query(models.Member).filter(
                models.Member.id.in_(test_created_member_ids)
            ).delete(synchronize_session=False)

        if test_created_user_ids:
            db.query(models.Member).filter(
                models.Member.user_id.in_(test_created_user_ids)
            ).delete(synchronize_session=False)
            db.query(models.User).filter(
                models.User.id.in_(test_created_user_ids)
            ).delete(synchronize_session=False)

        db.commit()
    except Exception as e:
        print(f"[Cleanup Warning] {e}")
    finally:
        db.close()


def run_tests():
    print("=" * 80)
    print("PHASE 3B AUTOMATED TEST SUITE: HOUSEHOLD INVITATIONS & RESPONDER ONBOARDING")
    print("=" * 80)

    clear_captured_dispatches()

    passed = 0
    total = 0

    def assert_true(cond, name, msg=""):
        nonlocal passed, total
        total += 1
        if cond:
            passed += 1
            print(f"  [PASS] {name}")
        else:
            print(f"  [FAIL] {name}: {msg}")
            raise AssertionError(f"{name}: {msg}")

    try:
        ensure_server_running()

        # Step 0: Obtain authenticated tokens for active admin accounts
        # Admin Beta (Household 5, is_platform_reviewer=True)
        # Admin Alpha (Household 4, is_platform_reviewer=False)
        from app.database import SessionLocal
        from app.models import User
        from app.auth import create_access_token

        _db = SessionLocal()
        try:
            _u4 = _db.query(User).filter(User.id == 4).first()
            _u5 = _db.query(User).filter(User.id == 5).first()
            alpha_name = _u4.username if _u4 else "test_admin_alpha"
            beta_name = _u5.username if _u5 else "test_admin_beta"
        finally:
            _db.close()

        beta_token = create_access_token({"sub": beta_name, "user_id": 5, "role": "admin", "household_id": 5})
        code, beta_user = client.request("GET", "/api/auth/me", token=beta_token)
        assert_true(code == 200, "Admin Beta authenticated on /api/auth/me")
        assert_true(beta_user.get("is_platform_reviewer") is True, "Admin Beta is_platform_reviewer verified (True)")

        alpha_token = create_access_token({"sub": alpha_name, "user_id": 4, "role": "admin", "household_id": 4})
        code, alpha_user = client.request("GET", "/api/auth/me", token=alpha_token)
        assert_true(code == 200, "Admin Alpha authenticated on /api/auth/me")
        assert_true(alpha_user.get("is_platform_reviewer") is False, "Admin Alpha is ordinary admin (is_platform_reviewer=False)")

        # -------------------------------------------------------------
        # Part 1: Household Invitations
        # -------------------------------------------------------------
        print("\n--- TEST GROUP 1: HOUSEHOLD INVITATIONS ---")

        # 1.1 Admin Alpha creates invitation
        invite_email = f"invited_member_{int(datetime.datetime.utcnow().timestamp())}@familycircle.test"
        code, resp = client.request("POST", "/api/household/invitations", {
            "email": invite_email,
            "role": "member"
        }, token=alpha_token)
        assert_true(code == 201, "Create household invitation as Household 4 Admin", f"Got status {code}: {resp}")
        inv_id = resp["id"]
        raw_token = resp["invitation_token"]
        test_created_invitation_ids.append(inv_id)
        assert_true(raw_token is not None and len(raw_token) > 20, "Invitation token returned to admin upon creation")
        assert_true(resp["household_id"] == 4, "Invitation household_id strictly scoped to caller's household (4)")

        # 1.2 Verify Database Token Hashing (Raw token must NEVER be stored in DB)
        db = SessionLocal()
        inv_record = db.query(models.HouseholdInvitation).filter(models.HouseholdInvitation.id == inv_id).first()
        expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        assert_true(inv_record.token_hash == expected_hash, "Token stored in DB as SHA-256 hash (never plaintext)")
        db.close()

        # 1.3 Verify Notification Dispatch
        from app.services.notifications import send_household_invitation_email
        dispatch_res = send_household_invitation_email(
            recipient_email=invite_email,
            inviter_name=alpha_name,
            household_name=f"{alpha_name}'s Household",
            invitation_link=f"http://127.0.0.1:5173/accept-invite?token={raw_token}",
            role="member",
            expires_hours=72
        )
        assert_true(dispatch_res.status in ("SENT", "DELIVERED", "SIMULATED"), f"Mock notification dispatch returned valid status, got {dispatch_res.status}")
        dispatches = get_captured_dispatches()
        assert_true(len(dispatches) >= 1, "Mock notification captured invitation dispatch")
        latest_dispatch = dispatches[-1]
        assert_true(latest_dispatch["recipient"] == invite_email, "Invitation email sent to correct recipient")
        assert_true("Invitation" in latest_dispatch["subject"], "Invitation email subject contains 'Invitation'")
        assert_true(raw_token in latest_dispatch["html"] or raw_token in latest_dispatch["body"], "Invitation body contains secure acceptance link with raw token")

        # 1.4 Scoped Listing: Household 4 sees invitation, Household 5 does NOT
        code, resp_alpha = client.request("GET", "/api/household/invitations", token=alpha_token)
        assert_true(code == 200, "Household 4 lists invitations")
        alpha_inv_ids = [inv["id"] for inv in resp_alpha]
        assert_true(inv_id in alpha_inv_ids, "Household 4 sees their created invitation")

        code, resp_beta = client.request("GET", "/api/household/invitations", token=beta_token)
        assert_true(code == 200, "Household 5 lists invitations")
        beta_inv_ids = [inv["id"] for inv in resp_beta]
        assert_true(inv_id not in beta_inv_ids, "Household 5 CANNOT see Household 4's invitations (Tenant Isolation)")

        # 1.5 Public Token Validation
        code, val_resp = client.request("GET", f"/api/household/invitations/validate?token={raw_token}")
        assert_true(code == 200 and val_resp.get("valid") is True, "Public token validation succeeds for valid token")
        assert_true(val_resp.get("email") == invite_email, "Validated token returns matching email")

        # Invalid token validation
        code, val_resp_bad = client.request("GET", f"/api/household/invitations/validate?token=invalid_dummy_token_12345")
        assert_true(val_resp_bad.get("valid") is False, "Public token validation rejects invalid token")

        # 1.6 Accept Invitation
        accepted_username = f"new_member_{int(datetime.datetime.utcnow().timestamp())}"
        code, accept_resp = client.request("POST", "/api/household/invitations/accept", {
            "token": raw_token,
            "username": accepted_username,
            "password": "MemberSecurePass123",
            "full_name": "Test Invited Member",
            "phone": "+1 (555) 777-8899"
        })
        assert_true(code == 201, "Accept invitation registers new user and joins household", f"Got status {code}: {accept_resp}")
        assert_true("access_token" in accept_resp, "Accept invitation returns authenticated access token")
        new_user = accept_resp["user"]
        test_created_user_ids.append(new_user["id"])
        if new_user.get("member_id"):
            test_created_member_ids.append(new_user["member_id"])
        assert_true(new_user["role"] == "member", "New user assigned role 'member'")
        assert_true(new_user["household_id"] == 4, "New user bound to inviting household (4)")

        # 1.7 Single-Use Enforcement: Second accept must fail
        code, replay_resp = client.request("POST", "/api/household/invitations/accept", {
            "token": raw_token,
            "username": f"{accepted_username}_replay",
            "password": "MemberSecurePass123"
        })
        assert_true(code == 400, "Single-use enforcement: reusing accepted token is rejected with 400", f"Got {code}")

        # 1.8 Revocation Workflow
        code, resp = client.request("POST", "/api/household/invitations", {
            "email": f"to_revoke_{int(datetime.datetime.utcnow().timestamp())}@familycircle.test",
            "role": "member"
        }, token=alpha_token)
        assert_true(code == 201, "Create second invitation to test revocation")
        revoke_id = resp["id"]
        revoke_token = resp["invitation_token"]
        test_created_invitation_ids.append(revoke_id)

        # Cross-household revocation rejection (Admin Beta cannot revoke Admin Alpha's invitation)
        code, cross_rev = client.request("DELETE", f"/api/household/invitations/{revoke_id}", token=beta_token)
        assert_true(code in (403, 404), "Cross-household revocation rejected (Tenant Protection)")

        # Legitimate revocation by owner
        code, owner_rev = client.request("DELETE", f"/api/household/invitations/{revoke_id}", token=alpha_token)
        assert_true(code == 200, "Owner successfully revokes invitation")

        # Validate revoked token
        code, val_revoked = client.request("GET", f"/api/household/invitations/validate?token={revoke_token}")
        assert_true(val_revoked.get("valid") is False, "Revoked token fails validation")

        # -------------------------------------------------------------
        # Part 2: First-Responder Onboarding & Vetting
        # -------------------------------------------------------------
        print("\n--- TEST GROUP 2: FIRST-RESPONDER ONBOARDING ---")

        # 2.1 Responder Application Submission
        resp_username = f"medic_applicant_{int(datetime.datetime.utcnow().timestamp())}"
        resp_email = f"{resp_username}@paramedic.org"
        code, app_resp = client.request("POST", "/api/auth/register-responder", {
            "username": resp_username,
            "password": "MedicPassword123",
            "email": resp_email,
            "phone": "+1 (555) 911-0022",
            "full_name": "Medic Jane Foster",
            "organization": "City Paramedic Squad 4",
            "badge_id": "MEDIC-889",
            "skills": "ACLS, Trauma Response"
        })
        assert_true(code == 201, "Submit responder registration application", f"Got status {code}: {app_resp}")
        assert_true(app_resp.get("status") == "pending_approval", "Application status reports pending_approval")
        app_id = app_resp["application_id"]
        test_created_app_ids.append(app_id)

        # Retrieve applicant User ID for cleanup and checks
        db = SessionLocal()
        applicant_user = db.query(models.User).filter(models.User.username == resp_username).first()
        assert_true(applicant_user is not None, "User record created for applicant")
        assert_true(applicant_user.is_active is False, "Applicant user is_active is strictly FALSE")
        assert_true(applicant_user.verification_status == "PENDING", "Applicant verification_status is 'PENDING'")
        test_created_user_ids.append(applicant_user.id)
        db.close()

        # 2.2 Blocked Login for Pending Responder
        code, block_resp = client.request("POST", "/api/auth/login", {
            "username": resp_username,
            "password": "MedicPassword123"
        })
        assert_true(code == 401, "Pending responder login is blocked with HTTP 401")
        assert_true("pending" in block_resp.get("detail", "").lower() or "disabled" in block_resp.get("detail", "").lower(),
                    "Informative message that account is pending review or disabled")

        # 2.3 Reviewer RBAC Protection
        # Ordinary admin (Admin Alpha) attempts to list applications -> 403 Forbidden
        code, unauth_review = client.request("GET", "/api/admin/responders/applications", token=alpha_token)
        assert_true(code == 403, "Ordinary household admin blocked from reviewer endpoints (403 Forbidden)")

        # Platform reviewer (Admin Beta) lists applications -> 200 OK
        code, auth_review = client.request("GET", "/api/admin/responders/applications?status=PENDING", token=beta_token)
        assert_true(code == 200, "Platform reviewer lists pending applications")
        app_ids = [a["id"] for a in auth_review]
        assert_true(app_id in app_ids, "Pending application appears in reviewer queue")

        # 2.4 Responder Application Rejection Test
        # Submit a second application to test rejection
        rej_username = f"unverified_resp_{int(datetime.datetime.utcnow().timestamp())}"
        code, rej_app_resp = client.request("POST", "/api/auth/register-responder", {
            "username": rej_username,
            "password": "RejectPass123",
            "email": f"{rej_username}@fakeagency.test",
            "phone": "+1 (555) 911-0033",
            "full_name": "Unverified Applicant",
            "organization": "Unverified Agency",
            "badge_id": "FAKE-001"
        })
        rej_app_id = rej_app_resp["application_id"]
        test_created_app_ids.append(rej_app_id)
        db = SessionLocal()
        rej_user = db.query(models.User).filter(models.User.username == rej_username).first()
        test_created_user_ids.append(rej_user.id)
        db.close()

        # Reviewer rejects application
        code, rej_action_resp = client.request(
            "POST",
            f"/api/admin/responders/applications/{rej_app_id}/review",
            {"action": "REJECT", "review_notes": "Unable to verify agency affiliation"},
            token=beta_token
        )
        assert_true(code == 200, "Platform reviewer rejects unverified application")
        assert_true(rej_action_resp["status"] == "REJECTED", "Application marked REJECTED")

        # Login attempt of rejected user must fail
        code, rej_login = client.request("POST", "/api/auth/login", {
            "username": rej_username,
            "password": "RejectPass123"
        })
        assert_true(code == 401, "Rejected responder login is blocked with HTTP 401")

        # 2.5 Responder Application Approval & Activation
        code, approve_resp = client.request(
            "POST",
            f"/api/admin/responders/applications/{app_id}/review",
            {"action": "APPROVE", "review_notes": "Credentials and agency affiliation verified with City Paramedic Squad 4"},
            token=beta_token
        )
        assert_true(code == 200, "Platform reviewer approves responder application")
        assert_true(approve_resp["status"] == "APPROVED", "Application marked APPROVED")
        created_responder_id = approve_resp["responder_id"]
        assert_true(created_responder_id is not None, "Responder profile created upon approval")
        test_created_responder_ids.append(created_responder_id)

        # 2.6 Verified Responder Login & Access
        code, approved_login = client.request("POST", "/api/auth/login", {
            "username": resp_username,
            "password": "MedicPassword123"
        })
        assert_true(code == 200 and "access_token" in approved_login, "Approved responder can now successfully log in!")
        approved_resp_token = approved_login["access_token"]
        approved_user_info = approved_login["user"]
        assert_true(approved_user_info["role"] == "responder", "User role is 'responder'")
        assert_true(approved_user_info["responder_id"] == created_responder_id, "User linked to active Responder ID")

        # 2.7 Responder Assignment Access
        code, assign_resp = client.request("GET", "/api/responders/me/assignments", token=approved_resp_token)
        assert_true(code == 200, "Approved responder can access assigned incidents endpoint")

        print("\n" + "=" * 80)
        print(f"ALL TESTS COMPLETED SUCCESSFULLY: {passed}/{total} assertions passed!")
        print("=" * 80)
        return True

    finally:
        print("\n[Teardown] Cleaning up temporary test accounts, applications, and invitations...")
        cleanup()
        print("[Teardown] Cleanup completed.")


if __name__ == "__main__":
    success = run_tests()
    if not success:
        sys.exit(1)
