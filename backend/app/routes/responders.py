import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Responder, User, IncidentResponder, EmergencyIncident, IncidentTimelineEvent
from ..schemas import (
    ResponderCreate,
    ResponderUpdate,
    ResponderLocationUpdate,
    ResponderResponse,
    AssignmentStatusUpdate
)
from ..ai.triage import calculate_haversine_distance
from ..services.realtime import realtime_manager
from ..auth import get_current_user, require_admin, logger

router = APIRouter(prefix="/api/responders", tags=["Responders"])


@router.get("", response_model=List[ResponderResponse])
def get_responders(
    available_only: bool = False,
    include_inactive: bool = False,
    exclude_demo: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve community responders and emergency units.
    Requires authenticated user (Admin, Member, or Responder).
    Excludes demo and inactive responders by default for production safety.
    Verifies linked user account active and verification status.
    """
    query = db.query(Responder)
    if exclude_demo:
        query = query.filter(Responder.is_demo == False)
    if not include_inactive:
        query = query.filter(Responder.is_active == True)
    if available_only:
        query = query.filter(Responder.is_available == True, Responder.is_active == True)

    raw_responders = query.order_by(Responder.is_active.desc(), Responder.is_available.desc(), Responder.id.asc()).all()

    # Build map of linked users: responder_id -> User
    linked_users = {u.responder_id: u for u in db.query(User).filter(User.responder_id != None).all()}

    results = []
    for r in raw_responders:
        linked_u = linked_users.get(r.id)
        linked_active = linked_u.is_active if linked_u else None

        # If responder is linked to a deactivated user, they are effectively inactive
        if linked_u is not None and not linked_u.is_active:
            if not include_inactive:
                continue
            effective_active = False
        else:
            effective_active = r.is_active

        resp_dict = {
            "id": r.id,
            "name": r.name,
            "role": r.role,
            "organization": r.organization,
            "phone": r.phone,
            "email": r.email,
            "latitude": r.latitude,
            "longitude": r.longitude,
            "location_source": r.location_source,
            "location_accuracy_m": getattr(r, "location_accuracy_m", None),
            "location_updated_at": r.location_updated_at,
            "is_available": r.is_available,
            "is_active": effective_active,
            "is_demo": r.is_demo,
            "skills": r.skills,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
            "linked_user_active": linked_active
        }
        results.append(ResponderResponse(**resp_dict))

    return results


@router.post("", response_model=ResponderResponse, status_code=status.HTTP_201_CREATED)
def create_responder(
    responder_in: ResponderCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Phase 6: Create a new responder profile (Admin only).
    Never invents or substitutes default coordinates when coordinates are omitted.
    """
    if (responder_in.latitude is None) != (responder_in.longitude is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both latitude and longitude must be supplied together, or both omitted."
        )

    clean_name = responder_in.name.strip()
    clean_phone = responder_in.phone.strip()

    duplicate = db.query(Responder).filter(
        func.lower(Responder.name) == clean_name.lower(),
        Responder.phone == clean_phone
    ).first()
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A responder named '{clean_name}' with phone '{clean_phone}' already exists."
        )

    now = datetime.datetime.utcnow()
    has_coords = responder_in.latitude is not None and responder_in.longitude is not None
    loc_source = (responder_in.location_source or "manual_coordinates").strip() if has_coords else "unset"
    loc_updated = now if has_coords else None

    responder = Responder(
        name=clean_name,
        role=(responder_in.role or "First Responder").strip(),
        organization=responder_in.organization.strip() if responder_in.organization else None,
        phone=clean_phone,
        email=responder_in.email.strip() if responder_in.email else None,
        latitude=responder_in.latitude,
        longitude=responder_in.longitude,
        location_source=loc_source,
        location_accuracy_m=responder_in.location_accuracy_m if has_coords else None,
        location_updated_at=loc_updated,
        is_available=responder_in.is_available,
        is_active=responder_in.is_active,
        is_demo=False,
        skills=(responder_in.skills or "Basic First Aid").strip(),
        created_at=now,
        updated_at=now
    )
    db.add(responder)
    db.commit()
    db.refresh(responder)
    logger.info(f"[Security Audit] Admin '{current_user.username}' created Responder #{responder.id} ('{responder.name}')")
    return responder


@router.put("/{responder_id}", response_model=ResponderResponse)
def update_responder(
    responder_id: int,
    responder_in: ResponderUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Phase 6: Update a responder profile, availability, or coordinates.
    Authorized for Admins (any responder) or the linked Responder user (own profile only).
    """
    if current_user.role == "member":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: family members cannot modify responder profiles"
        )
    if current_user.role == "responder" and current_user.responder_id != responder_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: responders can only update their own profile"
        )

    responder = db.query(Responder).filter(Responder.id == responder_id).first()
    if not responder:
        raise HTTPException(status_code=404, detail="Responder not found")

    update_data = responder_in.model_dump(exclude_unset=True)
    now = datetime.datetime.utcnow()

    if update_data.get("clear_coordinates"):
        responder.latitude = None
        responder.longitude = None
        responder.location_source = "unset"
        responder.location_accuracy_m = None
        responder.location_updated_at = None
    elif "latitude" in update_data or "longitude" in update_data:
        new_lat = update_data.get("latitude", responder.latitude)
        new_lon = update_data.get("longitude", responder.longitude)
        if (new_lat is None) != (new_lon is None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Both latitude and longitude must be supplied together."
            )
        responder.latitude = new_lat
        responder.longitude = new_lon
        if new_lat is not None and new_lon is not None:
            responder.location_source = (update_data.get("location_source") or "manual_coordinates").strip()
            responder.location_updated_at = now
        else:
            responder.location_source = "unset"
            responder.location_accuracy_m = None
            responder.location_updated_at = None

    for field in ["name", "role", "organization", "phone", "email", "skills", "is_available", "is_active", "location_accuracy_m"]:
        if field in update_data:
            val = update_data[field]
            if isinstance(val, str):
                setattr(responder, field, val.strip())
            else:
                setattr(responder, field, val)

    responder.updated_at = now
    db.commit()
    db.refresh(responder)
    logger.info(f"[Security Audit] User '{current_user.username}' updated Responder #{responder.id} ('{responder.name}')")
    return responder


@router.patch("/{responder_id}/location", response_model=ResponderResponse)
def update_responder_location(
    responder_id: int,
    loc_in: ResponderLocationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Phase 6: Update a responder's verified coordinates and recalculate distances
    for any active incidents assigned to this responder.
    """
    if current_user.role == "member":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: family members cannot update responder coordinates"
        )
    if current_user.role == "responder" and current_user.responder_id != responder_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: responders can only update their own coordinates"
        )

    responder = db.query(Responder).filter(Responder.id == responder_id).first()
    if not responder:
        raise HTTPException(status_code=404, detail="Responder not found")

    now = datetime.datetime.utcnow()
    responder.latitude = loc_in.latitude
    responder.longitude = loc_in.longitude
    responder.location_source = (loc_in.location_source or "browser_gps").strip()
    if loc_in.location_accuracy_m is not None:
        responder.location_accuracy_m = loc_in.location_accuracy_m
    if loc_in.is_available is not None:
        responder.is_available = loc_in.is_available
    responder.location_updated_at = now
    responder.updated_at = now

    # Recalculate distance on active assignments for this responder
    active_assignments = db.query(IncidentResponder).filter(
        IncidentResponder.responder_id == responder.id
    ).all()
    for a in active_assignments:
        if a.incident and a.incident.status != "RESOLVED":
            if a.incident.latitude is not None and a.incident.longitude is not None:
                a.distance_km = calculate_haversine_distance(
                    a.incident.latitude,
                    a.incident.longitude,
                    responder.latitude,
                    responder.longitude
                )

    db.commit()
    db.refresh(responder)
    logger.info(
        f"[Security Audit] User '{current_user.username}' updated coordinates for Responder #{responder.id} "
        f"to ({responder.latitude}, {responder.longitude}) [{responder.location_source}]"
    )
    return responder


@router.delete("/{responder_id}", status_code=status.HTTP_200_OK)
def delete_or_deactivate_responder(
    responder_id: int,
    hard_delete: bool = Query(False, description="Permanently delete if no incident assignments reference this responder"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Safely deactivate or remove a responder profile (Admin only).
    """
    responder = db.query(Responder).filter(Responder.id == responder_id).first()
    if not responder:
        raise HTTPException(status_code=404, detail="Responder not found")

    has_assignments = db.query(IncidentResponder).filter(IncidentResponder.responder_id == responder_id).count() > 0
    has_users = db.query(User).filter(User.responder_id == responder_id).count() > 0

    if hard_delete and not has_assignments and not has_users:
        resp_name = responder.name
        db.delete(responder)
        db.commit()
        logger.info(f"[Security Audit] Admin '{current_user.username}' permanently deleted Responder #{responder_id} ('{resp_name}')")
        return {
            "id": responder_id,
            "action": "deleted",
            "message": f"Responder '{resp_name}' permanently removed."
        }

    responder.is_active = False
    responder.is_available = False
    responder.updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(responder)
    logger.info(f"[Security Audit] Admin '{current_user.username}' deactivated Responder #{responder_id} ('{responder.name}')")
    return {
        "id": responder_id,
        "action": "deactivated",
        "is_active": False,
        "message": f"Responder '{responder.name}' deactivated safely."
    }


@router.get("/nearby")
def get_nearby_responders(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitude bounded between -90 and 90"),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitude bounded between -180 and 180"),
    limit: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Find closest active responders that have valid stored coordinates using Haversine distance.
    Excludes demo responders and responders linked to deactivated user accounts.
    Never calculates distance for responders missing coordinates.
    """
    linked_inactive_ids = {u.responder_id for u in db.query(User).filter(User.responder_id != None, User.is_active == False).all()}
    responders = db.query(Responder).filter(
        Responder.is_active == True,
        Responder.is_demo == False
    ).all()
    results = []
    for r in responders:
        if r.id in linked_inactive_ids:
            continue
        if r.latitude is None or r.longitude is None:
            continue
        dist = calculate_haversine_distance(lat, lon, r.latitude, r.longitude)
        results.append({
            "id": r.id,
            "name": r.name,
            "role": r.role,
            "organization": r.organization,
            "phone": r.phone,
            "email": r.email,
            "latitude": r.latitude,
            "longitude": r.longitude,
            "location_source": r.location_source,
            "location_accuracy_m": getattr(r, "location_accuracy_m", None),
            "location_updated_at": r.location_updated_at,
            "is_available": r.is_available,
            "skills": r.skills,
            "distance_km": dist
        })

    results.sort(key=lambda x: (not x["is_available"], x["distance_km"]))
    return results[:limit]


# --- Responder Assignment Lifecycle Endpoints (Phase 4B & Phase 5C) ---


@router.get("/me/assignments")
def get_my_assignments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve all assignments for the currently authenticated responder.
    Strictly isolated: responders see only their own assignments.
    """
    if current_user.role != "responder" or not current_user.responder_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Only authenticated responders can view their assignments"
        )

    assignments = db.query(IncidentResponder).filter(
        IncidentResponder.responder_id == current_user.responder_id
    ).all()

    results = []
    for a in assignments:
        inc = a.incident
        results.append({
            "assignment_id": a.id,
            "incident_id": a.incident_id,
            "responder_id": a.responder_id,
            "incident_type": inc.incident_type,
            "reporter_name": inc.reporter_name,
            "severity_level": inc.severity_level,
            "severity_score": inc.severity_score,
            "location_label": inc.location_label,
            "latitude": inc.latitude,
            "longitude": inc.longitude,
            "location_accuracy_m": inc.location_accuracy_m,
            "location_source": inc.location_source,
            "distance_km": a.distance_km,
            "status": a.status,
            "assigned_at": a.assigned_at,
            "accepted_at": a.accepted_at,
            "en_route_at": a.en_route_at,
            "arrived_at": a.arrived_at,
            "updated_at": a.updated_at,
            "incident_status": inc.status
        })
    return results


@router.patch("/me/assignments/{assignment_id}/status")
def update_assignment_status(
    assignment_id: int,
    status_update: AssignmentStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update responder assignment status:
    ASSIGNED -> ACCEPTED -> EN_ROUTE -> ARRIVED
    Strictly isolated: responders can modify only their own assignments.
    Enforces valid progression and persists timeline events without duplicate spam.
    """
    if current_user.role != "responder" or not current_user.responder_id:
        logger.warning(f"[Security Audit] User '{current_user.username}' (role '{current_user.role}') denied assignment status update.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Only assigned responders can update assignment status"
        )

    assignment = db.query(IncidentResponder).filter(
        IncidentResponder.id == assignment_id
    ).first()

    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    if assignment.responder_id != current_user.responder_id:
        logger.warning(
            f"[Security Audit] Cross-responder violation: Responder '{current_user.username}' "
            f"(ID {current_user.responder_id}) attempted to modify Assignment #{assignment_id} "
            f"(owned by ResponderID {assignment.responder_id})."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You cannot modify another responder's assignment"
        )

    new_status = status_update.status.upper().strip()
    valid_statuses = ["ACCEPTED", "EN_ROUTE", "ARRIVED"]
    if new_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status '{new_status}'. Allowed: {', '.join(valid_statuses)}"
        )

    current_status = (assignment.status or "ASSIGNED").upper()

    if current_status == new_status:
        return {
            "assignment_id": assignment.id,
            "incident_id": assignment.incident_id,
            "responder_id": assignment.responder_id,
            "status": assignment.status,
            "assigned_at": assignment.assigned_at,
            "accepted_at": assignment.accepted_at,
            "en_route_at": assignment.en_route_at,
            "arrived_at": assignment.arrived_at,
            "updated_at": assignment.updated_at,
            "message": f"Assignment is already at status '{new_status}'"
        }

    valid_transitions = {
        "RECOMMENDED": ["ACCEPTED"],
        "ASSIGNED": ["ACCEPTED"],
        "ACCEPTED": ["EN_ROUTE"],
        "EN_ROUTE": ["ARRIVED"],
        "ARRIVED": []
    }

    allowed_next = valid_transitions.get(current_status, [])
    if new_status not in allowed_next:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status transition: Cannot move from '{current_status}' to '{new_status}'. Allowed next: {allowed_next}"
        )

    now = datetime.datetime.utcnow()
    assignment.status = new_status
    assignment.updated_at = now
    unit_name = assignment.responder.name if assignment.responder else f"Unit #{assignment.responder_id}"

    if new_status == "ACCEPTED":
        assignment.accepted_at = now
        tl_event = IncidentTimelineEvent(
            incident_id=assignment.incident_id,
            event_type="RESPONDER_ACCEPTED",
            title=f"Dispatch Accepted by {unit_name}",
            description=f"{unit_name} accepted response assignment. Distance: {assignment.distance_km}km.",
            timestamp=now
        )
        db.add(tl_event)

        incident = assignment.incident
        if incident and incident.status == "ACTIVE":
            incident.status = "RESPONDING"

    elif new_status == "EN_ROUTE":
        assignment.en_route_at = now
        tl_event = IncidentTimelineEvent(
            incident_id=assignment.incident_id,
            event_type="RESPONDER_EN_ROUTE",
            title=f"Responder En Route: {unit_name}",
            description=f"{unit_name} is actively travelling to the incident location.",
            timestamp=now
        )
        db.add(tl_event)

    elif new_status == "ARRIVED":
        assignment.arrived_at = now
        tl_event = IncidentTimelineEvent(
            incident_id=assignment.incident_id,
            event_type="RESPONDER_ARRIVED",
            title=f"Responder Arrived On Scene: {unit_name}",
            description=f"{unit_name} recorded arrival at {assignment.incident.location_label}. On-site assessment initiated.",
            timestamp=now
        )
        db.add(tl_event)

    db.commit()
    db.refresh(assignment)

    logger.info(f"[Security Audit] Responder '{current_user.username}' progressed Assignment #{assignment.id} to '{new_status}'.")

    inc = assignment.incident
    assigned_ids = [ir.responder_id for ir in inc.assigned_responders] if inc else [assignment.responder_id]
    inc_household = inc.user_id if inc else None
    realtime_manager.broadcast_from_sync(
        event_type="RESPONDER_STATUS_UPDATED",
        incident_id=assignment.incident_id,
        assigned_responder_ids=assigned_ids,
        payload={
            "assignment_id": assignment.id,
            "incident_id": assignment.incident_id,
            "responder_id": assignment.responder_id,
            "responder_name": unit_name,
            "status": assignment.status,
            "incident_status": inc.status if inc else "RESPONDING",
            "updated_at": assignment.updated_at.isoformat() if assignment.updated_at else None
        },
        household_id=inc_household
    )

    return {
        "assignment_id": assignment.id,
        "incident_id": assignment.incident_id,
        "responder_id": assignment.responder_id,
        "status": assignment.status,
        "assigned_at": assignment.assigned_at,
        "accepted_at": assignment.accepted_at,
        "en_route_at": assignment.en_route_at,
        "arrived_at": assignment.arrived_at,
        "updated_at": assignment.updated_at,
        "message": f"Assignment status progressed to '{new_status}' successfully"
    }
