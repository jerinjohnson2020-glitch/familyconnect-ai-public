import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import (
    EmergencyIncident,
    IncidentResponder,
    Responder,
    Member,
    IncidentTimelineEvent,
    IncidentAlert,
    User,
    TrustedContact
)
from ..schemas import (
    IncidentCreate,
    IncidentResponse,
    IncidentStatusUpdate,
    IncidentLocationUpdate,
    AIAssessmentResponse,
    ResponderMatchResponse,
    IncidentTimelineEventResponse,
    IncidentAlertResponse,
    TestNotificationRequest
)
from ..ai.triage import assess_emergency, rank_responders, calculate_haversine_distance
from ..ai.independent_eval import evaluate_holdout_benchmark
from ..services.notifications import (
    dispatch_contact_notification,
    retry_failed_alert,
    get_notification_config_status,
    send_explicit_test_notification
)
from ..services.realtime import realtime_manager
from ..auth import (
    get_current_user,
    require_admin,
    require_member_or_admin,
    mask_phone_number,
    logger
)

router = APIRouter(prefix="/api/emergencies", tags=["Emergency SOS & Triage"])


def get_household_owner_id(current_user: User, db: Session) -> int:
    """Resolve the household owner ID for a user (admins own themselves, members link to their household)."""
    if getattr(current_user, "household_id", None):
        return current_user.household_id
    if current_user.member_id:
        curr_m = db.query(Member).filter(Member.id == current_user.member_id).first()
        if curr_m and curr_m.user_id:
            return curr_m.user_id
    return current_user.id


def format_alert_response(al: IncidentAlert, user_role: str = "admin") -> IncidentAlertResponse:
    contact_phone = al.contact_phone
    contact_email = al.contact_email
    if user_role == "responder":
        contact_phone = mask_phone_number(al.contact_phone)
        if contact_email and "@" in contact_email:
            parts = contact_email.split("@", 1)
            contact_email = f"{parts[0][:1]}***@{parts[1]}"

    return IncidentAlertResponse(
        id=al.id,
        incident_id=al.incident_id,
        contact_id=al.contact_id,
        contact_name=al.contact_name,
        contact_phone=contact_phone,
        contact_email=contact_email,
        channel=al.channel,
        status=al.status,
        provider=al.provider,
        provider_message_id=al.provider_message_id,
        delivery_attempts=al.delivery_attempts if al.delivery_attempts is not None else 0,
        last_attempt_at=al.last_attempt_at,
        delivered_at=al.delivered_at,
        error_message=al.error_message,
        sent_at=al.sent_at,
        acknowledged_at=al.acknowledged_at
    )


def format_incident_response(incident: EmergencyIncident, user_role: str = "admin") -> IncidentResponse:
    """
    Format incident response with role-based data redaction.
    For responders, sensitive family phone numbers are masked.
    """
    matched = []
    for ir in incident.assigned_responders:
        responder_phone = ir.responder.phone
        if user_role == "responder":
            responder_phone = mask_phone_number(ir.responder.phone)

        matched.append(ResponderMatchResponse(
            id=ir.id,
            assignment_id=ir.id,
            responder_id=ir.responder_id,
            name=ir.responder.name,
            role=ir.responder.role,
            organization=ir.responder.organization,
            phone=responder_phone,
            skills=ir.responder.skills,
            distance_km=ir.distance_km,
            is_available=bool(ir.responder.is_available),
            location_source=ir.responder.location_source,
            location_updated_at=ir.responder.location_updated_at,
            status=ir.status,
            assigned_at=ir.assigned_at,
            accepted_at=ir.accepted_at,
            en_route_at=ir.en_route_at,
            arrived_at=ir.arrived_at,
            updated_at=ir.updated_at
        ))

    timeline = []
    for te in (incident.timeline_events or []):
        timeline.append(IncidentTimelineEventResponse(
            id=te.id,
            incident_id=te.incident_id,
            event_type=te.event_type,
            title=te.title,
            description=te.description,
            timestamp=te.timestamp
        ))
    timeline.sort(key=lambda x: x.timestamp)

    alerts = [format_alert_response(al, user_role=user_role) for al in (incident.alerts or [])]
    alerts.sort(key=lambda x: x.sent_at)

    return IncidentResponse(
        id=incident.id,
        member_id=incident.member_id,
        reporter_name=incident.reporter_name,
        incident_type=incident.incident_type,
        description=incident.description,
        latitude=incident.latitude,
        longitude=incident.longitude,
        location_label=incident.location_label or "Current Location",
        location_accuracy_m=incident.location_accuracy_m,
        location_source=incident.location_source or "manual",
        location_updated_at=incident.location_updated_at or incident.created_at,
        severity_level=incident.severity_level or "PENDING",
        severity_score=incident.severity_score if incident.severity_score is not None else 0.0,
        ai_rationale=incident.ai_rationale,
        status=incident.status or "ACTIVE",
        created_at=incident.created_at or datetime.datetime.utcnow(),
        resolved_at=incident.resolved_at,
        resolution_notes=incident.resolution_notes,
        matched_responders=matched,
        timeline_events=timeline,
        alerts=alerts
    )


@router.get("", response_model=List[IncidentResponse])
def get_emergencies(
    status: Optional[str] = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve emergency incidents with role-scoped filtering:
    - Admin & Family Member: view all household emergency incidents.
    - Responder: view ONLY incidents where this unit is assigned or recommended.
    """
    query = db.query(EmergencyIncident).order_by(EmergencyIncident.created_at.desc())

    if current_user.role == "responder":
        if not current_user.responder_id:
            logger.warning(f"[Security Audit] Responder user '{current_user.username}' has no linked responder_id.")
            return []

        assigned_inc_ids = [
            r[0] for r in db.query(IncidentResponder.incident_id).filter(
                IncidentResponder.responder_id == current_user.responder_id
            ).all()
        ]
        query = query.filter(EmergencyIncident.id.in_(assigned_inc_ids))
    else:
        # Multi-tenant scoping for family users: strictly scoped to caller's household
        owner_id = get_household_owner_id(current_user, db)
        query = query.filter(EmergencyIncident.user_id == owner_id)

    if status:
        query = query.filter(EmergencyIncident.status == status.upper())

    incidents = query.limit(limit).all()
    return [format_incident_response(inc, user_role=current_user.role) for inc in incidents]


@router.get("/config/notifications")
def get_notification_config(
    current_user: User = Depends(get_current_user)
):
    """
    Report active notification provider configuration status and last explicit test result.
    Never exposes raw API keys or secrets.
    """
    return get_notification_config_status()


@router.post("/config/notifications/test")
def test_notification_delivery(
    payload: TestNotificationRequest,
    current_user: User = Depends(require_member_or_admin)
):
    """
    Phase 6 Section 6: Requires explicit user confirmation (confirm_send=True)
    before sending a test notification to the specified destination.
    """
    if not payload.confirm_send:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Explicit user confirmation (confirm_send=true) is required to send a test notification."
        )
    try:
        result = send_explicit_test_notification(
            channel=payload.channel,
            recipient=payload.recipient,
            confirm_send=payload.confirm_send,
            requested_by=current_user.username
        )
        logger.info(
            f"[Security Audit] User '{current_user.username}' triggered test notification "
            f"via {result['channel']} ({result['provider']}) -> {result['status']}"
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/ai-evaluation")
def get_ai_evaluation_benchmark(
    current_user: User = Depends(get_current_user)
):
    """
    Run and return the independent 40-scenario holdout evaluation benchmark
    comparing Raw ML Model v2 vs Hybrid System (ML v2 + Deterministic Safety Overrides),
    including per-class precision, recall, F1, confusion matrix, and limitations disclosure.
    """
    report = evaluate_holdout_benchmark()
    report["limitations_disclosure"] = (
        "This AI triage model is trained on synthetic and domain-engineered emergency scenarios "
        "and evaluated on an independent 40-scenario holdout suite. It is a decision-support aid "
        "for household emergency coordination, NOT a clinically validated medical device."
    )
    return report


@router.get("/{incident_id}", response_model=IncidentResponse)
def get_emergency_detail(
    incident_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get full details of a specific emergency incident.
    Responders are strictly blocked from accessing incidents to which they are not assigned.
    """
    incident = db.query(EmergencyIncident).filter(EmergencyIncident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Scope verification for responders
    if current_user.role == "responder":
        assigned_units = [ir.responder_id for ir in incident.assigned_responders]
        if current_user.responder_id not in assigned_units:
            logger.warning(
                f"[Security Audit] Unauthorized cross-incident access: Responder '{current_user.username}' "
                f"(ResponderID: {current_user.responder_id}) attempted to view unassigned Incident #{incident_id}."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Responders cannot access unrelated incidents"
            )
    else:
        owner_id = get_household_owner_id(current_user, db)
        if incident.user_id != owner_id:
            logger.warning(
                f"[Security Audit] Cross-tenant incident access: User '{current_user.username}' (ID: {current_user.id}) "
                f"attempted to view Incident #{incident_id} (belonging to User #{incident.user_id})."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You do not have permission to access this incident"
            )

    return format_incident_response(incident, user_role=current_user.role)


@router.get("/{incident_id}/timeline", response_model=List[IncidentTimelineEventResponse])
def get_incident_timeline(
    incident_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve chronological timeline events for a specific incident.
    Requires authentication. Responders can only access timelines of assigned incidents.
    """
    incident = db.query(EmergencyIncident).filter(EmergencyIncident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    if current_user.role == "responder":
        assigned_units = [ir.responder_id for ir in incident.assigned_responders]
        if current_user.responder_id not in assigned_units:
            logger.warning(
                f"[Security Audit] Responder '{current_user.username}' attempted to view timeline "
                f"of unassigned Incident #{incident_id}."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Responders cannot access unrelated incident timelines"
            )
    else:
        owner_id = get_household_owner_id(current_user, db)
        if incident.user_id != owner_id:
            logger.warning(
                f"[Security Audit] Cross-tenant incident access: User '{current_user.username}' (ID: {current_user.id}) "
                f"attempted to view timeline of Incident #{incident_id} (belonging to User #{incident.user_id})."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You do not have permission to access this incident"
            )

    events = db.query(IncidentTimelineEvent).filter(
        IncidentTimelineEvent.incident_id == incident_id
    ).order_by(IncidentTimelineEvent.timestamp.asc()).all()

    return [
        IncidentTimelineEventResponse(
            id=e.id,
            incident_id=e.incident_id,
            event_type=e.event_type,
            title=e.title,
            description=e.description,
            timestamp=e.timestamp
        )
        for e in events
    ]


@router.get("/{incident_id}/alerts", response_model=List[IncidentAlertResponse])
def get_incident_alerts(
    incident_id: int,
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db)
):
    """
    Retrieve trusted contact alerts for an incident.
    Restricted to Family Administrators and Family Members.
    Responders cannot view private family notification lists.
    """
    incident = db.query(EmergencyIncident).filter(EmergencyIncident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    owner_id = get_household_owner_id(current_user, db)
    if incident.user_id != owner_id:
        logger.warning(
            f"[Security Audit] Cross-tenant alerts access: User '{current_user.username}' (ID: {current_user.id}) "
            f"attempted to view alerts of Incident #{incident_id} (belonging to User #{incident.user_id})."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to access this incident"
        )

    alerts = db.query(IncidentAlert).filter(
        IncidentAlert.incident_id == incident_id
    ).order_by(IncidentAlert.sent_at.asc()).all()

    return [format_alert_response(a, user_role=current_user.role) for a in alerts]


@router.post("/{incident_id}/alerts/{alert_id}/acknowledge", response_model=IncidentAlertResponse)
def acknowledge_incident_alert(
    incident_id: int = Path(..., description="Incident ID"),
    alert_id: int = Path(..., description="Alert ID to acknowledge"),
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db)
):
    """
    Acknowledge receipt of a family emergency notification.
    Strictly validates that the targeted alert belongs to the targeted incident.
    Restricted to Family Administrators and Family Members.
    """
    incident = db.query(EmergencyIncident).filter(EmergencyIncident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    owner_id = get_household_owner_id(current_user, db)
    if incident.user_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to access this incident"
        )

    alert = db.query(IncidentAlert).filter(IncidentAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    # Strict targeting validation to prevent cross-incident manipulation
    if alert.incident_id != incident_id:
        logger.warning(
            f"[Security Audit] Alert targeting violation: User '{current_user.username}' attempted to acknowledge "
            f"Alert #{alert_id} (belonging to Incident #{alert.incident_id}) via route for Incident #{incident_id}."
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Security violation: Alert #{alert_id} does not belong to Incident #{incident_id}"
        )

    if alert.status != "ACKNOWLEDGED":
        alert.status = "ACKNOWLEDGED"
        alert.acknowledged_at = datetime.datetime.utcnow()

        timeline_event = IncidentTimelineEvent(
            incident_id=incident_id,
            event_type="ALERT_ACKNOWLEDGED",
            title=f"Alert Acknowledged by {alert.contact_name}",
            description=f"Trusted contact confirmed emergency receipt via {alert.channel}.",
            timestamp=datetime.datetime.utcnow()
        )
        db.add(timeline_event)
        db.commit()
        db.refresh(alert)
        logger.info(f"[Security Audit] User '{current_user.username}' acknowledged Alert #{alert_id} for Incident #{incident_id}")

        assigned_ids = [ir.responder_id for ir in incident.assigned_responders]
        realtime_manager.broadcast_from_sync(
            event_type="ALERT_ACKNOWLEDGED",
            incident_id=incident.id,
            assigned_responder_ids=assigned_ids,
            payload={
                "incident_id": incident.id,
                "alert_id": alert.id,
                "contact_name": alert.contact_name,
                "status": alert.status,
                "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None
            },
            household_id=incident.user_id
        )

    return format_alert_response(alert, user_role=current_user.role)


@router.post("/{incident_id}/alerts/{alert_id}/retry", response_model=IncidentAlertResponse)
def retry_incident_alert(
    incident_id: int = Path(..., description="Incident ID"),
    alert_id: int = Path(..., description="Alert ID to retry"),
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db)
):
    """
    Retry sending a failed or unconfigured trusted-contact notification.
    Restricted to Family Administrators and Family Members.
    """
    incident = db.query(EmergencyIncident).filter(EmergencyIncident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    owner_id = get_household_owner_id(current_user, db)
    if incident.user_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to access this incident"
        )

    alert = db.query(IncidentAlert).filter(IncidentAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    if alert.incident_id != incident_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Security violation: Alert #{alert_id} does not belong to Incident #{incident_id}"
        )

    alert = retry_failed_alert(db=db, incident=incident, alert=alert)
    now = datetime.datetime.utcnow()

    if alert.status in ("DELIVERED", "SENT"):
        tl_title = f"Trusted Contact Alert Delivered on Retry ({alert.contact_name})"
        tl_desc = (
            f"Live {alert.channel} notification delivered via {alert.provider} "
            f"(Attempt #{alert.delivery_attempts}, Ref: {alert.provider_message_id or 'N/A'})."
        )
    elif alert.status == "SIMULATED":
        tl_title = f"Trusted Contact Alert Simulated on Retry ({alert.contact_name})"
        tl_desc = (
            f"Simulated {alert.channel} notification ({alert.provider}) on retry "
            f"(Attempt #{alert.delivery_attempts}, Ref: {alert.provider_message_id or 'N/A'}). "
            f"External delivery suppressed (mock mode). Contact was NOT notified."
        )
    else:
        tl_title = f"Trusted Contact Alert Retry Failed ({alert.contact_name})"
        tl_desc = (
            f"Retry attempt #{alert.delivery_attempts} via {alert.channel} ({alert.provider}) "
            f"remained {alert.status}: {alert.error_message or 'Unknown error'}"
        )

    db.add(IncidentTimelineEvent(
        incident_id=incident_id,
        event_type="CONTACT_ALERT_RETRIED",
        title=tl_title,
        description=tl_desc,
        timestamp=now
    ))
    db.commit()
    db.refresh(alert)

    assigned_ids = [ir.responder_id for ir in incident.assigned_responders]
    realtime_manager.broadcast_from_sync(
        event_type="ALERT_UPDATED",
        incident_id=incident.id,
        assigned_responder_ids=assigned_ids,
        payload={
            "incident_id": incident.id,
            "alert_id": alert.id,
            "contact_name": alert.contact_name,
            "status": alert.status,
            "provider": alert.provider,
            "delivery_attempts": alert.delivery_attempts,
            "error_message": alert.error_message
        },
        household_id=incident.user_id
    )

    return format_alert_response(alert, user_role=current_user.role)


@router.patch("/{incident_id}/location", response_model=IncidentResponse)
def update_incident_location(
    incident_id: int,
    location_update: IncidentLocationUpdate,
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db)
):
    """
    Phase 5A: Refresh live incident coordinates during an active emergency.
    Updates latitude, longitude, accuracy, source, and timestamp, recalculates
    Haversine distances for assigned responders, records a timeline event,
    and broadcasts live coordinates over WebSocket to authorized sessions.
    """
    incident = db.query(EmergencyIncident).filter(EmergencyIncident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    owner_id = get_household_owner_id(current_user, db)
    if incident.user_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to access this incident"
        )

    now = datetime.datetime.utcnow()
    incident.latitude = location_update.latitude
    incident.longitude = location_update.longitude
    incident.location_accuracy_m = location_update.location_accuracy_m
    incident.location_source = location_update.location_source or "browser_gps"
    incident.location_updated_at = now
    if location_update.location_label:
        incident.location_label = location_update.location_label.strip()

    # Recalculate responder proximity distances against updated coordinates
    for ir in incident.assigned_responders:
        if ir.responder and ir.responder.latitude is not None and ir.responder.longitude is not None:
            ir.distance_km = calculate_haversine_distance(
                incident.latitude,
                incident.longitude,
                ir.responder.latitude,
                ir.responder.longitude
            )

    acc_str = f" (±{incident.location_accuracy_m:.0f}m)" if incident.location_accuracy_m is not None else ""
    tl_event = IncidentTimelineEvent(
        incident_id=incident.id,
        event_type="LOCATION_UPDATED",
        title=f"Live Location Refreshed ({incident.location_source})",
        description=f"Coordinates updated to ({incident.latitude:.5f}, {incident.longitude:.5f}){acc_str} at {incident.location_label}.",
        timestamp=now
    )
    db.add(tl_event)
    db.commit()
    db.refresh(incident)

    assigned_ids = [ir.responder_id for ir in incident.assigned_responders]
    realtime_manager.broadcast_from_sync(
        event_type="INCIDENT_LOCATION_UPDATED",
        incident_id=incident.id,
        assigned_responder_ids=assigned_ids,
        payload={
            "incident_id": incident.id,
            "latitude": incident.latitude,
            "longitude": incident.longitude,
            "location_label": incident.location_label,
            "location_accuracy_m": incident.location_accuracy_m,
            "location_source": incident.location_source,
            "location_updated_at": incident.location_updated_at.isoformat() if incident.location_updated_at else None
        },
        household_id=incident.user_id
    )

    logger.info(
        f"[Security Audit] User '{current_user.username}' updated location for Incident #{incident.id} "
        f"to ({incident.latitude}, {incident.longitude}) [{incident.location_source}]"
    )
    return format_incident_response(incident, user_role=current_user.role)


@router.post("/sos", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
def trigger_sos(
    payload: IncidentCreate,
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db)
):
    """
    ONE-TAP SOS DISPATCH (Phase 6 Real User-Managed Data Integration):
    Restricted to Family Administrators and Members.
    1. Validates selected saved family member (if provided) and uses their stored profile.
    2. Persists real coordinates, accuracy, and location source.
    3. Runs AI triage with resilient fallback so AI failure never discards an SOS incident.
    4. Matches only active responders that possess valid non-null coordinates.
    5. Dispatches notifications only to configured active trusted contacts, recording honest status.
    """
    now = datetime.datetime.utcnow()

    # 1. Fetch and validate saved patient profile
    patient_age = 40
    member = None
    effective_reporter_name = payload.reporter_name.strip()
    owner_id = get_household_owner_id(current_user, db)

    if payload.member_id:
        member = db.query(Member).filter(Member.id == payload.member_id).first()
        if not member:
            raise HTTPException(status_code=404, detail=f"Selected family member (ID #{payload.member_id}) not found.")
        if member.user_id != owner_id:
            logger.warning(
                f"[Security Audit] Cross-tenant SOS attempt: User '{current_user.username}' (ID: {current_user.id}) "
                f"attempted to trigger SOS for Member #{payload.member_id} (belonging to User #{member.user_id})."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You cannot trigger SOS for a family member belonging to another household."
            )
        if not member.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Selected family member '{member.name}' is currently deactivated."
            )
        effective_reporter_name = member.name
        if member.age is not None:
            patient_age = member.age

    # 2. Run AI Triage Assessment with resilient fallback (never discard a valid SOS if AI errors)
    try:
        ai_result = assess_emergency(
            incident_type=payload.incident_type,
            age=patient_age,
            is_conscious=payload.is_conscious if payload.is_conscious is not None else True,
            has_breathing_diff=payload.has_breathing_difficulty if payload.has_breathing_difficulty is not None else False,
            is_bleeding_severely=payload.is_bleeding_severely if payload.is_bleeding_severely is not None else False,
            is_alone=payload.is_alone if payload.is_alone is not None else True,
            description=payload.description or ""
        )
    except Exception as exc:
        logger.error(f"[SOS AI Fallback] Unexpected error during AI assessment: {exc}")
        ai_result = {
            "severity_level": "HIGH",
            "severity_score": 0.85,
            "ai_rationale": f"Classified as HIGH via emergency fallback rule (AI triage encountered error: {type(exc).__name__})."
        }

    # 3. Create Emergency Incident Record with Location Telemetry
    incident = EmergencyIncident(
        user_id=owner_id,
        member_id=payload.member_id,
        reporter_name=effective_reporter_name,
        incident_type=payload.incident_type,
        description=payload.description,
        latitude=payload.latitude,
        longitude=payload.longitude,
        location_label=payload.location_label,
        location_accuracy_m=payload.location_accuracy_m,
        location_source=payload.location_source or "manual_coordinates",
        location_updated_at=now,
        severity_level=ai_result["severity_level"],
        severity_score=ai_result["severity_score"],
        ai_rationale=ai_result["ai_rationale"],
        status="ACTIVE",
        created_at=now
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)

    # 4. Initial Timeline Events
    acc_info = f" (±{incident.location_accuracy_m:.0f}m, source: {incident.location_source})" if incident.location_accuracy_m is not None else f" (source: {incident.location_source})"
    t1 = IncidentTimelineEvent(
        incident_id=incident.id,
        event_type="INCIDENT_CREATED",
        title="SOS Emergency Logged",
        description=f"Alert registered for {incident.reporter_name} at {incident.location_label} [{incident.latitude:.5f}, {incident.longitude:.5f}]{acc_info}.",
        timestamp=now
    )
    t2 = IncidentTimelineEvent(
        incident_id=incident.id,
        event_type="AI_TRIAGED",
        title=f"AI Triage Classified: {incident.severity_level}",
        description=ai_result["ai_rationale"],
        timestamp=now + datetime.timedelta(milliseconds=200)
    )
    db.add_all([t1, t2])

    # 5. Responder Recommendation & Matching (ONLY active, non-demo responders with valid non-null coordinates)
    linked_inactive_ids = {u.responder_id for u in db.query(User).filter(User.responder_id != None, User.is_active == False).all()}
    active_responders = db.query(Responder).filter(
        Responder.is_active == True,
        Responder.is_demo == False
    ).all()
    responder_dicts = [
        {
            "id": r.id,
            "name": r.name,
            "role": r.role,
            "organization": r.organization,
            "phone": r.phone,
            "latitude": r.latitude,
            "longitude": r.longitude,
            "location_source": r.location_source,
            "location_updated_at": r.location_updated_at,
            "is_available": r.is_available,
            "is_active": r.is_active,
            "skills": r.skills
        }
        for r in active_responders
        if r.id not in linked_inactive_ids and r.latitude is not None and r.longitude is not None
    ]

    matched = rank_responders(
        incident_lat=payload.latitude,
        incident_lon=payload.longitude,
        responders=responder_dicts,
        top_k=3
    )

    for item in matched:
        is_avail = item.get("is_available", True)
        assignment = IncidentResponder(
            incident_id=incident.id,
            responder_id=item["id"],
            distance_km=item["distance_km"],
            status="ASSIGNED" if is_avail else "BUSY",
            assigned_at=now if is_avail else None,
            updated_at=now
        )
        db.add(assignment)

    if matched:
        top_unit = matched[0]
        t3 = IncidentTimelineEvent(
            incident_id=incident.id,
            event_type="RESPONDERS_MATCHED",
            title=f"Proximity Responders Ranked (Nearest: {top_unit['name']}, {top_unit['distance_km']}km)",
            description=f"Identified {len(matched)} closest units with verified coordinates using Haversine calculation.",
            timestamp=now + datetime.timedelta(milliseconds=400)
        )
        db.add(t3)
    else:
        db.add(IncidentTimelineEvent(
            incident_id=incident.id,
            event_type="NO_RESPONDERS_WITH_COORDINATES",
            title="No Responders With Verified Coordinates Available",
            description="SOS incident recorded, but no active responder profiles currently have valid geographic coordinates configured.",
            timestamp=now + datetime.timedelta(milliseconds=400)
        ))

    db.flush()

    # 6. Phase 5B & Phase 6: Trusted-Contact Notification Dispatch (Actual Saved Destinations Only)
    eligible_contacts = []
    if payload.member_id:
        eligible_contacts = db.query(TrustedContact).filter(
            TrustedContact.member_id == payload.member_id,
            TrustedContact.is_active == True
        ).order_by(TrustedContact.priority.asc(), TrustedContact.created_at.asc()).all()

    total_member_contacts = 0
    if payload.member_id:
        total_member_contacts = db.query(TrustedContact).filter(
            TrustedContact.member_id == payload.member_id
        ).count()

    if eligible_contacts:
        for idx, contact in enumerate(eligible_contacts):
            preferred = contact.notification_preferences or ("EMAIL" if contact.email else "SMS")
            alert = dispatch_contact_notification(
                db=db,
                incident=incident,
                contact_id=contact.id,
                contact_name=contact.name,
                contact_phone=contact.phone,
                contact_email=contact.email,
                preferred_channel=preferred
            )

            tier_label = "Primary" if contact.priority == 1 else f"Tier {contact.priority}"
            recipient_display = contact.email if (alert.channel == "EMAIL" and contact.email) else contact.phone
            if alert.status in ("DELIVERED", "SENT"):
                tl_title = f"Trusted Contact Notified ({tier_label} Priority: {contact.name})"
                tl_desc = (
                    f"Live {alert.channel} alert ({alert.provider}) dispatched to "
                    f"{contact.relationship} ({recipient_display}). Ref: {alert.provider_message_id or 'N/A'}."
                )
            elif alert.status == "SIMULATED":
                tl_title = f"Trusted Contact Alert Simulated ({tier_label} Priority: {contact.name})"
                tl_desc = (
                    f"Simulated {alert.channel} alert ({alert.provider}) recorded for "
                    f"{contact.relationship} ({recipient_display}). Ref: {alert.provider_message_id or 'N/A'}. "
                    f"External delivery suppressed (mock mode). Contact was NOT notified."
                )
            else:
                tl_title = f"Trusted Contact Alert ({tier_label} Priority: {contact.name}) — {alert.status}"
                tl_desc = (
                    f"{alert.channel} alert for {contact.relationship} ({recipient_display}) "
                    f"recorded as {alert.status} (provider: {alert.provider}). {alert.error_message or ''}"
                )

            t_contact = IncidentTimelineEvent(
                incident_id=incident.id,
                event_type="CONTACT_ALERTED",
                title=tl_title,
                description=tl_desc,
                timestamp=now + datetime.timedelta(milliseconds=600 + (idx * 50))
            )
            db.add(t_contact)
    elif total_member_contacts == 0 and member and member.emergency_contact_name and member.emergency_contact_phone:
        # Legacy fallback only if zero TrustedContact records exist for this member
        alert = dispatch_contact_notification(
            db=db,
            incident=incident,
            contact_id=None,
            contact_name=member.emergency_contact_name,
            contact_phone=member.emergency_contact_phone,
            contact_email=None,
            preferred_channel="SMS"
        )
        if alert.status in ("DELIVERED", "SENT"):
            t4_title = "Trusted Family Contact Notified"
            t4_desc = f"Live {alert.channel} alert ({alert.provider}) dispatched to {member.emergency_contact_name} ({member.emergency_contact_phone}). Ref: {alert.provider_message_id or 'N/A'}."
        elif alert.status == "SIMULATED":
            t4_title = "Trusted Family Contact Alert Simulated"
            t4_desc = (
                f"Simulated {alert.channel} alert ({alert.provider}) recorded for {member.emergency_contact_name} "
                f"({member.emergency_contact_phone}). Ref: {alert.provider_message_id or 'N/A'}. "
                f"External delivery suppressed (mock mode). Contact was NOT notified."
            )
        else:
            t4_title = f"Trusted Family Contact Alert ({alert.status})"
            t4_desc = f"Attempted {alert.channel} alert to {member.emergency_contact_name} ({member.emergency_contact_phone}) — Status: {alert.status}. {alert.error_message or ''}"

        db.add(IncidentTimelineEvent(
            incident_id=incident.id,
            event_type="CONTACT_ALERTED",
            title=t4_title,
            description=t4_desc,
            timestamp=now + datetime.timedelta(milliseconds=600)
        ))
    else:
        # Honest reporting when no active trusted contacts are configured for the member
        db.add(IncidentTimelineEvent(
            incident_id=incident.id,
            event_type="NO_ACTIVE_CONTACTS",
            title="No Active Trusted Contacts Configured",
            description=f"SOS incident preserved for {incident.reporter_name}, but no active trusted contact destinations were configured to receive external notifications.",
            timestamp=now + datetime.timedelta(milliseconds=600)
        ))

    db.commit()
    db.refresh(incident)
    logger.info(f"[Security Audit] User '{current_user.username}' triggered SOS Incident #{incident.id} for {incident.reporter_name}")

    # 7. Phase 5C: Broadcast live incident creation to authorized WebSocket clients
    assigned_ids = [ir.responder_id for ir in incident.assigned_responders]
    realtime_manager.broadcast_from_sync(
        event_type="INCIDENT_CREATED",
        incident_id=incident.id,
        assigned_responder_ids=assigned_ids,
        payload={
            "incident_id": incident.id,
            "reporter_name": incident.reporter_name,
            "incident_type": incident.incident_type,
            "severity_level": incident.severity_level,
            "severity_score": incident.severity_score,
            "status": incident.status,
            "latitude": incident.latitude,
            "longitude": incident.longitude,
            "location_label": incident.location_label,
            "location_source": incident.location_source,
            "location_accuracy_m": incident.location_accuracy_m
        },
        household_id=incident.user_id
    )

    return format_incident_response(incident, user_role=current_user.role)


@router.patch("/{incident_id}/status", response_model=IncidentResponse)
def update_incident_status(
    incident_id: int,
    status_update: IncidentStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update incident status (ACTIVE, RESPONDING, RESOLVED).
    - RESOLVED: Restricted to Family Admin and Family Member. Responders cannot close household incidents.
    - RESPONDING: Admins, Members, and assigned Responders. Unassigned responders are rejected.
    """
    incident = db.query(EmergencyIncident).filter(EmergencyIncident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    new_status = status_update.status.upper()
    if new_status not in ["ACTIVE", "RESPONDING", "RESOLVED"]:
        raise HTTPException(status_code=400, detail="Invalid status. Choose ACTIVE, RESPONDING, or RESOLVED")

    # Responder authorization check
    if current_user.role == "responder":
        assigned_units = [ir.responder_id for ir in incident.assigned_responders]
        if current_user.responder_id not in assigned_units:
            logger.warning(
                f"[Security Audit] Responder '{current_user.username}' attempted unauthorized status change "
                f"on unassigned Incident #{incident_id}."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Responders cannot modify unassigned incidents"
            )

        if new_status == "RESOLVED":
            logger.warning(
                f"[Security Audit] Responder '{current_user.username}' attempted to mark Incident #{incident_id} RESOLVED."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Only family administrators or members can mark incidents resolved"
            )
    else:
        owner_id = get_household_owner_id(current_user, db)
        if incident.user_id != owner_id:
            logger.warning(
                f"[Security Audit] Cross-tenant incident status change: User '{current_user.username}' (ID: {current_user.id}, Household: {owner_id}) "
                f"attempted to update status of Incident #{incident_id} (belonging to User #{incident.user_id})."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You do not have permission to access this incident"
            )

    if new_status == incident.status:
        if new_status == "RESOLVED" and status_update.resolution_notes and status_update.resolution_notes.strip() != (incident.resolution_notes or "").strip():
            incident.resolution_notes = status_update.resolution_notes.strip()
            db.commit()
            db.refresh(incident)
        return format_incident_response(incident, user_role=current_user.role)

    now = datetime.datetime.utcnow()
    incident.status = new_status

    if new_status == "RESOLVED":
        incident.resolved_at = now
        if status_update.resolution_notes:
            incident.resolution_notes = status_update.resolution_notes.strip()

        desc = incident.resolution_notes if incident.resolution_notes else "Emergency incident closed and confirmed safe."
        timeline_event = IncidentTimelineEvent(
            incident_id=incident.id,
            event_type="STATUS_RESOLVED",
            title=f"Incident Resolved by {current_user.username}",
            description=desc,
            timestamp=now
        )
        db.add(timeline_event)

        for al in incident.alerts:
            if al.status != "ACKNOWLEDGED":
                al.status = "ACKNOWLEDGED"
                al.acknowledged_at = now

    elif new_status == "RESPONDING":
        incident.resolved_at = None
        timeline_event = IncidentTimelineEvent(
            incident_id=incident.id,
            event_type="STATUS_RESPONDING",
            title=f"Responders En Route (Updated by {current_user.username})",
            description="Assigned community responders confirmed dispatch and are en route.",
            timestamp=now
        )
        db.add(timeline_event)

    elif new_status == "ACTIVE":
        incident.resolved_at = None
        timeline_event = IncidentTimelineEvent(
            incident_id=incident.id,
            event_type="STATUS_ACTIVE",
            title=f"Incident Returned to Active Status by {current_user.username}",
            description="Incident reopened for ongoing monitoring.",
            timestamp=now
        )
        db.add(timeline_event)

    db.commit()
    db.refresh(incident)
    logger.info(f"[Security Audit] Incident #{incident.id} status transitioned to {new_status} by '{current_user.username}'")

    assigned_ids = [ir.responder_id for ir in incident.assigned_responders]
    realtime_manager.broadcast_from_sync(
        event_type="INCIDENT_STATUS_UPDATED",
        incident_id=incident.id,
        assigned_responder_ids=assigned_ids,
        payload={
            "incident_id": incident.id,
            "status": incident.status,
            "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
            "resolution_notes": incident.resolution_notes,
            "updated_by": current_user.username
        },
        household_id=incident.user_id
    )

    return format_incident_response(incident, user_role=current_user.role)


@router.post("/preview-ai-triage", response_model=AIAssessmentResponse)
def preview_ai_triage(
    incident_type: str = Query("Chest Pain", description="Incident description"),
    age: int = Query(45, ge=0, le=130, description="Patient age"),
    is_conscious: bool = Query(True),
    has_breathing_difficulty: bool = Query(False),
    is_bleeding_severely: bool = Query(False),
    is_alone: bool = Query(True),
    description: Optional[str] = Query("", description="Free-text clinical or bystander notes"),
    current_user: User = Depends(get_current_user)
):
    """
    Direct scikit-learn emergency triage evaluation endpoint.
    Requires authenticated session.
    """
    ai_result = assess_emergency(
        incident_type=incident_type,
        age=age,
        is_conscious=is_conscious,
        has_breathing_diff=has_breathing_difficulty,
        is_bleeding_severely=is_bleeding_severely,
        is_alone=is_alone,
        description=description or ""
    )

    return AIAssessmentResponse(
        severity_level=ai_result["severity_level"],
        severity_score=ai_result["severity_score"],
        confidence_percentage=ai_result["confidence_percentage"],
        model_name="scikit-learn RandomForestClassifier (Triage-v2)",
        risk_factors=ai_result["risk_factors"],
        recommended_action=ai_result["recommended_action"],
        ai_rationale=ai_result["ai_rationale"],
        extracted_concepts=ai_result.get("extracted_concepts", []),
        negated_concepts=ai_result.get("negated_concepts", []),
        has_conflicts=ai_result.get("has_conflicts", False),
        conflict_warnings=ai_result.get("conflict_warnings", []),
        model_version=ai_result.get("model_version", "v2"),
        raw_model_prediction=ai_result.get("raw_model_prediction"),
        raw_model_confidence=ai_result.get("raw_model_confidence"),
        safety_override_applied=ai_result.get("safety_override_applied", False),
        safety_override_reason=ai_result.get("safety_override_reason"),
        prediction_source=ai_result.get("prediction_source", "ml_model_v2")
    )
