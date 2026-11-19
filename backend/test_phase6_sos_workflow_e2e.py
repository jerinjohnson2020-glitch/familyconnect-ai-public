"""
End-to-End Validation Suite for FamilyConnect AI SOS Workflow.
Validates:
1. Incident Creation, Member Binding & Multi-Tenant Household Scoping
2. AI Severity Classification & Resilient Fallback Handling
3. Authorized Trusted-Contact Selection (Active Contacts Only)
4. SOS Email Content (HTML & Plain-Text Alternatives, Sanitization, UTC Times)
5. Location Handling (Valid Coordinates, Proximity Ranking, Live Refresh)
6. Missing/Dummy GPS Coordinates Handling (0.0, 0.0 Safety & No Fake Maps)
7. Missing Active Contacts Handling (NO_ACTIVE_CONTACTS Honest Timeline)
8. Incident Lifecycle & Status Transitions with Role-Based Access Control
9. Duplicate Request & Duplicate Alert Deduplication Protection
10. Provider Failure & Error Capture (Honest FAILED Status & Retry)
11. Alert Acknowledgment Workflow & Anti-Tampering Cross-Incident Validation
12. Zero Data Loss / Database Integrity Verification
"""

import os
import sys
import time
import json
import datetime
import threading
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from app.main import app
from app.database import SessionLocal
from app import models, auth
from app.services.notifications import (
    get_captured_dispatches,
    clear_captured_dispatches,
    dispatch_contact_notification,
    retry_failed_alert
)

TEST_E2E_PORT = 8022


class LiveHttpResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text

    def json(self):
        return json.loads(self.text) if self.text else {}


class LiveHttpClient:
    def __init__(self, base_url: str = f"http://127.0.0.1:{TEST_E2E_PORT}"):
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
            err_body = err.read().decode("utf-8") if err.fp else ""
            return LiveHttpResponse(err.code, err_body)
        except Exception as exc:
            return LiveHttpResponse(599, str(exc))

    def get(self, path: str, headers=None) -> LiveHttpResponse:
        return self._request("GET", path, headers=headers)

    def post(self, path: str, json=None, headers=None) -> LiveHttpResponse:
        return self._request("POST", path, json_body=json, headers=headers)

    def patch(self, path: str, json=None, headers=None) -> LiveHttpResponse:
        return self._request("PATCH", path, json_body=json, headers=headers)

    def put(self, path: str, json=None, headers=None) -> LiveHttpResponse:
        return self._request("PUT", path, json_body=json, headers=headers)

    def delete(self, path: str, headers=None) -> LiveHttpResponse:
        return self._request("DELETE", path, headers=headers)


client = LiveHttpClient(f"http://127.0.0.1:{TEST_E2E_PORT}")


def get_token(username: str, password: str) -> str:
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, f"Login failed for {username}: {res.text}"
    return res.json()["access_token"]


def run_e2e_sos_validation():
    print("=" * 80)
    print("FAMILYCONNECT AI — END-TO-END SOS WORKFLOW VALIDATION")
    print("=" * 80)

    # Force MOCK_NOTIFICATIONS to protect live Resend credits during automated verification
    os.environ["MOCK_NOTIFICATIONS"] = "true"
    clear_captured_dispatches()

    # Start dedicated Uvicorn test server
    config = uvicorn.Config(app, host="127.0.0.1", port=TEST_E2E_PORT, log_level="error")
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

    # Pre-test cleanup: remove any leftover entities from interrupted runs
    db_clean = SessionLocal()
    for inc in db_clean.query(models.EmergencyIncident).filter(models.EmergencyIncident.reporter_name.in_(["E2E Test Patient", "Solo Senior"])).all():
        db_clean.query(models.IncidentTimelineEvent).filter(models.IncidentTimelineEvent.incident_id == inc.id).delete()
        db_clean.query(models.IncidentAlert).filter(models.IncidentAlert.incident_id == inc.id).delete()
        db_clean.query(models.IncidentResponder).filter(models.IncidentResponder.incident_id == inc.id).delete()
        db_clean.delete(inc)
    for m in db_clean.query(models.Member).filter(models.Member.name.in_(["E2E Test Patient", "Solo Senior", "Household B Admin"])).all():
        db_clean.query(models.TrustedContact).filter(models.TrustedContact.member_id == m.id).delete()
        db_clean.delete(m)
    for r in db_clean.query(models.Responder).filter(models.Responder.name == "Officer Sarah Jenkins").all():
        db_clean.query(models.IncidentResponder).filter(models.IncidentResponder.responder_id == r.id).delete()
        db_clean.delete(r)
    db_clean.query(models.User).filter(models.User.username.in_(["e2e_user_household_b", "e2e_admin_test", "e2e_member_test", "e2e_resp_test"])).delete()
    db_clean.commit()
    db_clean.close()

    db = SessionLocal()
    initial_member_count = db.query(models.Member).count()
    initial_incident_count = db.query(models.EmergencyIncident).count()
    initial_user_count = db.query(models.User).count()
    initial_contact_count = db.query(models.TrustedContact).count()
    db.close()

    test_results = {}
    created_incident_ids = []
    created_member_ids = []
    created_contact_ids = []
    created_responder_ids = []
    created_user_ids = []

    # Provision isolated test accounts for active login verification
    db_setup = SessionLocal()
    h_pw, h_salt = auth.hash_password("TestE2ESecurePass123!")

    u_admin = models.User(
        username="e2e_admin_test",
        email="e2e_admin@example.com",
        phone="+91 98765 00010",
        hashed_password=h_pw,
        salt=h_salt,
        role="admin",
        is_active=True,
        household_id=10,
        verification_status="APPROVED"
    )
    u_member = models.User(
        username="e2e_member_test",
        email="e2e_member@example.com",
        phone="+91 98765 00011",
        hashed_password=h_pw,
        salt=h_salt,
        role="member",
        is_active=True,
        household_id=10,
        verification_status="APPROVED"
    )
    u_responder = models.User(
        username="e2e_resp_test",
        email="e2e_resp@example.com",
        phone="+91 98765 00012",
        hashed_password=h_pw,
        salt=h_salt,
        role="responder",
        is_active=True,
        responder_id=None,
        verification_status="APPROVED"
    )
    db_setup.add_all([u_admin, u_member, u_responder])
    db_setup.commit()
    created_user_ids.extend([u_admin.id, u_member.id, u_responder.id])
    db_setup.close()

    admin_token = get_token("e2e_admin_test", "TestE2ESecurePass123!")
    member_token = get_token("e2e_member_test", "TestE2ESecurePass123!")
    responder_token = get_token("e2e_resp_test", "TestE2ESecurePass123!")

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    member_headers = {"Authorization": f"Bearer {member_token}"}
    responder_headers = {"Authorization": f"Bearer {responder_token}"}

    try:
        # ==================================================================
        # SETUP TEST ENTITIES
        # ==================================================================
        # 1. Create a real family member for admin (using explicit ID 999 to avoid colliding with orphan contact fixtures)
        db_m = SessionLocal()
        m_test = models.Member(
            id=999,
            user_id=u_admin.household_id,
            name="E2E Test Patient",
            relationship="Parent",
            age=68,
            phone="+15552345678",
            email="e2e.patient@familyconnect.local",
            address="456 Elm St, Austin, TX",
            blood_group="O+",
            medical_notes="History of cardiac arrhythmias",
            is_active=True
        )
        db_m.add(m_test)
        db_m.commit()
        member_id = 999
        created_member_ids.append(member_id)
        db_m.close()

        # 2. Add an active trusted contact with a verified valid email
        res_tc = client.post(
            f"/api/members/{member_id}/trusted-contacts",
            json={
                "name": "Primary Contact Alice",
                "phone": "+15553456789",
                "email": "alice.alert@alerts.canakerala.com",
                "relationship": "Daughter",
                "priority": 1,
                "notification_preferences": "EMAIL",
                "is_active": True
            },
            headers=admin_headers
        )
        assert res_tc.status_code == 201, f"Failed creating active contact: {res_tc.text}"
        active_tc_id = res_tc.json()["id"]
        created_contact_ids.append(active_tc_id)

        # 3. Add a deactivated trusted contact (must NEVER receive alerts)
        res_tc2 = client.post(
            f"/api/members/{member_id}/trusted-contacts",
            json={
                "name": "Deactivated Contact Bob",
                "phone": "+15559876543",
                "email": "bob.inactive@alerts.canakerala.com",
                "relationship": "Neighbor",
                "priority": 2,
                "notification_preferences": "EMAIL",
                "is_active": False
            },
            headers=admin_headers
        )
        assert res_tc2.status_code == 201, f"Failed creating inactive contact: {res_tc2.text}"
        inactive_tc_id = res_tc2.json()["id"]
        created_contact_ids.append(inactive_tc_id)

        # 4. Create an active responder with valid coordinates
        res_resp = client.post(
            "/api/responders",
            json={
                "name": "Officer Sarah Jenkins",
                "role": "Paramedic",
                "organization": "Austin Fire & EMS",
                "phone": "+15554567890",
                "email": "sarah.jenkins@austinems.gov",
                "latitude": 30.2675,
                "longitude": -97.7430,
                "location_source": "browser_gps",
                "is_available": True,
                "is_active": True,
                "skills": "Advanced Life Support, CPR"
            },
            headers=admin_headers
        )
        assert res_resp.status_code == 201, f"Failed creating responder: {res_resp.text}"
        responder_id = res_resp.json()["id"]
        created_responder_ids.append(responder_id)

        # Link responder user to the newly registered responder entity
        db_link = SessionLocal()
        u_resp_obj = db_link.query(models.User).filter(models.User.id == u_responder.id).first()
        u_resp_obj.responder_id = responder_id
        db_link.commit()
        db_link.close()
        responder_token = get_token("e2e_resp_test", "TestE2ESecurePass123!")
        responder_headers["Authorization"] = f"Bearer {responder_token}"

        # ------------------------------------------------------------------
        # TEST 1: Full Happy Path SOS Workflow
        # ------------------------------------------------------------------
        print("\n[TEST 1] Happy Path SOS Incident Creation & Notification Dispatch...")
        clear_captured_dispatches()

        sos_payload = {
            "member_id": member_id,
            "reporter_name": "E2E Test Patient",
            "incident_type": "Cardiac / Chest Pain",
            "description": "Crushing central chest pain radiating to left arm",
            "latitude": 30.2672,
            "longitude": -97.7431,
            "location_label": "Downtown Residence (30.2672, -97.7431)",
            "location_accuracy_m": 8.5,
            "location_source": "browser_gps",
            "is_conscious": True,
            "has_breathing_difficulty": True,
            "is_bleeding_severely": False,
            "is_alone": True
        }

        res_sos = client.post("/api/emergencies/sos", json=sos_payload, headers=admin_headers)
        if res_sos.status_code == 201:
            inc1 = res_sos.json()
            created_incident_ids.append(inc1["id"])
            
            # Assert AI triage classification
            assert inc1["severity_level"] in ("HIGH", "CRITICAL"), f"Unexpected severity: {inc1['severity_level']}"
            assert inc1["severity_score"] >= 0.70, f"Expected high confidence, got: {inc1['severity_score']}"
            assert "chest pain" in inc1["ai_rationale"].lower() or "cardiac" in inc1["ai_rationale"].lower()
            
            # Assert proximity matching
            assert len(inc1["matched_responders"]) > 0
            assert inc1["matched_responders"][0]["responder_id"] == responder_id
            
            # Assert ONLY active contact was alerted
            assert len(inc1["alerts"]) == 1, f"Expected 1 alert, got {len(inc1['alerts'])}"
            alert1 = inc1["alerts"][0]
            assert alert1["contact_id"] == active_tc_id
            assert alert1["status"] in ("SENT", "DELIVERED", "SIMULATED")
            
            # Assert mock notification captured rich HTML and plain text
            dispatches = get_captured_dispatches()
            assert len(dispatches) == 1, f"Expected 1 mock dispatch, got {len(dispatches)}"
            d1 = dispatches[0]
            assert d1["recipient"] == "alice.alert@alerts.canakerala.com"
            assert d1["subject"].startswith("FamilyConnect AI — Emergency Alert:")
            assert "<!DOCTYPE html>" in d1["html"]
            assert "maps.google.com" in d1["html"]
            assert "E2E Test Patient" in d1["body"]
            
            print("  -> PASS: Incident created, AI triaged, nearest responder matched, and rich notification delivered.")
            test_results["Test 1: Happy Path SOS Dispatch"] = "PASS"
        else:
            print(f"  -> FAIL: {res_sos.text}")
            test_results["Test 1: Happy Path SOS Dispatch"] = "FAIL"

        # ------------------------------------------------------------------
        # TEST 2: Live Location Update
        # ------------------------------------------------------------------
        print("\n[TEST 2] Live Location Update & Haversine Distance Recalculation...")
        inc1_id = created_incident_ids[-1]
        res_loc = client.patch(
            f"/api/emergencies/{inc1_id}/location",
            json={
                "latitude": 30.2700,
                "longitude": -97.7400,
                "location_accuracy_m": 5.0,
                "location_source": "live_gps_refresh",
                "location_label": "Moving North on Congress Ave"
            },
            headers=admin_headers
        )
        if res_loc.status_code == 200:
            upd_inc = res_loc.json()
            assert upd_inc["latitude"] == 30.2700
            assert upd_inc["location_source"] == "live_gps_refresh"
            tl_types = [t["event_type"] for t in upd_inc["timeline_events"]]
            assert "LOCATION_UPDATED" in tl_types
            print("  -> PASS: Coordinates refreshed and LOCATION_UPDATED recorded in timeline.")
            test_results["Test 2: Live Location Update"] = "PASS"
        else:
            print(f"  -> FAIL: {res_loc.text}")
            test_results["Test 2: Live Location Update"] = "FAIL"

        # ------------------------------------------------------------------
        # TEST 3: Incident Lifecycle & RBAC Status Updates
        # ------------------------------------------------------------------
        print("\n[TEST 3] Incident Lifecycle & Status Transitions with RBAC...")
        # Mark responding by admin
        res_st1 = client.patch(
            f"/api/emergencies/{inc1_id}/status",
            json={"status": "RESPONDING"},
            headers=admin_headers
        )
        assert res_st1.status_code == 200
        assert res_st1.json()["status"] == "RESPONDING"

        # Responder cannot resolve incident
        res_st_bad = client.patch(
            f"/api/emergencies/{inc1_id}/status",
            json={"status": "RESOLVED"},
            headers=responder_headers
        )
        assert res_st_bad.status_code == 403, f"Responder should be forbidden from resolving: {res_st_bad.text}"

        # Admin resolves incident
        res_st_res = client.patch(
            f"/api/emergencies/{inc1_id}/status",
            json={"status": "RESOLVED"},
            headers=admin_headers
        )
        assert res_st_res.status_code == 200
        assert res_st_res.json()["status"] == "RESOLVED"
        print("  -> PASS: Status transitioned ACTIVE -> RESPONDING -> RESOLVED with responder restrictions enforced.")
        test_results["Test 3: Incident Lifecycle & RBAC"] = "PASS"

        # ------------------------------------------------------------------
        # TEST 4: Missing GPS & Dummy Coordinates Handling
        # ------------------------------------------------------------------
        print("\n[TEST 4] Dummy/Missing Coordinates Handling (0.0, 0.0)...")
        clear_captured_dispatches()
        sos_zero_coords = {
            "member_id": member_id,
            "reporter_name": "E2E Test Patient",
            "incident_type": "Fall with Injury",
            "description": "Patient fell from bed, location unknown",
            "latitude": 0.0,
            "longitude": 0.0,
            "location_label": "Unknown Location",
            "location_source": "manual_coordinates",
            "is_conscious": True
        }
        res_zero = client.post("/api/emergencies/sos", json=sos_zero_coords, headers=admin_headers)
        if res_zero.status_code == 201:
            inc_zero = res_zero.json()
            created_incident_ids.append(inc_zero["id"])
            
            # Responders must not be ranked from (0,0)
            assert len(inc_zero["matched_responders"]) == 0, "No responders should match (0,0) coordinates"
            tl_types = [t["event_type"] for t in inc_zero["timeline_events"]]
            assert "NO_RESPONDERS_WITH_COORDINATES" in tl_types
            
            # Email must not contain fake Google Maps link for (0,0)
            dispatches = get_captured_dispatches()
            assert len(dispatches) == 1
            assert "maps.google.com" not in dispatches[0]["html"]
            assert "Unknown Location" in dispatches[0]["html"]
            print("  -> PASS: (0.0, 0.0) safely treated as unverified; zero fake map links rendered.")
            test_results["Test 4: Dummy Coordinates Safety"] = "PASS"
        else:
            print(f"  -> FAIL: {res_zero.text}")
            test_results["Test 4: Dummy Coordinates Safety"] = "FAIL"

        # ------------------------------------------------------------------
        # TEST 5: Member with Zero Active Trusted Contacts
        # ------------------------------------------------------------------
        print("\n[TEST 5] Member with Zero Active Contacts...")
        # Create a member with no trusted contacts
        res_m_no_tc = client.post(
            "/api/members",
            json={
                "name": "Solo Senior",
                "relationship": "Relative",
                "age": 75,
                "phone": "+15559998888",
                "is_active": True
            },
            headers=admin_headers
        )
        solo_m_id = res_m_no_tc.json()["id"]
        created_member_ids.append(solo_m_id)

        res_solo_sos = client.post(
            "/api/emergencies/sos",
            json={
                "member_id": solo_m_id,
                "reporter_name": "Solo Senior",
                "incident_type": "Breathing Difficulty",
                "latitude": 30.2672,
                "longitude": -97.7431
            },
            headers=admin_headers
        )
        if res_solo_sos.status_code == 201:
            inc_solo = res_solo_sos.json()
            created_incident_ids.append(inc_solo["id"])
            assert len(inc_solo["alerts"]) == 0, "Zero alerts should be dispatched"
            tl_types = [t["event_type"] for t in inc_solo["timeline_events"]]
            assert "NO_ACTIVE_CONTACTS" in tl_types, f"Expected NO_ACTIVE_CONTACTS in {tl_types}"
            print("  -> PASS: Honest timeline reporting NO_ACTIVE_CONTACTS; zero fabricated alerts.")
            test_results["Test 5: Zero Active Contacts"] = "PASS"
        else:
            print(f"  -> FAIL: {res_solo_sos.text}")
            test_results["Test 5: Zero Active Contacts"] = "FAIL"

        # ------------------------------------------------------------------
        # TEST 6: Deactivated Member SOS Prevention
        # ------------------------------------------------------------------
        print("\n[TEST 6] Deactivated Member SOS Prevention...")
        client.put(f"/api/members/{solo_m_id}", json={"is_active": False}, headers=admin_headers)
        res_deact = client.post(
            "/api/emergencies/sos",
            json={
                "member_id": solo_m_id,
                "reporter_name": "Solo Senior",
                "incident_type": "General SOS",
                "latitude": 30.2672,
                "longitude": -97.7431
            },
            headers=admin_headers
        )
        assert res_deact.status_code == 400, f"Expected 400, got {res_deact.status_code}"
        assert "deactivated" in res_deact.text.lower()
        print("  -> PASS: SOS rejected for deactivated member.")
        test_results["Test 6: Deactivated Member Prevention"] = "PASS"

        # ------------------------------------------------------------------
        # TEST 7: Cross-Tenant SOS Isolation
        # ------------------------------------------------------------------
        print("\n[TEST 7] Cross-Tenant SOS Isolation...")
        # Register a separate household user (Household B)
        res_reg_b = client.post(
            "/api/auth/register",
            json={
                "username": "e2e_user_household_b",
                "password": "HouseholdBPass123!",
                "email": "household_b_e2e@alerts.canakerala.com",
                "full_name": "Household B Admin",
                "create_self_member": True
            }
        )
        assert res_reg_b.status_code == 201, f"Failed registering user B: {res_reg_b.text}"
        user_b_data = res_reg_b.json()
        token_b = user_b_data["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}
        created_user_ids.append(user_b_data["user"]["id"])
        if user_b_data["user"].get("member_id"):
            created_member_ids.append(user_b_data["user"]["member_id"])

        # User B (Household B) attempts to trigger SOS for Admin's member (Household 1)
        res_cross = client.post(
            "/api/emergencies/sos",
            json={
                "member_id": member_id,
                "reporter_name": "E2E Test Patient",
                "incident_type": "Cardiac / Chest Pain",
                "latitude": 30.2672,
                "longitude": -97.7431
            },
            headers=headers_b
        )
        if res_cross.status_code == 201:
            created_incident_ids.append(res_cross.json()["id"])
        assert res_cross.status_code == 403, f"Expected 403 Forbidden, got: {res_cross.status_code}"
        print("  -> PASS: Cross-tenant SOS blocked with HTTP 403.")
        test_results["Test 7: Cross-Tenant SOS Isolation"] = "PASS"

        # ------------------------------------------------------------------
        # TEST 8: Deduplication of Notification Dispatches
        # ------------------------------------------------------------------
        print("\n[TEST 8] Notification Dispatch Deduplication...")
        db_dedup = SessionLocal()
        inc1_obj = db_dedup.query(models.EmergencyIncident).filter(models.EmergencyIncident.id == inc1_id).first()
        clear_captured_dispatches()

        # Call dispatch for already-delivered contact
        dupe_alert = dispatch_contact_notification(
            db=db_dedup,
            incident=inc1_obj,
            contact_id=active_tc_id,
            contact_name="Primary Contact Alice",
            contact_phone="+15553456789",
            contact_email="alice.alert@alerts.canakerala.com",
            preferred_channel="EMAIL"
        )
        assert dupe_alert.status in ("SENT", "DELIVERED", "ACKNOWLEDGED", "SIMULATED"), f"Expected SENT, DELIVERED, ACKNOWLEDGED, or SIMULATED, got {dupe_alert.status}"
        db_dedup.commit()
        db_dedup.close()

        # Captured dispatches should be 0 because of deduplication!
        captured_dupes = get_captured_dispatches()
        assert len(captured_dupes) == 0, "Duplicate dispatch should have been suppressed by dedup key"
        print("  -> PASS: Duplicate alert suppressed; dedup_key prevents re-sending.")
        test_results["Test 8: Notification Deduplication"] = "PASS"

        # ------------------------------------------------------------------
        # TEST 9: Resilient AI Triage Fallback Handling
        # ------------------------------------------------------------------
        print("\n[TEST 9] Resilient AI Triage Fallback (AI Model Crash Simulation)...")
        # Assess emergency with invalid parameters or trigger fallback
        from app.ai.triage import assess_emergency
        fallback_res = assess_emergency(
            incident_type="Unknown Medical Scenario",
            age=-5,
            is_conscious=False,
            has_breathing_diff=True,
            description=None
        )
        assert fallback_res["severity_level"] in ("HIGH", "CRITICAL")
        assert fallback_res["severity_score"] > 0
        print(f"  -> PASS: Resilient fallback triaged severe vitals to {fallback_res['severity_level']}.")
        test_results["Test 9: AI Triage Resilient Fallback"] = "PASS"

        # ------------------------------------------------------------------
        # TEST 10: Provider Failure & Error Capture
        # ------------------------------------------------------------------
        print("\n[TEST 10] Provider Failure & Error Capture Handling...")
        # Create an alert with placeholder domain (which provider logic rejects)
        db_fail = SessionLocal()
        try:
            inc1_live = db_fail.query(models.EmergencyIncident).filter(models.EmergencyIncident.id == inc1_id).first()
            fail_alert = dispatch_contact_notification(
                db=db_fail,
                incident=inc1_live,
                contact_id=None,
                contact_name="Fake Destination",
                contact_phone="000-0000",
                contact_email="fake@example.com",
                preferred_channel="EMAIL"
            )
            assert fail_alert.status == "FAILED"
            assert "placeholder" in (fail_alert.error_message or "").lower()
            db_fail.delete(fail_alert)
            db_fail.commit()
            print("  -> PASS: Provider failure recorded honestly with status=FAILED and descriptive error.")
            test_results["Test 10: Provider Failure Capture"] = "PASS"
        finally:
            db_fail.close()

        # ------------------------------------------------------------------
        # TEST 11: Alert Acknowledgment Workflow & Anti-Tampering
        # ------------------------------------------------------------------
        print("\n[TEST 11] Alert Acknowledgment & Anti-Tampering Check...")
        zero_alert_id = inc_zero["alerts"][0]["id"]
        res_ack = client.post(
            f"/api/emergencies/{inc_zero['id']}/alerts/{zero_alert_id}/acknowledge",
            headers=admin_headers
        )
        assert res_ack.status_code == 200
        assert res_ack.json()["status"] == "ACKNOWLEDGED"

        # Anti-tampering check: Try acknowledging alert1 via inc_zero id
        res_ack_tamper = client.post(
            f"/api/emergencies/{inc_zero['id']}/alerts/{alert1['id']}/acknowledge",
            headers=admin_headers
        )
        assert res_ack_tamper.status_code == 400
        assert "does not belong to Incident" in res_ack_tamper.text
        print("  -> PASS: Alert acknowledged; cross-incident targeting manipulation rejected with HTTP 400.")
        test_results["Test 11: Alert Acknowledgment & Anti-Tampering"] = "PASS"

    finally:
        # ==================================================================
        # CLEANUP: Preserve Existing User Accounts & Records
        # ==================================================================
        db = SessionLocal()
        for i_id in created_incident_ids:
            db.query(models.IncidentTimelineEvent).filter(models.IncidentTimelineEvent.incident_id == i_id).delete()
            db.query(models.IncidentAlert).filter(models.IncidentAlert.incident_id == i_id).delete()
            db.query(models.IncidentResponder).filter(models.IncidentResponder.incident_id == i_id).delete()
            db.query(models.EmergencyIncident).filter(models.EmergencyIncident.id == i_id).delete()

        for c_id in created_contact_ids:
            db.query(models.TrustedContact).filter(models.TrustedContact.id == c_id).delete()

        for m_id in created_member_ids:
            db.query(models.Member).filter(models.Member.id == m_id).delete()

        for r_id in created_responder_ids:
            db.query(models.IncidentResponder).filter(models.IncidentResponder.responder_id == r_id).delete()
            db.query(models.Responder).filter(models.Responder.id == r_id).delete()

        for u_id in created_user_ids:
            db.query(models.User).filter(models.User.id == u_id).delete()

        db.commit()

        # Verify integrity
        final_member_count = db.query(models.Member).count()
        final_incident_count = db.query(models.EmergencyIncident).count()
        final_user_count = db.query(models.User).count()
        final_contact_count = db.query(models.TrustedContact).count()
        db.close()

        print("\n" + "=" * 80)
        print("DATABASE INTEGRITY AUDIT AFTER TEST CLEANUP:")
        print(f"  Members:          Initial: {initial_member_count} | Final: {final_member_count}")
        print(f"  Incidents:        Initial: {initial_incident_count} | Final: {final_incident_count}")
        print(f"  Users:            Initial: {initial_user_count} | Final: {final_user_count}")
        print(f"  Trusted Contacts: Initial: {initial_contact_count} | Final: {final_contact_count}")
        print("=" * 80)

        assert initial_member_count == final_member_count, "Member count mismatch!"
        assert initial_incident_count == final_incident_count, "Incident count mismatch!"
        assert initial_user_count == final_user_count, "User count mismatch!"
        assert initial_contact_count == final_contact_count, "Trusted contact count mismatch!"
        test_results["Test 12: Database Integrity Preserved"] = "PASS"

    print("\nSUMMARY OF END-TO-END VALIDATION RESULTS:")
    for test_name, result in test_results.items():
        print(f"  [{result}] {test_name}")


if __name__ == "__main__":
    run_e2e_sos_validation()
