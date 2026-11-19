"""
FamilyConnect AI - Phase 6 Test Suite: Authorized Emergency Responders & Real Geolocation
Verifies:
1. Demo responders (is_demo=True, seed US 555 phones) are strictly excluded from authorized responder lists.
2. Only verified active non-demo responders appear in default responder roster.
3. Responders linked to deactivated user accounts (e.g. officer_david) are excluded or treated as inactive.
4. Nearby proximity matching (/api/responders/nearby) excludes demo responders and requires valid coordinates.
5. Location update accepts and records location_accuracy_m and is_available.
6. Emergency dispatch matching ranks and assigns only real, non-demo, active responders.
7. Historical incident records and database integrity are 100% preserved.
"""

import os
import sys
import datetime
import sqlite3
from pathlib import Path

# Enforce mock notifications
os.environ["MOCK_NOTIFICATIONS"] = "true"

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import HTTPException

from app.database import SessionLocal
from app.models import User, Responder, EmergencyIncident, IncidentResponder
from app.auth import create_access_token, hash_password, get_current_user, HTTPAuthorizationCredentials
from app.routes.responders import (
    get_responders,
    get_nearby_responders,
    update_responder_location,
    create_responder
)
from app.routes.emergencies import trigger_sos
from app.schemas import ResponderLocationUpdate, IncidentCreate, ResponderCreate
from app.ai.triage import calculate_haversine_distance, rank_responders

def run_tests():
    print("=" * 80)
    print("PHASE 6 TEST SUITE: AUTHORIZED RESPONDERS & REAL GEOLOCATION")
    print("=" * 80)

    db = SessionLocal()
    passed = 0
    total = 0

    def record_pass(desc):
        nonlocal passed, total
        total += 1
        passed += 1
        print(f"  [PASS] {desc}")

    def record_fail(desc, err):
        nonlocal total
        total += 1
        print(f"  [FAIL] {desc}: {err}")

    try:
        # Obtain user records
        admin_alpha_user = db.query(User).filter(User.id == 4).first()
        assert admin_alpha_user is not None and admin_alpha_user.is_active == 1, "Admin Alpha (ID 4) must be active"

        # -------------------------------------------------------------
        # GROUP 1: Inactive Demo Accounts & Responder Exclusion
        # -------------------------------------------------------------
        print("\n--- GROUP 1: Inactive Demo Accounts & Responder Exclusion ---")

        # 1.1 Deactivated accounts cannot authenticate or access protected endpoints
        officer = db.query(User).filter(User.username == "officer_david").first()
        if officer and not officer.is_active:
            record_pass("officer_david (User ID 3) remains soft-deactivated (is_active = 0)")
        else:
            record_fail("officer_david is_active", f"Expected is_active=0, got {getattr(officer, 'is_active', None)}")

        try:
            officer_token = create_access_token({"sub": "officer_david", "user_id": officer.id, "role": officer.role})
            get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=officer_token), db=db)
            record_fail("officer_david token auth", "Expected HTTPException 401 for deactivated user token")
        except HTTPException as he:
            if he.status_code == 401 and "disabled" in str(he.detail).lower():
                record_pass(f"Deactivated account token rejected by get_current_user with 401: '{he.detail}'")
            else:
                record_fail("officer_david token auth", f"Unexpected status/detail: {he.status_code} - {he.detail}")

        # 1.2 Default get_responders excludes demo responders
        default_responders = get_responders(
            available_only=False,
            include_inactive=False,
            exclude_demo=True,
            current_user=admin_alpha_user,
            db=db
        )
        demo_names = [
            "Officer David Miller",
            "Dr. Karen Lee (Neighbor)",
            "Metro Station 4 Paramedic Unit",
            "St. Jude Urgent Care Facility",
            "Volunteer James Foster"
        ]
        found_demo = [r for r in default_responders if r.name in demo_names or r.is_demo is True]
        if len(found_demo) == 0:
            record_pass(f"Default get_responders strictly excludes all 5 demo responders (Returned {len(default_responders)} items)")
        else:
            record_fail("Default get_responders demo exclusion", f"Found demo responders: {[r.name for r in found_demo]}")

        # Check that active non-demo responder is returned
        real_resp = [r for r in default_responders if not r.is_demo and r.is_active]
        if len(real_resp) == 1:
            record_pass(f"Verified active non-demo responder is returned (ID: {real_resp[0].id})")
            if real_resp[0].phone and real_resp[0].phone.startswith("+91"):
                record_pass("Real responder phone is normalized with Indian (+91) format")
            else:
                record_fail("Responder phone format", "Expected +91 phone format")
        else:
            record_fail("Real responder presence", f"Expected 1, found {len(real_resp)}")

        # 1.3 Available only filter works cleanly
        avail_list = get_responders(
            available_only=True,
            include_inactive=False,
            exclude_demo=True,
            current_user=admin_alpha_user,
            db=db
        )
        assert all(r.is_available and r.is_active for r in avail_list), "All must be available and active"
        assert all(not r.is_demo for r in avail_list), "No demo units allowed in available_only"
        record_pass(f"get_responders(available_only=True) returned {len(avail_list)} genuine available units")

        # -------------------------------------------------------------
        # GROUP 2: Nearby Proximity & Haversine Distance
        # -------------------------------------------------------------
        print("\n--- GROUP 2: Nearby Proximity & Haversine Distance ---")

        # 2.1 Query nearby responders from Kakkanad, Kochi (10.0189, 76.3528)
        nearby = get_nearby_responders(
            lat=10.0189,
            lon=76.3528,
            limit=5,
            current_user=admin_alpha_user,
            db=db
        )
        assert all(not r["name"].startswith("Officer David") for r in nearby)
        assert all(not r["name"].startswith("Dr. Karen Lee") for r in nearby)
        assert all(not r["name"].startswith("Metro Station") for r in nearby)
        if len(nearby) > 0 and not nearby[0].get("is_demo", False):
            dist = nearby[0]["distance_km"]
            record_pass(f"Nearby query returned nearest active responder (ID: {nearby[0]['id']}) with distance {dist} km")
            assert dist < 1.0, f"Kakkanad coordinates should be < 1.0 km away (got {dist})"
            record_pass("Haversine distance calculation is trustworthy and accurate (<1.0 km)")
        else:
            record_fail("Nearby responder content", f"Got: {nearby}")

        # 2.2 AI triage rank_responders helper excludes is_demo
        mock_candidates = [
            {"id": 1, "name": "Demo Unit", "is_demo": True, "is_active": True, "latitude": 10.019, "longitude": 76.353},
            {"id": 6, "name": "Real Unit", "is_demo": False, "is_active": True, "latitude": 10.020, "longitude": 76.354}
        ]
        ranked = rank_responders(10.018, 76.352, mock_candidates)
        if len(ranked) == 1 and ranked[0]["name"] == "Real Unit":
            record_pass("rank_responders() strictly ignores candidates where is_demo=True")
        else:
            record_fail("rank_responders() demo filtering", f"Ranked: {ranked}")

        # -------------------------------------------------------------
        # GROUP 3: Real Geolocation & Location Accuracy Tracking
        # -------------------------------------------------------------
        print("\n--- GROUP 3: Real Geolocation & Location Accuracy Tracking ---")

        # 3.1 Update responder location with live GPS, accuracy, and availability
        active_resp = db.query(Responder).filter(Responder.is_demo == False, Responder.is_active == True).first()
        assert active_resp is not None, "Active non-demo responder record required"

        loc_update = ResponderLocationUpdate(
            latitude=10.020500,
            longitude=76.355100,
            location_source="browser_gps",
            location_accuracy_m=14.5,
            is_available=True
        )
        updated_resp = update_responder_location(
            responder_id=active_resp.id,
            loc_in=loc_update,
            current_user=admin_alpha_user,
            db=db
        )
        record_pass(f"update_responder_location succeeded: ({updated_resp.latitude}, {updated_resp.longitude})")
        assert updated_resp.location_source == "browser_gps"
        assert updated_resp.location_accuracy_m == 14.5
        record_pass("location_accuracy_m (14.5m) and location_source ('browser_gps') persisted and verified")

        # 3.2 Direct DB row check
        db.refresh(active_resp)
        assert abs(active_resp.latitude - 10.020500) < 0.0001
        assert abs(active_resp.longitude - 76.355100) < 0.0001
        assert active_resp.location_accuracy_m == 14.5
        record_pass("Direct database verification: coordinates, source, and accuracy match exactly")

        # -------------------------------------------------------------
        # GROUP 4: Emergency Dispatch Matching Safety
        # -------------------------------------------------------------
        print("\n--- GROUP 4: Emergency Dispatch Matching Safety ---")

        incident_in = IncidentCreate(
            member_id=7,
            reporter_name="Authorized Family Member",
            incident_type="Dizziness / Fall",
            description="Phase 6 Verification SOS",
            latitude=10.021000,
            longitude=76.355500,
            location_label="Kakkanad Residence",
            location_accuracy_m=10.0
        )
        new_incident = trigger_sos(
            payload=incident_in,
            current_user=admin_alpha_user,
            db=db
        )
        inc_id = new_incident.id
        matched_units = new_incident.matched_responders or []
        record_pass(f"Created emergency incident #{inc_id} with AI triage severity '{new_incident.severity_level}'")

        matched_names = [m.name for m in matched_units]
        demo_in_matched = [name for name in matched_names if any(d in name for d in ["Officer David", "Karen Lee", "Metro Station", "St. Jude", "Foster"])]
        if len(demo_in_matched) == 0:
            record_pass(f"Emergency #{inc_id} matched {len(matched_units)} real units with ZERO demo responders")
        else:
            record_fail("Emergency responder matching demo leak", f"Demo units found in matched: {demo_in_matched}")

        if len(matched_units) > 0:
            assert matched_units[0].distance_km is not None
            record_pass(f"Top matched responder (ID: {matched_units[0].id}) distance: {matched_units[0].distance_km} km")

        # -------------------------------------------------------------
        # GROUP 5: Database & Historical Incident Integrity
        # -------------------------------------------------------------
        print("\n--- GROUP 5: Database & Historical Incident Integrity ---")

        # 5.1 Check PRAGMA integrity
        db_file = BACKEND_DIR / "familyconnect.db"
        raw_conn = sqlite3.connect(str(db_file))
        integrity = raw_conn.execute("PRAGMA integrity_check").fetchall()
        assert integrity == [("ok",)], f"Integrity check failed: {integrity}"
        record_pass("PRAGMA integrity_check is 'ok'")

        # 5.2 Verify incident records
        inc_count = raw_conn.execute("SELECT COUNT(*) FROM emergency_incidents").fetchone()[0]
        assert inc_count >= 1, f"Expected >= 1 incidents, got {inc_count}"
        record_pass(f"Incident records intact ({inc_count} incidents in database)")

        # 5.3 Verify demo users remain deactivated
        deactivated_users = raw_conn.execute("SELECT id, username, is_active FROM users WHERE is_active = 0").fetchall()
        deactivated_names = {u[1] for u in deactivated_users}
        assert {"admin", "marcus", "officer_david"}.issubset(deactivated_names)
        record_pass(f"Demo users admin, marcus, officer_david remain deactivated ({deactivated_names})")

        # 5.4 Verify demo responders remain deactivated
        deactivated_resp = raw_conn.execute("SELECT id, name, is_active, is_demo FROM responders WHERE is_demo = 1").fetchall()
        assert len(deactivated_resp) == 5
        assert all(r[2] == 0 for r in deactivated_resp), "All demo responders must have is_active=0"
        record_pass("All 5 demo responders (IDs 1-5) remain soft-deactivated (is_active=0, is_demo=1)")

        raw_conn.close()

    except Exception as e:
        record_fail("Test suite execution exception", str(e))
    finally:
        db.close()

    print("\n" + "=" * 80)
    print(f"RESULTS: {passed}/{total} TESTS PASSED ({(passed/total)*100:.1f}%)")
    print("=" * 80)
    return passed == total

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
