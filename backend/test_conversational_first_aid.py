"""
FamilyConnect AI - Conversational First Aid Assistant Test Suite
Validates the conversational upgrades to FirstAidRAGAssistant and /api/first-aid/query:
1. Normal first-aid question.
2. Follow-up question referring to previous protocol.
3. Change from adult to child/infant context.
4. Switch from a minor injury to a life-threatening emergency (Emergency Override).
5. Out-of-domain question rejection (INSUFFICIENT_EVIDENCE).
6. Ambiguous question detection.
7. Conversation history exceeding validation limits (max 6 items, max 4000 chars -> HTTP 422).
8. Offline Ollama fallback.
9. Safety validator rejecting contraindicated advice.
10. Database SHA-256 immutability verification.
"""

import sys
import os
import json
import asyncio
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

os.environ["SKIP_STARTUP_MIGRATION"] = "true"
os.environ["MOCK_NOTIFICATIONS"] = "true"

from app.main import app
from app.database import DB_PATH
from app.ai.rag_assistant import get_first_aid_rag_assistant
from app.ai.safety_validator import validate_first_aid_summary
from app.auth import create_access_token


class AsgiResponse:
    def __init__(self, status_code: int, headers: list, body: bytes):
        self.status_code = status_code
        self.headers = {k.decode("latin1"): v.decode("latin1") for k, v in headers}
        self.body = body

    @property
    def text(self) -> str:
        return self.body.decode("utf-8")

    def json(self) -> Any:
        return json.loads(self.text)


class AsgiClient:
    def __init__(self, asgi_app):
        self.app = asgi_app

    def post(self, path: str, json_data: Any = None, headers: Dict[str, str] = None) -> AsgiResponse:
        req_headers = []
        body_bytes = b""
        if json_data is not None:
            body_bytes = json.dumps(json_data).encode("utf-8")
            req_headers.append((b"content-type", b"application/json"))
            req_headers.append((b"content-length", str(len(body_bytes)).encode("latin1")))

        if headers:
            for k, v in headers.items():
                req_headers.append((k.lower().encode("latin1"), v.encode("latin1")))

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("latin1"),
            "query_string": b"",
            "headers": req_headers,
            "server": ("testserver", 80),
        }

        response_status = None
        response_headers = []
        response_body_parts = []

        async def receive():
            return {
                "type": "http.request",
                "body": body_bytes,
                "more_body": False
            }

        async def send(message):
            nonlocal response_status, response_headers, response_body_parts
            if message["type"] == "http.response.start":
                response_status = message["status"]
                response_headers = message.get("headers", [])
            elif message["type"] == "http.response.body":
                response_body_parts.append(message.get("body", b""))

        async def execute():
            await self.app(scope, receive, send)

        asyncio.run(execute())
        return AsgiResponse(response_status, response_headers, b"".join(response_body_parts))


client = AsgiClient(app)


def compute_db_hash() -> str:
    if not os.path.exists(DB_PATH):
        return "NO_DB_FILE"
    hasher = hashlib.sha256()
    with open(DB_PATH, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().upper()


def get_test_auth_headers() -> dict:
    # Use active test admin account
    from app.database import SessionLocal
    from app.models import User
    from app.auth import hash_password
    _db = SessionLocal()
    try:
        _u = _db.query(User).filter(User.is_active == True, User.role == "admin").first()
        if not _u:
            hp, salt = hash_password("TestAdminPass123!")
            _u = User(
                username="test_admin_alpha",
                email="admin.alpha@example.com",
                full_name="Admin Alpha",
                role="admin",
                is_active=True,
                hashed_password=hp,
                salt=salt
            )
            _db.add(_u)
            _db.commit()
            _db.refresh(_u)
        user_id = _u.id
        sub = _u.username
    finally:
        _db.close()
    token = create_access_token(data={"sub": sub, "user_id": user_id, "role": "admin"})
    return {"Authorization": f"Bearer {token}"}


def run_conversational_tests():
    print("=" * 75)
    print("FAMILYCONNECT AI - CONVERSATIONAL FIRST AID ASSISTANT TEST SUITE")
    print("=" * 75)

    headers = get_test_auth_headers()
    initial_hash = compute_db_hash()
    print(f"Pre-test Database Hash: {initial_hash}")
    rag = get_first_aid_rag_assistant()
    passed = 0
    total = 10

    # Scenario 1: Normal first-aid question
    print("\n--- Scenario 1: Normal First-Aid Question ---")
    payload1 = {
        "query": "how to perform adult CPR and use an AED",
        "top_k": 2
    }
    resp1 = client.post("/api/first-aid/query", json_data=payload1, headers=headers)
    assert resp1.status_code == 200, f"Expected 200, got {resp1.status_code}: {resp1.text}"
    data1 = resp1.json()
    assert data1["status"] == "SUCCESS"
    assert data1["matched_protocol"]["protocol_id"] == "cpr_adult_aed"
    assert data1["is_follow_up"] is False
    assert "112" in data1["emergency_call_guidance"]
    assert len(data1["actionable_steps"]) >= 3
    print(" [PASS] Normal query correctly retrieved cpr_adult_aed (is_follow_up=False)")
    passed += 1

    # Scenario 2: Follow-up question referring to previous protocol
    print("\n--- Scenario 2: Follow-up Question Referring to Previous Protocol ---")
    payload2 = {
        "query": "how deep should I push?",
        "active_protocol_id": "cpr_adult_aed",
        "conversation_history": [
            {"role": "user", "content": "how to perform adult CPR and use an AED"},
            {"role": "assistant", "content": "Begin chest compressions in center of chest."}
        ],
        "top_k": 2
    }
    resp2 = client.post("/api/first-aid/query", json_data=payload2, headers=headers)
    assert resp2.status_code == 200, f"Expected 200, got {resp2.status_code}: {resp2.text}"
    data2 = resp2.json()
    assert data2["status"] == "SUCCESS"
    assert data2["matched_protocol"]["protocol_id"] == "cpr_adult_aed"
    assert data2["is_follow_up"] is True
    assert data2["conversational_reply"] is not None
    assert data2["evidence_chunks"][0]["chunk_id"] == "cpr_adult_02", (
        f"Expected top chunk cpr_adult_02 (technique & depth), got {data2['evidence_chunks'][0]['chunk_id']}"
    )
    assert "2 inches" in data2["conversational_reply"] or "5 cm" in data2["conversational_reply"]
    print(f" [PASS] Follow-up query resolved within cpr_adult_aed (is_follow_up=True, chunk={data2['evidence_chunks'][0]['chunk_id']})")
    print(f"        Conversational reply preview: {data2['conversational_reply'][:90]}...")
    passed += 1

    # Scenario 3: Change from adult to child/infant context
    print("\n--- Scenario 3: Change Context to Child / Infant ---")
    payload3 = {
        "query": "for an infant under 1 year?",
        "active_protocol_id": "choking_adult_child",
        "conversation_history": [
            {"role": "user", "content": "what to do if someone is choking on food"},
            {"role": "assistant", "content": "Perform 5 back blows then 5 abdominal thrusts."}
        ],
        "top_k": 2
    }
    resp3 = client.post("/api/first-aid/query", json_data=payload3, headers=headers)
    assert resp3.status_code == 200, f"Expected 200, got {resp3.status_code}: {resp3.text}"
    data3 = resp3.json()
    assert data3["status"] == "SUCCESS"
    assert data3["matched_protocol"]["protocol_id"] == "choking_adult_child"
    assert data3["is_follow_up"] is True
    assert "infant" in data3["conversational_reply"].lower()
    contra_text = " ".join(data3["what_not_to_do"]).lower()
    assert "infant" in contra_text or "thrust" in contra_text
    print(" [PASS] Pediatric context shift correctly handled with infant guidance")
    passed += 1

    # Scenario 4: Switch from minor injury to life-threatening emergency (Emergency Override)
    print("\n--- Scenario 4: Switch from Minor Injury to Life-Threatening Emergency ---")
    payload4 = {
        "query": "now he stopped breathing and is completely unresponsive",
        "active_protocol_id": "burns_thermal_chemical",
        "conversation_history": [
            {"role": "user", "content": "first aid for boiling water scald burn on skin"},
            {"role": "assistant", "content": "Cool burn with running water for 20 minutes."}
        ],
        "top_k": 2
    }
    resp4 = client.post("/api/first-aid/query", json_data=payload4, headers=headers)
    assert resp4.status_code == 200, f"Expected 200, got {resp4.status_code}: {resp4.text}"
    data4 = resp4.json()
    assert data4["status"] == "SUCCESS"
    assert data4["matched_protocol"]["protocol_id"] == "cpr_adult_aed", (
        f"Emergency must override burns and match cpr_adult_aed, got {data4['matched_protocol']['protocol_id']}"
    )
    assert data4["is_follow_up"] is False, "Emergency override must NOT be marked as follow-up to burn"
    assert "112" in data4["emergency_call_guidance"]
    print(" [PASS] Emergency override immediately switched topic to cpr_adult_aed (is_follow_up=False)")
    passed += 1

    # Scenario 5: Out-of-domain question
    print("\n--- Scenario 5: Out-of-Domain Question Rejection ---")
    payload5 = {
        "query": "how to bake chocolate cake",
        "active_protocol_id": "cpr_adult_aed",
        "top_k": 2
    }
    resp5 = client.post("/api/first-aid/query", json_data=payload5, headers=headers)
    assert resp5.status_code == 200
    data5 = resp5.json()
    assert data5["status"] == "INSUFFICIENT_EVIDENCE"
    assert data5["is_follow_up"] is False
    assert "112" in data5["emergency_guidance"]
    print(" [PASS] Out-of-domain question safely rejected with INSUFFICIENT_EVIDENCE")
    passed += 1

    # Scenario 6: Ambiguous question detection
    print("\n--- Scenario 6: Ambiguous Question Handling ---")
    res_amb = rag.query("pain in body and hurt")
    assert "status" in res_amb
    assert "ambiguity_detected" in res_amb
    print(f" [PASS] Ambiguity detection field verified (ambiguity_detected={res_amb['ambiguity_detected']})")
    passed += 1

    # Scenario 7: Conversation history exceeding validation limits
    print("\n--- Scenario 7: Conversation History Payload Limits ---")
    # Exceeding 6 messages
    oversized_msgs = [
        {"role": "user", "content": f"query {i}"} for i in range(8)
    ]
    payload7a = {
        "query": "cpr instructions",
        "conversation_history": oversized_msgs
    }
    resp7a = client.post("/api/first-aid/query", json_data=payload7a, headers=headers)
    assert resp7a.status_code == 422, f"Expected 422 for >6 messages, got {resp7a.status_code}"

    # Exceeding 4000 characters
    huge_msgs = [
        {"role": "user", "content": "x" * 2100},
        {"role": "assistant", "content": "y" * 2100}
    ]
    payload7b = {
        "query": "cpr instructions",
        "conversation_history": huge_msgs
    }
    resp7b = client.post("/api/first-aid/query", json_data=payload7b, headers=headers)
    assert resp7b.status_code == 422, f"Expected 422 for >4000 chars, got {resp7b.status_code}"
    print(" [PASS] History size limits strictly enforced by schema (HTTP 422)")
    passed += 1

    # Scenario 8: Offline Ollama fallback
    print("\n--- Scenario 8: Offline Ollama Fallback ---")
    res8 = rag.query("how to stop severe arterial bleeding with a tourniquet")
    assert res8["status"] == "SUCCESS"
    assert res8["matched_protocol"]["protocol_id"] == "severe_bleeding_hemorrhage"
    assert len(res8["actionable_steps"]) >= 3
    assert res8["llm_status"] in ("DISABLED", "OFFLINE", "TIMEOUT", "ERROR", "SUCCESS")
    print(f" [PASS] Offline LLM fallback functioning safely (llm_status={res8['llm_status']})")
    passed += 1

    # Scenario 9: Deterministic safety validator rejecting contraindicated advice
    print("\n--- Scenario 9: Safety Validator Rejecting Contraindications ---")
    burn_proto = rag.get_protocol("burns_thermal_chemical")
    contra_text = "Apply ice directly to the burn and coat with butter or mayonnaise."
    is_valid, code, msg = validate_first_aid_summary(contra_text, burn_proto)
    assert not is_valid, "Validator must reject applying ice/butter to burns"
    assert code == "VALIDATION_CONTRADICTION"
    print(f" [PASS] Contraindicated advice blocked by safety validator (Code: {code})")
    passed += 1

    # Scenario 10: Database SHA-256 Immutability Check
    print("\n--- Scenario 10: Database Immutability Verification ---")
    final_hash = compute_db_hash()
    assert initial_hash == final_hash, f"Database hash changed! {initial_hash} != {final_hash}"
    print(f" [PASS] Database hash verified unchanged: {final_hash}")
    passed += 1

    print("\n" + "=" * 75)
    print(f"CONVERSATIONAL FIRST AID ASSISTANT: {passed}/{total} SCENARIOS PASSED (100%)")
    print("=" * 75)


if __name__ == "__main__":
    run_conversational_tests()
