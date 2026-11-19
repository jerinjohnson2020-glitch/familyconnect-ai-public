"""
FamilyConnect AI - Authentication Routes
Login and identity verification endpoints.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import func
import datetime
from ..database import get_db
from ..models import User, Member, ResponderApplication, Responder
from ..schemas import (
    LoginRequest,
    LoginResponse,
    UserResponse,
    RegisterRequest,
    ResponderRegisterRequest
)
from ..services.notifications import send_responder_application_received_email
from ..auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    http_bearer,
    revoke_token,
    logger
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def format_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        phone=user.phone,
        full_name=user.full_name,
        role=user.role,
        is_active=getattr(user, "is_active", True),
        member_id=user.member_id,
        responder_id=user.responder_id,
        household_id=getattr(user, "household_id", None) or (user.id if user.role == "admin" else None),
        verification_status=getattr(user, "verification_status", "APPROVED"),
        organization=getattr(user, "organization", None),
        badge_id=getattr(user, "badge_id", None),
        is_platform_reviewer=bool(getattr(user, "is_platform_reviewer", False)),
        created_at=user.created_at
    )


@router.post("/register", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """
    Self-service household registration.
    Creates a new user account with role 'admin' for their household,
    optionally creates an initial primary household member profile,
    and returns a signed bearer token.
    """
    username_clean = req.username.strip()
    email_clean = req.email.strip()
    phone_clean = req.phone.strip() if req.phone else None
    full_name_clean = req.full_name.strip() if req.full_name else None

    # Check for duplicate username (case-insensitive)
    existing_user = db.query(User).filter(func.lower(User.username) == username_clean.lower()).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{username_clean}' is already registered. Please choose another."
        )

    # Check for duplicate email (case-insensitive)
    existing_email = db.query(User).filter(func.lower(User.email) == email_clean.lower()).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An account with email '{email_clean}' already exists."
        )

    now = datetime.datetime.utcnow()
    hashed_pw, salt = hash_password(req.password)

    new_user = User(
        username=username_clean,
        email=email_clean,
        phone=phone_clean,
        full_name=full_name_clean,
        hashed_password=hashed_pw,
        salt=salt,
        role="admin",  # Newly registered users administer their own household
        is_active=True,
        verification_status="APPROVED",
        is_platform_reviewer=False,
        created_at=now
    )
    db.add(new_user)
    db.flush()
    # Explicitly set household_id to self for admin
    new_user.household_id = new_user.id

    if req.create_self_member:
        self_member = Member(
            user_id=new_user.id,
            name=full_name_clean or username_clean,
            relationship="Self",
            phone=phone_clean or "+91 98765 00001",
            email=email_clean,
            is_active=True,
            is_demo=False,
            created_at=now,
            updated_at=now
        )
        db.add(self_member)
        db.flush()
        new_user.member_id = self_member.id

    db.commit()
    db.refresh(new_user)

    logger.info(f"[Security Audit] New user registered: '{new_user.username}' (ID: {new_user.id}, role: {new_user.role})")

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


@router.post("/login", response_model=LoginResponse)
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate with username and password.
    Returns a signed bearer token with user claims.
    Never exposes stored hashes or salts.
    """
    username_clean = credentials.username.strip()
    user = db.query(User).filter(User.username == username_clean).first()

    if not user or not verify_password(credentials.password, user.hashed_password, user.salt):
        logger.warning(f"[Security Audit] Failed login attempt for username: '{username_clean}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if not getattr(user, "is_active", True):
        logger.warning(f"[Security Audit] Login rejected: User '{user.username}' is disabled.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account has been disabled",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if getattr(user, "verification_status", "APPROVED") != "APPROVED":
        status_msg = "Responder application is pending administrative review" if user.verification_status == "PENDING" else "User account verification pending approval"
        if user.verification_status == "REJECTED":
            status_msg = "Responder application was not approved"
        logger.warning(f"[Security Audit] Login rejected: User '{user.username}' verification status is '{user.verification_status}'.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=status_msg,
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Issue signed bearer token
    token_claims = {
        "sub": user.username,
        "user_id": user.id,
        "role": user.role,
        "member_id": user.member_id,
        "responder_id": user.responder_id,
        "household_id": getattr(user, "household_id", None) or (user.id if user.role == "admin" else None)
    }
    access_token = create_access_token(token_claims)

    logger.info(f"[Security Audit] Successful authentication for user '{user.username}' (role: {user.role})")

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=format_user_response(user)
    )


@router.post("/register-responder", status_code=status.HTTP_201_CREATED)
def register_responder(req: ResponderRegisterRequest, db: Session = Depends(get_db)):
    """
    Public First Responder Onboarding Application.
    Creates a User with role 'responder', is_active=False, verification_status='PENDING',
    and logs a ResponderApplication for administrative review.
    Unverified responders cannot log in, receive alerts, or access incidents until approved.
    """
    username_clean = req.username.strip()
    email_clean = req.email.strip()
    phone_clean = req.phone.strip()
    full_name_clean = req.full_name.strip()
    org_clean = req.organization.strip()
    badge_clean = req.badge_id.strip() if req.badge_id else None
    skills_clean = req.skills.strip() if req.skills else "First Responder"

    existing_user = db.query(User).filter(func.lower(User.username) == username_clean.lower()).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{username_clean}' is already registered. Please choose another."
        )

    existing_email = db.query(User).filter(func.lower(User.email) == email_clean.lower()).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An account with email '{email_clean}' already exists."
        )

    now = datetime.datetime.utcnow()
    hashed_pw, salt = hash_password(req.password)

    new_user = User(
        username=username_clean,
        email=email_clean,
        phone=phone_clean,
        full_name=full_name_clean,
        hashed_password=hashed_pw,
        salt=salt,
        role="responder",
        is_active=False,  # Blocked until administrative approval
        verification_status="PENDING",
        organization=org_clean,
        badge_id=badge_clean,
        is_platform_reviewer=False,
        created_at=now
    )
    db.add(new_user)
    db.flush()

    application = ResponderApplication(
        user_id=new_user.id,
        applicant_name=full_name_clean,
        email=email_clean,
        phone=phone_clean,
        organization=org_clean,
        badge_id=badge_clean,
        skills=skills_clean,
        status="PENDING",
        created_at=now
    )
    db.add(application)
    db.commit()
    db.refresh(application)

    logger.info(f"[Security Audit] New responder application submitted: '{new_user.username}' (App ID: {application.id}, Org: '{org_clean}')")

    # Dispatch confirmation email via verified sender (safe mock in tests)
    try:
        send_responder_application_received_email(
            recipient_email=email_clean,
            applicant_name=full_name_clean,
            organization=org_clean
        )
    except Exception as exc:
        logger.warning(f"[Notifications] Failed to send responder application confirmation email: {exc}")

    return {
        "status": "pending_approval",
        "message": "Application submitted successfully. A platform administrator will review your credentials before account activation.",
        "application_id": application.id
    }


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """
    Retrieve authenticated user's profile and active role.
    Requires a valid bearer token.
    """
    return format_user_response(current_user)


@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Revoke caller's active bearer token.
    Stores the token's cryptographic SHA-256 hash in the database blocklist.
    """
    if credentials and credentials.credentials:
        revoke_token(credentials.credentials, db, user_id=current_user.id, reason="user_logout")
    logger.info(f"[Security Audit] User '{current_user.username}' logged out and revoked active token.")
    return {"status": "success", "message": "Successfully logged out and revoked token"}

