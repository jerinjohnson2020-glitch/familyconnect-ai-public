"""
FamilyConnect AI - Phase 2 Verification Suite
Verifies:
1. Deactivated accounts (admin ID 1, marcus ID 2, officer_david ID 3) CANNOT log in (HTTP 401 'User account has been disabled').
2. Existing tokens for deactivated accounts are rejected by protected HTTP endpoints (HTTP 401 'User account has been disabled').
3. Existing tokens for deactivated accounts are rejected by WebSocket endpoint (close code 1008).
4. Active accounts (Admin Alpha ID 4, Admin Beta ID 5) remain active (is_active == 1).
5. Protected endpoints accept valid tokens for Admin Alpha and Admin Beta.
6. WebSocket connects successfully for Admin Alpha and Admin Beta.
"""

import sys
import os
import json
import asyncio
import threading
import time
import urllib.request
import urllib.error
import uvicorn
from pathlib import Path

# Add backend to sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import websockets
from app.auth import create_access_token
from app.database import SessionLocal
from app.models import User

HTTP_BASE = "http://127.0.0.1:8000"
WS_BASE = "ws://127.0.0.1:8000/api/ws/incidents"


def ensure_server_running():
    try:
        with urllib.request.urlopen(f"{HTTP_BASE}/api/health", timeout=1):
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
            with urllib.request.urlopen(f"{HTTP_BASE}/api/health", timeout=1):
                break
        except Exception:
            time.sleep(0.1)
    return server


def http_post_login(username, password):
    url = f"{HTTP_BASE}/api/auth/login"
    body = json.dumps({"username": username, "password": password}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read().decode("utf-8"))


def http_get_me(token):
    url = f"{HTTP_BASE}/api/auth/me"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"}, method="GET")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read().decode("utf-8"))


async def test_websocket_connection(token):
    try:
        async with websockets.connect(f"{WS_BASE}?token={token}") as ws:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
            return True, msg
    except Exception as exc:
        return False, str(exc)


async def main():
    print("=" * 70)
    print("FamilyConnect AI - Phase 2 Deactivation & Real-User Verification Suite")
    print("=" * 70)
    ensure_server_running()

    # 1. Database Check
    db = SessionLocal()
    users = db.query(User).order_by(User.id.asc()).all()
    user_map = {u.id: u for u in users}
    db.close()

    assert user_map[1].is_active is False, "admin (ID 1) must be inactive"
    assert user_map[2].is_active is False, "marcus (ID 2) must be inactive"
    assert user_map[3].is_active is False, "officer_david (ID 3) must be inactive"
    assert user_map[4].is_active is True, "Admin Alpha (ID 4) must remain active"
    assert user_map[5].is_active is True, "Admin Beta (ID 5) must remain active"
    print("[Check 1] Database account status verified:")
    print("  - ID 1 (admin): is_active = 0")
    print("  - ID 2 (marcus): is_active = 0")
    print("  - ID 3 (officer_david): is_active = 0")
    print("  - ID 4 (Admin Alpha): is_active = 1 (Active)")
    print("  - ID 5 (Admin Beta): is_active = 1 (Active)")

    # 2. Login Rejection for Demo Accounts
    print("\n[Check 2] Verifying login is REJECTED for deactivated demo accounts:")
    for uname, pw in [("admin", "AdminPass123!"), ("marcus", "MemberPass123!"), ("officer_david", "RespPass123!")]:
        code, body = http_post_login(uname, pw)
        assert code == 401, f"Expected 401 for {uname}, got {code}"
        assert "disabled" in body.get("detail", "").lower(), f"Expected 'disabled' in {body}"
        print(f"  -> PASS: Login as '{uname}' correctly rejected with HTTP {code} ({body['detail']})")

    # 3. Existing Token Invalidation for Demo Accounts
    print("\n[Check 3] Verifying existing/crafted tokens for deactivated accounts are REJECTED:")
    token_admin = create_access_token({"sub": "admin", "user_id": 1, "role": "admin"})
    token_marcus = create_access_token({"sub": "marcus", "user_id": 2, "role": "member"})
    token_david = create_access_token({"sub": "officer_david", "user_id": 3, "role": "responder"})

    for uname, tok in [("admin", token_admin), ("marcus", token_marcus), ("officer_david", token_david)]:
        code, body = http_get_me(tok)
        assert code == 401, f"Expected 401 for token {uname}, got {code}"
        assert "disabled" in body.get("detail", "").lower(), f"Expected 'disabled' in {body}"
        print(f"  -> PASS: Token for '{uname}' rejected on GET /api/auth/me with HTTP {code} ({body['detail']})")

    # 4. WebSocket Rejection for Demo Accounts
    print("\n[Check 4] Verifying WebSocket access is REJECTED for deactivated demo accounts:")
    for uname, tok in [("admin", token_admin), ("marcus", token_marcus), ("officer_david", token_david)]:
        success, err = await test_websocket_connection(tok)
        assert not success, f"WebSocket connection for {uname} should have failed"
        assert "1008" in err or "rejected" in err.lower() or "closed" in err.lower()
        print(f"  -> PASS: WebSocket rejected for '{uname}' (Connection closed with error: {err[:60]}...)")

    # 5. Active Admin Token Acceptance on Protected Endpoints
    print("\n[Check 5] Verifying active admin accounts can access protected HTTP endpoints:")
    alpha_name = user_map[4].username
    beta_name = user_map[5].username
    token_alpha = create_access_token({"sub": alpha_name, "user_id": 4, "role": "admin"})
    token_beta = create_access_token({"sub": beta_name, "user_id": 5, "role": "admin"})

    code_alpha, body_alpha = http_get_me(token_alpha)
    assert code_alpha == 200, f"Expected 200 for Admin Alpha, got {code_alpha}"
    assert body_alpha["username"] == alpha_name
    assert body_alpha["is_active"] is True
    print(f"  -> PASS: Admin Alpha (ID 4) authenticated successfully (username={body_alpha['username']})")

    code_beta, body_beta = http_get_me(token_beta)
    assert code_beta == 200, f"Expected 200 for Admin Beta, got {code_beta}"
    assert body_beta["username"] == beta_name
    assert body_beta["is_active"] is True
    print(f"  -> PASS: Admin Beta (ID 5) authenticated successfully (username={body_beta['username']})")

    # 6. Active Admin WebSocket Connection
    print("\n[Check 6] Verifying active admin accounts can connect to real-time WebSocket:")
    success_alpha, msg_alpha = await test_websocket_connection(token_alpha)
    assert success_alpha, f"Admin Alpha failed to connect to WebSocket: {msg_alpha}"
    assert msg_alpha["event_type"] == "CONNECTED"
    assert msg_alpha["user"]["username"] == alpha_name
    print("  -> PASS: Admin Alpha connected to WebSocket successfully")

    success_beta, msg_beta = await test_websocket_connection(token_beta)
    assert success_beta, f"Admin Beta failed to connect to WebSocket: {msg_beta}"
    assert msg_beta["event_type"] == "CONNECTED"
    assert msg_beta["user"]["username"] == beta_name
    print("  -> PASS: Admin Beta connected to WebSocket successfully")

    print("\n" + "=" * 70)
    print("ALL PHASE 2 VERIFICATION CHECKS PASSED (100% SUCCESS)")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
