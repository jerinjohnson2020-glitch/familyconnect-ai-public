"""
FamilyConnect AI - Household & Member Invitation Routes
Phase 3B: Secure Cryptographic Household Invitations
"""

import os
import hashlib
import secrets
import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..models import User, Member, HouseholdInvitation
from ..schemas import (
    CreateInvitationRequest,
    InvitationResponse,
    ValidateInvitationResponse,
    AcceptInvitationRequest,
    LoginResponse
)
from ..routes.auth import format_user_response
from ..auth import (
    hash_password,
    create_access_token,
    get_current_user,
    require_admin,
    logger
)
from ..services.notifications import send_household_invitation_email

router = APIRouter(prefix="/api/household", tags=["Household Invitations"])


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


def _get_household_id(user: User) -> int:
    return getattr(user, "household_id", None) or user.id


@router.post("/invitations", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED)
def create_invitation(
    req: CreateInvitationRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Issue a secure household invitation.
    - Household admin only, strictly scoped to their own household.
    - Stores only the SHA-256 hash of a cryptographically secure random token.
    - Dispatches a verified email notification to the invitee.
    """
    household_id = _get_household_id(current_user)
    invited_email_clean = req.email.strip().lower()

    # Verify if user with this email is already a member of this household
    existing_user = db.query(User).filter(
        func.lower(User.email) == invited_email_clean
    ).first()
    if existing_user and (existing_user.household_id == household_id or existing_user.id == household_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with email '{invited_email_clean}' is already part of this household."
        )

    # If a specific member_id is targeted, verify it belongs to this household
    if req.member_id:
        member = db.query(Member).filter(Member.id == req.member_id).first()
        if not member or member.user_id != household_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected member profile does not belong to your household."
            )

    now = datetime.datetime.utcnow()
    expires_at = now + datetime.timedelta(hours=72)

    # Revoke any prior pending invites for this email in this household to prevent token collision
    prior_invites = db.query(HouseholdInvitation).filter(
        HouseholdInvitation.household_id == household_id,
        func.lower(HouseholdInvitation.invited_email) == invited_email_clean,
        HouseholdInvitation.status == "PENDING"
    ).all()
    for prior in prior_invites:
        prior.status = "REVOKED"

    # Generate high-entropy single-use URL token
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)

    invitation = HouseholdInvitation(
        household_id=household_id,
        member_id=req.member_id,
        invited_email=invited_email_clean,
        role=req.role or "member",
        token_hash=token_hash,
        status="PENDING",
        expires_at=expires_at,
        created_at=now
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    logger.info(
        f"[Security Audit] Admin '{current_user.username}' created invitation #{invitation.id} "
        f"for '{invited_email_clean}' into Household #{household_id} (Expires: {expires_at.isoformat()})"
    )

    # Construct invitation link using FRONTEND_PUBLIC_URL if configured, falling back to APP_BASE_URL or local dev
    frontend_base_url = (os.environ.get("FRONTEND_PUBLIC_URL") or os.environ.get("APP_BASE_URL") or "").strip().rstrip("/")
    if not frontend_base_url:
        frontend_base_url = "http://127.0.0.1:5173"
    invitation_link = f"{frontend_base_url}/accept-invite?token={raw_token}"

    household_name = current_user.full_name or current_user.username
    try:
        send_household_invitation_email(
            recipient_email=invited_email_clean,
            inviter_name=household_name,
            household_name=f"{household_name}'s Household",
            invitation_link=invitation_link,
            role=invitation.role,
            expires_hours=72
        )
    except Exception as exc:
        logger.warning(f"[Notifications] Error dispatching invitation email to '{invited_email_clean}': {exc}")

    # Return invitation response including token and link for immediate display in UI
    resp = InvitationResponse(
        id=invitation.id,
        household_id=invitation.household_id,
        member_id=invitation.member_id,
        invited_email=invitation.invited_email,
        role=invitation.role,
        status=invitation.status,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        accepted_at=invitation.accepted_at,
        invitation_token=raw_token,
        invitation_link=invitation_link
    )
    return resp


@router.get("/invitations", response_model=List[InvitationResponse])
def list_household_invitations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List invitations for the caller's household.
    Strictly isolated: users can only view invitations belonging to their household.
    """
    household_id = _get_household_id(current_user)

    now = datetime.datetime.utcnow()
    # Auto-expire any overdue pending invitations on fetch
    overdue_invites = db.query(HouseholdInvitation).filter(
        HouseholdInvitation.household_id == household_id,
        HouseholdInvitation.status == "PENDING",
        HouseholdInvitation.expires_at < now
    ).all()
    if overdue_invites:
        for oi in overdue_invites:
            oi.status = "EXPIRED"
        db.commit()

    invitations = db.query(HouseholdInvitation).filter(
        HouseholdInvitation.household_id == household_id
    ).order_by(HouseholdInvitation.created_at.desc()).all()

    return [
        InvitationResponse(
            id=inv.id,
            household_id=inv.household_id,
            member_id=inv.member_id,
            invited_email=inv.invited_email,
            role=inv.role,
            status=inv.status,
            expires_at=inv.expires_at,
            created_at=inv.created_at,
            accepted_at=inv.accepted_at,
            invitation_token=None,
            invitation_link=None
        )
        for inv in invitations
    ]


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_200_OK)
def revoke_invitation(
    invitation_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Revoke a pending household invitation.
    Strictly isolated: only the inviting household admin can revoke.
    """
    household_id = _get_household_id(current_user)
    invitation = db.query(HouseholdInvitation).filter(
        HouseholdInvitation.id == invitation_id
    ).first()

    if not invitation or invitation.household_id != household_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found or belongs to another household"
        )

    if invitation.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot revoke invitation with status '{invitation.status}'"
        )

    invitation.status = "REVOKED"
    db.commit()

    logger.info(f"[Security Audit] Admin '{current_user.username}' revoked invitation #{invitation.id}")
    return {"status": "success", "message": "Invitation successfully revoked"}


@router.get("/invitations/validate", response_model=ValidateInvitationResponse)
def validate_invitation_token(
    token: str = Query(..., min_length=10),
    db: Session = Depends(get_db)
):
    """
    Public token validation endpoint.
    Verifies that the invitation token is valid, unexpired, and pending.
    Does not require authentication.
    """
    token_hash = _hash_token(token)
    invitation = db.query(HouseholdInvitation).filter(
        HouseholdInvitation.token_hash == token_hash
    ).first()

    if not invitation:
        return ValidateInvitationResponse(
            valid=False,
            error="Invitation token is invalid or does not exist."
        )

    now = datetime.datetime.utcnow()
    if invitation.expires_at < now:
        if invitation.status == "PENDING":
            invitation.status = "EXPIRED"
            db.commit()
        return ValidateInvitationResponse(
            valid=False,
            error="This invitation has expired. Please request a new invitation."
        )

    if invitation.status != "PENDING":
        return ValidateInvitationResponse(
            valid=False,
            error=f"This invitation has already been {invitation.status.lower()}."
        )

    household_owner = db.query(User).filter(User.id == invitation.household_id).first()
    household_name = (household_owner.full_name or household_owner.username) if household_owner else "Family Household"

    return ValidateInvitationResponse(
        valid=True,
        email=invitation.invited_email,
        household_id=invitation.household_id,
        household_name=household_name,
        role=invitation.role
    )


@router.post("/invitations/accept", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
def accept_invitation(
    req: AcceptInvitationRequest,
    db: Session = Depends(get_db)
):
    """
    Accept a household invitation and register a new user account.
    - Validates token hash and pending state.
    - Single-use: marks invitation ACCEPTED immediately.
    - Binds user to the inviting household_id with assigned role.
    - Returns authenticated session token.
    """
    token_hash = _hash_token(req.token)
    invitation = db.query(HouseholdInvitation).filter(
        HouseholdInvitation.token_hash == token_hash
    ).first()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation token is invalid."
        )

    now = datetime.datetime.utcnow()
    if invitation.expires_at < now:
        if invitation.status == "PENDING":
            invitation.status = "EXPIRED"
            db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation has expired."
        )

    if invitation.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"This invitation has already been {invitation.status.lower()}."
        )

    username_clean = req.username.strip()
    full_name_clean = req.full_name.strip() if req.full_name else username_clean
    phone_clean = req.phone.strip() if req.phone else None

    # Check for duplicate username
    existing_user = db.query(User).filter(
        func.lower(User.username) == username_clean.lower()
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{username_clean}' is already taken. Please choose another."
        )

    # Check for duplicate email
    existing_email = db.query(User).filter(
        func.lower(User.email) == invitation.invited_email.lower()
    ).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An account with email '{invitation.invited_email}' already exists. Please log in instead."
        )

    hashed_pw, salt = hash_password(req.password)

    new_user = User(
        username=username_clean,
        email=invitation.invited_email,
        phone=phone_clean,
        full_name=full_name_clean,
        hashed_password=hashed_pw,
        salt=salt,
        role=invitation.role or "member",
        is_active=True,
        verification_status="APPROVED",
        household_id=invitation.household_id,
        is_platform_reviewer=False,
        created_at=now
    )
    db.add(new_user)
    db.flush()

    # Link or create member profile
    if invitation.member_id:
        member = db.query(Member).filter(Member.id == invitation.member_id).first()
        if member:
            member.user_id = invitation.household_id
            if phone_clean and not member.phone:
                member.phone = phone_clean
            if not member.email:
                member.email = invitation.invited_email
            new_user.member_id = member.id
    else:
        # Create a member profile in this household for the user
        member = Member(
            user_id=invitation.household_id,
            name=full_name_clean,
            relationship="Family Member",
            phone=phone_clean or "+91 98765 00002",
            email=invitation.invited_email,
            is_active=True,
            is_demo=False,
            created_at=now,
            updated_at=now
        )
        db.add(member)
        db.flush()
        new_user.member_id = member.id

    # Mark invitation as accepted
    invitation.status = "ACCEPTED"
    invitation.accepted_at = now

    db.commit()
    db.refresh(new_user)

    logger.info(
        f"[Security Audit] User '{new_user.username}' (ID: {new_user.id}) accepted invitation #{invitation.id} "
        f"and joined Household #{invitation.household_id} as '{new_user.role}'."
    )

    token_claims = {
        "sub": new_user.username,
        "user_id": new_user.id,
        "role": new_user.role,
        "member_id": new_user.member_id,
        "responder_id": new_user.responder_id,
        "household_id": new_user.household_id
    }
    access_token = create_access_token(token_claims)

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=format_user_response(new_user)
    )
