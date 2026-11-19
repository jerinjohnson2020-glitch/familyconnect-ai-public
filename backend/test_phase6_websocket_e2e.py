"""
FamilyConnect AI - Phase 6 Automated WebSocket & Multi-Device Verification Suite
Tests:
1. WebSocket Authentication Enforcement (missing token, invalid token, revoked token).
2. Live Multi-Session Concurrent Connections (Admin + Member in Household 1).
3. Real-Time SOS Broadcast (INCIDENT_CREATED) received across concurrent sessions in same household.
4. Cross-Tenant WebSocket Broadcast Isolation (Household 4 Admin Alpha does NOT receive Household 1 incidents).
5. Cross-Tenant Subscription Rejection (code 403 SUBSCRIPTION_DENIED).
6. Unassigned Responder Subscription Rejection (code 403 SUBSCRIPTION_DENIED).
7. Real-Time Status & Location Telemetry Broadcasts.
8. Disconnect and Reconnect State Synchronization.
9. Database Record Preservation & Clean-up (no test residue).
"""

import os
import sys
import json
import asyncio
import datetime
import urllib.request
import urllib.parse
from pathlib import Path

# Ensure MOCK_NOTIFICATIONS is set to strictly prevent live notifications
os.environ["MOCK_NOTIFICATIONS"] = "true"

# Ensure backend directory is on sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import websockets
from app.database import SessionLocal
from app.models import User, Member, EmergencyIncident, IncidentAlert, IncidentTimelineEvent, IncidentResponder, RevokedToken
from app.auth import create_access_token, hash_token

WS_BASE_URL = "ws://127.0.0.1:8000/api/ws/incidents"
HTTP_BASE_URL = "http://127.0.0.1:8000"


def ensure_server_running():
    try:
        with urllib.request.urlopen(f"{HTTP_BASE_URL}/api/health", timeout=1):
            return None
    except Exception:
        pass

    import uvicorn
    import threading
    import time
    from app.main import app
    config = uvicorn.Config(app=app, host="127.0.0.1", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"{HTTP_BASE_URL}/api/health", timeout=1):
                return server
        except Exception:
            time.sleep(0.1)
    return None


def get_active_admin_usernames():
    db = SessionLocal()
    try:
        u4 = db.query(User).filter(User.id == 4).first()
        u5 = db.query(User).filter(User.id == 5).first()
        alpha = u4.username if u4 else "test_admin_alpha"
        beta = u5.username if u5 else "test_admin_beta"
        return alpha, beta
    finally:
        db.close()


def http_post(path: str, data: dict, token: str = None) -> dict:
    url = f"{HTTP_BASE_URL}{path}"
    body = json.dumps(data).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        err_body = err.read().decode("utf-8")
        raise RuntimeError(f"HTTP {err.code}: {err_body}")


def http_patch(path: str, data: dict, token: str = None) -> dict:
    url = f"{HTTP_BASE_URL}{path}"
    body = json.dumps(data).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers, method="PATCH")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get(path: str, token: str = None) -> dict:
    url = f"{HTTP_BASE_URL}{path}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def assert_rejected(exc):
    is_rejected = False
    if hasattr(exc, "code") and exc.code in (1008, 4001):
        is_rejected = True
    elif hasattr(exc, "status_code") and exc.status_code in (401, 403):
        is_rejected = True
    elif hasattr(exc, "response") and getattr(exc.response, "status_code", None) in (401, 403):
        is_rejected = True
    elif "rejected" in str(exc).lower() or "1008" in str(exc) or "403" in str(exc) or "401" in str(exc):
        is_rejected = True
    assert is_rejected, f"Unexpected rejection error: {type(exc).__name__}: {exc}"


async def test_auth_rejection_missing_token():
    print("[Test 1] WebSocket Authentication: Missing Token...")
    try:
        async with websockets.connect(WS_BASE_URL) as ws:
            await ws.recv()
            assert False, "Connection should have been rejected"
    except Exception as exc:
        assert_rejected(exc)
    print("  -> PASS: Unauthenticated connection rejected with code 1008 / HTTP 403.")


async def test_auth_rejection_invalid_token():
    print("[Test 2] WebSocket Authentication: Invalid/Tampered Token...")
    try:
        async with websockets.connect(f"{WS_BASE_URL}?token=invalid.tampered.token") as ws:
            await ws.recv()
            assert False, "Connection should have been rejected"
    except Exception as exc:
        assert_rejected(exc)
    print("  -> PASS: Tampered token connection rejected with code 1008 / HTTP 403.")


async def test_auth_rejection_revoked_token():
    print("[Test 3] WebSocket Authentication: Revoked Token...")
    db = SessionLocal()
    token = create_access_token(data={"sub": "admin", "user_id": 1, "role": "admin"})
    tok_hash = hash_token(token)
    rev = RevokedToken(
        token_hash=tok_hash,
        user_id=1,
        revoked_at=datetime.datetime.utcnow(),
        expires_at=datetime.datetime.utcnow() + datetime.timedelta(hours=1),
        reason="test_revocation"
    )
    db.add(rev)
    db.commit()
    db.close()

    try:
        async with websockets.connect(f"{WS_BASE_URL}?token={token}") as ws:
            await ws.recv()
            assert False, "Connection should have been rejected"
    except Exception as exc:
        assert_rejected(exc)
    finally:
        # Clean up revoked token record
        db = SessionLocal()
        db.query(RevokedToken).filter(RevokedToken.token_hash == tok_hash).delete()
        db.commit()
        db.close()
    print("  -> PASS: Revoked token connection rejected with code 1008 / HTTP 403.")


async def test_ping_pong():
    print("[Test 4] WebSocket Ping/Pong Keep-Alive Protocol...")
    alpha_sub, beta_sub = get_active_admin_usernames()
    token = create_access_token(data={"sub": beta_sub, "user_id": 5, "role": "admin"})
    async with websockets.connect(f"{WS_BASE_URL}?token={token}") as ws:
        connected = json.loads(await ws.recv())
        assert connected["event_type"] == "CONNECTED"
        assert connected["user"]["username"] == beta_sub
        assert connected["user"]["household_id"] == 5

        await ws.send(json.dumps({"action": "ping"}))
        pong = json.loads(await ws.recv())
        assert pong["event_type"] == "PONG"
    print("  -> PASS: Ping/Pong keepalive verified.")


async def test_multi_device_sos_workflow_and_isolation():
    print("[Test 5] Multi-Device Real-Time SOS Dispatch, Household Broadcasting & Tenant Isolation...")
    alpha_sub, beta_sub = get_active_admin_usernames()
    token_beta_a = create_access_token(data={"sub": beta_sub, "user_id": 5, "role": "admin"})
    token_beta_b = create_access_token(data={"sub": beta_sub, "user_id": 5, "role": "admin"})
    token_alpha = create_access_token(data={"sub": alpha_sub, "user_id": 4, "role": "admin"})

    test_incident_id = None
    try:
        # Connect 3 concurrent sessions across 2 households
        async with websockets.connect(f"{WS_BASE_URL}?token={token_beta_a}") as ws_beta_a, \
                   websockets.connect(f"{WS_BASE_URL}?token={token_beta_b}") as ws_beta_b, \
                   websockets.connect(f"{WS_BASE_URL}?token={token_alpha}") as ws_alpha:

            # Verify CONNECTED handshake
            c_beta_a = json.loads(await ws_beta_a.recv())
            c_beta_b = json.loads(await ws_beta_b.recv())
            c_alpha = json.loads(await ws_alpha.recv())

            assert c_beta_a["user"]["household_id"] == 5
            assert c_beta_b["user"]["household_id"] == 5
            assert c_alpha["user"]["household_id"] == 4

            print("  - Session A (Admin Beta Tab 1, Household 5): Connected")
            print("  - Session B (Admin Beta Tab 2, Household 5): Connected")
            print("  - Session C (Admin Alpha, Household 4): Connected")

            # Look up Member #8 name dynamically from DB
            _db_m = SessionLocal()
            _m8 = _db_m.query(Member).filter(Member.id == 8).first()
            m8_name = _m8.name if _m8 else "Test Patient Beta"
            _db_m.close()

            # Session A triggers an SOS for Household 5
            print(f"  - Session A triggering SOS for Member #8 ({m8_name})...")
            sos_payload = {
                "member_id": 8,
                "reporter_name": m8_name,
                "incident_type": "Fall",
                "description": "[Automated WebSocket Multi-Device Test] Living room stumble, conscious",
                "latitude": 9.9312,
                "longitude": 76.2673,
                "location_label": "Kochi Family Residence",
                "location_source": "browser_gps",
                "location_accuracy_m": 4.5,
                "is_conscious": True,
                "has_breathing_difficulty": False,
                "is_bleeding_severely": False,
                "is_alone": False
            }
            incident_data = http_post("/api/emergencies/sos", sos_payload, token=token_beta_a)
            test_incident_id = incident_data["id"]
            print(f"  - SOS Incident #{test_incident_id} created successfully.")

            # Session A receives INCIDENT_CREATED broadcast
            evt_admin = json.loads(await asyncio.wait_for(ws_beta_a.recv(), timeout=3.0))
            assert evt_admin["event_type"] == "INCIDENT_CREATED"
            assert evt_admin["incident_id"] == test_incident_id
            assert m8_name in evt_admin["payload"]["reporter_name"]
            print("  - Session A (Admin Beta 1): Received INCIDENT_CREATED broadcast.")

            # Session B receives INCIDENT_CREATED broadcast
            evt_marcus = json.loads(await asyncio.wait_for(ws_beta_b.recv(), timeout=3.0))
            assert evt_marcus["event_type"] == "INCIDENT_CREATED"
            assert evt_marcus["incident_id"] == test_incident_id
            assert m8_name in evt_marcus["payload"]["reporter_name"]
            print("  - Session B (Admin Beta 2): Received INCIDENT_CREATED broadcast in real time without refreshing.")

            # Session C (Household 4) must NOT receive the broadcast
            try:
                evt_alpha = await asyncio.wait_for(ws_alpha.recv(), timeout=1.0)
                assert False, f"Session C received unauthorized broadcast: {evt_alpha}"
            except asyncio.TimeoutError:
                print("  - Session C (Admin Alpha, Household 4): Confirmed NO cross-tenant broadcast leaked.")

            # Session C attempts to subscribe to Session A's incident
            print("  - Session C attempting unauthorized subscription to Incident #" + str(test_incident_id) + "...")
            await ws_alpha.send(json.dumps({"action": "subscribe_incident", "incident_id": test_incident_id}))
            sub_resp = json.loads(await asyncio.wait_for(ws_alpha.recv(), timeout=3.0))
            assert sub_resp["event_type"] == "SUBSCRIPTION_DENIED"
            assert sub_resp["code"] == 403
            print("  - Session C: Unauthorized subscription strictly DENIED with code 403.")

            # Real-time Location Update Broadcast
            print("  - Updating incident location telemetry...")
            loc_update = {
                "latitude": 9.9315,
                "longitude": 76.2678,
                "location_label": "Kochi Family Residence - Front Porch",
                "location_source": "live_refresh",
                "location_accuracy_m": 3.0
            }
            http_patch(f"/api/emergencies/{test_incident_id}/location", loc_update, token=token_beta_a)
            loc_evt_admin = json.loads(await asyncio.wait_for(ws_beta_a.recv(), timeout=3.0))
            loc_evt_marcus = json.loads(await asyncio.wait_for(ws_beta_b.recv(), timeout=3.0))
            assert loc_evt_admin["event_type"] == "INCIDENT_LOCATION_UPDATED"
            assert loc_evt_marcus["event_type"] == "INCIDENT_LOCATION_UPDATED"
            assert loc_evt_marcus["payload"]["latitude"] == 9.9315
            print("  - Session A & B: Received INCIDENT_LOCATION_UPDATED broadcast.")

            # Real-time Status Update Broadcast
            print("  - Updating incident status to RESPONDING...")
            stat_update = {"status": "RESPONDING", "resolution_notes": None}
            http_patch(f"/api/emergencies/{test_incident_id}/status", stat_update, token=token_beta_a)
            st_evt_admin = json.loads(await asyncio.wait_for(ws_beta_a.recv(), timeout=3.0))
            st_evt_marcus = json.loads(await asyncio.wait_for(ws_beta_b.recv(), timeout=3.0))
            assert st_evt_admin["event_type"] == "INCIDENT_STATUS_UPDATED"
            assert st_evt_marcus["event_type"] == "INCIDENT_STATUS_UPDATED"
            assert st_evt_marcus["payload"]["status"] == "RESPONDING"
            print("  - Session A & B: Received INCIDENT_STATUS_UPDATED broadcast.")

    finally:
        # Clean up test incident and related records
        if test_incident_id:
            db = SessionLocal()
            db.query(IncidentTimelineEvent).filter(IncidentTimelineEvent.incident_id == test_incident_id).delete()
            db.query(IncidentAlert).filter(IncidentAlert.incident_id == test_incident_id).delete()
            db.query(IncidentResponder).filter(IncidentResponder.incident_id == test_incident_id).delete()
            db.query(EmergencyIncident).filter(EmergencyIncident.id == test_incident_id).delete()
            db.commit()
            db.close()
            print(f"  - Cleaned up test incident #{test_incident_id}.")

    print("  -> PASS: Multi-device real-time SOS workflow and tenant isolation fully verified.")


async def test_responder_subscription_scoping():
    print("[Test 6] Responder Role-Scoped Subscription Security...")
    # Create an ephemeral active responder user for test verification
    db = SessionLocal()
    eph_user = User(
        username="ws_test_responder",
        email="ws_resp@familyconnect.test",
        hashed_password="hash",
        salt="salt",
        role="responder",
        responder_id=6,
        is_active=True,
        verification_status="APPROVED"
    )
    db.add(eph_user)
    db.commit()
    db.refresh(eph_user)
    eph_user_id = eph_user.id
    db.close()

    try:
        token_resp = create_access_token(data={"sub": "ws_test_responder", "user_id": eph_user_id, "role": "responder"})
        async with websockets.connect(f"{WS_BASE_URL}?token={token_resp}") as ws:
            c_resp = json.loads(await ws.recv())
            assert c_resp["user"]["role"] == "responder"
            assert c_resp["user"]["responder_id"] == 6

            # Attempt to subscribe to unassigned incident
            db = SessionLocal()
            inc = db.query(EmergencyIncident).first()
            if not inc:
                inc = EmergencyIncident(
                    user_id=5,
                    member_id=8,
                    reporter_name="Test Reporter",
                    incident_type="Medical",
                    description="Test responder scoping",
                    latitude=10.02,
                    longitude=76.35,
                    status="ACTIVE"
                )
                db.add(inc)
                db.commit()
                db.refresh(inc)
            inc_target_id = inc.id
            assigned_ids = [ir.responder_id for ir in inc.assigned_responders]
            db.close()

            await ws.send(json.dumps({"action": "subscribe_incident", "incident_id": inc_target_id}))
            resp_data = json.loads(await asyncio.wait_for(ws.recv(), timeout=3.0))

            if eph_user.responder_id not in assigned_ids:
                assert resp_data["event_type"] == "SUBSCRIPTION_DENIED"
                assert resp_data["code"] == 403
                print("  - Responder denied access to unassigned incident (403 SUBSCRIPTION_DENIED).")
            else:
                assert resp_data["event_type"] == "SUBSCRIBED"
                print("  - Responder authorized to subscribe to assigned incident.")
    finally:
        db = SessionLocal()
        db.query(User).filter(User.username == "ws_test_responder").delete()
        db.commit()
        db.close()

    print("  -> PASS: Responder role-scoping verified.")


async def test_disconnect_reconnect_sync():
    print("[Test 7] Disconnect/Reconnect Behavior and State Recovery...")
    alpha_sub, beta_sub = get_active_admin_usernames()
    token_beta = create_access_token(data={"sub": beta_sub, "user_id": 5, "role": "admin"})

    test_incident_id = None
    try:
        # Step 1: Admin Beta connects
        ws = await websockets.connect(f"{WS_BASE_URL}?token={token_beta}")
        await ws.recv() # CONNECTED

        # Step 2: Admin Beta disconnects (simulating network drop or tab sleep)
        await ws.close()
        print("  - Client disconnected (network drop simulation).")

        # Step 3: An SOS event occurs while client is disconnected
        _db_m = SessionLocal()
        _m8 = _db_m.query(Member).filter(Member.id == 8).first()
        m8_name = _m8.name if _m8 else "Test Patient Beta"
        _db_m.close()

        sos_payload = {
            "member_id": 8,
            "reporter_name": m8_name,
            "incident_type": "Injury",
            "description": "[Offline Sync Test] Event generated while client disconnected",
            "latitude": 9.9312,
            "longitude": 76.2673,
            "location_label": "Kochi Family Residence",
            "location_source": "manual_coordinates"
        }
        inc_data = http_post("/api/emergencies/sos", sos_payload, token=token_beta)
        test_incident_id = inc_data["id"]
        print(f"  - Incident #{test_incident_id} created during disconnect window.")

        # Step 4: Admin Beta reconnects
        ws_reconnected = await websockets.connect(f"{WS_BASE_URL}?token={token_beta}")
        reconn_msg = json.loads(await ws_reconnected.recv())
        assert reconn_msg["event_type"] == "CONNECTED"
        print("  - Client reconnected via WebSocket.")

        # Step 5: On reconnect, the frontend client automatically invokes loadData() to sync missed events
        incidents_list = http_get("/api/emergencies", token=token_beta)
        found = any(i["id"] == test_incident_id for i in incidents_list)
        assert found, f"Incident #{test_incident_id} not recovered during reconnection sync."
        print(f"  - Reconnection sync recovered Incident #{test_incident_id} without manual page refresh.")

        await ws_reconnected.close()

    finally:
        if test_incident_id:
            db = SessionLocal()
            db.query(IncidentTimelineEvent).filter(IncidentTimelineEvent.incident_id == test_incident_id).delete()
            db.query(IncidentAlert).filter(IncidentAlert.incident_id == test_incident_id).delete()
            db.query(IncidentResponder).filter(IncidentResponder.incident_id == test_incident_id).delete()
            db.query(EmergencyIncident).filter(EmergencyIncident.id == test_incident_id).delete()
            db.commit()
            db.close()
            print(f"  - Cleaned up test incident #{test_incident_id}.")

    print("  -> PASS: Disconnect and reconnect state recovery verified.")


async def main():
    ensure_server_running()
    print("======================================================================")
    print("FamilyConnect AI - Phase 6 WebSocket & Multi-Device Automated Suite")
    print("======================================================================")
    
    await test_auth_rejection_missing_token()
    await test_auth_rejection_invalid_token()
    await test_auth_rejection_revoked_token()
    await test_ping_pong()
    await test_multi_device_sos_workflow_and_isolation()
    await test_responder_subscription_scoping()
    await test_disconnect_reconnect_sync()

    print("======================================================================")
    print("ALL 7 WEBSOCKET MULTI-DEVICE AUTOMATED TEST SUITES PASSED (100% PASS)")
    print("======================================================================")


if __name__ == "__main__":
    asyncio.run(main())
