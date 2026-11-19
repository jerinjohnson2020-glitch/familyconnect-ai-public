import os
import sqlite3
import datetime
import secrets
from sqlalchemy.orm import Session
from .database import DB_PATH, engine, Base, SessionLocal
from .models import (
    EmergencyIncident,
    IncidentTimelineEvent,
    IncidentAlert,
    Member,
    Responder,
    IncidentResponder,
    User,
    TrustedContact,
    RevokedToken
)
from .auth import hash_password


SEED_MEMBER_PHONES = {
    "+1 (555) 234-5678",
    "+1 (555) 876-5432",
    "+1 (555) 345-6789",
    "+1 (555) 456-7890"
}

SEED_RESPONDER_PHONES = {
    "+1 (555) 901-1122",
    "+1 (555) 902-3344",
    "+1 (555) 903-5566",
    "+1 (555) 904-7788",
    "+1 (555) 905-9900"
}


def provision_platform_reviewer(db: Session, username: str) -> bool:
    """
    Explicit administrative provisioning function to grant platform reviewer privileges.
    Never automatically invoked based on hardcoded usernames.
    Returns True if user was found and granted reviewer privileges, False otherwise.
    """
    target = username.strip() if username else ""
    if not target:
        return False
    user = db.query(User).filter(User.username == target).first()
    if user:
        user.is_platform_reviewer = True
        db.commit()
        print(f"[Admin Provisioning] Platform reviewer privileges explicitly granted to '{user.username}'.")
        return True
    return False


def seed_demo_users(db: Session):
    """
    Seeds the 3 demo login roles (admin, marcus, officer_david) ONLY when
    ENABLE_DEMO_USERS=true is explicitly configured in the environment.
    Defaults to False when unset to prevent automatic recreation of demo accounts
    in production environments. If accounts already exist, credentials are NEVER overwritten.
    Never permitted in production mode.
    """
    env = os.environ.get("ENVIRONMENT", "development").lower()
    if env == "production":
        print("[Migration] Production environment detected. Demo user creation strictly prohibited.")
        return

    enable_demo_users = os.environ.get("ENABLE_DEMO_USERS", "false").lower() in ("true", "1", "yes")
    if not enable_demo_users:
        print("[Migration] Demo user seeding is disabled (ENABLE_DEMO_USERS != 'true'). Skipping demo user creation.")
        return

    # Use explicitly configured demo passwords or generate unguessable random credentials in memory
    admin_pw = os.environ.get("DEMO_ADMIN_PASSWORD") or secrets.token_urlsafe(24)
    member_pw = os.environ.get("DEMO_MEMBER_PASSWORD") or secrets.token_urlsafe(24)
    resp_pw = os.environ.get("DEMO_RESPONDER_PASSWORD") or secrets.token_urlsafe(24)

    # 1. Admin account
    existing_admin = db.query(User).filter(User.username == "admin").first()
    if not existing_admin:
        h, s = hash_password(admin_pw)
        admin_user = User(
            username="admin",
            hashed_password=h,
            salt=s,
            role="admin",
            is_active=False,
            is_platform_reviewer=False,
            verification_status="APPROVED",
            created_at=datetime.datetime.utcnow()
        )
        db.add(admin_user)
        print("[Migration] Seeded account: 'admin' (Role: admin)")
    else:
        print("[Migration] Account 'admin' already exists (retaining existing credentials).")

    # 2. Member account (marcus)
    existing_member_user = db.query(User).filter(User.username == "marcus").first()
    if not existing_member_user:
        marcus_member = db.query(Member).filter(Member.phone == "+1 (555) 876-5432").first()
        h, s = hash_password(member_pw)
        member_user = User(
            username="marcus",
            hashed_password=h,
            salt=s,
            role="member",
            is_active=False,
            is_platform_reviewer=False,
            verification_status="APPROVED",
            member_id=marcus_member.id if marcus_member else None,
            created_at=datetime.datetime.utcnow()
        )
        db.add(member_user)
        print(f"[Migration] Seeded account: 'marcus' (Role: member, MemberID: {member_user.member_id})")
    else:
        print("[Migration] Account 'marcus' already exists (retaining existing credentials).")

    # 3. Responder account (officer_david)
    existing_resp_user = db.query(User).filter(User.username == "officer_david").first()
    if not existing_resp_user:
        david_responder = db.query(Responder).filter(Responder.phone == "+1 (555) 901-1122").first()
        h, s = hash_password(resp_pw)
        resp_user = User(
            username="officer_david",
            hashed_password=h,
            salt=s,
            role="responder",
            is_active=False,
            is_platform_reviewer=False,
            verification_status="APPROVED",
            responder_id=david_responder.id if david_responder else None,
            created_at=datetime.datetime.utcnow()
        )
        db.add(resp_user)
        print(f"[Migration] Seeded account: 'officer_david' (Role: responder, ResponderID: {resp_user.responder_id})")
    else:
        print("[Migration] Account 'officer_david' already exists (retaining existing credentials).")

    db.commit()


def run_migration():
    print(f"[Migration] Checking database at {DB_PATH}...")
    # Production / PostgreSQL safety guard:
    # Ensure schema tables and indexes exist via SQLAlchemy metadata and return.
    # Never execute SQLite raw SQL or demo user backfill logic on production/PostgreSQL databases.
    if not str(engine.url).startswith("sqlite"):
        print("[Migration] Detected PostgreSQL / non-SQLite database. Ensuring schema tables and indexes exist...")
        Base.metadata.create_all(bind=engine)
        print("[Migration] PostgreSQL schema ready. Bypassing demo seeding and dev migrations.")
        return

    # Ensure all tables and indexes exist on fresh clone before running column checks
    Base.metadata.create_all(bind=engine)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Check members columns (Phase 6 User-Managed Profiles)
    cursor.execute("PRAGMA table_info(members);")
    member_cols = [row[1] for row in cursor.fetchall()]
    if member_cols:
        member_migrations = [
            ("user_id", "INTEGER"),
            ("email", "VARCHAR(120)"),
            ("address", "VARCHAR(255)"),
            ("is_active", "BOOLEAN DEFAULT 1 NOT NULL"),
            ("is_demo", "BOOLEAN DEFAULT 0 NOT NULL"),
            ("updated_at", "DATETIME")
        ]

        # Family Location MVP (Stage 1.5): Gated to prevent silent migration of existing databases
        location_migrations = [
            ("is_sharing_location", "BOOLEAN DEFAULT 0 NOT NULL"),
            ("latitude", "FLOAT"),
            ("longitude", "FLOAT"),
            ("location_accuracy_m", "FLOAT"),
            ("location_label", "VARCHAR(100)"),
            ("location_updated_at", "DATETIME")
        ]
        if os.environ.get("ENABLE_LOCATION_MIGRATION", "").lower() in ("true", "1", "yes"):
            member_migrations.extend(location_migrations)

        for col_name, col_type in member_migrations:
            if col_name not in member_cols:
                print(f"[Migration] Adding {col_name} column to members...")
                cursor.execute(f"ALTER TABLE members ADD COLUMN {col_name} {col_type};")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_members_user_id ON members (user_id);")

    # 2. Check responders columns & nullable coordinates (Phase 6 Configurable Responders)
    cursor.execute("PRAGMA table_info(responders);")
    responder_info = cursor.fetchall()
    responder_cols = [row[1] for row in responder_info]
    lat_notnull = any(row[1] == "latitude" and row[3] == 1 for row in responder_info)
    lon_notnull = any(row[1] == "longitude" and row[3] == 1 for row in responder_info)

    if responder_cols:
        resp_migrations = [
            ("organization", "VARCHAR(120)"),
            ("email", "VARCHAR(120)"),
            ("location_source", "VARCHAR(30)"),
            ("location_updated_at", "DATETIME"),
            ("is_active", "BOOLEAN DEFAULT 1 NOT NULL"),
            ("is_demo", "BOOLEAN DEFAULT 0 NOT NULL"),
            ("created_at", "DATETIME"),
            ("updated_at", "DATETIME")
        ]
        for col_name, col_type in resp_migrations:
            if col_name not in responder_cols:
                print(f"[Migration] Adding {col_name} column to responders...")
                cursor.execute(f"ALTER TABLE responders ADD COLUMN {col_name} {col_type};")

        if lat_notnull or lon_notnull:
            print("[Migration] Relaxing NOT NULL constraint on responders.latitude/longitude so responders can be created without fabricated coordinates...")
            cursor.execute("PRAGMA foreign_keys=OFF;")
            cursor.execute("""
                CREATE TABLE responders_new (
                    id INTEGER NOT NULL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    role VARCHAR(50),
                    organization VARCHAR(120),
                    phone VARCHAR(30) NOT NULL,
                    email VARCHAR(120),
                    latitude FLOAT,
                    longitude FLOAT,
                    location_source VARCHAR(30),
                    location_updated_at DATETIME,
                    is_available BOOLEAN,
                    is_active BOOLEAN DEFAULT 1 NOT NULL,
                    is_demo BOOLEAN DEFAULT 0 NOT NULL,
                    skills VARCHAR(150),
                    created_at DATETIME,
                    updated_at DATETIME
                );
            """)
            cursor.execute("""
                INSERT INTO responders_new (
                    id, name, role, organization, phone, email, latitude, longitude,
                    location_source, location_updated_at, is_available, is_active, is_demo,
                    skills, created_at, updated_at
                )
                SELECT
                    id, name, role, organization, phone, email, latitude, longitude,
                    location_source, location_updated_at, is_available,
                    COALESCE(is_active, 1), COALESCE(is_demo, 0),
                    skills, created_at, updated_at
                FROM responders;
            """)
            cursor.execute("DROP TABLE responders;")
            cursor.execute("ALTER TABLE responders_new RENAME TO responders;")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_responders_id ON responders (id);")
            cursor.execute("PRAGMA foreign_keys=ON;")

    # 3. Check emergency_incidents columns (Phase 1/2 + Phase 5A Geolocation)
    cursor.execute("PRAGMA table_info(emergency_incidents);")
    inc_columns = [row[1] for row in cursor.fetchall()]
    print(f"[Migration] Existing emergency_incidents columns: {inc_columns}")

    if inc_columns:
        if "resolved_at" not in inc_columns:
            cursor.execute("ALTER TABLE emergency_incidents ADD COLUMN resolved_at DATETIME;")
        if "resolution_notes" not in inc_columns:
            cursor.execute("ALTER TABLE emergency_incidents ADD COLUMN resolution_notes TEXT;")
        if "location_accuracy_m" not in inc_columns:
            cursor.execute("ALTER TABLE emergency_incidents ADD COLUMN location_accuracy_m FLOAT;")
        if "location_source" not in inc_columns:
            cursor.execute("ALTER TABLE emergency_incidents ADD COLUMN location_source VARCHAR(30) DEFAULT 'manual_coordinates';")
        if "location_updated_at" not in inc_columns:
            cursor.execute("ALTER TABLE emergency_incidents ADD COLUMN location_updated_at DATETIME;")
        if "user_id" not in inc_columns:
            print("[Migration] Adding user_id column to emergency_incidents...")
            cursor.execute("ALTER TABLE emergency_incidents ADD COLUMN user_id INTEGER;")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_emergency_incidents_user_id ON emergency_incidents (user_id);")

    # 4. Check incident_responders columns (Phase 3 lifecycle)
    cursor.execute("PRAGMA table_info(incident_responders);")
    resp_columns = [row[1] for row in cursor.fetchall()]
    if resp_columns:
        lifecycle_cols = ["assigned_at", "accepted_at", "en_route_at", "arrived_at", "updated_at"]
        for col in lifecycle_cols:
            if col not in resp_columns:
                cursor.execute(f"ALTER TABLE incident_responders ADD COLUMN {col} DATETIME;")

    # 5. Check users columns
    cursor.execute("PRAGMA table_info(users);")
    user_columns = [row[1] for row in cursor.fetchall()]
    if user_columns:
        if "is_active" not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1;")
        if "email" not in user_columns:
            print("[Migration] Adding email column to users...")
            cursor.execute("ALTER TABLE users ADD COLUMN email VARCHAR(120);")
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email);")
        if "phone" not in user_columns:
            print("[Migration] Adding phone column to users...")
            cursor.execute("ALTER TABLE users ADD COLUMN phone VARCHAR(30);")
        if "full_name" not in user_columns:
            print("[Migration] Adding full_name column to users...")
            cursor.execute("ALTER TABLE users ADD COLUMN full_name VARCHAR(100);")
        if "household_id" not in user_columns:
            print("[Migration] Adding household_id column to users...")
            cursor.execute("ALTER TABLE users ADD COLUMN household_id INTEGER;")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_users_household_id ON users (household_id);")
        if "verification_status" not in user_columns:
            print("[Migration] Adding verification_status column to users...")
            cursor.execute("ALTER TABLE users ADD COLUMN verification_status VARCHAR(30) DEFAULT 'APPROVED' NOT NULL;")
        if "organization" not in user_columns:
            print("[Migration] Adding organization column to users...")
            cursor.execute("ALTER TABLE users ADD COLUMN organization VARCHAR(120);")
        if "badge_id" not in user_columns:
            print("[Migration] Adding badge_id column to users...")
            cursor.execute("ALTER TABLE users ADD COLUMN badge_id VARCHAR(50);")
        if "is_platform_reviewer" not in user_columns:
            print("[Migration] Adding is_platform_reviewer column to users...")
            cursor.execute("ALTER TABLE users ADD COLUMN is_platform_reviewer BOOLEAN DEFAULT 0 NOT NULL;")

    # 6. Check trusted_contacts columns (Phase 5B Email + Phase 6 Demo flag)
    cursor.execute("PRAGMA table_info(trusted_contacts);")
    tc_columns = [row[1] for row in cursor.fetchall()]
    if tc_columns:
        if "email" not in tc_columns:
            cursor.execute("ALTER TABLE trusted_contacts ADD COLUMN email VARCHAR(120);")
        if "is_demo" not in tc_columns:
            cursor.execute("ALTER TABLE trusted_contacts ADD COLUMN is_demo BOOLEAN DEFAULT 0 NOT NULL;")

    # 7. Check incident_alerts columns (Phase 5B Real Notification Provider Tracking)
    cursor.execute("PRAGMA table_info(incident_alerts);")
    alert_columns = [row[1] for row in cursor.fetchall()]
    if alert_columns:
        alert_migrations = [
            ("contact_id", "INTEGER"),
            ("contact_email", "VARCHAR(120)"),
            ("provider", "VARCHAR(50)"),
            ("provider_message_id", "VARCHAR(120)"),
            ("delivery_attempts", "INTEGER DEFAULT 0"),
            ("last_attempt_at", "DATETIME"),
            ("delivered_at", "DATETIME"),
            ("error_message", "TEXT"),
            ("dedup_key", "VARCHAR(150)")
        ]
        for col_name, col_type in alert_migrations:
            if col_name not in alert_columns:
                cursor.execute(f"ALTER TABLE incident_alerts ADD COLUMN {col_name} {col_type};")

    # 8. Check responders columns (Phase 5B Real Coordinates & Accuracy)
    cursor.execute("PRAGMA table_info(responders);")
    resp_tab_cols = [row[1] for row in cursor.fetchall()]
    if resp_tab_cols and "location_accuracy_m" not in resp_tab_cols:
        cursor.execute("ALTER TABLE responders ADD COLUMN location_accuracy_m FLOAT;")

    conn.commit()
    conn.close()

    # 9. Create any new tables
    Base.metadata.create_all(bind=engine)
    print("[Migration] Database schema and tables verified.")

    # 10. Non-destructive metadata enrichment & demo flagging (by seed 555 phones, never by name alone)
    db = SessionLocal()
    try:
        now = datetime.datetime.utcnow()

        # Check whether location columns exist before querying via Member ORM
        c_check = sqlite3.connect(DB_PATH)
        cur_check = c_check.cursor()
        cur_check.execute("PRAGMA table_info(members);")
        has_location_cols = any(row[1] == "is_sharing_location" for row in cur_check.fetchall())
        c_check.close()

        # Flag original seed members by their RFC-reserved +1 (555) fixture phone numbers
        if has_location_cols:
            for m in db.query(Member).all():
                if m.is_active is None:
                    m.is_active = True
                if m.updated_at is None:
                    m.updated_at = m.created_at or now
                if m.phone in SEED_MEMBER_PHONES and m.id <= 4:
                    m.is_demo = True
        else:
            c_upd = sqlite3.connect(DB_PATH)
            cur_upd = c_upd.cursor()
            cur_upd.execute("UPDATE members SET is_active = 1 WHERE is_active IS NULL;")
            cur_upd.execute("UPDATE members SET updated_at = COALESCE(created_at, datetime('now')) WHERE updated_at IS NULL;")
            for p in SEED_MEMBER_PHONES:
                cur_upd.execute("UPDATE members SET is_demo = 1 WHERE phone = ? AND id <= 4;", (p,))
            c_upd.commit()
            c_upd.close()

        # Flag original seed trusted contacts by their RFC-reserved +1 (555) fixture phone numbers
        for tc in db.query(TrustedContact).all():
            if tc.phone in SEED_MEMBER_PHONES and tc.id <= 5:
                tc.is_demo = True

        # Flag original seed responders and keep demo responders deactivated for safety
        for r in db.query(Responder).all():
            if r.is_active is None:
                r.is_active = True
            if r.created_at is None:
                r.created_at = now
            if r.updated_at is None:
                r.updated_at = now
            if (r.phone in SEED_RESPONDER_PHONES and r.id <= 5) or r.is_demo:
                r.is_demo = True
                r.is_active = False
                r.is_available = False
                if not r.location_source:
                    r.location_source = "demo_seed"
                if not r.location_updated_at:
                    r.location_updated_at = r.created_at or now
            else:
                if r.latitude is not None and r.longitude is not None and not r.location_source:
                    r.location_source = "manual_coordinates"
                    r.location_updated_at = r.updated_at or now
                elif r.latitude is None or r.longitude is None:
                    r.location_source = "unset"

        db.commit()

        # Ensure login users exist without overwriting credentials (development only)
        if os.environ.get("ENVIRONMENT", "development").lower() != "production":
            seed_demo_users(db)

        # Enrich demo users with default metadata if not set
        admin_user = db.query(User).filter(User.username == "admin").first()
        if admin_user:
            if not admin_user.email:
                admin_user.email = "admin@familyconnect.local"
            if not admin_user.full_name:
                admin_user.full_name = "Family Administrator"

        marcus_user = db.query(User).filter(User.username == "marcus").first()
        if marcus_user:
            if not marcus_user.email:
                marcus_user.email = "marcus.chen@familyconnect.local"
            if not marcus_user.phone:
                marcus_user.phone = "+1 (555) 876-5432"
            if not marcus_user.full_name:
                marcus_user.full_name = "Marcus Chen"

        officer_user = db.query(User).filter(User.username == "officer_david").first()
        if officer_user:
            if not officer_user.email:
                officer_user.email = "david.miller@familyconnect.local"
            if not officer_user.phone:
                officer_user.phone = "+1 (555) 901-1122"
            if not officer_user.full_name:
                officer_user.full_name = "Officer David Miller"

        # Backfill user_id on existing members and incidents to admin if unassigned
        if admin_user:
            if not admin_user.household_id:
                admin_user.household_id = admin_user.id
            if has_location_cols:
                for m in db.query(Member).filter(Member.user_id == None).all():
                    m.user_id = admin_user.id
            else:
                c_upd = sqlite3.connect(DB_PATH)
                cur_upd = c_upd.cursor()
                cur_upd.execute("UPDATE members SET user_id = ? WHERE user_id IS NULL;", (admin_user.id,))
                c_upd.commit()
                c_upd.close()
            for inc in db.query(EmergencyIncident).filter(EmergencyIncident.user_id == None).all():
                inc.user_id = admin_user.id

        if marcus_user and not marcus_user.household_id and admin_user:
            marcus_user.household_id = admin_user.id

        if officer_user:
            if not officer_user.organization:
                officer_user.organization = "Metropolitan Emergency Response"
            if not officer_user.badge_id:
                officer_user.badge_id = "RES-401"

        # Ensure all administrative users have a household_id assigned to self if unassigned
        for admin_acc in db.query(User).filter(User.role == "admin", User.household_id == None).all():
            admin_acc.household_id = admin_acc.id

        # Explicit administrative provisioning of platform reviewers via environment configuration.
        # Arbitrary accounts NEVER automatically receive platform reviewer privileges during migration.
        # Existing platform reviewer status on active accounts is strictly preserved.
        reviewer_config = (
            os.environ.get("INITIAL_PLATFORM_REVIEWER_USERNAME")
            or os.environ.get("PLATFORM_REVIEWER_USERNAMES")
            or ""
        ).strip()
        if reviewer_config:
            allowed_reviewers = [name.strip() for name in reviewer_config.split(",") if name.strip()]
            for reviewer_user in db.query(User).filter(User.username.in_(allowed_reviewers)).all():
                reviewer_user.is_platform_reviewer = True
                print(f"[Migration] Platform reviewer explicitly provisioned from configuration: '{reviewer_user.username}'.")

        # Assign default verification status for users where verification_status IS NULL, empty, or legacy PENDING_VERIFICATION:
        # Responders must remain PENDING until explicitly reviewed and approved by an administrator.
        # Household administrators and members receive APPROVED.
        # Existing users with an assigned verification status ('APPROVED', 'PENDING', 'REJECTED') are preserved untouched.
        for u in db.query(User).all():
            if not u.verification_status or u.verification_status == "PENDING_VERIFICATION":
                if u.role == "responder":
                    u.verification_status = "PENDING"
                else:
                    u.verification_status = "APPROVED"

        db.commit()

        print("[Migration] User-managed authentication & data migration completed successfully. All existing records preserved.")
    finally:
        db.close()


if __name__ == "__main__":
    run_migration()
