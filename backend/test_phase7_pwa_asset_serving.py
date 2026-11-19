"""
Phase 7: PWA Asset Serving & Static Mount Security Test Suite
Tests FastAPI production PWA static asset delivery, MIME types, cache headers,
missing asset handling, and non-interference with /api/* routes.
Zero external test client dependencies (pure standard library ASGI runner).
"""
import os
import sys
import json
import hashlib
import asyncio
import unittest
from pathlib import Path
from typing import Dict, Any

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Mock environment and disable DB migrations before importing main app
os.environ["ENVIRONMENT"] = "development"
os.environ["MOCK_NOTIFICATIONS"] = "true"
os.environ["SKIP_STARTUP_MIGRATION"] = "true"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-pwa-asset-testing-only-32bytes"

from app.main import app, FRONTEND_DIST


def compute_file_sha256(file_path: Path) -> str:
    """Computes SHA-256 hash of a file using shared read mode."""
    if not file_path.exists():
        return ""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().upper()


class AsgiResponse:
    """Lightweight HTTP response container for ASGI test invocations."""
    def __init__(self, status_code: int, headers: list, body: bytes):
        self.status_code = status_code
        self.headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in headers}
        self.content = body

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text)


class AsgiClient:
    """
    Direct ASGI3 in-memory client that dispatches requests straight into FastAPI.
    Provides complete end-to-end routing, middleware, and response handling
    without requiring httpx.
    """
    def __init__(self, asgi_app):
        self.app = asgi_app

    def get(self, path: str, headers: Dict[str, str] = None) -> AsgiResponse:
        return self.request("GET", path, headers=headers)

    def request(
        self,
        method: str,
        path: str,
        headers: Dict[str, str] = None
    ) -> AsgiResponse:
        req_headers = [(b"host", b"testserver")]
        if headers:
            for k, v in headers.items():
                req_headers.append((k.lower().encode("latin1"), v.encode("latin1")))

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.0"},
            "http_version": "1.1",
            "method": method.upper(),
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
                "body": b"",
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


class TestPhase7PwaAssetServing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = AsgiClient(app)
        cls.db_path = backend_dir / "familyconnect.db"
        cls.pre_db_hash = compute_file_sha256(cls.db_path)
        cls.expected_db_hash = "7BBA36C52CD6C47F55211FDD03AC9DE4508072AD5553FDDB6B6AF99CC88CE195"
        cls.model_v2_path = backend_dir / "app" / "ai" / "triage_model_v2.joblib"
        cls.model_v1_path = backend_dir / "app" / "ai" / "triage_model.joblib"
        cls.expected_model_v2_hash = "9770748D0B265984181CCF46645142E9A5F8E530248CFF7E0BE8AD13EB071A17"
        cls.expected_model_v1_hash = "FAB67BD65801D60358B222268D112AFA64238E19D54D8CB2EB31441FC60C5320"

    @classmethod
    def tearDownClass(cls):
        post_db_hash = compute_file_sha256(cls.db_path)
        assert post_db_hash == cls.pre_db_hash, (
            f"DB integrity violation: pre-test was {cls.pre_db_hash}, got {post_db_hash}"
        )
        assert compute_file_sha256(cls.model_v2_path) == cls.expected_model_v2_hash, "ML model v2 hash changed!"
        assert compute_file_sha256(cls.model_v1_path) == cls.expected_model_v1_hash, "ML model v1 hash changed!"

    def test_pwa_01_manifest_webmanifest_serving_and_content_type(self):
        """Test GET /manifest.webmanifest returns HTTP 200 and application/manifest+json."""
        manifest_file = FRONTEND_DIST / "manifest.webmanifest"
        if not manifest_file.exists():
            self.skipTest("frontend/dist/manifest.webmanifest does not exist (run npm run build in frontend/)")

        resp = self.client.get("/manifest.webmanifest")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/manifest+json", resp.headers.get("content-type", ""))
        data = resp.json()
        self.assertEqual(data.get("short_name"), "FamilyConnect")
        self.assertEqual(data.get("display"), "standalone")
        self.assertEqual(data.get("start_url"), "/")

    def test_pwa_02_manifest_json_alias_serving(self):
        """Test GET /manifest.json alias works identically for legacy PWA crawlers."""
        manifest_file = FRONTEND_DIST / "manifest.webmanifest"
        if not manifest_file.exists():
            self.skipTest("frontend/dist/manifest.webmanifest does not exist")

        resp = self.client.get("/manifest.json")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/manifest+json", resp.headers.get("content-type", ""))

    def test_pwa_03_service_worker_serving_and_no_cache_headers(self):
        """Test GET /sw.js returns HTTP 200, application/javascript, and no-cache headers."""
        sw_file = FRONTEND_DIST / "sw.js"
        if not sw_file.exists():
            self.skipTest("frontend/dist/sw.js does not exist")

        resp = self.client.get("/sw.js")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/javascript", resp.headers.get("content-type", ""))
        cache_control = resp.headers.get("cache-control", "")
        self.assertIn("no-cache", cache_control)
        self.assertIn("no-store", cache_control)
        self.assertIn("must-revalidate", cache_control)
        self.assertIn("familyconnect-static-v2", resp.text)

    def test_pwa_04_icons_192_512_and_svg_serving(self):
        """Test GET /icons/icon-192.png, icon-512.png, and icon.svg return HTTP 200 and image MIME types."""
        icons_dir = FRONTEND_DIST / "icons"
        if not icons_dir.exists():
            self.skipTest("frontend/dist/icons does not exist")

        resp_192 = self.client.get("/icons/icon-192.png")
        self.assertEqual(resp_192.status_code, 200)
        self.assertIn("image/png", resp_192.headers.get("content-type", ""))
        self.assertGreater(len(resp_192.content), 0)

        resp_512 = self.client.get("/icons/icon-512.png")
        self.assertEqual(resp_512.status_code, 200)
        self.assertIn("image/png", resp_512.headers.get("content-type", ""))
        self.assertGreater(len(resp_512.content), 0)

        resp_svg = self.client.get("/icons/icon.svg")
        self.assertEqual(resp_svg.status_code, 200)
        self.assertIn("image/svg+xml", resp_svg.headers.get("content-type", ""))
        self.assertGreater(len(resp_svg.content), 0)

    def test_pwa_05_api_routes_isolation_and_no_shadowing(self):
        """Verify that PWA root mounts do not interfere with API endpoints or documentation."""
        health_resp = self.client.get("/api/health")
        self.assertEqual(health_resp.status_code, 200)
        self.assertEqual(health_resp.json().get("status"), "healthy")

        # Protected API router correctly responds with 401 (dispatched to API, not shadowed)
        topics_resp = self.client.get("/api/first-aid/topics")
        self.assertEqual(topics_resp.status_code, 401)
        self.assertIn("Authentication credentials were not provided", topics_resp.json().get("detail", ""))

        docs_resp = self.client.get("/docs")
        self.assertEqual(docs_resp.status_code, 200)

    def test_pwa_06_nonexistent_route_returns_proper_404(self):
        """Ensure non-existent static paths return clean 404 without crashing."""
        resp = self.client.get("/icons/non_existent_icon.png")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
