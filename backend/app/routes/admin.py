"""
FamilyConnect AI - Platform Administration & Responder Review Routes
Phase 3B: Community First-Responder Vetting and Administrative Approval
"""

import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..models import User, Responder, ResponderApplication
from ..schemas import ResponderApplicationResponse, ResponderReviewRequest
from ..auth import require_platform_reviewer, logger
from ..services.notifications import send_responder_application_decision_email

router = APIRouter(prefix="/api/admin", tags=["Platform Administration"])


@router.get("/responders/applications", response_model=List[ResponderApplicationResponse])
def list_responder_applications(
    app_status: Optional[str] = Query(None, alias="status", description="Filter by status: PENDING, APPROVED, REJECTED"),
    current_user: User = Depends(require_platform_reviewer),
    db: Session = Depends(get_db)
):
    """
    List all first-responder applications.
    Restricted strictly to authorized platform reviewers.
    """
    query = db.query(ResponderApplication)
    if app_status:
        query = query.filter(func.upper(ResponderApplication.status) == app_status.strip().upper())
    return query.order_by(ResponderApplication.created_at.desc()).all()


@router.get("/responders/applications/{app_id}", response_model=ResponderApplicationResponse)
def get_responder_application(
    app_id: int,
    current_user: User = Depends(require_platform_reviewer),
    db: Session = Depends(get_db)
):
    """
    Retrieve single first-responder application by ID.
    Restricted strictly to authorized platform reviewers.
    """
    application = db.query(ResponderApplication).filter(ResponderApplication.id == app_id).first()
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Responder application #{app_id} not found."
        )
    return application


@router.post("/responders/applications/{app_id}/review", response_model=ResponderApplicationResponse)
def review_responder_application(
    app_id: int,
    review_req: ResponderReviewRequest,
    current_user: User = Depends(require_platform_reviewer),
    db: Session = Depends(get_db)
):
    """
    Approve or reject a community first-responder application.
    Restricted strictly to authorized platform reviewers.
    - If approved: Activates the user account, creates/links their responder profile,
      and dispatches approval notification via verified sender.
    - If rejected: Leaves account disabled, logs reviewer notes, and notifies applicant.
    """
    application = db.query(ResponderApplication).filter(ResponderApplication.id == app_id).first()
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Responder application #{app_id} not found."
        )

    action = review_req.action.upper()
    now = datetime.datetime.utcnow()

    user = db.query(User).filter(User.id == application.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated user account for this application could not be found."
        )

    if action == "APPROVE":
        application.status = "APPROVED"
        application.reviewed_by_id = current_user.id
        application.reviewed_at = now
        application.review_notes = review_req.review_notes

        # Activate user account
        user.is_active = True
        user.verification_status = "APPROVED"

        # Create or link Responder record
        if user.responder_id:
            responder = db.query(Responder).filter(Responder.id == user.responder_id).first()
            if responder:
                responder.is_active = True
                responder.is_available = True
                responder.organization = application.organization
                responder.updated_at = now
        else:
            responder = Responder(
                name=application.applicant_name,
                role="First Responder",
                organization=application.organization,
                phone=application.phone,
                email=application.email,
                is_available=True,
                is_active=True,
                is_demo=False,
                skills=application.skills or "First Responder",
                location_source="unset",
                created_at=now,
                updated_at=now
            )
            db.add(responder)
            db.flush()
            user.responder_id = responder.id
            application.responder_id = responder.id

        db.commit()
        db.refresh(application)

        logger.info(
            f"[Security Audit] Platform Reviewer '{current_user.username}' APPROVED responder application #{app_id} "
            f"for user '{user.username}' (Responder ID: {user.responder_id})"
        )

        try:
            send_responder_application_decision_email(
                recipient_email=application.email,
                applicant_name=application.applicant_name,
                approved=True,
                review_notes=review_req.review_notes
            )
        except Exception as exc:
            logger.warning(f"[Notifications] Error dispatching approval email to '{application.email}': {exc}")

    elif action == "REJECT":
        application.status = "REJECTED"
        application.reviewed_by_id = current_user.id
        application.reviewed_at = now
        application.review_notes = review_req.review_notes

        user.is_active = False
        user.verification_status = "REJECTED"

        db.commit()
        db.refresh(application)

        logger.info(
            f"[Security Audit] Platform Reviewer '{current_user.username}' REJECTED responder application #{app_id} "
            f"for user '{user.username}'"
        )

        try:
            send_responder_application_decision_email(
                recipient_email=application.email,
                applicant_name=application.applicant_name,
                approved=False,
                review_notes=review_req.review_notes
            )
        except Exception as exc:
            logger.warning(f"[Notifications] Error dispatching rejection email to '{application.email}': {exc}")

    return application
