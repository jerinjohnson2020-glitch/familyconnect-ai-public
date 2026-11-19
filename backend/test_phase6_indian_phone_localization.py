"""
FamilyConnect AI - Phase 6: Indian Phone Number Localization & Normalization Test Suite
Tests:
  1. Unit tests for schemas.validate_phone_format with all Indian formats, domestic trunk '0',
     91 prefix without plus, and 10-digit mobile defaults.
  2. Validation error handling for non-mobile starting digits (0-5), short numbers, invalid characters,
     and placeholder test numbers.
  3. Preservation of existing international numbers (+1, +44, etc.) without corrupting or prepending +91.
  4. End-to-end API integration tests for Member, Trusted Contact, Responder Application, and Registration.
  5. Teardown ensuring zero persistent test records remain in the database.
"""
import os
import sys
import json
import urllib.request
import urllib.error
from typing import Tuple, Dict, Any

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["MOCK_NOTIFICATIONS"] = "true"
os.environ["ENABLE_DEMO_USERS"] = "false"

import threading
import time
import uvicorn
from app.database import SessionLocal, engine
from app import models, schemas
from app.auth import create_access_token

BASE_URL = "http://127.0.0.1:8000"


def ensure_server_running():
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=1):
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
            with urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=1):
                break
        except Exception:
            time.sleep(0.1)
    return server


class HttpClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def request(self, method: str, path: str, data: Dict[str, Any] = None, token: str = None) -> Tuple[int, Dict[str, Any]]:
        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        body = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                code = resp.status
                resp_body = resp.read().decode("utf-8")
                try:
                    parsed = json.loads(resp_body)
                except Exception:
                    parsed = {"raw": resp_body}
                return code, parsed
        except urllib.error.HTTPError as e:
            code = e.code
            body = e.read().decode("utf-8")
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = {"detail": body}
            return code, parsed


client = HttpClient(BASE_URL)
test_created_user_ids = []
test_created_member_ids = []
test_created_contact_ids = []
test_created_app_ids = []


def cleanup():
    db = SessionLocal()
    try:
        if test_created_contact_ids:
            db.query(models.TrustedContact).filter(
                models.TrustedContact.id.in_(test_created_contact_ids)
            ).delete(synchronize_session=False)

        if test_created_member_ids:
            db.query(models.Member).filter(
                models.Member.id.in_(test_created_member_ids)
            ).delete(synchronize_session=False)

        if test_created_app_ids:
            db.query(models.ResponderApplication).filter(
                models.ResponderApplication.id.in_(test_created_app_ids)
            ).delete(synchronize_session=False)

        if test_created_user_ids:
            users_to_clean = db.query(models.User).filter(
                models.User.id.in_(test_created_user_ids)
            ).all()
            for u in users_to_clean:
                u.member_id = None
                u.household_id = None
            db.commit()

            db.query(models.Member).filter(
                models.Member.user_id.in_(test_created_user_ids)
            ).delete(synchronize_session=False)
            db.query(models.User).filter(
                models.User.id.in_(test_created_user_ids)
            ).delete(synchronize_session=False)

        db.commit()
    except Exception as e:
        print(f"[Cleanup Warning] {e}")
    finally:
        db.close()


def run_tests():
    print("=" * 80)
    print("PHASE 6 AUTOMATED TEST SUITE: INDIAN PHONE LOCALIZATION & NORMALIZATION (+91)")
    print("=" * 80)

    passed = 0
    total = 0

    def assert_true(cond, name, msg=""):
        nonlocal passed, total
        total += 1
        if cond:
            passed += 1
            print(f"  [PASS] {name}")
        else:
            print(f"  [FAIL] {name}: {msg}")
            raise AssertionError(f"Test assertion failed: {name} - {msg}")

    try:
        # =====================================================================
        # GROUP 1: Unit Tests for Schema Validation and Normalization
        # =====================================================================
        print("\n--- GROUP 1: Schema Phone Validation & Normalization ---")

        # 1.1 Valid 10-digit Indian Mobile Numbers
        assert_true(
            schemas.validate_phone_format("9876543210") == "+91 98765 43210",
            "10-digit number defaults to +91 98765 43210"
        )
        assert_true(
            schemas.validate_phone_format("8765432109") == "+91 87654 32109",
            "10-digit number starting with 8 normalizes correctly"
        )
        assert_true(
            schemas.validate_phone_format("7654321098") == "+91 76543 21098",
            "10-digit number starting with 7 normalizes correctly"
        )
        assert_true(
            schemas.validate_phone_format("6282001122") == "+91 62820 01122",
            "10-digit number starting with 6 normalizes correctly"
        )

        # 1.2 Formats with Spaces and Hyphens
        assert_true(
            schemas.validate_phone_format("98765 43210") == "+91 98765 43210",
            "10-digit with space normalizes to +91 98765 43210"
        )
        assert_true(
            schemas.validate_phone_format("98765-43210") == "+91 98765 43210",
            "10-digit with hyphen normalizes to +91 98765 43210"
        )

        # 1.3 Explicit +91 Prefix Formats
        assert_true(
            schemas.validate_phone_format("+919876543210") == "+91 98765 43210",
            "+919876543210 normalizes to +91 98765 43210"
        )
        assert_true(
            schemas.validate_phone_format("+91 98765 43210") == "+91 98765 43210",
            "+91 98765 43210 normalizes to +91 98765 43210"
        )
        assert_true(
            schemas.validate_phone_format("+91-98765-43210") == "+91 98765 43210",
            "+91-98765-43210 normalizes to +91 98765 43210"
        )
        assert_true(
            schemas.validate_phone_format("+91  9876543210") == "+91 98765 43210",
            "+91 with irregular spaces normalizes to +91 98765 43210"
        )

        # 1.4 Domestic Trunk Prefix '0'
        assert_true(
            schemas.validate_phone_format("09876543210") == "+91 98765 43210",
            "09876543210 domestic trunk prefix normalizes to +91 98765 43210"
        )

        # 1.5 Country Code 91 without Plus
        assert_true(
            schemas.validate_phone_format("919876543210") == "+91 98765 43210",
            "919876543210 without plus normalizes to +91 98765 43210"
        )

        # 1.6 International Number Preservation (Never Prepend +91)
        assert_true(
            schemas.validate_phone_format("+1 415 891 3344") == "+1 415 891 3344",
            "US international number preserved intact"
        )
        assert_true(
            schemas.validate_phone_format("+1 (555) 234-5678") == "+1 (555) 234-5678",
            "US formatted international number preserved intact"
        )
        assert_true(
            schemas.validate_phone_format("+44 7911 123456") == "+44 7911 123456",
            "UK international number preserved intact"
        )
        assert_true(
            schemas.validate_phone_format("+61 2 9374 4000") == "+61 2 9374 4000",
            "Australia international number preserved intact"
        )
        assert_true(
            schemas.validate_phone_format("1-415-891-3344") == "+1 415 891 3344",
            "1-415-891-3344 NANP number normalized with +1"
        )

        # =====================================================================
        # GROUP 2: Invalid Phone Rejection and Error Feedback
        # =====================================================================
        print("\n--- GROUP 2: Invalid Phone Rejections ---")

        # 2.1 10-digit number starting with 0-5
        try:
            schemas.validate_phone_format("1234567890")
            assert_true(False, "Reject 10-digit number starting with 1")
        except ValueError as e:
            assert_true("6, 7, 8, or 9" in str(e), "Reject 10-digit starting with 1 with helpful message")

        # 2.2 +91 with invalid leading digit
        try:
            schemas.validate_phone_format("+91 12345 67890")
            assert_true(False, "Reject +91 12345 67890")
        except ValueError as e:
            assert_true("6, 7, 8, or 9" in str(e), "Reject +91 starting with 1 with helpful message")

        # 2.3 +91 with too few digits
        try:
            schemas.validate_phone_format("+91 98765")
            assert_true(False, "Reject +91 with too few digits")
        except ValueError as e:
            assert_true("Expected exactly 10 digits" in str(e), "Reject +91 98765 with digit count message")

        # 2.4 Short number (< 7 digits)
        try:
            schemas.validate_phone_format("12345")
            assert_true(False, "Reject short phone number")
        except ValueError as e:
            assert_true("too short" in str(e), "Reject short phone with length error")

        # 2.5 Invalid characters
        try:
            schemas.validate_phone_format("98765abcde")
            assert_true(False, "Reject letters in phone number")
        except ValueError as e:
            assert_true("invalid characters" in str(e), "Reject letters with character error")

        # 2.6 Placeholder phone ending in 000-0000
        try:
            schemas.validate_phone_format("+1 555 000-0000")
            assert_true(False, "Reject +1 555 000-0000 placeholder")
        except ValueError as e:
            assert_true("000-0000" in str(e), "Reject 000-0000 placeholder with clear message")

        try:
            schemas.validate_phone_format("+91 98765 000-0000")
            assert_true(False, "Reject +91 000-0000 placeholder")
        except ValueError as e:
            assert_true("000-0000" in str(e), "Reject +91 000-0000 placeholder with clear message")

        # 2.7 Double +91 prefix
        try:
            schemas.validate_phone_format("+91 +91 9876543210")
            assert_true(False, "Reject double +91 prefix")
        except ValueError as e:
            assert_true("Invalid Indian mobile number" in str(e), "Reject double +91 prefix")

        # =====================================================================
        # GROUP 3: Pydantic Model Integration
        # =====================================================================
        print("\n--- GROUP 3: Pydantic Model Normalization ---")

        # MemberCreate
        m_in = schemas.MemberCreate(
            name="Suresh Kumar",
            relationship="Uncle",
            phone="9876543210",
            emergency_contact_phone="8765432109"
        )
        assert_true(m_in.phone == "+91 98765 43210", "MemberCreate normalizes phone to +91 98765 43210")
        assert_true(m_in.emergency_contact_phone == "+91 87654 32109", "MemberCreate normalizes emergency_contact_phone")

        # TrustedContactCreate
        tc_in = schemas.TrustedContactCreate(
            name="Lakshmi Suresh",
            phone="+919876543210",
            relationship="Aunt"
        )
        assert_true(tc_in.phone == "+91 98765 43210", "TrustedContactCreate normalizes +919876543210")

        # ResponderCreate
        resp_in = schemas.ResponderCreate(
            name="Nurse Priya",
            phone="09876543210",
            role="Paramedic"
        )
        assert_true(resp_in.phone == "+91 98765 43210", "ResponderCreate normalizes 09876543210")

        # =====================================================================
        # GROUP 4: Live API End-to-End Tests
        # =====================================================================
        print("\n--- GROUP 4: Live API End-to-End Integration ---")
        ensure_server_running()

        # Mint token for Admin Alpha (Household 4 Admin)
        from app.database import SessionLocal
        from app.models import User
        _db = SessionLocal()
        try:
            _u4 = _db.query(User).filter(User.id == 4).first()
            alpha_sub = _u4.username if _u4 else "test_admin_alpha"
        finally:
            _db.close()

        alpha_token = create_access_token({
            "sub": alpha_sub,
            "user_id": 4,
            "role": "admin",
            "household_id": 4
        })

        # 4.1 Create Member with 10-digit number via POST /api/members
        code, created_m = client.request("POST", "/api/members", {
            "name": "Kiran Varma",
            "relationship": "Brother",
            "phone": "9876543210",
            "emergency_contact_name": "Emergency Contact Alpha",
            "emergency_contact_phone": "8765432109"
        }, token=alpha_token)
        assert_true(code == 201, "POST /api/members creates member with 10-digit number")
        assert_true(created_m["phone"] == "+91 98765 43210", "API returns normalized phone: +91 98765 43210")
        assert_true(created_m["emergency_contact_phone"] == "+91 87654 32109", "API returns normalized emergency_contact_phone")
        kiran_id = created_m["id"]
        test_created_member_ids.append(kiran_id)

        # 4.2 Add Trusted Contact with +91 format via POST /api/members/{id}/trusted-contacts
        code, created_tc = client.request("POST", f"/api/members/{kiran_id}/trusted-contacts", {
            "name": "Anand Varma",
            "phone": "+919876543210",
            "relationship": "Father",
            "notification_preferences": "EMAIL",
            "email": "anand.varma@familycircle.test"
        }, token=alpha_token)
        assert_true(code == 201, "POST /api/members/{id}/trusted-contacts adds contact")
        assert_true(created_tc["phone"] == "+91 98765 43210", "Contact phone normalized to +91 98765 43210")
        test_created_contact_ids.append(created_tc["id"])

        # 4.3 Update Member phone via PUT /api/members/{id}
        code, updated_m = client.request("PUT", f"/api/members/{kiran_id}", {
            "phone": "7654321098"
        }, token=alpha_token)
        assert_true(code == 200, "PUT /api/members/{id} updates phone")
        assert_true(updated_m["phone"] == "+91 76543 21098", "Updated phone normalized to +91 76543 21098")

        # 4.4 Reject Invalid Phone on API
        code, err_resp = client.request("POST", "/api/members", {
            "name": "Invalid Phone Test",
            "phone": "1234567890"
        }, token=alpha_token)
        assert_true(code == 422, "API rejects 10-digit starting with 1 with HTTP 422")

        # 4.5 Preserve International Phone on API
        code, intl_m = client.request("POST", "/api/members", {
            "name": "Alex Vance US",
            "relationship": "Cousin",
            "phone": "+1 415 891 3344"
        }, token=alpha_token)
        assert_true(code == 201, "API accepts international phone (+1...)")
        assert_true(intl_m["phone"] == "+1 415 891 3344", "International phone preserved intact without +91")
        test_created_member_ids.append(intl_m["id"])

        # 4.6 Responder Self-Registration via POST /api/auth/register-responder
        resp_username = f"kerala_medic_{int(os.times().system * 1000)}"
        code, resp_reg = client.request("POST", "/api/auth/register-responder", {
            "username": resp_username,
            "password": "SecurePassword123",
            "email": f"{resp_username}@keralamedic.test",
            "phone": "9876543210",
            "full_name": "Dr. Manoj Kumar",
            "organization": "Kerala EMS",
            "badge_id": "KL-EMS-404"
        })
        assert_true(code == 201, "Responder registration succeeds with 10-digit number")
        app_id = resp_reg["application_id"]
        test_created_app_ids.append(app_id)

        # Query DB to verify phone was saved normalized
        db_check = SessionLocal()
        saved_app = db_check.query(models.ResponderApplication).filter(models.ResponderApplication.id == app_id).first()
        assert_true(saved_app is not None and saved_app.phone == "+91 98765 43210", "Responder application phone stored normalized in DB: +91 98765 43210")
        saved_user = db_check.query(models.User).filter(models.User.id == saved_app.user_id).first()
        assert_true(saved_user is not None and saved_user.phone == "+91 98765 43210", "Responder user phone stored normalized in DB: +91 98765 43210")
        test_created_user_ids.append(saved_user.id)
        db_check.close()

        print("\n" + "=" * 80)
        print(f"ALL TESTS COMPLETED SUCCESSFULLY: {passed}/{total} assertions passed!")
        print("=" * 80)
        return True

    finally:
        print("\n[Teardown] Cleaning up temporary test entities...")
        cleanup()
        print("[Teardown] Cleanup completed.")


if __name__ == "__main__":
    success = run_tests()
    if not success:
        sys.exit(1)
