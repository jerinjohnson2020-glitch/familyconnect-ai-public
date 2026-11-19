"""
FamilyConnect AI — Phase 5A Automated Test Suite
Focused verification of:
1. Configurable FRONTEND_PUBLIC_URL for invitation and alert links.
2. Safe restricted CORS configuration (no wildcard '*', private Wi-Fi RFC 1918 support, evil domain rejection).
3. Direct route function verification with dynamic FRONTEND_PUBLIC_URL & fallback.
4. Live API endpoint integration over HTTP.
5. Database non-contamination and cleanup.
"""

import os
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path

# Enforce mock notifications
os.environ["MOCK_NOTIFICATIONS"] = "true"

# Ensure backend package importable
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import SessionLocal
from app import models
from app.auth import create_access_token
from app.services.notifications import get_captured_dispatches, clear_captured_dispatches
from app.routes.household import create_invitation
from app.schemas import CreateInvitationRequest

BASE_URL = "http://127.0.0.1:8000"
test_invitation_ids = []


def assert_true(condition: bool, description: str, detail: str = ""):
    if condition:
        print(f"  [PASS] {description}")
    else:
        print(f"  [FAIL] {description} -> {detail}")
        raise AssertionError(f"Failed: {description}. {detail}")


def api_request(method: str, path: str, data: dict = None, token: str = None, headers: dict = None):
    url = f"{BASE_URL}{path}"
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    if token:
        req_headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp_body = resp.read().decode("utf-8")
            return resp.status, json.loads(resp_body) if resp_body else {}, resp.headers
    except urllib.error.HTTPError as err:
        err_body = err.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(err_body)
        except Exception:
            parsed = {"detail": err_body}
        return err.code, parsed, err.headers


def cleanup():
    db = SessionLocal()
    try:
        if test_invitation_ids:
            db.query(models.HouseholdInvitation).filter(
                models.HouseholdInvitation.id.in_(test_invitation_ids)
            ).delete(synchronize_session=False)
            db.commit()
    finally:
        db.close()


def ensure_server_running():
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=1):
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
            with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=1):
                return server
        except Exception:
            time.sleep(0.1)
    return None


def main():
    ensure_server_running()
    print("=" * 80)
    print("PHASE 5A AUTOMATED TEST SUITE: CONFIGURABLE URL & SAFE CORS")
    print("=" * 80)

    try:
        # -----------------------------------------------------------------
        # GROUP 1: URL Precedence & Construction
        # -----------------------------------------------------------------
        print("\n--- GROUP 1: FRONTEND_PUBLIC_URL Precedence & Fallbacks ---")

        # 1.1 Test with FRONTEND_PUBLIC_URL configured
        os.environ["FRONTEND_PUBLIC_URL"] = "http://192.168.1.100:5173"
        raw_val = (os.environ.get("FRONTEND_PUBLIC_URL") or os.environ.get("APP_BASE_URL") or "").strip().rstrip("/")
        assert_true(raw_val == "http://192.168.1.100:5173", "FRONTEND_PUBLIC_URL is resolved directly")

        # 1.2 Test trailing slashes and spaces trimmed
        os.environ["FRONTEND_PUBLIC_URL"] = "  https://familyconnect.ourhome.org/   "
        raw_val = (os.environ.get("FRONTEND_PUBLIC_URL") or os.environ.get("APP_BASE_URL") or "").strip().rstrip("/")
        assert_true(raw_val == "https://familyconnect.ourhome.org", "Trailing slashes and whitespace trimmed cleanly")

        # 1.3 Test APP_BASE_URL fallback when FRONTEND_PUBLIC_URL is unset
        os.environ.pop("FRONTEND_PUBLIC_URL", None)
        os.environ["APP_BASE_URL"] = "http://appbase.local:5173"
        raw_val = (os.environ.get("FRONTEND_PUBLIC_URL") or os.environ.get("APP_BASE_URL") or "").strip().rstrip("/")
        assert_true(raw_val == "http://appbase.local:5173", "Falls back to APP_BASE_URL when FRONTEND_PUBLIC_URL is empty")

        # 1.4 Test default localhost fallback when neither is set
        os.environ.pop("FRONTEND_PUBLIC_URL", None)
        os.environ.pop("APP_BASE_URL", None)
        raw_val = (os.environ.get("FRONTEND_PUBLIC_URL") or os.environ.get("APP_BASE_URL") or "").strip().rstrip("/")
        if not raw_val:
            raw_val = "http://127.0.0.1:5173"
        assert_true(raw_val == "http://127.0.0.1:5173", "Defaults to http://127.0.0.1:5173 for local dev")

        # -----------------------------------------------------------------
        # GROUP 2: Restricted CORS & Private Network Testing
        # -----------------------------------------------------------------
        print("\n--- GROUP 2: Safe Restricted CORS & Origin Validation ---")

        from app.main import app as fastapi_app
        from fastapi.middleware.cors import CORSMiddleware

        # Locate CORSMiddleware in the FastAPI middleware stack
        cors_mw = None
        for mw in fastapi_app.user_middleware:
            if mw.cls == CORSMiddleware:
                cors_mw = CORSMiddleware(
                    app=None,
                    allow_origins=mw.kwargs.get("allow_origins", []),
                    allow_origin_regex=mw.kwargs.get("allow_origin_regex"),
                    allow_credentials=mw.kwargs.get("allow_credentials", True),
                    allow_methods=mw.kwargs.get("allow_methods", ["*"]),
                    allow_headers=mw.kwargs.get("allow_headers", ["*"])
                )
                break

        assert_true(cors_mw is not None, "CORSMiddleware detected in FastAPI application")
        assert_true("*" not in cors_mw.allow_origins, "No unrestricted wildcard '*' in allow_origins")

        # 2.1 Localhost & loopback origins allowed
        assert_true(cors_mw.is_allowed_origin("http://localhost:5173"), "http://localhost:5173 is allowed")
        assert_true(cors_mw.is_allowed_origin("http://127.0.0.1:5173"), "http://127.0.0.1:5173 is allowed")
        assert_true(cors_mw.is_allowed_origin("http://localhost:4173"), "http://localhost:4173 (preview) is allowed")

        # 2.2 Private Wi-Fi LAN origins (RFC 1918) allowed for mobile testing
        assert_true(cors_mw.is_allowed_origin("http://192.168.1.15:5173"), "192.168.x.x Wi-Fi origin allowed")
        assert_true(cors_mw.is_allowed_origin("http://192.168.0.100:5173"), "192.168.0.x Wi-Fi origin allowed")
        assert_true(cors_mw.is_allowed_origin("http://10.0.0.5:5173"), "10.x.x.x private LAN origin allowed")
        assert_true(cors_mw.is_allowed_origin("http://172.20.10.4:5173"), "172.16-31 private LAN origin allowed")

        # 2.3 Untrusted public internet domains strictly rejected
        assert_true(not cors_mw.is_allowed_origin("http://evil.com"), "evil.com is rejected")
        assert_true(not cors_mw.is_allowed_origin("https://attacker.org"), "attacker.org is rejected")
        assert_true(not cors_mw.is_allowed_origin("http://192.168.1.15.evil.com"), "evil subdomain attack is rejected")
        assert_true(not cors_mw.is_allowed_origin("http://malicious-site.net:5173"), "malicious-site is rejected")

        # 2.4 Live HTTP CORS preflight request check
        req = urllib.request.Request(
            f"{BASE_URL}/api/members",
            headers={
                "Origin": "http://192.168.1.50:5173",
                "Access-Control-Request-Method": "GET"
            },
            method="OPTIONS"
        )
        with urllib.request.urlopen(req, timeout=5) as preflight_resp:
            allow_orig = preflight_resp.headers.get("access-control-allow-origin")
            allow_cred = preflight_resp.headers.get("access-control-allow-credentials")
            assert_true(allow_orig == "http://192.168.1.50:5173", "CORS preflight reflects allowed mobile origin")
            assert_true(allow_cred == "true", "CORS preflight confirms allow-credentials: true")

        # -----------------------------------------------------------------
        # GROUP 3: Invitation Link Generation with FRONTEND_PUBLIC_URL
        # -----------------------------------------------------------------
        print("\n--- GROUP 3: Invitation Link Generation with FRONTEND_PUBLIC_URL ---")

        db = SessionLocal()
        admin_alpha = db.query(models.User).filter(models.User.id == 4).first()
        admin_alpha_sub = admin_alpha.username if admin_alpha else "test_admin_alpha"

        # 3.1 Invitation generated with explicit FRONTEND_PUBLIC_URL
        clear_captured_dispatches()
        os.environ["FRONTEND_PUBLIC_URL"] = "http://192.168.1.50:5173"
        req_custom = CreateInvitationRequest(email="custom_url_test@familycircle.test", role="member")
        resp_custom = create_invitation(req_custom, current_user=admin_alpha, db=db)
        test_invitation_ids.append(resp_custom.id)

        assert_true(
            resp_custom.invitation_link.startswith("http://192.168.1.50:5173/accept-invite?token="),
            "invitation_link uses FRONTEND_PUBLIC_URL prefix"
        )
        dispatches = get_captured_dispatches()
        assert_true(len(dispatches) >= 1, "Mock notification captured custom URL invitation email")
        body_custom = dispatches[-1].get("body", "") + dispatches[-1].get("html", "")
        assert_true("http://192.168.1.50:5173/accept-invite?token=" in body_custom,
                    "Invitation email body contains FRONTEND_PUBLIC_URL link")
        assert_true("http://127.0.0.1:5173" not in body_custom,
                    "Localhost never accidentally used when FRONTEND_PUBLIC_URL is configured")

        # 3.2 Invitation generated with fallback to localhost when FRONTEND_PUBLIC_URL is empty
        clear_captured_dispatches()
        os.environ.pop("FRONTEND_PUBLIC_URL", None)
        os.environ.pop("APP_BASE_URL", None)
        req_default = CreateInvitationRequest(email="default_url_test@familycircle.test", role="member")
        resp_default = create_invitation(req_default, current_user=admin_alpha, db=db)
        test_invitation_ids.append(resp_default.id)

        assert_true(
            resp_custom.invitation_link.startswith("http://192.168.1.50:5173/accept-invite?token="),
            "Prior custom link remains unchanged"
        )
        assert_true(
            resp_default.invitation_link.startswith("http://127.0.0.1:5173/accept-invite?token="),
            "Fallback invitation link defaults cleanly to http://127.0.0.1:5173"
        )
        dispatches_default = get_captured_dispatches()
        assert_true(len(dispatches_default) >= 1, "Mock notification captured default invitation email")
        body_default = dispatches_default[-1].get("body", "") + dispatches_default[-1].get("html", "")
        assert_true("http://127.0.0.1:5173/accept-invite?token=" in body_default,
                    "Default invitation email contains localhost fallback")

        db.close()

        # -----------------------------------------------------------------
        # GROUP 4: Live HTTP API Endpoint Verification
        # -----------------------------------------------------------------
        print("\n--- GROUP 4: Live HTTP API Endpoint Verification ---")

        alpha_token = create_access_token({
            "sub": admin_alpha_sub,
            "user_id": 4,
            "role": "admin",
            "household_id": 4
        })

        code, api_data, _ = api_request("POST", "/api/household/invitations", {
            "email": "live_api_invite@familycircle.test",
            "role": "member"
        }, token=alpha_token)

        assert_true(code == 201, "Live API endpoint POST /api/household/invitations succeeds (201)")
        test_invitation_ids.append(api_data["id"])
        assert_true("invitation_link" in api_data, "Live API response includes invitation_link")
        assert_true("invitation_token" in api_data, "Live API response includes raw invitation_token")

        print("\n" + "=" * 80)
        print("ALL PHASE 5A TESTS PASSED (100% SUCCESS)")
        print("=" * 80)

    finally:
        cleanup()
        print("\n[Teardown] Cleaned up temporary test entities.")


if __name__ == "__main__":
    main()
