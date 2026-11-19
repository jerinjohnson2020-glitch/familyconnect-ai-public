import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Member, TrustedContact, Responder, EmergencyIncident, User
from ..schemas import (
    MemberCreate,
    MemberUpdate,
    MemberResponse,
    TrustedContactCreate,
    TrustedContactUpdate,
    TrustedContactResponse,
    MemberLocationConsentToggle,
    MemberLocationUpdate,
    MemberLocationItem,
    HouseholdLocationsResponse
)
from ..services.realtime import realtime_manager
from ..auth import (
    get_current_user,
    require_admin,
    require_member_or_admin,
    logger
)

router = APIRouter(prefix="/api/members", tags=["Family Members & Trusted Contacts"])

PLACEHOLDER_EMAIL_DOMAINS = {"example.com", "example.org", "example.net", "test.invalid", "placeholder.local"}


def _validate_contact_destinations(phone: str, email: Optional[str], channel_pref: str):
    pref = (channel_pref or "EMAIL").upper()
    if ("EMAIL" in pref or pref == "BOTH") and not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An email address is required when notification preference includes EMAIL."
        )
    if email:
        domain = email.split("@")[-1].lower()
        if domain in PLACEHOLDER_EMAIL_DOMAINS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Placeholder email domain '@{domain}' is not allowed. Please enter a real email destination."
            )
    if phone and phone.strip().endswith("000-0000"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Placeholder phone numbers ending in 000-0000 are not allowed."
        )


def get_household_owner_id(current_user: User, db: Session) -> int:
    """Resolve the household owner ID for a user (admins own themselves, members link to their household)."""
    if getattr(current_user, "household_id", None):
        return current_user.household_id
    if current_user.member_id:
        curr_m = db.query(Member).filter(Member.id == current_user.member_id).first()
        if curr_m and curr_m.user_id:
            return curr_m.user_id
    return current_user.id


@router.get("", response_model=List[MemberResponse])
def get_members(
    include_inactive: bool = Query(True, description="Include deactivated family members"),
    exclude_demo: bool = Query(False, description="Exclude seeded demo records"),
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db)
):
    """
    Fetch family members scoped to caller's household.
    Restricted to Family Administrators and Family Members.
    Responders cannot browse private family rosters.
    """
    query = db.query(Member)
    owner_id = get_household_owner_id(current_user, db)

    # Multi-tenant scoping: Each household sees ONLY their own family members
    query = query.filter(Member.user_id == owner_id)

    if not include_inactive:
        query = query.filter(Member.is_active == True)
    if exclude_demo:
        query = query.filter(Member.is_demo == False)
    return query.order_by(Member.is_active.desc(), Member.id.asc()).all()


LOCATION_STALE_THRESHOLD_MINUTES = 15


@router.get("/locations", response_model=HouseholdLocationsResponse)
def get_household_member_locations(
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db)
):
    """
    Retrieve current location status for all active members in the caller's household.
    - Household Scoping: Scoped exclusively to caller's household.
    - Least Privilege: Responders cannot browse family locations (HTTP 403 via require_member_or_admin).
    - Stale Indicator: Tags locations older than 15 minutes with is_stale=True.
    - Privacy: For members where is_sharing_location is False, coordinates are null.
    """
    owner_id = get_household_owner_id(current_user, db)
    members = db.query(Member).filter(
        Member.user_id == owner_id,
        Member.is_active == True
    ).order_by(Member.id.asc()).all()

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    items: List[MemberLocationItem] = []
    active_sharing = 0

    for m in members:
        is_sharing = bool(getattr(m, "is_sharing_location", False))
        lat = m.latitude if is_sharing else None
        lon = m.longitude if is_sharing else None
        acc = m.location_accuracy_m if is_sharing else None
        lbl = m.location_label if is_sharing else None
        upd = m.location_updated_at if is_sharing else None

        is_stale = False
        age_min = None
        if is_sharing and upd:
            upd_aware = upd if upd.tzinfo else upd.replace(tzinfo=datetime.timezone.utc)
            delta = now_utc - upd_aware
            age_min = max(0, int(delta.total_seconds() // 60))
            if age_min >= LOCATION_STALE_THRESHOLD_MINUTES:
                is_stale = True
            active_sharing += 1
        elif is_sharing:
            is_stale = True
            active_sharing += 1

        items.append(MemberLocationItem(
            member_id=m.id,
            name=m.name,
            relationship=m.relationship or "Family Member",
            is_sharing_location=is_sharing,
            latitude=lat,
            longitude=lon,
            location_accuracy_m=acc,
            location_label=lbl,
            location_updated_at=upd,
            is_stale=is_stale,
            age_minutes=age_min
        ))

    return HouseholdLocationsResponse(
        household_id=owner_id,
        members=items,
        active_sharing_count=active_sharing
    )


@router.post("/{member_id}/location/toggle-sharing", response_model=MemberLocationItem)
def toggle_member_location_sharing(
    member_id: int,
    toggle: MemberLocationConsentToggle,
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db)
):
    """
    Explicit Application Consent Toggle for Location Sharing.
    - Enables or revokes location sharing for a family member profile.
    - Household Isolation: Member must belong to caller's household.
    - Role Permission: Family members can only toggle sharing for their own profile.
    - Immediate Clearing on Revocation: If is_sharing is False, coordinates, accuracy,
      label, and timestamps are immediately purged (set to None).
    - Real-Time Broadcast: Notifies household WebSocket sessions of consent state change.
    """
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family member not found")

    owner_id = get_household_owner_id(current_user, db)
    if member.user_id != owner_id:
        logger.warning(
            f"[Security Audit] Cross-tenant violation: User '{current_user.username}' (ID: {current_user.id}) "
            f"attempted to toggle location sharing for Member #{member_id} in household #{member.user_id}."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You cannot modify location consent for a member in another household."
        )

    if current_user.role == "member" and current_user.member_id != member_id:
        logger.warning(
            f"[Security Audit] User '{current_user.username}' (MemberID: {current_user.member_id}) "
            f"attempted unauthorized consent change for Member #{member_id}."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Family members can only toggle location sharing for their own profile."
        )

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    member.is_sharing_location = toggle.is_sharing

    if not toggle.is_sharing:
        # Immediate clearing on stop-sharing / consent revocation
        member.latitude = None
        member.longitude = None
        member.location_accuracy_m = None
        member.location_label = None
        member.location_updated_at = None
        member.updated_at = now_utc
        db.commit()
        db.refresh(member)

        realtime_manager.broadcast_household_location_from_sync(
            event_type="MEMBER_LOCATION_STOPPED",
            household_id=owner_id,
            payload={
                "member_id": member.id,
                "name": member.name,
                "is_sharing_location": False
            }
        )
        logger.info(f"[Location Privacy] User '{current_user.username}' revoked location sharing for Member '{member.name}' (ID: {member.id}). Coordinates purged.")
    else:
        member.updated_at = now_utc
        db.commit()
        db.refresh(member)

        realtime_manager.broadcast_household_location_from_sync(
            event_type="MEMBER_LOCATION_SHARING_ENABLED",
            household_id=owner_id,
            payload={
                "member_id": member.id,
                "name": member.name,
                "is_sharing_location": True
            }
        )
        logger.info(f"[Location Privacy] User '{current_user.username}' granted location sharing consent for Member '{member.name}' (ID: {member.id}).")

    return MemberLocationItem(
        member_id=member.id,
        name=member.name,
        relationship=member.relationship or "Family Member",
        is_sharing_location=member.is_sharing_location,
        latitude=member.latitude,
        longitude=member.longitude,
        location_accuracy_m=member.location_accuracy_m,
        location_label=member.location_label,
        location_updated_at=member.location_updated_at,
        is_stale=False,
        age_minutes=None
    )


@router.put("/{member_id}/location", response_model=MemberLocationItem)
def update_member_location(
    member_id: int,
    location_in: MemberLocationUpdate,
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db)
):
    """
    Update live location for a household member.
    - Requires Explicit Application Consent: Fails with HTTP 400 if is_sharing_location is False.
    - Household Scoping: Target member must belong to caller's household.
    - Role Permissions: Family members can only update their own linked profile.
    - Server-Generated UTC Timestamp: Client cannot spoof location_updated_at.
    - Latest Location Only: Overwrites existing coordinates; no location history or background tracking.
    - Real-Time Broadcast: Transmits MEMBER_LOCATION_UPDATED to household sessions.
    """
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family member not found")

    owner_id = get_household_owner_id(current_user, db)
    if member.user_id != owner_id:
        logger.warning(
            f"[Security Audit] Cross-tenant violation: User '{current_user.username}' (ID: {current_user.id}) "
            f"attempted to update location for Member #{member_id} in household #{member.user_id}."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You cannot update location for a member in another household."
        )

    if current_user.role == "member" and current_user.member_id != member_id:
        logger.warning(
            f"[Security Audit] User '{current_user.username}' (MemberID: {current_user.member_id}) "
            f"attempted unauthorized location update for Member #{member_id}."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Family members can only update their own location."
        )

    # Consent Gate: Application consent must be explicitly True
    if not member.is_sharing_location:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Location sharing consent is disabled for this family member. Explicit application consent is required before updating coordinates."
        )

    # Server-generated timezone-aware UTC timestamp
    now_utc = datetime.datetime.now(datetime.timezone.utc)

    member.latitude = location_in.latitude
    member.longitude = location_in.longitude
    member.location_accuracy_m = location_in.accuracy_m
    member.location_label = (location_in.label or "Live GPS").strip()
    member.location_updated_at = now_utc
    member.updated_at = now_utc

    db.commit()
    db.refresh(member)

    # Broadcast to household sessions via WebSocket
    realtime_manager.broadcast_household_location_from_sync(
        event_type="MEMBER_LOCATION_UPDATED",
        household_id=owner_id,
        payload={
            "member_id": member.id,
            "name": member.name,
            "latitude": member.latitude,
            "longitude": member.longitude,
            "location_accuracy_m": member.location_accuracy_m,
            "location_label": member.location_label,
            "location_updated_at": member.location_updated_at.isoformat() if member.location_updated_at else None,
            "is_sharing_location": True
        }
    )

    return MemberLocationItem(
        member_id=member.id,
        name=member.name,
        relationship=member.relationship or "Family Member",
        is_sharing_location=member.is_sharing_location,
        latitude=member.latitude,
        longitude=member.longitude,
        location_accuracy_m=member.location_accuracy_m,
        location_label=member.location_label,
        location_updated_at=member.location_updated_at,
        is_stale=False,
        age_minutes=0
    )


@router.get("/{member_id}", response_model=MemberResponse)
def get_member(
    member_id: int,
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db)
):
    """
    Get a specific family member profile.
    Restricted to Family Administrators and Family Members with access to this household.
    """
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    owner_id = get_household_owner_id(current_user, db)
    if member.user_id != owner_id:
        logger.warning(
            f"[Security Audit] Cross-tenant violation: User '{current_user.username}' (ID: {current_user.id}) "
            f"attempted to access Member #{member_id} belonging to User #{member.user_id}."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have access to this family member profile."
        )

    return member


@router.post("", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
def create_member(
    member_in: MemberCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Register a new family member profile in the caller's household.
    Restricted to Family Administrators.
    Validates inputs and prevents duplicate (name + phone) profiles within household.
    """
    clean_name = member_in.name.strip()
    clean_phone = member_in.phone.strip()
    norm_phone = "".join(ch for ch in clean_phone if ch.isdigit())

    owner_id = get_household_owner_id(current_user, db)
    same_name_query = db.query(Member).filter(func.lower(Member.name) == clean_name.lower())
    same_name_query = same_name_query.filter(Member.user_id == owner_id)

    same_name_members = same_name_query.all()
    for existing in same_name_members:
        existing_norm = "".join(ch for ch in (existing.phone or "") if ch.isdigit())
        if existing.phone == clean_phone or (norm_phone and existing_norm == norm_phone):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A family member named '{clean_name}' with phone '{clean_phone}' already exists."
            )

    now = datetime.datetime.utcnow()
    data = member_in.model_dump()
    data["user_id"] = owner_id
    data["name"] = clean_name
    data["phone"] = clean_phone
    data["relationship"] = (member_in.relationship or "Family Member").strip()
    if data.get("email"):
        data["email"] = data["email"].strip()
    if data.get("address"):
        data["address"] = data["address"].strip()

    member = Member(
        **data,
        is_demo=False,
        created_at=now,
        updated_at=now
    )
    db.add(member)
    db.commit()
    db.refresh(member)

    # If primary emergency contact details were supplied during member creation, create a Priority 1 TrustedContact
    if member.emergency_contact_name and member.emergency_contact_phone:
        tc = TrustedContact(
            member_id=member.id,
            name=member.emergency_contact_name.strip(),
            phone=member.emergency_contact_phone.strip(),
            email=None,
            relationship="Primary Contact",
            priority=1,
            notification_preferences="SMS",
            is_active=True,
            is_demo=False,
            created_at=now,
            updated_at=now
        )
        db.add(tc)
        db.commit()
        db.refresh(member)

    logger.info(f"[Security Audit] Admin '{current_user.username}' created family member '{member.name}' (ID: {member.id})")
    return member


@router.put("/{member_id}", response_model=MemberResponse)
def update_member(
    member_id: int,
    member_in: MemberUpdate,
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db)
):
    """
    Update family member details, medical notes, active status, or emergency contacts.
    Admins can update any profile; family members can only update their own linked profile.
    """
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    owner_id = get_household_owner_id(current_user, db)
    if member.user_id != owner_id:
        logger.warning(
            f"[Security Audit] Cross-tenant violation: User '{current_user.username}' (ID: {current_user.id}) "
            f"attempted unauthorized edit of MemberID {member_id} (belonging to User #{member.user_id})."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You cannot modify a profile belonging to another household."
        )

    if current_user.role == "member" and current_user.member_id != member_id:
        logger.warning(
            f"[Security Audit] User '{current_user.username}' (MemberID: {current_user.member_id}) "
            f"attempted unauthorized edit of MemberID {member_id}."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: family members can only update their own profile"
        )

    update_data = member_in.model_dump(exclude_unset=True)
    new_name = (update_data.get("name") or member.name).strip()
    new_phone = (update_data.get("phone") or member.phone).strip()

    duplicate = db.query(Member).filter(
        Member.id != member_id,
        func.lower(Member.name) == new_name.lower(),
        Member.phone == new_phone
    ).first()
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Another family member named '{new_name}' with phone '{new_phone}' already exists."
        )

    for key, value in update_data.items():
        if isinstance(value, str):
            setattr(member, key, value.strip())
        else:
            setattr(member, key, value)

    member.updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(member)
    logger.info(f"[Security Audit] User '{current_user.username}' updated family member profile ID {member.id}")
    return member


@router.delete("/{member_id}", status_code=status.HTTP_200_OK)
def delete_or_deactivate_member(
    member_id: int,
    hard_delete: bool = Query(False, description="Permanently delete if no incidents or users reference this member"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Safely deactivate or remove a family member profile (Admin only).
    If historical emergency incidents or user accounts reference this member,
    or if hard_delete=False, the member is safely deactivated (is_active=False)
    to preserve audit trail integrity.
    """
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    owner_id = get_household_owner_id(current_user, db)
    if member.user_id != owner_id:
        logger.warning(
            f"[Security Audit] Cross-tenant violation: User '{current_user.username}' (ID: {current_user.id}) "
            f"attempted to delete MemberID {member_id} (belonging to User #{member.user_id})."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You cannot delete a profile belonging to another household."
        )

    has_incidents = db.query(EmergencyIncident).filter(EmergencyIncident.member_id == member_id).count() > 0
    has_users = db.query(User).filter(User.member_id == member_id).count() > 0

    if hard_delete and not has_incidents and not has_users:
        member_name = member.name
        db.delete(member)
        db.commit()
        logger.info(f"[Security Audit] Admin '{current_user.username}' permanently deleted Member #{member_id} ('{member_name}')")
        return {
            "id": member_id,
            "action": "deleted",
            "message": f"Family member '{member_name}' permanently removed."
        }

    member.is_active = False
    member.updated_at = datetime.datetime.utcnow()
    for tc in member.trusted_contacts:
        tc.is_active = False
    db.commit()
    db.refresh(member)
    logger.info(f"[Security Audit] Admin '{current_user.username}' deactivated Member #{member_id} ('{member.name}')")
    return {
        "id": member_id,
        "action": "deactivated",
        "is_active": False,
        "message": (
            f"Family member '{member.name}' deactivated safely "
            f"({'referenced by historical incidents/accounts' if (has_incidents or has_users) else 'soft-deactivated'})."
        )
    }


@router.post("/admin/demo-records", status_code=status.HTTP_200_OK)
def manage_demo_records(
    action: str = Query("deactivate", description="'deactivate' or 'activate' all records marked is_demo=True"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Phase 6 Section 5: Safe administrative control to deactivate or reactivate
    explicitly flagged demo records (is_demo=True) without deleting historical data
    or guessing based on names.
    """
    act = action.strip().lower()
    if act not in ("deactivate", "activate"):
        raise HTTPException(status_code=400, detail="Invalid action. Use 'deactivate' or 'activate'.")

    target_active = (act == "activate")
    now = datetime.datetime.utcnow()

    demo_members = db.query(Member).filter(Member.is_demo == True).all()
    for m in demo_members:
        m.is_active = target_active
        m.updated_at = now

    demo_contacts = db.query(TrustedContact).filter(TrustedContact.is_demo == True).all()
    for tc in demo_contacts:
        tc.is_active = target_active
        tc.updated_at = now

    demo_responders = db.query(Responder).filter(Responder.is_demo == True).all()
    for r in demo_responders:
        r.is_active = target_active
        r.is_available = target_active
        r.updated_at = now

    db.commit()
    logger.info(
        f"[Security Audit] Admin '{current_user.username}' executed '{act}' on demo records "
        f"(members={len(demo_members)}, contacts={len(demo_contacts)}, responders={len(demo_responders)})."
    )
    return {
        "action": act,
        "demo_members_updated": len(demo_members),
        "demo_contacts_updated": len(demo_contacts),
        "demo_responders_updated": len(demo_responders)
    }


# --- Trusted Contacts Endpoints (Phase 4A + Phase 6 Validation) ---


def check_member_access(member_id: int, current_user: User, db: Optional[Session] = None):
    """
    Enforces authorization:
    - Household admin can manage only their own household members' contacts.
    - Member can view and manage only their own contacts.
    - Responder is blocked completely (HTTP 403).
    """
    if current_user.role == "responder":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: responders cannot access family trusted contacts"
        )
    owner_id = get_household_owner_id(current_user, db) if db is not None else (getattr(current_user, "household_id", None) or current_user.id)
    if db is not None:
        member = db.query(Member).filter(Member.id == member_id).first()
        if member and member.user_id != owner_id:
            logger.warning(
                f"[Security Audit] Cross-tenant violation: User '{current_user.username}' (ID: {current_user.id}) "
                f"attempted to access contacts of Member #{member_id} (belonging to User #{member.user_id})."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You cannot access contacts belonging to another household."
            )
    if current_user.role == "member":
        if current_user.member_id != member_id:
            logger.warning(
                f"[Security Audit] Cross-member violation: User '{current_user.username}' (MemberID: {current_user.member_id}) "
                f"attempted access to MemberID {member_id}'s trusted contacts."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: family members can only access their own trusted contacts"
            )


@router.get("/{member_id}/trusted-contacts", response_model=List[TrustedContactResponse])
def get_trusted_contacts(
    member_id: int,
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db)
):
    """
    Get all trusted contacts for a family member, ordered by priority.
    """
    check_member_access(member_id, current_user, db)
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    contacts = db.query(TrustedContact).filter(
        TrustedContact.member_id == member_id
    ).order_by(TrustedContact.priority.asc(), TrustedContact.created_at.asc()).all()
    return contacts


@router.post("/{member_id}/trusted-contacts", response_model=TrustedContactResponse, status_code=status.HTTP_201_CREATED)
def create_trusted_contact(
    member_id: int,
    contact_in: TrustedContactCreate,
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db)
):
    """
    Add a new trusted contact for a family member.
    Validates phone, email, and notification channel requirements.
    """
    check_member_access(member_id, current_user, db)
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    clean_phone = contact_in.phone.strip()
    clean_email = contact_in.email.strip() if contact_in.email else None
    clean_pref = contact_in.notification_preferences.strip()

    _validate_contact_destinations(clean_phone, clean_email, clean_pref)

    existing = db.query(TrustedContact).filter(
        TrustedContact.member_id == member_id,
        TrustedContact.phone == clean_phone
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A trusted contact with phone number '{clean_phone}' already exists for this member."
        )

    now = datetime.datetime.utcnow()
    tc = TrustedContact(
        member_id=member_id,
        name=contact_in.name.strip(),
        phone=clean_phone,
        email=clean_email,
        relationship=contact_in.relationship.strip(),
        priority=contact_in.priority,
        notification_preferences=clean_pref,
        is_active=contact_in.is_active,
        is_demo=False,
        created_at=now,
        updated_at=now
    )
    db.add(tc)
    db.commit()
    db.refresh(tc)

    if tc.priority == 1 and tc.is_active:
        member.emergency_contact_name = tc.name
        member.emergency_contact_phone = tc.phone
        db.commit()

    logger.info(f"[Security Audit] User '{current_user.username}' created TrustedContact '{tc.name}' (Priority {tc.priority}) for Member #{member_id}")
    return tc


@router.put("/{member_id}/trusted-contacts/{contact_id}", response_model=TrustedContactResponse)
def update_trusted_contact(
    member_id: int,
    contact_id: int,
    contact_in: TrustedContactUpdate,
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db)
):
    """
    Update a trusted contact's details, priority, or active status.
    """
    check_member_access(member_id, current_user, db)
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    tc = db.query(TrustedContact).filter(
        TrustedContact.id == contact_id,
        TrustedContact.member_id == member_id
    ).first()
    if not tc:
        raise HTTPException(status_code=404, detail="Trusted contact not found for this member")

    update_data = contact_in.model_dump(exclude_unset=True)
    next_phone = update_data.get("phone", tc.phone)
    next_email = update_data.get("email", tc.email)
    next_pref = update_data.get("notification_preferences", tc.notification_preferences)
    _validate_contact_destinations(next_phone, next_email, next_pref)

    for field, val in update_data.items():
        if field == "email" and val is None:
            setattr(tc, field, None)
        elif val is not None:
            if isinstance(val, str):
                setattr(tc, field, val.strip())
            else:
                setattr(tc, field, val)

    tc.updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(tc)

    if tc.priority == 1 and tc.is_active:
        member.emergency_contact_name = tc.name
        member.emergency_contact_phone = tc.phone
        db.commit()

    logger.info(f"[Security Audit] User '{current_user.username}' updated TrustedContact #{tc.id} for Member #{member_id}")
    return tc


@router.delete("/{member_id}/trusted-contacts/{contact_id}", status_code=status.HTTP_200_OK)
def delete_trusted_contact(
    member_id: int,
    contact_id: int,
    current_user: User = Depends(require_member_or_admin),
    db: Session = Depends(get_db)
):
    """
    Delete a trusted contact for a family member.
    """
    check_member_access(member_id, current_user, db)
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    tc = db.query(TrustedContact).filter(
        TrustedContact.id == contact_id,
        TrustedContact.member_id == member_id
    ).first()
    if not tc:
        raise HTTPException(status_code=404, detail="Trusted contact not found for this member")

    contact_name = tc.name
    db.delete(tc)
    db.commit()

    next_primary = db.query(TrustedContact).filter(
        TrustedContact.member_id == member_id,
        TrustedContact.is_active == True
    ).order_by(TrustedContact.priority.asc()).first()
    if next_primary:
        member.emergency_contact_name = next_primary.name
        member.emergency_contact_phone = next_primary.phone
    else:
        member.emergency_contact_name = None
        member.emergency_contact_phone = None
    db.commit()

    logger.info(f"[Security Audit] User '{current_user.username}' deleted TrustedContact '{contact_name}' (ID: {contact_id}) for Member #{member_id}")
    return {"message": f"Trusted contact '{contact_name}' deleted successfully", "id": contact_id}
