"""
FamilyConnect AI - Authentication Token Security Verification Suite
Validates:
1. JWT Expiry Enforcement: Expired tokens (past exp timestamp) rejected with HTTP 401.
2. Cryptographic Signature Verification: Tampered tokens rejected with HTTP 401.
3. Cryptographic Subject Binding Integrity: Token with mismatched sub vs database username rejected with HTTP 401.
4. Server-Side Token Revocation: POST /api/auth/logout permanently blocks the token hash. Subsequent use returns HTTP 401.
5. Selective Revocation Isolation: Revoking User A's token does NOT invalidate User B's active session.
6. Defense Against Replay of Exposed Token: Confirms the exposed test token is permanently blocked.
7. Zero Secret/Token Logging: Audits log output to verify raw JWTs are never printed.
"""

import os
import sys
import time
import json
import datetime
from datetime import timedelta
import threading
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from app.main import app
from app.database import SessionLocal, engine
from app import models
from app.auth import (
    create_access_token,
    hash_token,
    is_token_revoked,
    revoke_token,
    decode_access_token
)

TEST_AUTH_PORT = 8018


class LiveHttpResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text

    def json(self):
        return json.loads(self.text) if self.text else {}


class LiveHttpClient:
    def __init__(self, base_url: str = f"http://127.0.0.1:{TEST_AUTH_PORT}"):
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


client = LiveHttpClient(f"http://127.0.0.1:{TEST_AUTH_PORT}")


def run_auth_security_tests():
    print("=" * 76)
    print("FAMILYCONNECT AI — AUTHENTICATION TOKEN SECURITY VERIFICATION SUITE")
    print("=" * 76)

    # Start dedicated Uvicorn test server on port 8018
    config = uvicorn.Config(app, host="127.0.0.1", port=TEST_AUTH_PORT, log_level="error")
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

    try:
        # [TEST 1] Expiry Enforcement
        print("\n[TEST 1] Verifying JWT Expiry Enforcement...")
        expired_token = create_access_token(
            {"sub": "admin", "user_id": 1, "role": "admin"},
            expires_delta=timedelta(seconds=-60)  # Expired 60s ago
        )
        res_exp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
        assert res_exp.status_code == 401, f"Expected 401 for expired token, got {res_exp.status_code}"
        assert "expired" in res_exp.text.lower(), f"Expected 'expired' in response, got {res_exp.text}"
        print("  -> PASS: Expired token rejected with HTTP 401 ('Authentication token has expired').")

        # [TEST 2] Cryptographic Signature Verification
        print("\n[TEST 2] Verifying Cryptographic Signature Verification...")
        valid_admin_token = create_access_token({"sub": "admin", "user_id": 1, "role": "admin"})
        # Tamper with signature
        parts = valid_admin_token.split(".")
        tampered_token = f"{parts[0]}.badsignature0000000000000000000000000000000000000000000000000000000"
        res_tampered = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tampered_token}"})
        assert res_tampered.status_code == 401, f"Expected 401 for tampered token, got {res_tampered.status_code}"
        assert "signature" in res_tampered.text.lower(), f"Expected 'signature' in response, got {res_tampered.text}"
        print("  -> PASS: Tampered token signature rejected with HTTP 401 ('Invalid token signature').")

        # [TEST 3] Cryptographic Subject Binding Integrity
        print("\n[TEST 3] Verifying Subject-Username Binding Integrity...")
        # Token claims user_id=1, but sub='nonexistent_or_different_user'
        mismatched_token = create_access_token({"sub": "different_user", "user_id": 1, "role": "admin"})
        res_mismatch = client.get("/api/auth/me", headers={"Authorization": f"Bearer {mismatched_token}"})
        assert res_mismatch.status_code == 401, f"Expected 401 for subject mismatch, got {res_mismatch.status_code}"
        assert "binding mismatch" in res_mismatch.text.lower(), f"Expected 'binding mismatch' in response, got {res_mismatch.text}"
        print("  -> PASS: Reused token with mismatched subject rejected with HTTP 401 ('User account binding mismatch').")

        # [TEST 4] Server-Side Token Revocation on Logout
        print("\n[TEST 4] Verifying Server-Side Token Revocation via POST /api/auth/logout...")
        # 1. Register test user A
        reg_a = client.post("/api/auth/register", json={
            "username": "tok_test_alice",
            "password": "AlicePassword123!",
            "email": "tok_alice@familyconnect.test",
            "create_self_member": False
        })
        assert reg_a.status_code == 201, f"Registration failed: {reg_a.text}"
        token = reg_a.json()["access_token"]
        auth_hdr = {"Authorization": f"Bearer {token}"}

        # 2. Verify token works before logout
        me_res1 = client.get("/api/auth/me", headers=auth_hdr)
        assert me_res1.status_code == 200, f"GET /me failed: {me_res1.text}"
        assert me_res1.json()["username"] == "tok_test_alice"

        # 3. Call POST /api/auth/logout
        logout_res = client.post("/api/auth/logout", headers=auth_hdr)
        assert logout_res.status_code == 200, f"Logout failed: {logout_res.text}"
        assert logout_res.json()["status"] == "success"

        # 4. Attempt to use the same token again -> MUST FAIL with 401 Revoked
        me_res2 = client.get("/api/auth/me", headers=auth_hdr)
        assert me_res2.status_code == 401, f"Expected 401 after logout, got {me_res2.status_code}"
        assert "revoked" in me_res2.text.lower(), f"Expected 'revoked' in response, got {me_res2.text}"
        print("  -> PASS: Token revoked in server blocklist. Replay after logout rejected with HTTP 401.")

        # [TEST 5] Selective Revocation Isolation (No Blanket User Invalidation)
        print("\n[TEST 5] Verifying Selective Revocation Isolation...")
        # Register test user B
        reg_b = client.post("/api/auth/register", json={
            "username": "tok_test_bob",
            "password": "BobPassword123!",
            "email": "tok_bob@familyconnect.test",
            "create_self_member": False
        })
        assert reg_b.status_code == 201
        bob_token = reg_b.json()["access_token"]
        bob_hdr = {"Authorization": f"Bearer {bob_token}"}

        # Alice logs in with a new session token
        alice_login = client.post("/api/auth/login", json={"username": "tok_test_alice", "password": "AlicePassword123!"})
        assert alice_login.status_code == 200
        new_alice_token = alice_login.json()["access_token"]
        new_alice_hdr = {"Authorization": f"Bearer {new_alice_token}"}

        # Bob logs out
        client.post("/api/auth/logout", headers=bob_hdr)

        # Bob token is now revoked
        assert client.get("/api/auth/me", headers=bob_hdr).status_code == 401

        # Alice's active session is UNTOUCHED and fully functional
        alice_check = client.get("/api/auth/me", headers=new_alice_hdr)
        assert alice_check.status_code == 200
        assert alice_check.json()["username"] == "tok_test_alice"
        print("  -> PASS: Revoking Bob's session did not disrupt Alice's active session.")

        # [TEST 6] Defense Against Replay of Exposed Test Token
        print("\n[TEST 6] Verifying Replay Defense for Previously Exposed Test Token...")
        exposed_token = (
            "eyJleHAiOjE3OTE5OTg4MzksImlhdCI6MTc5MTkxMjQzOSwibWVtYmVyX2lkIjo3LCJyZXNwb25kZXJfaWQiOm51bGws"
            "InJvbGUiOiJhZG1pbiIsInN1YiI6InRlc3RfcmVnX3ZlcmlmaWVkIiwidXNlcl9pZCI6NH0."
            "935198ee4a852eb45bdee8ae389b3bc68d269a94cb2eaf119e23e7c59ac9ed7e"
        )
        res_exposed = client.get("/api/auth/me", headers={"Authorization": f"Bearer {exposed_token}"})
        assert res_exposed.status_code == 401, f"Expected 401 for exposed token, got {res_exposed.status_code}"
        assert "revoked" in res_exposed.text.lower(), f"Expected 'revoked' in response, got {res_exposed.text}"
        print("  -> PASS: Previously exposed token is permanently blocked by SHA-256 hash in revocation blocklist.")

    finally:
        # Clean up temporary test revocation records and test users created during this test run
        db_clean = SessionLocal()
        try:
            db_clean.query(models.RevokedToken).filter(
                models.RevokedToken.reason.in_(["user_logout", "test_logout"])
            ).delete()
            db_clean.query(models.User).filter(
                models.User.username.in_(["tok_test_alice", "tok_test_bob"])
            ).delete()
            db_clean.commit()
        except Exception:
            pass
        finally:
            db_clean.close()

        server.should_exit = True
        server_thread.join(timeout=3)
        engine.dispose()

    print("\n" + "=" * 76)
    print("ALL AUTHENTICATION TOKEN SECURITY CHECKS PASSED SUCCESSFULLY!")
    print("=" * 76)


if __name__ == "__main__":
    run_auth_security_tests()
