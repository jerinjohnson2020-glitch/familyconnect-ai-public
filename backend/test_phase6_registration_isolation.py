"""
Phase 6 Automated Verification: Multi-Tenant Household Registration & Data Isolation Suite
Validates:
1. Self-service registration (/api/auth/register) with password policy and email format validation.
2. Multi-tenant household data isolation (User B cannot view or tamper with User A's members, contacts, or incidents).
3. RBAC protections and zero cross-tenant data leakage.
4. Database integrity and cleanup guarantee.
"""

import json
import os
import sys
import time
import threading
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from app.main import app
from app.database import engine, SessionLocal
from app import models

TEST_PORT = 8017


class LiveHttpResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text

    def json(self):
        return json.loads(self.text) if self.text else {}


class LiveHttpClient:
    def __init__(self, base_url: str = f"http://127.0.0.1:{TEST_PORT}"):
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, json_body=None, headers=None) -> LiveHttpResponse:
        url = f"{self.base_url}{path}"
        req_headers = {"Content-Type": "application/json"}
        if headers:
            req_headers.update(headers)
        data = json.dumps(json_body).encode("utf-8") if json_body is not None else None
        req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return LiveHttpResponse(resp.status, resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", errors="replace")
            return LiveHttpResponse(err.code, body)

    def get(self, path: str, headers=None) -> LiveHttpResponse:
        return self._request("GET", path, headers=headers)

    def post(self, path: str, json=None, headers=None) -> LiveHttpResponse:
        return self._request("POST", path, json_body=json, headers=headers)

    def put(self, path: str, json=None, headers=None) -> LiveHttpResponse:
        return self._request("PUT", path, json_body=json, headers=headers)

    def patch(self, path: str, json=None, headers=None) -> LiveHttpResponse:
        return self._request("PATCH", path, json_body=json, headers=headers)

    def delete(self, path: str, headers=None) -> LiveHttpResponse:
        return self._request("DELETE", path, headers=headers)


client = LiveHttpClient(f"http://127.0.0.1:{TEST_PORT}")


def run_isolation_tests():
    print("=" * 76)
    print("FAMILYCONNECT AI — MULTI-TENANT REGISTRATION & ISOLATION SUITE")
    print("=" * 76)

    # Start dedicated Uvicorn server on port 8017
    config = uvicorn.Config(app, host="127.0.0.1", port=TEST_PORT, log_level="error")
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    for _ in range(40):
        try:
            if client.get("/api/health").status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.15)

    db = SessionLocal()
    # Baseline counts before test
    initial_member_count = db.query(models.Member).count()
    initial_incident_count = db.query(models.EmergencyIncident).count()
    initial_user_count = db.query(models.User).count()
    db.close()

    try:
        # [TEST 1] Registration Validation
        print("\n[TEST 1] Verifying Registration Input Validation & Password Complexity...")
        res_short = client.post("/api/auth/register", json={
            "username": "short_pw_user",
            "password": "p1!",
            "email": "valid@household.test"
        })
        assert res_short.status_code == 422, f"Expected 422 for short pw, got {res_short.status_code}"

        res_email = client.post("/api/auth/register", json={
            "username": "bad_email_user",
            "password": "SecurePassword123!",
            "email": "not-an-email"
        })
        assert res_email.status_code == 422, f"Expected 422 for invalid email, got {res_email.status_code}"

        res_nonum = client.post("/api/auth/register", json={
            "username": "nonum_user",
            "password": "PasswordWithoutNumber",
            "email": "valid2@household.test"
        })
        assert res_nonum.status_code == 422, f"Expected 422 for password without number, got {res_nonum.status_code}"
        print("  -> PASS: Short passwords, invalid emails, and weak passwords properly rejected.")

        # [TEST 2] Register Household A and Household B
        print("\n[TEST 2] Registering Two Distinct Household Administrators...")
        res_a = client.post("/api/auth/register", json={
            "username": "test_user_a_isolation",
            "password": "HouseAPassword123!",
            "email": "household_a@familyconnect.test",
            "full_name": "Alice Admin",
            "phone": "+1 (555) 111-2222",
            "create_self_member": True
        })
        assert res_a.status_code == 201, f"User A registration failed: {res_a.text}"
        data_a = res_a.json()
        token_a = data_a["access_token"]
        user_a_id = data_a["user"]["id"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        # Verify duplicate username rejected
        res_dup = client.post("/api/auth/register", json={
            "username": "test_user_a_isolation",
            "password": "HouseAPassword123!",
            "email": "different_email@familyconnect.test"
        })
        assert res_dup.status_code == 409, f"Expected 409 for duplicate username, got {res_dup.status_code}"

        res_b = client.post("/api/auth/register", json={
            "username": "test_user_b_isolation",
            "password": "HouseBPassword123!",
            "email": "household_b@familyconnect.test",
            "full_name": "Bob Admin",
            "phone": "+1 (555) 333-4444",
            "create_self_member": False
        })
        assert res_b.status_code == 201, f"User B registration failed: {res_b.text}"
        data_b = res_b.json()
        token_b = data_b["access_token"]
        user_b_id = data_b["user"]["id"]
        headers_b = {"Authorization": f"Bearer {token_b}"}
        print("  -> PASS: Distinct households registered; duplicate prevention confirmed.")

        # [TEST 3] Member Roster Isolation
        print("\n[TEST 3] Verifying Household Member Roster & CRUD Isolation...")
        res_create_m = client.post("/api/members", headers=headers_a, json={
            "name": "Charlie from Household A",
            "relationship": "Child",
            "age": 10,
            "phone": "+1 (555) 777-8888",
            "blood_group": "O+",
            "medical_notes": "No allergies",
            "is_active": True
        })
        assert res_create_m.status_code == 201, f"Member creation failed: {res_create_m.text}"
        member_a_id = res_create_m.json()["id"]

        # User A roster contains Charlie
        res_roster_a = client.get("/api/members", headers=headers_a)
        assert res_roster_a.status_code == 200
        ids_a = [m["id"] for m in res_roster_a.json()]
        assert member_a_id in ids_a, "Charlie should appear in Household A roster"

        # User B roster does NOT contain Charlie
        res_roster_b = client.get("/api/members", headers=headers_b)
        assert res_roster_b.status_code == 200
        ids_b = [m["id"] for m in res_roster_b.json()]
        assert member_a_id not in ids_b, "Charlie must NOT appear in Household B roster"

        # User B cross-tenant operations return HTTP 403 Forbidden
        assert client.get(f"/api/members/{member_a_id}", headers=headers_b).status_code == 403
        assert client.put(f"/api/members/{member_a_id}", headers=headers_b, json={"name": "Hacked"}).status_code == 403
        assert client.delete(f"/api/members/{member_a_id}", headers=headers_b).status_code == 403
        print("  -> PASS: Member roster private to Household A; User B blocked with HTTP 403 on GET/PUT/DELETE.")

        # [TEST 4] Trusted Contact Isolation
        print("\n[TEST 4] Verifying Trusted Contact Isolation Across Households...")
        res_tc = client.post(f"/api/members/{member_a_id}/trusted-contacts", headers=headers_a, json={
            "name": "Trusted Neighbor Jane",
            "phone": "+1 (555) 999-0011",
            "email": "jane.neighbor@realfamily.org",
            "relationship": "Neighbor",
            "priority": 1,
            "notification_preferences": "EMAIL",
            "is_active": True
        })
        assert res_tc.status_code == 201, f"Contact creation failed: {res_tc.text}"

        assert client.get(f"/api/members/{member_a_id}/trusted-contacts", headers=headers_b).status_code == 403
        assert client.post(f"/api/members/{member_a_id}/trusted-contacts", headers=headers_b, json={
            "name": "Attacker Contact",
            "phone": "+1 (555) 000-9999",
            "relationship": "Attacker",
            "priority": 1,
            "notification_preferences": "SMS",
            "is_active": True
        }).status_code == 403
        print("  -> PASS: Trusted contacts private; User B blocked with HTTP 403.")

        # [TEST 5] Incident, Timeline & Alerts Isolation
        print("\n[TEST 5] Verifying Emergency Incident, Timeline & Alerts Multi-Tenant Privacy...")
        res_sos = client.post("/api/emergencies/sos", headers=headers_a, json={
            "member_id": member_a_id,
            "reporter_name": "Alice Admin",
            "incident_type": "Asthma Attack",
            "description": "Child having severe shortness of breath",
            "latitude": 37.7749,
            "longitude": -122.4194,
            "location_label": "Home",
            "location_source": "browser_gps",
            "location_accuracy_m": 5.0,
            "is_conscious": True,
            "has_breathing_difficulty": True,
            "is_bleeding_severely": False,
            "is_alone": False
        })
        assert res_sos.status_code == 201, f"SOS creation failed: {res_sos.text}"
        inc_a_id = res_sos.json()["id"]

        # User A sees incident in list
        res_inc_a = client.get("/api/emergencies", headers=headers_a)
        assert res_inc_a.status_code == 200
        assert inc_a_id in [i["id"] for i in res_inc_a.json()]

        # User B list does NOT contain incident
        res_inc_b = client.get("/api/emergencies", headers=headers_b)
        assert res_inc_b.status_code == 200
        assert inc_a_id not in [i["id"] for i in res_inc_b.json()]

        # User B blocked from details, timeline, alerts, and status modification
        assert client.get(f"/api/emergencies/{inc_a_id}", headers=headers_b).status_code == 403
        assert client.get(f"/api/emergencies/{inc_a_id}/timeline", headers=headers_b).status_code == 403
        assert client.get(f"/api/emergencies/{inc_a_id}/alerts", headers=headers_b).status_code == 403
        assert client.patch(f"/api/emergencies/{inc_a_id}/status", headers=headers_b, json={
            "status": "RESOLVED",
            "resolution_notes": "Unauthorized close"
        }).status_code == 403

        # User A can resolve their incident
        res_res = client.patch(f"/api/emergencies/{inc_a_id}/status", headers=headers_a, json={
            "status": "RESOLVED",
            "resolution_notes": "Inhaler administered, patient recovered."
        })
        assert res_res.status_code == 200
        assert res_res.json()["status"] == "RESOLVED"
        print("  -> PASS: Incident, timeline, and alerts strictly isolated between households.")

    finally:
        # Clean up test records in safe order
        db_clean = SessionLocal()
        try:
            test_users = db_clean.query(models.User).filter(
                models.User.username.in_(["test_user_a_isolation", "test_user_b_isolation"])
            ).all()
            test_user_ids = [u.id for u in test_users]
            if test_user_ids:
                # 1. Clear member_id and household_id foreign keys on users
                for u in test_users:
                    u.member_id = None
                    u.household_id = None
                db_clean.commit()

                # 2. Delete test incidents
                incs = db_clean.query(models.EmergencyIncident).filter(models.EmergencyIncident.user_id.in_(test_user_ids)).all()
                for inc in incs:
                    db_clean.query(models.IncidentAlert).filter(models.IncidentAlert.incident_id == inc.id).delete()
                    db_clean.query(models.IncidentTimelineEvent).filter(models.IncidentTimelineEvent.incident_id == inc.id).delete()
                    db_clean.query(models.IncidentResponder).filter(models.IncidentResponder.incident_id == inc.id).delete()
                    db_clean.delete(inc)
                db_clean.commit()

                # 3. Delete test members and their contacts
                mems = db_clean.query(models.Member).filter(models.Member.user_id.in_(test_user_ids)).all()
                for m in mems:
                    db_clean.query(models.TrustedContact).filter(models.TrustedContact.member_id == m.id).delete()
                    db_clean.delete(m)
                db_clean.commit()

                # 4. Delete test users
                for u in test_users:
                    db_clean.delete(u)
                db_clean.commit()
        finally:
            final_m_cnt = db_clean.query(models.Member).count()
            final_i_cnt = db_clean.query(models.EmergencyIncident).count()
            final_u_cnt = db_clean.query(models.User).count()
            db_clean.close()
            server.should_exit = True
            server_thread.join(timeout=3)
            engine.dispose()

        assert final_m_cnt == initial_member_count, f"Member count mismatch: {initial_member_count} vs {final_m_cnt}"
        assert final_i_cnt == initial_incident_count, f"Incident count mismatch: {initial_incident_count} vs {final_i_cnt}"
        assert final_u_cnt == initial_user_count, f"User count mismatch: {initial_user_count} vs {final_u_cnt}"
        print("\n[CLEANUP VERIFIED] All test accounts and entities cleaned; database counts restored:")
        print(f"  Members: {final_m_cnt} | Incidents: {final_i_cnt} | Users: {final_u_cnt}")

    print("\n" + "=" * 76)
    print("ALL MULTI-TENANT ISOLATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 76)


if __name__ == "__main__":
    run_isolation_tests()
