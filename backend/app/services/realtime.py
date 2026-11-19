"""
FamilyConnect AI - Real-Time Incident Coordination Service (Phase 5C)
Provides authenticated WebSocket connection management and role-scoped real-time
broadcasting across multiple browser sessions.
"""

import json
import asyncio
import datetime
import logging
from typing import Dict, List, Optional, Any, Set
from fastapi import WebSocket

logger = logging.getLogger("familyconnect.realtime")


class AuthenticatedConnection:
    def __init__(
        self,
        websocket: WebSocket,
        user_id: int,
        username: str,
        role: str,
        member_id: Optional[int] = None,
        responder_id: Optional[int] = None,
        household_id: Optional[int] = None
    ):
        self.websocket = websocket
        self.user_id = user_id
        self.username = username
        self.role = role
        self.member_id = member_id
        self.responder_id = responder_id
        self.household_id = household_id
        self.subscribed_incidents: Set[int] = set()
        self.connected_at = datetime.datetime.utcnow()


class RealtimeCoordinationManager:
    def __init__(self):
        self.active_connections: List[AuthenticatedConnection] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def active_count(self) -> int:
        return len(self.active_connections)

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    async def connect(
        self,
        websocket: WebSocket,
        user_id: int,
        username: str,
        role: str,
        member_id: Optional[int] = None,
        responder_id: Optional[int] = None,
        household_id: Optional[int] = None
    ) -> AuthenticatedConnection:
        await websocket.accept()
        conn = AuthenticatedConnection(
            websocket=websocket,
            user_id=user_id,
            username=username,
            role=role,
            member_id=member_id,
            responder_id=responder_id,
            household_id=household_id
        )
        self.active_connections.append(conn)
        logger.info(
            f"[Realtime] WebSocket connected: user='{conn.username}' (role='{conn.role}', "
            f"household={conn.household_id}, active_sessions={len(self.active_connections)})"
        )
        return conn

    async def disconnect(self, conn: Optional[AuthenticatedConnection]):
        if conn and conn in self.active_connections:
            self.active_connections.remove(conn)
            logger.info(
                f"[Realtime] WebSocket disconnected: user='{conn.username}' "
                f"(active_sessions={len(self.active_connections)})"
            )

    async def send_personal_message(self, conn: AuthenticatedConnection, payload: Dict[str, Any]):
        try:
            await conn.websocket.send_text(json.dumps(payload, default=str))
        except Exception as exc:
            logger.debug(f"[Realtime] Failed sending to '{conn.username}': {exc}")
            await self.disconnect(conn)

    async def broadcast_incident_update(
        self,
        event_type: str,
        incident_id: int,
        assigned_responder_ids: List[int],
        payload: Optional[Dict[str, Any]] = None,
        household_id: Optional[int] = None
    ):
        """
        Broadcasts an incident update strictly to authorized sessions:
        - 'admin' and 'member' receive incident updates only if they belong to the incident's household.
        - 'responder' receives updates ONLY if their responder_id is in assigned_responder_ids.
        - Any connection explicitly authorized and subscribed to this incident also receives the update.
        """
        now_iso = datetime.datetime.utcnow().isoformat() + "Z"
        stale_conns = []
        assigned_set = set(assigned_responder_ids or [])
        inc_household = household_id

        for conn in list(self.active_connections):
            try:
                should_send = False
                if conn.role in ("admin", "member"):
                    conn_household = conn.household_id or conn.user_id
                    if inc_household is not None and conn_household == inc_household:
                        should_send = True
                    elif incident_id in conn.subscribed_incidents:
                        should_send = True
                elif conn.role == "responder":
                    if conn.responder_id and conn.responder_id in assigned_set:
                        should_send = True
                    elif incident_id in conn.subscribed_incidents:
                        should_send = True

                if should_send:
                    msg = {
                        "event_type": event_type,
                        "incident_id": incident_id,
                        "timestamp": now_iso,
                        "payload": payload or {}
                    }
                    await conn.websocket.send_text(json.dumps(msg, default=str))
            except Exception:
                stale_conns.append(conn)

        for sc in stale_conns:
            await self.disconnect(sc)

    def broadcast_from_sync(
        self,
        event_type: str,
        incident_id: int,
        assigned_responder_ids: List[int],
        payload: Optional[Dict[str, Any]] = None,
        household_id: Optional[int] = None
    ):
        """
        Thread-safe helper to trigger WebSocket broadcast from synchronous FastAPI endpoints.
        """
        if not self.active_connections:
            return

        try:
            import anyio
            anyio.from_thread.run(
                self.broadcast_incident_update,
                event_type,
                incident_id,
                assigned_responder_ids,
                payload,
                household_id
            )
            return
        except Exception:
            pass

        if self._loop and self._loop.is_running():
            coro = self.broadcast_incident_update(
                event_type=event_type,
                incident_id=incident_id,
                assigned_responder_ids=assigned_responder_ids,
                payload=payload,
                household_id=household_id
            )
            asyncio.run_coroutine_threadsafe(coro, self._loop)

    async def broadcast_household_location(
        self,
        event_type: str,
        household_id: int,
        payload: Dict[str, Any]
    ):
        """
        Broadcasts member location telemetry strictly to authorized sessions
        in the specified household. Cross-household sessions never receive these events.
        """
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        stale_conns = []

        for conn in list(self.active_connections):
            try:
                conn_household = conn.household_id or conn.user_id
                if conn.role in ("admin", "member") and conn_household == household_id:
                    msg = {
                        "event_type": event_type,
                        "household_id": household_id,
                        "timestamp": now_iso,
                        "payload": payload
                    }
                    await conn.websocket.send_text(json.dumps(msg, default=str))
            except Exception:
                stale_conns.append(conn)

        for sc in stale_conns:
            await self.disconnect(sc)

    def broadcast_household_location_from_sync(
        self,
        event_type: str,
        household_id: int,
        payload: Dict[str, Any]
    ):
        """
        Thread-safe helper to trigger WebSocket location broadcast from synchronous FastAPI endpoints.
        """
        if not self.active_connections:
            return

        try:
            import anyio
            anyio.from_thread.run(
                self.broadcast_household_location,
                event_type,
                household_id,
                payload
            )
            return
        except Exception:
            pass

        if self._loop and self._loop.is_running():
            coro = self.broadcast_household_location(
                event_type=event_type,
                household_id=household_id,
                payload=payload
            )
            asyncio.run_coroutine_threadsafe(coro, self._loop)


realtime_manager = RealtimeCoordinationManager()
