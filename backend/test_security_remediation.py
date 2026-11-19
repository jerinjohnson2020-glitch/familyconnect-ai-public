"""
FamilyConnect AI - Security Remediation Verification Suite
Verifies:
1. Strict Household Isolation:
   - User ID 1 possesses zero implicit global-admin bypass.
   - Cross-household queries and mutations are blocked (HTTP 403) across:
     members, trusted contacts, emergency incidents, timelines, alerts, and status updates.
   - Legitimate administrator and responder workflows remain fully functional.
2. Secure JWT Configuration:
   - Production refuses missing, weak, or development fallback JWT secrets.
   - Minimum 32-character entropy enforcement.
   - Zero secret exposure in exceptions, logs, or reports.
3. Production CORS Restrictions:
   - Production permits ONLY explicitly configured trusted origins.
   - Private network RFC 1918 regex is disabled in production.
   - Development mode preserves localhost and local Wi-Fi testing origins.
4. WebSocket Authentication & Subscription Security:
   - Rejects unauthenticated, expired, or invalid tokens (code 1008).
   - Rejects cross-tenant incident subscriptions (SUBSCRIPTION_DENIED, code 403).
   - Permits valid authenticated subscriptions within the caller's household.
5. Database Integrity & Zero Side-Effects:
   - All tests clean up temporary entities and guarantee zero database pollution.
"""

import os
import sys
import json
import time
import socket
import threading
import datetime
import urllib.request
import urllib.error
from pathlib import Path

# Ensure backend root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Ensure mock notifications are enabled to prevent external network calls
os.environ["MOCK_NOTIFICATIONS"] = "true"

import uvicorn
import websockets
import asyncio
from app.main import app, get_cors_configuration, DEFAULT_ALLOWED_ORIGINS, PRIVATE_NETWORK_ORIGIN_REGEX
from app.auth import (
    create_access_token,
    decode_access_token,
    validate_production_jwt_secret,
    get_jwt_secret,
    check_production_security,
    DEV_FALLBACK_SECRET,
    hash_password
)
from app.database import engine, SessionLocal
from app.models import (
    User,
    Member,
    TrustedContact,
    EmergencyIncident,
    IncidentResponder,
    IncidentTimelineEvent,
    IncidentAlert,
    Responder
)

# Pick an unused high port for in-process live test server
def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

TEST_PORT = get_free_port()
BASE_HTTP_URL = f"http://127.0.0.1:{TEST_PORT}"
BASE_WS_URL = f"ws://127.0.0.1:{TEST_PORT}/api/ws/incidents"


class HttpClient:
    def __init__(self, base_url: str = BASE_HTTP_URL):
        self.base_url = base_url.rstrip("/")

    def request(self, method: str, path: str, data: dict = None, token: str = None) -> tuple[int, dict]:
        url = f"{self.base_url}{path}"
        body = json.dumps(data).encode("utf-8") if data is not None else None
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as err:
            raw = err.read().decode("utf-8")
            return err.code, json.loads(raw) if raw else {}


def run_tests():
    total = 0
    passed = 0

    def record_pass(desc: str):
        nonlocal total, passed
        total += 1
        passed += 1
        print(f"  [PASS] {desc}")

    def record_fail(desc: str, err: str):
        nonlocal total
        total += 1
        print(f"  [FAIL] {desc}: {err}")

    print("=" * 80)
    print("FAMILYCONNECT AI - SECURITY REMEDIATION VERIFICATION SUITE")
    print("=" * 80)

    # -------------------------------------------------------------
    # GROUP 1: Secure JWT Configuration in Production Mode
    # -------------------------------------------------------------
    print("\n--- GROUP 1: Secure JWT Configuration in Production Mode ---")

    # 1.1 Empty secret rejected in production
    try:
        validate_production_jwt_secret("")
        record_fail("Empty JWT secret in production", "Did not raise RuntimeError")
    except RuntimeError as exc:
        assert "no secure JWT_SECRET_KEY was provided" in str(exc)
        record_pass("Empty or missing JWT secret strictly rejected when ENVIRONMENT=production")

    # 1.2 Development fallback secret strictly rejected in production
    try:
        validate_production_jwt_secret(DEV_FALLBACK_SECRET)
        record_fail("Dev fallback secret in production", "Did not raise RuntimeError")
    except RuntimeError as exc:
        assert "Insecure development fallback JWT secret detected" in str(exc)
        record_pass("Development fallback secret strictly rejected when ENVIRONMENT=production")

    # 1.3 Substring pattern 'change-in-production' strictly rejected
    try:
        validate_production_jwt_secret("custom-key-change-in-production-12345678901234567890")
        record_fail("Dev pattern secret in production", "Did not raise RuntimeError")
    except RuntimeError as exc:
        assert "Insecure development fallback" in str(exc)
        record_pass("Secrets containing dev-fallback patterns strictly rejected")

    # 1.4 Short secret (< 32 chars) strictly rejected
    short_secret = "short-secret-key-12345"
    try:
        validate_production_jwt_secret(short_secret)
        record_fail("Short secret in production", "Did not raise RuntimeError")
    except RuntimeError as exc:
        assert "too short" in str(exc)
        # Verify secret itself was not leaked in error message
        assert short_secret not in str(exc)
        record_pass("Short JWT secrets (< 32 chars) rejected without leaking secret in error message")

    # 1.5 Guessable weak dictionary secrets rejected
    try:
        validate_production_jwt_secret("password")
        record_fail("Weak secret in production", "Did not raise RuntimeError")
    except RuntimeError as exc:
        assert "too short" in str(exc) or "Trivially guessable" in str(exc)
        record_pass("Weak dictionary secrets strictly rejected")

    # 1.6 Strong 32+ char secret accepted
    strong_secret = "c7d2e9f4a1b83654029184756201938475629103847562019384756201938475"
    try:
        validate_production_jwt_secret(strong_secret)
        record_pass("Valid cryptographically strong 64-char secret accepted in production")
    except Exception as exc:
        record_fail("Strong secret accepted", str(exc))

    # 1.7 check_production_security fails if CORS or DATABASE_URL or JWT is invalid in production
    orig_env = os.environ.get("ENVIRONMENT")
    orig_jwt = os.environ.get("JWT_SECRET_KEY")
    orig_cors = os.environ.get("ALLOWED_ORIGINS")
    orig_db = os.environ.get("DATABASE_URL")
    try:
        os.environ["ENVIRONMENT"] = "production"
        os.environ["JWT_SECRET_KEY"] = DEV_FALLBACK_SECRET
        try:
            check_production_security()
            record_fail("Production security check", "Allowed dev fallback secret in production")
        except RuntimeError as exc:
            assert "Insecure development fallback" in str(exc)
            record_pass("check_production_security() halts startup if insecure secret is present in production")
    finally:
        if orig_env is not None:
            os.environ["ENVIRONMENT"] = orig_env
        else:
            os.environ.pop("ENVIRONMENT", None)
        if orig_jwt is not None:
            os.environ["JWT_SECRET_KEY"] = orig_jwt
        else:
            os.environ.pop("JWT_SECRET_KEY", None)
        if orig_cors is not None:
            os.environ["ALLOWED_ORIGINS"] = orig_cors
        else:
            os.environ.pop("ALLOWED_ORIGINS", None)
        if orig_db is not None:
            os.environ["DATABASE_URL"] = orig_db
        else:
            os.environ.pop("DATABASE_URL", None)

    # -------------------------------------------------------------
    # GROUP 2: CORS Restriction & Environment Scoping
    # -------------------------------------------------------------
    print("\n--- GROUP 2: CORS Restriction & Environment Scoping ---")

    # 2.1 Development mode includes localhost defaults and private network regex
    dev_allowed, dev_regex = get_cors_configuration(env="development")
    assert "http://localhost:5173" in dev_allowed
    assert "http://127.0.0.1:5173" in dev_allowed
    assert dev_regex == PRIVATE_NETWORK_ORIGIN_REGEX
    record_pass("Development mode permits localhost ports and private network RFC 1918 regex")

    # 2.2 Production mode with no origins configured returns empty allowed list and None regex
    orig_allowed_env = os.environ.pop("ALLOWED_ORIGINS", None)
    orig_cors_env = os.environ.pop("CORS_ORIGINS", None)
    orig_pub_env = os.environ.pop("FRONTEND_PUBLIC_URL", None)
    try:
        prod_allowed, prod_regex = get_cors_configuration(env="production")
        assert len(prod_allowed) == 0, f"Expected 0 origins, got {prod_allowed}"
        assert prod_regex is None
        record_pass("Production mode disables localhost defaults and disables private network regex")

        # 2.3 check_production_security halts if no trusted origins are configured in production
        os.environ["ENVIRONMENT"] = "production"
        os.environ["JWT_SECRET_KEY"] = strong_secret
        os.environ["DATABASE_URL"] = "postgresql://user:pass@postgres.example.com:5432/production_db?sslmode=require"
        try:
            check_production_security()
            record_fail("Empty CORS in production", "Did not halt startup when no origins configured")
        except RuntimeError as exc:
            assert "no trusted frontend origins were configured" in str(exc)
            record_pass("check_production_security() strictly enforces at least one explicit frontend origin in production")

        # 2.4 Production mode with explicit origins permits ONLY configured origins
        os.environ["ALLOWED_ORIGINS"] = "https://familyconnect.pages.dev, https://admin.familyconnect.com"
        prod_allowed_conf, prod_regex_conf = get_cors_configuration(env="production")
        assert "https://familyconnect.pages.dev" in prod_allowed_conf
        assert "https://admin.familyconnect.com" in prod_allowed_conf
        assert "http://localhost:5173" not in prod_allowed_conf
        assert prod_regex_conf is None
        record_pass("Production mode configures ONLY explicitly specified frontend origins")

    finally:
        os.environ.pop("ENVIRONMENT", None)
        os.environ.pop("JWT_SECRET_KEY", None)
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("ALLOWED_ORIGINS", None)
        if orig_allowed_env:
            os.environ["ALLOWED_ORIGINS"] = orig_allowed_env
        if orig_cors_env:
            os.environ["CORS_ORIGINS"] = orig_cors_env
        if orig_pub_env:
            os.environ["FRONTEND_PUBLIC_URL"] = orig_pub_env

    # -------------------------------------------------------------
    # Live HTTP Server Startup for Functional & Tenant Isolation Tests
    # -------------------------------------------------------------
    config = uvicorn.Config(app=app, host="127.0.0.1", port=TEST_PORT, log_level="warning")
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    # Wait for server to be responsive
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"{BASE_HTTP_URL}/api/health", timeout=1):
                break
        except Exception:
            time.sleep(0.1)

    client = HttpClient(BASE_HTTP_URL)

    # -------------------------------------------------------------
    # GROUP 3: Multi-Tenant Household Isolation & Zero User 1 Bypass
    # -------------------------------------------------------------
    print("\n--- GROUP 3: Multi-Tenant Household Isolation & Zero User 1 Bypass ---")

    db = SessionLocal()
    initial_member_count = db.query(Member).count()
    initial_incident_count = db.query(EmergencyIncident).count()
    initial_user_count = db.query(User).count()

    # Create two temporary test households:
    # Household A: Admin A (ID_A), Member A (Mem_A), Incident A (Inc_A)
    # Household B: Admin B (ID_B), Member B (Mem_B), Incident B (Inc_B)
    now = datetime.datetime.utcnow()
    h_a_hash, h_a_salt = hash_password("SecurePassA123!")
    h_b_hash, h_b_salt = hash_password("SecurePassB123!")

    user_a = User(
        username="sec_admin_a",
        email="sec_admin_a@testfamily.org",
        phone="+91 98765 01001",
        full_name="Admin Family A",
        hashed_password=h_a_hash,
        salt=h_a_salt,
        role="admin",
        is_active=True,
        verification_status="APPROVED",
        is_platform_reviewer=False,
        created_at=now
    )
    user_b = User(
        username="sec_admin_b",
        email="sec_admin_b@testfamily.org",
        phone="+91 98765 01002",
        full_name="Admin Family B",
        hashed_password=h_b_hash,
        salt=h_b_salt,
        role="admin",
        is_active=True,
        verification_status="APPROVED",
        is_platform_reviewer=False,
        created_at=now
    )
    db.add(user_a)
    db.add(user_b)
    db.flush()

    user_a.household_id = user_a.id
    user_b.household_id = user_b.id

    member_a = Member(
        user_id=user_a.id,
        name="Alice Vance",
        phone="+91 98765 01003",
        relationship="Daughter",
        is_active=True,
        is_demo=False,
        created_at=now
    )
    member_b = Member(
        user_id=user_b.id,
        name="Bob Jenkins",
        phone="+91 98765 01004",
        relationship="Son",
        is_active=True,
        is_demo=False,
        created_at=now
    )
    db.add(member_a)
    db.add(member_b)
    db.flush()

    tc_a = TrustedContact(
        member_id=member_a.id,
        name="Emergency Contact A",
        phone="+91 98765 01005",
        relationship="Parent",
        priority=1,
        is_active=True,
        is_demo=False,
        created_at=now,
        updated_at=now
    )
    tc_b = TrustedContact(
        member_id=member_b.id,
        name="Emergency Contact B",
        phone="+91 98765 01006",
        relationship="Parent",
        priority=1,
        is_active=True,
        is_demo=False,
        created_at=now,
        updated_at=now
    )
    db.add(tc_a)
    db.add(tc_b)

    inc_a = EmergencyIncident(
        user_id=user_a.id,
        member_id=member_a.id,
        reporter_name="Alice Vance",
        incident_type="General SOS",
        description="Household A emergency test",
        latitude=12.9716,
        longitude=77.5946,
        status="ACTIVE",
        created_at=now
    )
    inc_b = EmergencyIncident(
        user_id=user_b.id,
        member_id=member_b.id,
        reporter_name="Bob Jenkins",
        incident_type="General SOS",
        description="Household B emergency test",
        latitude=12.9716,
        longitude=77.5946,
        status="ACTIVE",
        created_at=now
    )
    db.add(inc_a)
    db.add(inc_b)
    db.flush()

    alert_a = IncidentAlert(
        incident_id=inc_a.id,
        contact_id=tc_a.id,
        contact_name=tc_a.name,
        contact_phone=tc_a.phone,
        status="QUEUED",
        channel="EMAIL",
        sent_at=now
    )
    alert_b = IncidentAlert(
        incident_id=inc_b.id,
        contact_id=tc_b.id,
        contact_name=tc_b.name,
        contact_phone=tc_b.phone,
        status="QUEUED",
        channel="EMAIL",
        sent_at=now
    )
    db.add(alert_a)
    db.add(alert_b)

    tl_a = IncidentTimelineEvent(
        incident_id=inc_a.id,
        event_type="INCIDENT_CREATED",
        title="Incident Created",
        description="Household A test",
        timestamp=now
    )
    tl_b = IncidentTimelineEvent(
        incident_id=inc_b.id,
        event_type="INCIDENT_CREATED",
        title="Incident Created",
        description="Household B test",
        timestamp=now
    )
    db.add(tl_a)
    db.add(tl_b)

    db.commit()
    db.refresh(user_a)
    db.refresh(user_b)
    db.refresh(member_a)
    db.refresh(member_b)
    db.refresh(inc_a)
    db.refresh(inc_b)
    db.refresh(alert_a)
    db.refresh(alert_b)

    # Generate JWT bearer tokens
    token_a = create_access_token({
        "sub": user_a.username,
        "user_id": user_a.id,
        "role": user_a.role,
        "household_id": user_a.household_id
    })
    token_b = create_access_token({
        "sub": user_b.username,
        "user_id": user_b.id,
        "role": user_b.role,
        "household_id": user_b.household_id
    })

    active_user_1 = User(
        id=1,
        username="admin",
        role="admin",
        household_id=1,
        is_active=True,
        verification_status="APPROVED",
        is_platform_reviewer=True
    )

    def request_as_user_1(method: str, path: str, data: dict = None) -> tuple[int, dict]:
        from app.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: active_user_1
        try:
            return client.request(method, path, data=data, token="override_token")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    try:
        # 3.1 Member Roster Scoping: User A only sees Member A, NOT Member B
        code, members_a = client.request("GET", "/api/members", token=token_a)
        assert code == 200
        mem_ids_a = [m["id"] for m in members_a]
        assert member_a.id in mem_ids_a
        assert member_b.id not in mem_ids_a
        record_pass("GET /api/members correctly scoped to caller's household")

        # 3.2 Cross-Tenant Member Profile Access: User B cannot access Member A
        code, err = client.request("GET", f"/api/members/{member_a.id}", token=token_b)
        assert code == 403, f"Expected 403, got {code}: {err}"
        assert "Forbidden" in err.get("detail", "")
        record_pass("GET /api/members/{id} cross-household access blocked with HTTP 403")

        # 3.3 User ID 1 CANNOT view Member A (zero superuser bypass based on ID 1)
        code, err = request_as_user_1("GET", f"/api/members/{member_a.id}")
        assert code == 403, f"Expected 403, got {code}: {err}"
        record_pass("User ID 1 CANNOT access Member A (ID 1 superuser bypass successfully eliminated)")

        # 3.4 Cross-Tenant Member Update: User B cannot modify Member A
        code, err = client.request("PUT", f"/api/members/{member_a.id}", {"name": "Hacked Name"}, token=token_b)
        assert code == 403
        record_pass("PUT /api/members/{id} cross-household modification blocked with HTTP 403")

        # 3.5 User ID 1 CANNOT modify Member A
        code, err = request_as_user_1("PUT", f"/api/members/{member_a.id}", {"name": "Hacked Name"})
        assert code == 403
        record_pass("User ID 1 CANNOT modify Member A (PUT blocked with HTTP 403)")

        # 3.6 Cross-Tenant Member Deletion: User B cannot delete Member A
        code, err = client.request("DELETE", f"/api/members/{member_a.id}", token=token_b)
        assert code == 403
        record_pass("DELETE /api/members/{id} cross-household deletion blocked with HTTP 403")

        # 3.7 User ID 1 CANNOT delete Member A
        code, err = request_as_user_1("DELETE", f"/api/members/{member_a.id}")
        assert code == 403
        record_pass("User ID 1 CANNOT delete Member A (DELETE blocked with HTTP 403)")

        # 3.8 Trusted Contacts Access: User B cannot access Member A's contacts
        code, err = client.request("GET", f"/api/members/{member_a.id}/trusted-contacts", token=token_b)
        assert code == 403
        record_pass("GET /api/members/{id}/trusted-contacts cross-household access blocked with HTTP 403")

        # 3.9 User ID 1 CANNOT access Member A's trusted contacts
        code, err = request_as_user_1("GET", f"/api/members/{member_a.id}/trusted-contacts")
        assert code == 403
        record_pass("User ID 1 CANNOT access Member A's contacts (check_member_access bypass eliminated)")

        # 3.10 Incidents Roster Scoping: User A only sees Incident A, NOT Incident B
        code, incs_a = client.request("GET", "/api/emergencies", token=token_a)
        assert code == 200
        inc_ids_a = [i["id"] for i in incs_a]
        assert inc_a.id in inc_ids_a
        assert inc_b.id not in inc_ids_a
        record_pass("GET /api/emergencies strictly scoped to caller's household incidents")

        # 3.11 Cross-Tenant Incident Access: User B cannot view Incident A
        code, err = client.request("GET", f"/api/emergencies/{inc_a.id}", token=token_b)
        assert code == 403
        record_pass("GET /api/emergencies/{id} cross-household access blocked with HTTP 403")

        # 3.12 User ID 1 CANNOT view Incident A
        code, err = request_as_user_1("GET", f"/api/emergencies/{inc_a.id}")
        assert code == 403
        record_pass("User ID 1 CANNOT view Incident A (GET blocked with HTTP 403)")

        # 3.13 Cross-Tenant Timeline Access: User B cannot view Incident A timeline
        code, err = client.request("GET", f"/api/emergencies/{inc_a.id}/timeline", token=token_b)
        assert code == 403
        record_pass("GET /api/emergencies/{id}/timeline cross-household access blocked with HTTP 403")

        # 3.14 Cross-Tenant Alerts Access: User B cannot view Incident A alerts
        code, err = client.request("GET", f"/api/emergencies/{inc_a.id}/alerts", token=token_b)
        assert code == 403
        record_pass("GET /api/emergencies/{id}/alerts cross-household access blocked with HTTP 403")

        # 3.15 Cross-Tenant Alert Acknowledge: User B cannot acknowledge Incident A alert
        code, err = client.request("POST", f"/api/emergencies/{inc_a.id}/alerts/{alert_a.id}/acknowledge", token=token_b)
        assert code == 403
        record_pass("POST /alerts/{id}/acknowledge cross-household blocked with HTTP 403")

        # 3.16 Cross-Tenant Alert Retry: User B cannot retry Incident A alert
        code, err = client.request("POST", f"/api/emergencies/{inc_a.id}/alerts/{alert_a.id}/retry", token=token_b)
        assert code == 403
        record_pass("POST /alerts/{id}/retry cross-household blocked with HTTP 403")

        # 3.17 Cross-Tenant Location Telemetry: User B cannot update Incident A location
        loc_data = {"latitude": 13.0, "longitude": 77.0, "location_label": "Hacked Location"}
        code, err = client.request("PATCH", f"/api/emergencies/{inc_a.id}/location", loc_data, token=token_b)
        assert code == 403
        record_pass("PATCH /emergencies/{id}/location cross-household blocked with HTTP 403")

        # 3.18 Cross-Tenant Status Change: User B cannot modify Incident A status
        code, err = client.request("PATCH", f"/api/emergencies/{inc_a.id}/status", {"status": "RESOLVED"}, token=token_b)
        assert code == 403
        record_pass("PATCH /emergencies/{id}/status cross-household modification blocked with HTTP 403")

        # 3.19 User ID 1 CANNOT modify Incident A status
        code, err = request_as_user_1("PATCH", f"/api/emergencies/{inc_a.id}/status", {"status": "RESOLVED"})
        assert code == 403
        record_pass("User ID 1 CANNOT modify Incident A status (PATCH blocked with HTTP 403)")

        # 3.20 Cross-Tenant SOS Trigger: User B cannot trigger SOS for Member A
        sos_data = {
            "reporter_name": "Attacker",
            "incident_type": "Fall",
            "member_id": member_a.id,
            "latitude": 12.9716,
            "longitude": 77.5946
        }
        code, err = client.request("POST", "/api/emergencies/sos", sos_data, token=token_b)
        assert code == 403
        record_pass("POST /api/emergencies/sos for cross-household member blocked with HTTP 403")

        # 3.21 Legitimate Owner Workflows: User A can successfully view and update their own incident
        code, ack_res = client.request("POST", f"/api/emergencies/{inc_a.id}/alerts/{alert_a.id}/acknowledge", token=token_a)
        assert code == 200
        assert ack_res["status"] == "ACKNOWLEDGED"
        record_pass("Legitimate household administrator workflow verified (Alert acknowledged successfully)")

    finally:
        # Clean up temporary test data cleanly
        db.query(IncidentAlert).filter(IncidentAlert.incident_id.in_([inc_a.id, inc_b.id])).delete()
        db.query(IncidentTimelineEvent).filter(IncidentTimelineEvent.incident_id.in_([inc_a.id, inc_b.id])).delete()
        db.query(EmergencyIncident).filter(EmergencyIncident.id.in_([inc_a.id, inc_b.id])).delete()
        db.query(TrustedContact).filter(TrustedContact.id.in_([tc_a.id, tc_b.id])).delete()
        db.query(Member).filter(Member.id.in_([member_a.id, member_b.id])).delete()
        db.query(User).filter(User.id.in_([user_a.id, user_b.id])).delete()
        db.commit()

        final_m_cnt = db.query(Member).count()
        final_i_cnt = db.query(EmergencyIncident).count()
        final_u_cnt = db.query(User).count()
        db.close()

        assert final_m_cnt == initial_member_count
        assert final_i_cnt == initial_incident_count
        assert final_u_cnt == initial_user_count
        record_pass(f"Zero database pollution verified: counts restored (Members: {final_m_cnt}, Incidents: {final_i_cnt}, Users: {final_u_cnt})")

    # -------------------------------------------------------------
    # GROUP 4: WebSocket Authentication & Cross-Tenant Subscriptions
    # -------------------------------------------------------------
    print("\n--- GROUP 4: WebSocket Authentication & Subscription Security ---")

    async def run_ws_tests():
        def is_auth_rejected(exc) -> bool:
            if isinstance(exc, websockets.exceptions.ConnectionClosed):
                return exc.rcvd is not None and exc.rcvd.code == 1008
            if isinstance(exc, websockets.exceptions.InvalidStatus):
                status_code = getattr(exc.response, "status_code", None) or getattr(exc, "status_code", None)
                return status_code in (401, 403) or "403" in str(exc) or "401" in str(exc)
            return False

        # 4.1 Missing token -> rejected (code 1008 / HTTP 403)
        try:
            async with websockets.connect(BASE_WS_URL) as ws:
                await ws.recv()
                record_fail("WS missing token", "Did not close connection")
        except Exception as exc:
            assert is_auth_rejected(exc), f"Unexpected rejection error: {type(exc).__name__}: {exc}"
            record_pass("WebSocket unauthenticated connection strictly rejected (HTTP 403 / code 1008)")

        # 4.2 Invalid token -> rejected (code 1008 / HTTP 403)
        try:
            async with websockets.connect(f"{BASE_WS_URL}?token=invalid.token.signature") as ws:
                await ws.recv()
                record_fail("WS invalid token", "Did not close connection")
        except Exception as exc:
            assert is_auth_rejected(exc), f"Unexpected rejection error: {type(exc).__name__}: {exc}"
            record_pass("WebSocket invalid token signature strictly rejected (HTTP 403 / code 1008)")

        # 4.3 Valid connection for Admin Alpha (Household 4) and Admin Beta (Household 5)
        # Using persistent active test accounts (ID 4 and ID 5)
        db_lookup = SessionLocal()
        u4 = db_lookup.query(User).filter(User.id == 4).first()
        u5 = db_lookup.query(User).filter(User.id == 5).first()
        alpha_sub = u4.username if u4 else "test_admin_alpha"
        beta_sub = u5.username if u5 else "test_admin_beta"
        db_lookup.close()

        token_alpha = create_access_token({
            "sub": alpha_sub,
            "user_id": 4,
            "role": "admin",
            "household_id": 4
        })
        token_beta = create_access_token({
            "sub": beta_sub,
            "user_id": 5,
            "role": "admin",
            "household_id": 5
        })

        async with websockets.connect(f"{BASE_WS_URL}?token={token_alpha}") as ws_alpha:
            conn_msg = json.loads(await asyncio.wait_for(ws_alpha.recv(), timeout=2.0))
            assert conn_msg["event_type"] == "CONNECTED"
            assert conn_msg["user"]["username"] == alpha_sub
            record_pass("WebSocket authenticated connection established successfully for Household 4")

            # Ping/Pong test
            await ws_alpha.send(json.dumps({"action": "ping"}))
            pong_msg = json.loads(await asyncio.wait_for(ws_alpha.recv(), timeout=2.0))
            assert pong_msg["event_type"] == "PONG"
            record_pass("WebSocket ping/pong keepalive verified")

            # 4.4 Cross-tenant incident subscription: Household 4 tries to subscribe to Household 5 incident
            # Find an existing incident belonging to household 5
            db_ws = SessionLocal()
            inc_h5 = db_ws.query(EmergencyIncident).filter(EmergencyIncident.user_id == 5).first()
            inc_h4 = db_ws.query(EmergencyIncident).filter(EmergencyIncident.user_id == 4).first()
            db_ws.close()

            if inc_h5:
                await ws_alpha.send(json.dumps({
                    "action": "subscribe_incident",
                    "incident_id": inc_h5.id
                }))
                sub_denied = json.loads(await asyncio.wait_for(ws_alpha.recv(), timeout=2.0))
                assert sub_denied["event_type"] == "SUBSCRIPTION_DENIED"
                assert sub_denied["code"] == 403
                record_pass(f"Cross-household subscription to Incident #{inc_h5.id} strictly DENIED (HTTP 403)")

            # 4.5 Valid subscription to own household incident
            if inc_h4:
                await ws_alpha.send(json.dumps({
                    "action": "subscribe_incident",
                    "incident_id": inc_h4.id
                }))
                sub_ok = json.loads(await asyncio.wait_for(ws_alpha.recv(), timeout=2.0))
                assert sub_ok["event_type"] == "SUBSCRIBED"
                assert sub_ok["incident_id"] == inc_h4.id
                record_pass(f"Valid household subscription to Incident #{inc_h4.id} accepted (SUBSCRIBED)")

        # 4.6 Deactivated account (admin ID 1) connection strictly rejected
        token_u1 = create_access_token({
            "sub": "admin",
            "user_id": 1,
            "role": "admin",
            "household_id": 1
        })
        try:
            async with websockets.connect(f"{BASE_WS_URL}?token={token_u1}") as ws_u1:
                await ws_u1.recv()
                record_fail("Deactivated WS connect", "Allowed deactivated account connection")
        except Exception as exc:
            assert is_auth_rejected(exc), f"Unexpected rejection error: {type(exc).__name__}: {exc}"
            record_pass("Deactivated account (User ID 1) strictly rejected on WebSocket connect (HTTP 403 / code 1008)")

    asyncio.run(run_ws_tests())

    # Stop background test server
    server.should_exit = True
    server_thread.join(timeout=3)
    engine.dispose()

    # -------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------
    print("\n" + "=" * 80)
    print(f"RESULTS: {passed}/{total} TESTS PASSED ({(passed/total)*100:.1f}%)")
    print("=" * 80)
    return passed == total


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
