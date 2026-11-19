import os
import asyncio
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Explicitly load .env from project root or backend folder
_root_env = Path(__file__).resolve().parent.parent.parent / ".env"
_backend_env = Path(__file__).resolve().parent.parent / ".env"
if _root_env.exists():
    load_dotenv(dotenv_path=_root_env)
elif _backend_env.exists():
    load_dotenv(dotenv_path=_backend_env)
else:
    load_dotenv()
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from .database import engine, Base, SessionLocal
from .models import Member, Responder, EmergencyIncident, User
from .seed_data import seed_database
from .ai.triage import get_model
from .routes import members, responders, emergencies, auth, household, admin, first_aid
from .auth import check_production_security, decode_access_token, is_token_revoked, logger
from .migrate_db import run_migration
from .services.realtime import realtime_manager
from .services.notifications import get_notification_config_status


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Register running asyncio loop for thread-safe WebSocket broadcasts
    realtime_manager.set_event_loop(asyncio.get_running_loop())

    # Enforce production security constraints if ENVIRONMENT=production
    check_production_security()

    # Safe schema migration & tables creation (preserves existing DB)
    if os.environ.get("SKIP_STARTUP_MIGRATION", "").lower() not in ("true", "1", "yes"):
        run_migration()
        if os.environ.get("ENVIRONMENT", "development").lower() != "production":
            db = SessionLocal()
            try:
                seed_database(db)
            finally:
                db.close()

    # Pre-warm AI triage model
    try:
        get_model()
        print("[Startup] Scikit-learn triage model verified and loaded.")
    except Exception as e:
        print(f"[Startup] Error loading AI model: {e}")

    yield


app = FastAPI(
    title="FamilyConnect AI API",
    description="AI-Powered Family Emergency Response and Safety Platform",
    version="1.2.0",
    lifespan=lifespan
)

# Configure safe, restricted CORS origins (never unrestricted "*" with credentials)
DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# Allow private network IP patterns (RFC 1918) for local Wi-Fi mobile testing (192.168.x.x, 10.x.x.x, 172.16-31.x.x)
# Public untrusted domains (e.g. evil.com) are strictly disallowed
PRIVATE_NETWORK_ORIGIN_REGEX = (
    r"^https?://(localhost|127\.0\.0\.1"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})"
    r"(:\d+)?$"
)


def get_cors_configuration(env: Optional[str] = None) -> tuple[list[str], Optional[str]]:
    """
    Compute allowed CORS origins and optional regex according to deployment environment.
    - Production: Allows ONLY explicitly configured origins from ALLOWED_ORIGINS/CORS_ORIGINS
      and FRONTEND_PUBLIC_URL. Disables localhost defaults and private network regex.
    - Development: Permits localhost development ports and private network RFC 1918 regex for mobile testing.
    """
    if env is None:
        env = os.environ.get("ENVIRONMENT", "development").lower()
    is_prod = (env == "production")

    configured_origins: list[str] = []
    raw_origins = (os.environ.get("ALLOWED_ORIGINS") or os.environ.get("CORS_ORIGINS") or "").strip()
    if raw_origins and raw_origins != "*":
        configured_origins.extend([o.strip().rstrip("/") for o in raw_origins.split(",") if o.strip()])

    frontend_pub = (os.environ.get("FRONTEND_PUBLIC_URL") or "").strip().rstrip("/")
    if frontend_pub and frontend_pub.startswith(("http://", "https://")):
        if frontend_pub not in configured_origins:
            configured_origins.append(frontend_pub)

    if is_prod:
        allowed = list(dict.fromkeys(configured_origins))
        origin_regex = None
    else:
        allowed = list(dict.fromkeys(DEFAULT_ALLOWED_ORIGINS + configured_origins))
        origin_regex = PRIVATE_NETWORK_ORIGIN_REGEX

    return allowed, origin_regex


cors_allowed_origins, cors_origin_regex = get_cors_configuration()

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins,
    allow_origin_regex=cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth.router)
app.include_router(household.router)
app.include_router(admin.router)
app.include_router(members.router)
app.include_router(responders.router)
app.include_router(emergencies.router)
app.include_router(first_aid.router)


@app.websocket("/api/ws/incidents")
async def websocket_incidents_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """
    Phase 5C: Authenticated Real-Time Incident Coordination WebSocket.
    - Verifies authentication bearer token on connection.
    - Enforces role-based authorization on live broadcasts and incident subscriptions.
    - Responders only receive events for incidents to which they are assigned.
    """
    raw_token = token
    if not raw_token:
        auth_header = websocket.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            raw_token = auth_header.split(" ", 1)[1].strip()

    if not raw_token:
        logger.warning("[WebSocket Security] Rejected unauthenticated connection (missing token)")
        await websocket.close(code=1008, reason="Missing authentication token")
        return

    try:
        payload = decode_access_token(raw_token)
    except Exception as exc:
        logger.warning(f"[WebSocket Security] Rejected invalid token connection: {exc}")
        await websocket.close(code=1008, reason="Invalid or expired authentication token")
        return

    db = SessionLocal()
    try:
        if is_token_revoked(raw_token, db):
            logger.warning("[WebSocket Security] Rejected connection: Token has been revoked")
            await websocket.close(code=1008, reason="Authentication token has been revoked")
            return

        user_id = payload.get("user_id")
        user = db.query(User).filter(User.id == user_id).first()
        token_sub = payload.get("sub")
        if (
            not user
            or (token_sub and user.username != token_sub)
            or not getattr(user, "is_active", True)
            or getattr(user, "verification_status", "APPROVED") != "APPROVED"
        ):
            logger.warning("[WebSocket Security] Rejected connection for inactive, unverified, missing, or mismatched user")
            await websocket.close(code=1008, reason="User account not active")
            return

        owner_id = getattr(user, "household_id", None) or user.id
        if user.member_id:
            curr_m = db.query(Member).filter(Member.id == user.member_id).first()
            if curr_m and curr_m.user_id:
                owner_id = curr_m.user_id

        user_info = {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "member_id": user.member_id,
            "responder_id": user.responder_id,
            "household_id": owner_id
        }
    finally:
        db.close()

    conn = await realtime_manager.connect(
        websocket=websocket,
        user_id=user_info["id"],
        username=user_info["username"],
        role=user_info["role"],
        member_id=user_info["member_id"],
        responder_id=user_info["responder_id"],
        household_id=user_info["household_id"]
    )

    try:
        await websocket.send_json({
            "event_type": "CONNECTED",
            "user": user_info,
            "active_connections": realtime_manager.active_count
        })

        while True:
            data = await websocket.receive_json()
            action = (data.get("action") or "").strip().lower()

            if action == "ping":
                await websocket.send_json({"event_type": "PONG"})

            elif action == "subscribe_incident":
                inc_id = data.get("incident_id")
                db_sub = SessionLocal()
                try:
                    incident = db_sub.query(EmergencyIncident).filter(EmergencyIncident.id == inc_id).first()
                    if not incident:
                        await websocket.send_json({
                            "event_type": "ERROR",
                            "code": 404,
                            "incident_id": inc_id,
                            "detail": "Incident not found"
                        })
                        continue

                    if user_info["role"] == "responder":
                        assigned_ids = [ir.responder_id for ir in incident.assigned_responders]
                        if user_info["responder_id"] not in assigned_ids:
                            logger.warning(
                                f"[WebSocket Security] Responder '{user_info['username']}' "
                                f"(ResponderID {user_info['responder_id']}) denied subscription to unassigned Incident #{inc_id}"
                            )
                            await websocket.send_json({
                                "event_type": "SUBSCRIPTION_DENIED",
                                "code": 403,
                                "incident_id": inc_id,
                                "detail": "Forbidden: Responders cannot subscribe to unassigned incidents"
                            })
                            continue
                    else:
                        inc_household = incident.user_id
                        user_household = user_info.get("household_id") or user_info.get("id")
                        if inc_household is None or inc_household != user_household:
                            logger.warning(
                                f"[WebSocket Security] Cross-tenant subscription denied: User '{user_info['username']}' "
                                f"(Household {user_household}) attempted to subscribe to Incident #{inc_id} (Household {inc_household})"
                            )
                            await websocket.send_json({
                                "event_type": "SUBSCRIPTION_DENIED",
                                "code": 403,
                                "incident_id": inc_id,
                                "detail": "Forbidden: Cannot subscribe to another household's private incidents"
                            })
                            continue

                    conn.subscribed_incidents.add(inc_id)
                    await websocket.send_json({
                        "event_type": "SUBSCRIBED",
                        "incident_id": inc_id,
                        "status": incident.status
                    })
                finally:
                    db_sub.close()

    except WebSocketDisconnect:
        await realtime_manager.disconnect(conn)
    except Exception:
        await realtime_manager.disconnect(conn)


# Optional production static serving when frontend/dist is built
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="frontend_assets")

# Mount PWA icons directory when available
if (FRONTEND_DIST / "icons").exists():
    app.mount("/icons", StaticFiles(directory=str(FRONTEND_DIST / "icons")), name="frontend_icons")


@app.get("/manifest.webmanifest", include_in_schema=False)
@app.get("/manifest.json", include_in_schema=False)
def serve_manifest():
    manifest_file = FRONTEND_DIST / "manifest.webmanifest"
    if manifest_file.exists():
        return FileResponse(
            str(manifest_file),
            media_type="application/manifest+json",
            headers={"Cache-Control": "public, max-age=3600"}
        )
    return JSONResponse({"detail": "Manifest not found"}, status_code=404)


@app.get("/sw.js", include_in_schema=False)
def serve_service_worker():
    sw_file = FRONTEND_DIST / "sw.js"
    if sw_file.exists():
        return FileResponse(
            str(sw_file),
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
        )
    return JSONResponse({"detail": "Service worker not found"}, status_code=404)


@app.api_route("/", methods=["GET", "HEAD"], tags=["General"])
def root(request: Request):
    accept = request.headers.get("accept", "")
    if "text/html" in accept and (FRONTEND_DIST / "index.html").exists():
        return FileResponse(str(FRONTEND_DIST / "index.html"))
    return {
        "platform": "FamilyConnect AI",
        "status": "Online",
        "documentation": "/docs",
        "version": "1.2.0"
    }


@app.get("/app", include_in_schema=False)
def serve_spa():
    if (FRONTEND_DIST / "index.html").exists():
        return FileResponse(str(FRONTEND_DIST / "index.html"))
    return JSONResponse({"detail": "Frontend build not found. Run npm run build in frontend/."}, status_code=404)


@app.api_route("/api/health", methods=["GET", "HEAD"], tags=["General"])
def health_check():
    notif_status = get_notification_config_status()
    db_dialect = getattr(getattr(engine, "dialect", None), "name", "unknown")
    return {
        "status": "healthy",
        "database": f"{db_dialect}_connected",
        "ai_engine": "scikit-learn_active",
        "realtime_ws": "enabled",
        "active_ws_connections": realtime_manager.active_count,
        "notifications_live_ready": notif_status["live_delivery_available"]
    }
