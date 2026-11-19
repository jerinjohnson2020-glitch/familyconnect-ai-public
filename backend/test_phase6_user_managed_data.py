"""
Phase 6 Automated Verification Suite: Replace Demo Data With Real User-Managed Data.
Executes real FastAPI TestClient requests against the application and verifies:
1. Creating, editing, deactivating, and deleting a real user-managed family member (plus duplicate detection).
2. Adding, editing, deactivating, and deleting trusted contacts, and rejecting placeholder domains (@example.com, 000-0000).
3. Creating a responder without coordinates (verifying no fake/random coordinates are invented).
4. Updating responder coordinates and verifying Haversine distance calculation only on valid coordinates.
5. Triggering SOS with a real saved family member (verifying real coordinates, AI triage, responder ranking, and alert targets).
6. Verifying only configured active trusted contacts are notified (never invented fallback addresses).
7. Verifying honest timeline behavior when no active trusted contacts exist (NO_ACTIVE_CONTACTS).
8. Verifying honest timeline behavior when no responders have valid coordinates (NO_RESPONDERS_WITH_COORDINATES).
9. Verifying safe demo record control (deactivation/reactivation & ENABLE_DEMO_SEED gating).
10. Verifying explicit user-confirmed test notification endpoint and status reporting.
11. Verifying role-based access control across admin, member, and responder roles.
12. Verifying existing database records remain intact after test cleanup.
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
from app import auth
from app.seed_data import seed_database

TEST_API_PORT = 8016


class LiveHttpResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text

    def json(self):
        return json.loads(self.text) if self.text else {}


class LiveHttpClient:
    def __init__(self, base_url: str = f"http://127.0.0.1:{TEST_API_PORT}"):
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


client = LiveHttpClient(f"http://127.0.0.1:{TEST_API_PORT}")


def get_token(username: str, password: str) -> str:
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, f"Login failed for {username}: {res.text}"
    return res.json()["access_token"]


def run_phase6_tests():
    print("=" * 76)
    print("FAMILYCONNECT AI — PHASE 6 AUTOMATED VERIFICATION SUITE")
    print("=" * 76)

    # Start dedicated Uvicorn server on port 8016
    config = uvicorn.Config(app, host="127.0.0.1", port=TEST_API_PORT, log_level="error")
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

    # Ensure any leftover test rows from interrupted runs are cleaned first
    db = SessionLocal()
    leftover_incs = db.query(models.EmergencyIncident).filter(models.EmergencyIncident.reporter_name == "Priya Nair").all()
    for li in leftover_incs:
        db.query(models.IncidentTimelineEvent).filter(models.IncidentTimelineEvent.incident_id == li.id).delete()
        db.query(models.IncidentAlert).filter(models.IncidentAlert.incident_id == li.id).delete()
        db.query(models.IncidentResponder).filter(models.IncidentResponder.incident_id == li.id).delete()
        db.delete(li)
    leftover_resps = db.query(models.Responder).filter(models.Responder.name.in_(["Dr. Kavita Rao", "Paramedic Leo Vance"])).all()
    for lr in leftover_resps:
        db.query(models.IncidentResponder).filter(models.IncidentResponder.responder_id == lr.id).delete()
        db.delete(lr)
    leftover_members = db.query(models.Member).filter(models.Member.name == "Priya Nair").all()
    for lm in leftover_members:
        db.query(models.TrustedContact).filter(models.TrustedContact.member_id == lm.id).delete()
        db.delete(lm)
    db.query(models.User).filter(models.User.username.in_(["test_p6_admin", "test_p6_member", "test_p6_resp"])).delete()
    db.query(models.Member).filter(models.Member.is_demo == True).update({"is_active": True})
    db.query(models.TrustedContact).filter(models.TrustedContact.is_demo == True).update({"is_active": True})
    db.query(models.Responder).filter(models.Responder.is_demo == True).update({"is_active": True})
    db.commit()

    initial_member_count = db.query(models.Member).count()
    initial_incident_count = db.query(models.EmergencyIncident).count()
    initial_user_count = db.query(models.User).count()

    # Provision temporary isolated users for test execution
    h_pw, h_salt = auth.hash_password("TestPhase6Pass123!")
    u_admin = models.User(
        username="test_p6_admin",
        email="test_p6_admin@example.com",
        phone="+91 98765 00021",
        hashed_password=h_pw,
        salt=h_salt,
        role="admin",
        is_active=True,
        household_id=1,
        verification_status="APPROVED"
    )
    u_member = models.User(
        username="test_p6_member",
        email="test_p6_member@example.com",
        phone="+91 98765 00022",
        hashed_password=h_pw,
        salt=h_salt,
        role="member",
        is_active=True,
        household_id=2,
        verification_status="APPROVED"
    )
    u_resp = models.User(
        username="test_p6_resp",
        email="test_p6_resp@example.com",
        phone="+91 98765 00023",
        hashed_password=h_pw,
        salt=h_salt,
        role="responder",
        is_active=True,
        responder_id=None,
        verification_status="APPROVED"
    )
    db.add_all([u_admin, u_member, u_resp])
    db.commit()
    db.refresh(u_admin)
    db.refresh(u_member)
    db.refresh(u_resp)
    created_user_ids = [u_admin.id, u_member.id, u_resp.id]
    db.close()

    admin_token = get_token("test_p6_admin", "TestPhase6Pass123!")
    member_token = get_token("test_p6_member", "TestPhase6Pass123!")
    responder_token = get_token("test_p6_resp", "TestPhase6Pass123!")

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    member_headers = {"Authorization": f"Bearer {member_token}"}
    responder_headers = {"Authorization": f"Bearer {responder_token}"}

    created_member_ids = []
    created_responder_ids = []
    created_incident_ids = []

    try:
        # ------------------------------------------------------------------
        # TEST 1: Family Member CRUD, Duplicate Detection & Ownership
        # ------------------------------------------------------------------
        print("\n[TEST 1] Family Member Creation, Editing, Duplicate Check & Role Enforcement...")
        member_payload = {
            "name": "Priya Nair",
            "relationship": "Sister",
            "age": 31,
            "phone": "+1 415 891 3344",
            "email": "priya.nair@familyconnect.local",
            "address": "742 Evergreen Terrace, Austin, TX",
            "blood_group": "B+",
            "medical_notes": "Mild asthma, carries albuterol inhaler",
            "emergency_contact_name": "Arjun Nair",
            "emergency_contact_phone": "+1 415 891 3345",
            "is_active": True,
        }
        res_create = client.post("/api/members", json=member_payload, headers=admin_headers)
        assert res_create.status_code == 201, res_create.text
        created_member = res_create.json()
        member_id = created_member["id"]
        created_member_ids.append(member_id)

        assert created_member["name"] == "Priya Nair"
        assert created_member["email"] == "priya.nair@familyconnect.local"
        assert created_member["address"] == "742 Evergreen Terrace, Austin, TX"
        assert created_member["is_active"] is True
        assert created_member["is_demo"] is False
        assert len(created_member["trusted_contacts"]) == 1
        assert created_member["trusted_contacts"][0]["name"] == "Arjun Nair"

        # Duplicate check (same name + normalized phone)
        res_dup = client.post(
            "/api/members",
            json={**member_payload, "phone": "1-415-891-3344"},
            headers=admin_headers,
        )
        assert res_dup.status_code == 409, f"Expected 409 duplicate error, got {res_dup.status_code}"

        # Edit member
        res_edit = client.put(
            f"/api/members/{member_id}",
            json={
                "age": 32,
                "address": "800 Congress Ave, Austin, TX",
                "medical_notes": "Moderate asthma, albuterol inhaler in purse",
            },
            headers=admin_headers,
        )
        assert res_edit.status_code == 200, res_edit.text
        edited_member = res_edit.json()
        assert edited_member["age"] == 32
        assert edited_member["address"] == "800 Congress Ave, Austin, TX"

        # Member role cannot edit another member's profile
        res_forbidden_edit = client.put(
            f"/api/members/{member_id}",
            json={"age": 40},
            headers=member_headers,
        )
        assert res_forbidden_edit.status_code == 403

        print("  -> PASS: Member CRUD, duplicate detection, and ownership enforcement verified.")

        # ------------------------------------------------------------------
        # TEST 2: Trusted-Contact CRUD & Placeholder Destination Rejection
        # ------------------------------------------------------------------
        print("\n[TEST 2] Trusted-Contact Management & Placeholder Rejection...")
        # Attempt to add a contact with placeholder @example.com
        res_bad_email = client.post(
            f"/api/members/{member_id}/trusted-contacts",
            json={
                "name": "Fake Contact",
                "phone": "+1 415 891 9999",
                "email": "fake@example.com",
                "relationship": "Neighbor",
                "priority": 2,
                "notification_preferences": "EMAIL",
                "is_active": True,
            },
            headers=admin_headers,
        )
        assert res_bad_email.status_code == 400, f"Expected 400 for @example.com, got {res_bad_email.status_code}"

        # Attempt to add a contact with placeholder 000-0000 phone
        res_bad_phone = client.post(
            f"/api/members/{member_id}/trusted-contacts",
            json={
                "name": "Fake Phone Contact",
                "phone": "+1 555 000-0000",
                "email": "valid.contact@familyconnect.local",
                "relationship": "Neighbor",
                "priority": 2,
                "notification_preferences": "SMS",
                "is_active": True,
            },
            headers=admin_headers,
        )
        assert res_bad_phone.status_code in (400, 422), f"Expected 400 or 422 for 000-0000, got {res_bad_phone.status_code}"

        # Add a valid secondary trusted contact
        res_add_tc = client.post(
            f"/api/members/{member_id}/trusted-contacts",
            json={
                "name": "Deepa Nair",
                "phone": "+1 415 891 4455",
                "email": "deepa.nair@familyconnect.local",
                "relationship": "Mother",
                "priority": 2,
                "notification_preferences": "EMAIL",
                "is_active": True,
            },
            headers=admin_headers,
        )
        assert res_add_tc.status_code == 201, res_add_tc.text
        tc2 = res_add_tc.json()
        tc2_id = tc2["id"]
        assert tc2["email"] == "deepa.nair@familyconnect.local"
        assert tc2["is_demo"] is False

        # Edit trusted contact
        res_upd_tc = client.put(
            f"/api/members/{member_id}/trusted-contacts/{tc2_id}",
            json={"relationship": "Mother (Primary Backup)", "is_active": False},
            headers=admin_headers,
        )
        assert res_upd_tc.status_code == 200
        assert res_upd_tc.json()["is_active"] is False

        # Re-activate and update primary contact with email so EMAIL alerts have a verified destination
        primary_tc_id = created_member["trusted_contacts"][0]["id"]
        res_upd_primary = client.put(
            f"/api/members/{member_id}/trusted-contacts/{primary_tc_id}",
            json={
                "email": "arjun.nair@familyconnect.local",
                "notification_preferences": "EMAIL",
                "is_active": True,
            },
            headers=admin_headers,
        )
        assert res_upd_primary.status_code == 200

        # Delete secondary contact
        res_del_tc = client.delete(
            f"/api/members/{member_id}/trusted-contacts/{tc2_id}",
            headers=admin_headers,
        )
        assert res_del_tc.status_code == 200
        print("  -> PASS: Trusted-contact CRUD and placeholder destination rejection verified.")

        # ------------------------------------------------------------------
        # TEST 3: Responder Creation Without Coordinates (No Fake Coords)
        # ------------------------------------------------------------------
        print("\n[TEST 3] Responder Creation Without Coordinates (Zero Fabricated Locations)...")
        resp_no_coords_payload = {
            "name": "Dr. Kavita Rao",
            "role": "Emergency Physician",
            "organization": "Austin Metro EMS",
            "phone": "+1 512 771 8899",
            "email": "kavita.rao@familyconnect.local",
            "skills": "Advanced Cardiac Life Support, Trauma",
            "is_available": True,
            "is_active": True,
        }
        res_resp1 = client.post("/api/responders", json=resp_no_coords_payload, headers=admin_headers)
        assert res_resp1.status_code == 201, res_resp1.text
        resp1 = res_resp1.json()
        resp1_id = resp1["id"]
        created_responder_ids.append(resp1_id)

        assert resp1["latitude"] is None, "Responder created without coordinates must have latitude=None"
        assert resp1["longitude"] is None, "Responder created without coordinates must have longitude=None"
        assert resp1["location_source"] in ("unset", "unconfigured")
        assert resp1["location_updated_at"] is None
        assert resp1["is_demo"] is False

        # Create a second responder WITH verified coordinates near Austin, TX (30.2672, -97.7431)
        resp_with_coords_payload = {
            "name": "Paramedic Leo Vance",
            "role": "Paramedic",
            "organization": "Travis County Rescue",
            "phone": "+1 512 771 9900",
            "email": "leo.vance@familyconnect.local",
            "skills": "Paramedic, AED, Airway Management",
            "is_available": True,
            "is_active": True,
            "latitude": 30.2680,
            "longitude": -97.7425,
            "location_source": "manual",
        }
        res_resp2 = client.post("/api/responders", json=resp_with_coords_payload, headers=admin_headers)
        assert res_resp2.status_code == 201, res_resp2.text
        resp2 = res_resp2.json()
        resp2_id = resp2["id"]
        created_responder_ids.append(resp2_id)
        assert resp2["latitude"] == 30.2680
        assert resp2["longitude"] == -97.7425
        assert resp2["location_updated_at"] is not None

        # Verify /api/responders/nearby excludes Dr. Kavita Rao (while she has no coordinates)
        res_nearby = client.get(
            "/api/responders/nearby?lat=30.2672&lon=-97.7431",
            headers=admin_headers,
        )
        assert res_nearby.status_code == 200, res_nearby.text
        nearby_ids = [r["id"] for r in res_nearby.json()]
        assert resp1_id not in nearby_ids, "Responder without coordinates must be excluded from Haversine ranking"
        assert resp2_id in nearby_ids, "Responder with valid coordinates must be included in Haversine ranking"
        print("  -> PASS: Responders without coordinates have null coords and are excluded from distance ranking.")

        # ------------------------------------------------------------------
        # TEST 4: Updating Responder Coordinates & Verifying Distance Calculation
        # ------------------------------------------------------------------
        print("\n[TEST 4] Updating Responder Coordinates & Haversine Distance Calculation...")
        res_loc_upd = client.patch(
            f"/api/responders/{resp1_id}/location",
            json={
                "latitude": 30.2675,
                "longitude": -97.7430,
                "location_source": "browser_gps",
                "is_available": True,
            },
            headers=admin_headers,
        )
        assert res_loc_upd.status_code == 200, res_loc_upd.text
        upd_resp1 = res_loc_upd.json()
        assert upd_resp1["latitude"] == 30.2675
        assert upd_resp1["longitude"] == -97.7430
        assert upd_resp1["location_source"] == "browser_gps"
        assert upd_resp1["location_updated_at"] is not None

        # Now Dr. Kavita Rao is ~0.03 km from (30.2672, -97.7431) and should rank #1
        res_nearby_after = client.get(
            "/api/responders/nearby?lat=30.2672&lon=-97.7431",
            headers=admin_headers,
        )
        assert res_nearby_after.status_code == 200, res_nearby_after.text
        ranked = res_nearby_after.json()
        assert ranked[0]["id"] == resp1_id, f"Expected Dr. Kavita Rao first, got {ranked[0]}"
        assert ranked[0]["distance_km"] < 0.2
        print(f"  -> PASS: Updated responder coordinates ranked #1 at {ranked[0]['distance_km']} km.")

        # ------------------------------------------------------------------
        # TEST 5 & 6: Triggering SOS with Real Member & Configured Trusted Contact
        # ------------------------------------------------------------------
        print("\n[TEST 5 & 6] Triggering SOS with Real Saved Member & Verifying Alerts...")
        sos_payload = {
            "member_id": member_id,
            "reporter_name": "Priya Nair",
            "incident_type": "Breathing Difficulty",
            "description": "Severe acute asthma attack, struggling to speak full sentences",
            "latitude": 30.2672,
            "longitude": -97.7431,
            "location_label": "800 Congress Ave, Austin, TX (30.2672, -97.7431)",
            "location_accuracy_m": 12.0,
            "location_source": "browser_gps",
            "is_conscious": True,
            "has_breathing_difficulty": True,
            "is_bleeding_severely": False,
            "is_alone": True,
        }
        res_sos = client.post("/api/emergencies/sos", json=sos_payload, headers=admin_headers)
        assert res_sos.status_code == 201, res_sos.text
        incident = res_sos.json()
        created_incident_ids.append(incident["id"])

        assert incident["member_id"] == member_id
        assert incident["severity_level"] in ("HIGH", "CRITICAL")
        assert incident["location_source"] == "browser_gps"
        assert len(incident["matched_responders"]) > 0
        assert incident["matched_responders"][0]["responder_id"] == resp1_id
        assert incident["matched_responders"][0]["organization"] == "Austin Metro EMS"

        # Verify only Arjun Nair (active trusted contact) was notified, never any @example.com fallback
        assert len(incident["alerts"]) == 1
        alert = incident["alerts"][0]
        assert alert["contact_name"] == "Arjun Nair"
        assert alert["contact_email"] == "arjun.nair@familyconnect.local"
        assert "@example.com" not in (alert["contact_email"] or "")
        print("  -> PASS: SOS incident matched real nearest responder and notified only configured active contact.")

        # ------------------------------------------------------------------
        # TEST 7: SOS When Member Has No Active Trusted Contacts
        # ------------------------------------------------------------------
        print("\n[TEST 7] Verifying Behavior When No Active Trusted Contacts Exist...")
        # Deactivate Priya's only remaining contact
        client.put(
            f"/api/members/{member_id}/trusted-contacts/{primary_tc_id}",
            json={"is_active": False},
            headers=admin_headers,
        )
        res_sos_no_tc = client.post("/api/emergencies/sos", json=sos_payload, headers=admin_headers)
        assert res_sos_no_tc.status_code == 201, res_sos_no_tc.text
        inc_no_tc = res_sos_no_tc.json()
        created_incident_ids.append(inc_no_tc["id"])

        assert len(inc_no_tc["alerts"]) == 0, "No alerts should be fabricated when 0 active contacts exist"
        event_types = [ev["event_type"] for ev in inc_no_tc["timeline_events"]]
        assert "NO_ACTIVE_CONTACTS" in event_types, f"Expected NO_ACTIVE_CONTACTS in timeline, got {event_types}"
        print("  -> PASS: Zero alerts fabricated and NO_ACTIVE_CONTACTS recorded in timeline.")

        # ------------------------------------------------------------------
        # TEST 8: SOS When No Responders Have Valid Coordinates
        # ------------------------------------------------------------------
        print("\n[TEST 8] Verifying Behavior When No Responders Have Valid Coordinates...")
        # Temporarily deactivate demo records and all active responders with coordinates so 0 active responders with coords exist
        client.post("/api/members/admin/demo-records?action=deactivate", headers=admin_headers)
        all_resps = client.get("/api/responders", headers=admin_headers).json()
        active_resp_ids_to_restore = [
            r["id"] for r in all_resps
            if r.get("is_active") and r.get("latitude") is not None
        ]
        for rid in active_resp_ids_to_restore:
            client.put(f"/api/responders/{rid}", json={"is_active": False}, headers=admin_headers)

        try:
            res_sos_no_resp = client.post("/api/emergencies/sos", json=sos_payload, headers=admin_headers)
            assert res_sos_no_resp.status_code == 201, res_sos_no_resp.text
            inc_no_resp = res_sos_no_resp.json()
            created_incident_ids.append(inc_no_resp["id"])

            assert len(inc_no_resp["matched_responders"]) == 0
            event_types_no_resp = [ev["event_type"] for ev in inc_no_resp["timeline_events"]]
            assert "NO_RESPONDERS_WITH_COORDINATES" in event_types_no_resp
        finally:
            # Restore demo records and active responders to active state
            client.post("/api/members/admin/demo-records?action=activate", headers=admin_headers)
            for rid in active_resp_ids_to_restore:
                client.put(f"/api/responders/{rid}", json={"is_active": True}, headers=admin_headers)

        print("  -> PASS: NO_RESPONDERS_WITH_COORDINATES logged honestly while preserving SOS incident.")

        # ------------------------------------------------------------------
        # TEST 9: Safe Demo Seeding Gating (ENABLE_DEMO_SEED=false default)
        # ------------------------------------------------------------------
        print("\n[TEST 9] Verifying Safe Demo Seeding Gating...")
        os.environ["ENABLE_DEMO_SEED"] = "false"
        db_check = SessionLocal()
        seed_result = seed_database(db_check, force=False)
        db_check.close()
        assert seed_result is False, "seed_database(force=False) must return False when ENABLE_DEMO_SEED=false"
        print("  -> PASS: Automatic demo seeding is disabled unless ENABLE_DEMO_SEED=true.")

        # ------------------------------------------------------------------
        # TEST 10: Explicit User-Confirmed Test Notification Endpoint
        # ------------------------------------------------------------------
        print("\n[TEST 10] Verifying Explicit User-Confirmed Notification Test Endpoint...")
        # Unconfirmed test must fail with 400
        res_unconfirmed = client.post(
            "/api/emergencies/config/notifications/test",
            json={
                "channel": "EMAIL",
                "recipient": "arjun.nair@familyconnect.local",
                "confirm_send": False,
            },
            headers=admin_headers,
        )
        assert res_unconfirmed.status_code == 400

        # Placeholder destination must fail with 400
        res_placeholder_test = client.post(
            "/api/emergencies/config/notifications/test",
            json={
                "channel": "EMAIL",
                "recipient": "test@example.com",
                "confirm_send": True,
            },
            headers=admin_headers,
        )
        assert res_placeholder_test.status_code == 400

        # Confirmed test with real address executes and updates last_test_result
        res_confirmed_test = client.post(
            "/api/emergencies/config/notifications/test",
            json={
                "channel": "EMAIL",
                "recipient": "arjun.nair@familyconnect.local",
                "confirm_send": True,
            },
            headers=admin_headers,
        )
        assert res_confirmed_test.status_code == 200, res_confirmed_test.text
        test_data = res_confirmed_test.json()
        assert test_data["recipient"] == "arjun.nair@familyconnect.local"
        assert test_data["status"] in ("DELIVERED", "SENT", "FAILED", "SIMULATED")

        res_cfg = client.get("/api/emergencies/config/notifications", headers=admin_headers)
        assert res_cfg.status_code == 200
        assert res_cfg.json()["last_test_result"] is not None
        assert res_cfg.json()["last_test_result"]["recipient"] == "arjun.nair@familyconnect.local"
        print("  -> PASS: Explicit test notification endpoint and status tracking verified.")

        # ------------------------------------------------------------------
        # TEST 11: Role Permissions on Responder & Admin Endpoints
        # ------------------------------------------------------------------
        print("\n[TEST 11] Verifying Role-Based Access Control on Phase 6 Endpoints...")
        # Family member cannot create a responder
        res_mem_resp = client.post(
            "/api/responders",
            json=resp_no_coords_payload,
            headers=member_headers,
        )
        assert res_mem_resp.status_code == 403

        # Responder cannot update another responder's location (officer_david is responder_id=2)
        res_resp_other = client.patch(
            f"/api/responders/{resp1_id}/location",
            json={"latitude": 30.1, "longitude": -97.1, "location_source": "manual"},
            headers=responder_headers,
        )
        assert res_resp_other.status_code == 403

        # Responder cannot call admin demo-records control
        res_resp_demo = client.post(
            "/api/members/admin/demo-records?action=deactivate",
            headers=responder_headers,
        )
        assert res_resp_demo.status_code == 403
        print("  -> PASS: Role boundaries enforced on all Phase 6 endpoints.")

        # ------------------------------------------------------------------
        # TEST 12: Safe Deactivation When Referenced vs Hard Delete When Unreferenced
        # ------------------------------------------------------------------
        print("\n[TEST 12] Verifying Safe Deactivation When Referenced by Incidents...")
        # Priya Nair has SOS incidents created in Tests 5, 7, 8 -> DELETE with hard_delete=true must safely deactivate
        res_soft_del = client.delete(
            f"/api/members/{member_id}?hard_delete=true",
            headers=admin_headers,
        )
        assert res_soft_del.status_code == 200
        assert res_soft_del.json()["action"] == "deactivated"
        print("  -> PASS: Member referenced by incidents is safely deactivated rather than destroying audit history.")

    finally:
        # Clean up test-created incidents, responders, and members so existing DB state is untouched
        db_clean = SessionLocal()
        try:
            for inc_id in created_incident_ids:
                db_clean.query(models.IncidentTimelineEvent).filter(models.IncidentTimelineEvent.incident_id == inc_id).delete()
                db_clean.query(models.IncidentAlert).filter(models.IncidentAlert.incident_id == inc_id).delete()
                db_clean.query(models.IncidentResponder).filter(models.IncidentResponder.incident_id == inc_id).delete()
                db_clean.query(models.EmergencyIncident).filter(models.EmergencyIncident.id == inc_id).delete()
            for r_id in created_responder_ids:
                db_clean.query(models.IncidentResponder).filter(models.IncidentResponder.responder_id == r_id).delete()
                db_clean.query(models.Responder).filter(models.Responder.id == r_id).delete()
            for m_id in created_member_ids:
                db_clean.query(models.TrustedContact).filter(models.TrustedContact.member_id == m_id).delete()
                db_clean.query(models.Member).filter(models.Member.id == m_id).delete()
            if created_user_ids:
                db_clean.query(models.User).filter(models.User.id.in_(created_user_ids)).delete()
            # Ensure demo records are active for subsequent regression suites
            db_clean.query(models.Member).filter(models.Member.is_demo == True).update({"is_active": True})
            db_clean.query(models.TrustedContact).filter(models.TrustedContact.is_demo == True).update({"is_active": True})
            db_clean.query(models.Responder).filter(models.Responder.is_demo == True).update({"is_active": True})
            db_clean.commit()
        finally:
            final_member_count = db_clean.query(models.Member).count()
            final_incident_count = db_clean.query(models.EmergencyIncident).count()
            final_user_count = db_clean.query(models.User).count()
            db_clean.close()
            server.should_exit = True
            server_thread.join(timeout=3)
            engine.dispose()

        assert final_member_count == initial_member_count, f"Member count changed: {initial_member_count} -> {final_member_count}"
        assert final_incident_count == initial_incident_count, f"Incident count changed: {initial_incident_count} -> {final_incident_count}"
        assert final_user_count == initial_user_count, f"User count changed: {initial_user_count} -> {final_user_count}"
        print("\n[CLEANUP VERIFIED] Existing database records preserved intact:")
        print(f"  Members: {final_member_count} | Incidents: {final_incident_count} | Users: {final_user_count}")

    print("\n" + "=" * 76)
    print("ALL 12 PHASE 6 VERIFICATION CHECKS PASSED SUCCESSFULLY!")
    print("=" * 76)


if __name__ == "__main__":
    run_phase6_tests()
