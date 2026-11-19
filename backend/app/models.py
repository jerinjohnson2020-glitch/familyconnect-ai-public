import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship as orm_relationship
from .database import Base


class Member(Base):
    __tablename__ = "members"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    name = Column(String(100), nullable=False)
    relationship = Column(String(50), default="Family Member")
    age = Column(Integer, nullable=True)
    phone = Column(String(30), nullable=False)
    email = Column(String(120), nullable=True)
    address = Column(String(255), nullable=True)
    blood_group = Column(String(10), nullable=True)
    medical_notes = Column(Text, nullable=True)
    emergency_contact_name = Column(String(100), nullable=True)
    emergency_contact_phone = Column(String(30), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_demo = Column(Boolean, default=False, nullable=False)
    # Location Sharing & Telemetry (Phase 1 Family Location MVP)
    is_sharing_location = Column(Boolean, default=False, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    location_accuracy_m = Column(Float, nullable=True)
    location_label = Column(String(100), nullable=True)
    location_updated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=True)

    user = orm_relationship("User", foreign_keys=[user_id], back_populates="members")
    incidents = orm_relationship("EmergencyIncident", back_populates="member")
    trusted_contacts = orm_relationship("TrustedContact", back_populates="member", cascade="all, delete-orphan", order_by="TrustedContact.priority")


class TrustedContact(Base):
    __tablename__ = "trusted_contacts"

    id = Column(Integer, primary_key=True, index=True)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(30), nullable=False)
    email = Column(String(120), nullable=True)
    relationship = Column(String(50), default="Family Member")  # e.g., Parent, Sibling, Spouse, Guardian, Caregiver
    priority = Column(Integer, default=1, nullable=False)        # 1 = Primary, 2 = Secondary, 3 = Tertiary...
    notification_preferences = Column(String(50), default="EMAIL")  # 'EMAIL', 'SMS', 'BOTH'
    is_active = Column(Boolean, default=True, nullable=False)
    is_demo = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    member = orm_relationship("Member", back_populates="trusted_contacts")


class Responder(Base):
    __tablename__ = "responders"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    role = Column(String(50), default="First Responder")  # Family, Neighbor, Paramedic, Nearby Clinic
    organization = Column(String(120), nullable=True)
    phone = Column(String(30), nullable=False)
    email = Column(String(120), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    location_source = Column(String(30), nullable=True)  # browser_gps, manual_coordinates, unset, demo_seed
    location_accuracy_m = Column(Float, nullable=True)
    location_updated_at = Column(DateTime, nullable=True)
    is_available = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_demo = Column(Boolean, default=False, nullable=False)
    skills = Column(String(150), default="Basic First Aid")
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=True)


class EmergencyIncident(Base):
    __tablename__ = "emergency_incidents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=True)
    reporter_name = Column(String(100), nullable=False)
    incident_type = Column(String(50), nullable=False)  # Fall, Cardiac/Chest Pain, Breathing, Unconscious, Injury, General SOS
    description = Column(Text, nullable=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    location_label = Column(String(100), default="Current Location")
    location_accuracy_m = Column(Float, nullable=True)
    location_source = Column(String(30), default="manual_coordinates")  # browser_gps, manual_coordinates, live_refresh
    location_updated_at = Column(DateTime, nullable=True)

    # AI Assessment Fields
    severity_level = Column(String(20), default="PENDING")  # LOW, MEDIUM, HIGH, CRITICAL
    severity_score = Column(Float, default=0.0)             # Probability / certainty [0.0 - 1.0]
    ai_rationale = Column(Text, nullable=True)              # Factors that drove the severity classification

    status = Column(String(20), default="ACTIVE")  # ACTIVE, RESPONDING, RESOLVED
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    resolution_notes = Column(Text, nullable=True)

    user = orm_relationship("User", foreign_keys=[user_id], back_populates="incidents")
    member = orm_relationship("Member", back_populates="incidents")
    assigned_responders = orm_relationship("IncidentResponder", back_populates="incident", cascade="all, delete-orphan")
    timeline_events = orm_relationship("IncidentTimelineEvent", back_populates="incident", cascade="all, delete-orphan", order_by="IncidentTimelineEvent.timestamp")
    alerts = orm_relationship("IncidentAlert", back_populates="incident", cascade="all, delete-orphan", order_by="IncidentAlert.sent_at")


class IncidentResponder(Base):
    __tablename__ = "incident_responders"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("emergency_incidents.id"), nullable=False)
    responder_id = Column(Integer, ForeignKey("responders.id"), nullable=False)
    distance_km = Column(Float, nullable=False)
    status = Column(String(20), default="RECOMMENDED")  # RECOMMENDED, ASSIGNED, ACCEPTED, EN_ROUTE, ARRIVED

    # Responder Lifecycle Timestamps
    assigned_at = Column(DateTime, nullable=True)
    accepted_at = Column(DateTime, nullable=True)
    en_route_at = Column(DateTime, nullable=True)
    arrived_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)

    incident = orm_relationship("EmergencyIncident", back_populates="assigned_responders")
    responder = orm_relationship("Responder")


class IncidentTimelineEvent(Base):
    __tablename__ = "incident_timeline_events"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("emergency_incidents.id"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)  # INCIDENT_CREATED, AI_TRIAGED, RESPONDERS_MATCHED, STATUS_UPDATED, ALERT_ACKNOWLEDGED, LOCATION_UPDATED
    title = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    incident = orm_relationship("EmergencyIncident", back_populates="timeline_events")


class IncidentAlert(Base):
    __tablename__ = "incident_alerts"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("emergency_incidents.id"), nullable=False, index=True)
    contact_id = Column(Integer, ForeignKey("trusted_contacts.id"), nullable=True)
    contact_name = Column(String(100), nullable=False)
    contact_phone = Column(String(30), nullable=False)
    contact_email = Column(String(120), nullable=True)
    channel = Column(String(50), default="EMAIL")            # EMAIL, SMS
    status = Column(String(30), default="QUEUED")            # QUEUED, SENT, DELIVERED, FAILED, ACKNOWLEDGED, SIMULATED
    provider = Column(String(50), nullable=True)             # smtp, resend, twilio, unconfigured, smtp_mock, resend_mock, twilio_mock
    provider_message_id = Column(String(120), nullable=True)
    delivery_attempts = Column(Integer, default=0, nullable=False)
    last_attempt_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    dedup_key = Column(String(150), nullable=True, index=True)
    sent_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    acknowledged_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=True)

    incident = orm_relationship("EmergencyIncident", back_populates="alerts")


def _default_user_verification_status(context):
    """
    Responders require explicit administrative verification and default to 'PENDING'.
    Household administrators and members default to 'APPROVED'.
    """
    if context:
        params = context.get_current_parameters()
        if params and params.get("role") == "responder":
            return "PENDING"
    return "APPROVED"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=True, index=True)
    phone = Column(String(30), nullable=True)
    full_name = Column(String(100), nullable=True)
    hashed_password = Column(String(128), nullable=False)
    salt = Column(String(64), nullable=False)
    role = Column(String(20), nullable=False)  # 'admin', 'member', 'responder'
    is_active = Column(Boolean, default=True, nullable=False)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=True)
    responder_id = Column(Integer, ForeignKey("responders.id"), nullable=True)
    household_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    verification_status = Column(String(30), default=_default_user_verification_status, nullable=False)  # 'APPROVED', 'PENDING', 'REJECTED'
    organization = Column(String(120), nullable=True)
    badge_id = Column(String(50), nullable=True)
    is_platform_reviewer = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    member = orm_relationship("Member", foreign_keys=[member_id])
    responder = orm_relationship("Responder", foreign_keys=[responder_id])
    members = orm_relationship("Member", foreign_keys="Member.user_id", back_populates="user")
    incidents = orm_relationship("EmergencyIncident", foreign_keys="EmergencyIncident.user_id", back_populates="user")
    head_of_household = orm_relationship("User", remote_side=[id], foreign_keys=[household_id], post_update=True)


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    id = Column(Integer, primary_key=True, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    revoked_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    reason = Column(String(100), default="logout", nullable=False)


class HouseholdInvitation(Base):
    __tablename__ = "household_invitations"

    id = Column(Integer, primary_key=True, index=True)
    household_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    member_id = Column(Integer, ForeignKey("members.id"), nullable=True, index=True)
    invited_email = Column(String(120), nullable=False, index=True)
    role = Column(String(20), default="member", nullable=False)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    status = Column(String(20), default="PENDING", nullable=False)  # PENDING, ACCEPTED, REVOKED, EXPIRED
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    accepted_at = Column(DateTime, nullable=True)

    household = orm_relationship("User", foreign_keys=[household_id])
    member = orm_relationship("Member", foreign_keys=[member_id])


class ResponderApplication(Base):
    __tablename__ = "responder_applications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    responder_id = Column(Integer, ForeignKey("responders.id"), nullable=True, index=True)
    applicant_name = Column(String(100), nullable=False)
    email = Column(String(120), nullable=False, index=True)
    phone = Column(String(30), nullable=False)
    organization = Column(String(120), nullable=False)
    badge_id = Column(String(50), nullable=True)
    skills = Column(String(150), nullable=True)
    status = Column(String(30), default="PENDING", nullable=False)  # PENDING, APPROVED, REJECTED
    reviewed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    review_notes = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    user = orm_relationship("User", foreign_keys=[user_id])
    reviewer = orm_relationship("User", foreign_keys=[reviewed_by_id])
    responder = orm_relationship("Responder", foreign_keys=[responder_id])


