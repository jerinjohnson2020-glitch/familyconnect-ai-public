import re
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


PHONE_PATTERN = re.compile(r"^[0-9+\-().\s]+$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_phone_format(v: Optional[str]) -> Optional[str]:
    """
    Validates and normalizes phone numbers with India (+91) as default.
    - 10-digit Indian numbers starting with 6, 7, 8, 9 -> '+91 XXXXX XXXXX'
    - '+91' prefixed numbers -> '+91 XXXXX XXXXX'
    - '0' prefixed 11-digit numbers (domestic) -> '+91 XXXXX XXXXX'
    - '91' prefixed 12-digit numbers -> '+91 XXXXX XXXXX'
    - International numbers starting with '+' preserved without altering country code
    - Rejects invalid formats, wrong lengths, and placeholder patterns (ending with 000-0000)
    """
    if v is None:
        return None
    cleaned = v.strip()
    if not cleaned:
        return None

    # Check for placeholder phone pattern (e.g. ending with 000-0000)
    if cleaned.endswith("000-0000"):
        raise ValueError("Placeholder phone numbers ending in 000-0000 are not allowed.")

    # Character set check: digits, +, -, (, ), ., and spaces
    if not PHONE_PATTERN.match(cleaned):
        raise ValueError("Phone number contains invalid characters (allowed: digits, spaces, hyphens, parentheses, and '+').")

    if len(cleaned) > 30:
        raise ValueError("Phone number is too long (maximum 30 characters).")

    digits = "".join(c for c in cleaned if c.isdigit())
    if len(digits) < 7:
        raise ValueError("Phone number is too short (must contain at least 7 digits).")

    # 1. Indian Mobile Number with explicit +91 country prefix
    if cleaned.startswith("+91"):
        in_digits = digits[2:] if digits.startswith("91") else digits
        if len(in_digits) != 10:
            raise ValueError(
                f"Invalid Indian mobile number. Expected exactly 10 digits after +91, but got {len(in_digits)} (e.g. +91 98765 43210)."
            )
        if in_digits[0] not in "6789":
            raise ValueError(
                f"Invalid Indian mobile number. Mobile numbers in India must start with 6, 7, 8, or 9 (got '{in_digits[0]}')."
            )
        return f"+91 {in_digits[:5]} {in_digits[5:]}"

    # 2. Domestic trunk prefix '0' (11 digits: 0 followed by 10 digits starting with 6-9)
    if len(digits) == 11 and digits.startswith("0") and digits[1] in "6789":
        in_digits = digits[1:]
        return f"+91 {in_digits[:5]} {in_digits[5:]}"

    # 3. 12 digits starting with '91' without '+'
    if len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
        in_digits = digits[2:]
        return f"+91 {in_digits[:5]} {in_digits[5:]}"

    # 4. Standard 10-digit Indian Mobile Number without country code (Default Country: India +91)
    if len(digits) == 10 and not cleaned.startswith("+"):
        if digits[0] in "6789":
            return f"+91 {digits[:5]} {digits[5:]}"
        else:
            raise ValueError(
                "Invalid Indian mobile number. A 10-digit mobile number must start with 6, 7, 8, or 9 (e.g. +91 98765 43210). "
                "For international numbers, please prefix with '+' and the country code."
            )

    # 5. International Number starting with '+' (and not +91)
    if cleaned.startswith("+"):
        if len(digits) < 7 or len(digits) > 15:
            raise ValueError("Invalid international phone number. Expected 7 to 15 digits including country code.")
        return cleaned

    # 6. US/NANP 11-digit number starting with 1 (e.g. 1-415-891-3344)
    if len(digits) == 11 and digits.startswith("1"):
        return f"+1 {digits[1:4]} {digits[4:7]} {digits[7:]}"

    raise ValueError(
        "Invalid phone number format. Please provide a valid 10-digit Indian mobile number (e.g. 98765 43210 or +91 98765 43210) "
        "or an international number starting with '+'."
    )


def validate_email_format(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    cleaned = v.strip()
    if not cleaned:
        return None
    if not EMAIL_PATTERN.match(cleaned):
        raise ValueError("Invalid email address format")
    return cleaned


# Auth Schemas
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=100)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=100)
    email: str = Field(..., min_length=5, max_length=120)
    phone: Optional[str] = Field(None, max_length=30)
    full_name: Optional[str] = Field(None, min_length=1, max_length=100)
    create_self_member: bool = True

    @field_validator("username")
    @classmethod
    def check_username(cls, v: str) -> str:
        cleaned = v.strip()
        if not re.match(r"^[a-zA-Z0-9_.-]+$", cleaned):
            raise ValueError("Username may only contain letters, numbers, underscores, dots, and hyphens.")
        return cleaned

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        has_letter = any(c.isalpha() for c in v)
        has_digit = any(c.isdigit() for c in v)
        if not (has_letter and has_digit):
            raise ValueError("Password must contain at least one letter and at least one digit.")
        return v

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        val = validate_email_format(v)
        if not val:
            raise ValueError("A valid email address is required.")
        return val

    @field_validator("phone")
    @classmethod
    def check_phone(cls, v: Optional[str]) -> Optional[str]:
        return validate_phone_format(v)


class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    phone: Optional[str] = None
    full_name: Optional[str] = None
    role: str
    is_active: bool = True
    member_id: Optional[int] = None
    responder_id: Optional[int] = None
    household_id: Optional[int] = None
    verification_status: Optional[str] = "APPROVED"
    organization: Optional[str] = None
    badge_id: Optional[str] = None
    is_platform_reviewer: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# Member Schemas
class MemberBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    relationship: str = Field("Family Member", max_length=50)
    age: Optional[int] = Field(None, ge=0, le=130)
    phone: str = Field(..., min_length=7, max_length=30)
    email: Optional[str] = Field(None, max_length=120)
    address: Optional[str] = Field(None, max_length=255)
    blood_group: Optional[str] = Field(None, max_length=10)
    medical_notes: Optional[str] = Field(None, max_length=1000)
    emergency_contact_name: Optional[str] = Field(None, max_length=100)
    emergency_contact_phone: Optional[str] = Field(None, max_length=30)
    is_active: bool = True

    @field_validator("phone")
    @classmethod
    def check_phone(cls, v: str) -> str:
        res = validate_phone_format(v)
        if not res:
            raise ValueError("Phone number is required.")
        return res

    @field_validator("emergency_contact_phone")
    @classmethod
    def check_emergency_phone(cls, v: Optional[str]) -> Optional[str]:
        return validate_phone_format(v)

    @field_validator("email")
    @classmethod
    def check_email(cls, v: Optional[str]) -> Optional[str]:
        return validate_email_format(v)


class MemberCreate(MemberBase):
    pass


class MemberUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    relationship: Optional[str] = Field(None, max_length=50)
    age: Optional[int] = Field(None, ge=0, le=130)
    phone: Optional[str] = Field(None, min_length=7, max_length=30)
    email: Optional[str] = Field(None, max_length=120)
    address: Optional[str] = Field(None, max_length=255)
    blood_group: Optional[str] = Field(None, max_length=10)
    medical_notes: Optional[str] = Field(None, max_length=1000)
    emergency_contact_name: Optional[str] = Field(None, max_length=100)
    emergency_contact_phone: Optional[str] = Field(None, max_length=30)
    is_active: Optional[bool] = None

    @field_validator("phone", "emergency_contact_phone")
    @classmethod
    def check_phone(cls, v: Optional[str]) -> Optional[str]:
        return validate_phone_format(v)

    @field_validator("email")
    @classmethod
    def check_email(cls, v: Optional[str]) -> Optional[str]:
        return validate_email_format(v)


# Trusted Contact Schemas (Phase 4A + Phase 5B + Phase 6 Validation)
class TrustedContactBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    phone: str = Field(..., min_length=7, max_length=30)
    email: Optional[str] = Field(None, max_length=120)
    relationship: str = Field("Family Member", min_length=1, max_length=50)
    priority: int = Field(1, ge=1, le=10, description="1=Primary, 2=Secondary, 3=Tertiary...")
    notification_preferences: str = Field("EMAIL", max_length=50)
    is_active: bool = True

    @field_validator("phone")
    @classmethod
    def check_phone(cls, v: str) -> str:
        res = validate_phone_format(v)
        if not res:
            raise ValueError("Phone number is required.")
        return res

    @field_validator("email")
    @classmethod
    def check_email(cls, v: Optional[str]) -> Optional[str]:
        return validate_email_format(v)


class TrustedContactCreate(TrustedContactBase):
    pass


class TrustedContactUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = Field(None, min_length=7, max_length=30)
    email: Optional[str] = Field(None, max_length=120)
    relationship: Optional[str] = Field(None, min_length=1, max_length=50)
    priority: Optional[int] = Field(None, ge=1, le=10)
    notification_preferences: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None

    @field_validator("phone")
    @classmethod
    def check_phone(cls, v: Optional[str]) -> Optional[str]:
        return validate_phone_format(v)

    @field_validator("email")
    @classmethod
    def check_email(cls, v: Optional[str]) -> Optional[str]:
        return validate_email_format(v)


class TrustedContactResponse(TrustedContactBase):
    id: int
    member_id: int
    is_demo: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MemberResponse(MemberBase):
    id: int
    is_demo: bool = False
    is_sharing_location: bool = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_accuracy_m: Optional[float] = None
    location_label: Optional[str] = None
    location_updated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    trusted_contacts: List[TrustedContactResponse] = []

    class Config:
        from_attributes = True


# Member Location Schemas (Phase 1 Family Location MVP)
class MemberLocationConsentToggle(BaseModel):
    is_sharing: bool = Field(..., description="Explicit user consent to share real-time location with household")


class MemberLocationUpdate(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0, description="WGS84 Latitude between -90.0 and 90.0")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="WGS84 Longitude between -180.0 and 180.0")
    accuracy_m: Optional[float] = Field(None, ge=0.0, description="Optional GPS sensor accuracy in meters")
    label: Optional[str] = Field(None, max_length=100, description="Optional location label")

    @field_validator("latitude")
    @classmethod
    def validate_latitude(cls, v: float) -> float:
        if v is None or not (-90.0 <= v <= 90.0):
            raise ValueError("Latitude must be between -90.0 and 90.0 degrees.")
        return float(v)

    @field_validator("longitude")
    @classmethod
    def validate_longitude(cls, v: float) -> float:
        if v is None or not (-180.0 <= v <= 180.0):
            raise ValueError("Longitude must be between -180.0 and 180.0 degrees.")
        return float(v)


class MemberLocationItem(BaseModel):
    member_id: int
    name: str
    relationship: str
    is_sharing_location: bool
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_accuracy_m: Optional[float] = None
    location_label: Optional[str] = None
    location_updated_at: Optional[datetime] = None
    is_stale: bool = False
    age_minutes: Optional[int] = None

    class Config:
        from_attributes = True


class HouseholdLocationsResponse(BaseModel):
    household_id: int
    members: List[MemberLocationItem]
    active_sharing_count: int


# Responder Schemas (Phase 6 Configurable Responders & Real Coordinates)
class ResponderBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    role: str = Field("First Responder", max_length=50)
    organization: Optional[str] = Field(None, max_length=120)
    phone: str = Field(..., min_length=7, max_length=30)
    email: Optional[str] = Field(None, max_length=120)
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    location_source: Optional[str] = Field(None, max_length=30)
    location_accuracy_m: Optional[float] = Field(None, ge=0.0)
    is_available: bool = True
    is_active: bool = True
    skills: str = Field("Basic First Aid", max_length=150)

    @field_validator("phone")
    @classmethod
    def check_phone(cls, v: str) -> str:
        res = validate_phone_format(v)
        if not res:
            raise ValueError("Phone number is required.")
        return res

    @field_validator("email")
    @classmethod
    def check_email(cls, v: Optional[str]) -> Optional[str]:
        return validate_email_format(v)


class ResponderCreate(ResponderBase):
    pass


class ResponderUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    role: Optional[str] = Field(None, max_length=50)
    organization: Optional[str] = Field(None, max_length=120)
    phone: Optional[str] = Field(None, min_length=7, max_length=30)
    email: Optional[str] = Field(None, max_length=120)
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    location_source: Optional[str] = Field(None, max_length=30)
    location_accuracy_m: Optional[float] = Field(None, ge=0.0)
    clear_coordinates: Optional[bool] = False
    is_available: Optional[bool] = None
    is_active: Optional[bool] = None
    skills: Optional[str] = Field(None, max_length=150)

    @field_validator("phone")
    @classmethod
    def check_phone(cls, v: Optional[str]) -> Optional[str]:
        return validate_phone_format(v)

    @field_validator("email")
    @classmethod
    def check_email(cls, v: Optional[str]) -> Optional[str]:
        return validate_email_format(v)


class ResponderLocationUpdate(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    location_source: str = Field("browser_gps", max_length=30)
    location_accuracy_m: Optional[float] = Field(None, ge=0.0)
    is_available: Optional[bool] = None


class ResponderResponse(ResponderBase):
    id: int
    is_demo: bool = False
    location_accuracy_m: Optional[float] = None
    location_updated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    linked_user_active: Optional[bool] = None

    class Config:
        from_attributes = True


# Emergency Incident Schemas
class IncidentCreate(BaseModel):
    member_id: Optional[int] = None
    reporter_name: str = Field(..., min_length=1, max_length=100)
    incident_type: str = Field(..., min_length=2, max_length=100, description="e.g., Chest Pain, Fall, Breathing Difficulty, Unconscious, Severe Bleeding, General SOS")
    description: Optional[str] = Field(None, max_length=1000)
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    location_label: str = Field("Current Location", max_length=100)
    location_accuracy_m: Optional[float] = Field(None, ge=0.0)
    location_source: Optional[str] = Field("manual_coordinates", max_length=30)
    is_conscious: Optional[bool] = True
    has_breathing_difficulty: Optional[bool] = False
    is_bleeding_severely: Optional[bool] = False
    is_alone: Optional[bool] = True


class IncidentLocationUpdate(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    location_accuracy_m: Optional[float] = Field(None, ge=0.0)
    location_source: str = Field("LIVE_REFRESH", max_length=30)
    location_label: Optional[str] = Field(None, max_length=100)


class ResponderMatchResponse(BaseModel):
    id: Optional[int] = None
    assignment_id: Optional[int] = None
    responder_id: int
    name: str
    role: str
    organization: Optional[str] = None
    phone: str
    skills: str
    distance_km: float
    is_available: bool = True
    location_source: Optional[str] = None
    location_updated_at: Optional[datetime] = None
    status: str
    assigned_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    en_route_at: Optional[datetime] = None
    arrived_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AssignmentStatusUpdate(BaseModel):
    status: str = Field(..., description="ACCEPTED, EN_ROUTE, ARRIVED")


class IncidentTimelineEventResponse(BaseModel):
    id: int
    incident_id: int
    event_type: str
    title: str
    description: Optional[str] = None
    timestamp: datetime

    class Config:
        from_attributes = True


class IncidentAlertResponse(BaseModel):
    id: int
    incident_id: int
    contact_id: Optional[int] = None
    contact_name: str
    contact_phone: str
    contact_email: Optional[str] = None
    channel: str
    status: str
    provider: Optional[str] = None
    provider_message_id: Optional[str] = None
    delivery_attempts: int = 0
    last_attempt_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    error_message: Optional[str] = None
    sent_at: datetime
    acknowledged_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class IncidentResponse(BaseModel):
    id: int
    member_id: Optional[int]
    reporter_name: str
    incident_type: str
    description: Optional[str]
    latitude: float
    longitude: float
    location_label: str
    location_accuracy_m: Optional[float] = None
    location_source: Optional[str] = "manual_coordinates"
    location_updated_at: Optional[datetime] = None
    severity_level: str
    severity_score: float
    ai_rationale: Optional[str]
    status: str
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    matched_responders: List[ResponderMatchResponse] = []
    timeline_events: List[IncidentTimelineEventResponse] = []
    alerts: List[IncidentAlertResponse] = []

    class Config:
        from_attributes = True


class IncidentStatusUpdate(BaseModel):
    status: str = Field(..., description="ACTIVE, RESPONDING, RESOLVED")
    resolution_notes: Optional[str] = Field(None, max_length=1000, description="Resolution notes when marking incident RESOLVED")


class TestNotificationRequest(BaseModel):
    channel: str = Field("EMAIL", description="EMAIL or SMS")
    recipient: str = Field(..., min_length=3, max_length=120, description="Destination email address or phone number")
    confirm_send: bool = Field(..., description="Must be explicitly True to dispatch a test message")


class AIAssessmentResponse(BaseModel):
    severity_level: str
    severity_score: float
    confidence_percentage: float
    model_name: str
    risk_factors: List[str]
    recommended_action: str
    ai_rationale: Optional[str] = None
    extracted_concepts: List[str] = []
    negated_concepts: List[str] = []
    has_conflicts: bool = False
    conflict_warnings: List[str] = []
    model_version: Optional[str] = "v2"
    raw_model_prediction: Optional[str] = None
    raw_model_confidence: Optional[float] = None
    safety_override_applied: bool = False
    safety_override_reason: Optional[str] = None
    prediction_source: Optional[str] = "ML_MODEL_V2"


# Household Invitation Schemas
class CreateInvitationRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=120)
    member_id: Optional[int] = None
    role: str = Field("member", max_length=20)

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        val = validate_email_format(v)
        if not val:
            raise ValueError("A valid recipient email address is required.")
        return val


class InvitationResponse(BaseModel):
    id: int
    household_id: int
    member_id: Optional[int] = None
    invited_email: str
    role: str
    status: str
    expires_at: datetime
    created_at: datetime
    accepted_at: Optional[datetime] = None
    invitation_token: Optional[str] = None
    invitation_link: Optional[str] = None

    class Config:
        from_attributes = True


class ValidateInvitationResponse(BaseModel):
    valid: bool
    email: Optional[str] = None
    household_id: Optional[int] = None
    household_name: Optional[str] = None
    role: Optional[str] = None
    error: Optional[str] = None


class AcceptInvitationRequest(BaseModel):
    token: str = Field(..., min_length=10)
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=100)
    full_name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=30)

    @field_validator("username")
    @classmethod
    def check_username(cls, v: str) -> str:
        cleaned = v.strip()
        if not re.match(r"^[a-zA-Z0-9_.-]+$", cleaned):
            raise ValueError("Username may only contain letters, numbers, underscores, dots, and hyphens.")
        return cleaned

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        has_letter = any(c.isalpha() for c in v)
        has_digit = any(c.isdigit() for c in v)
        if not (has_letter and has_digit):
            raise ValueError("Password must contain at least one letter and at least one digit.")
        return v

    @field_validator("phone")
    @classmethod
    def check_phone(cls, v: Optional[str]) -> Optional[str]:
        return validate_phone_format(v)


# Responder Onboarding Schemas
class ResponderRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=100)
    email: str = Field(..., min_length=5, max_length=120)
    phone: str = Field(..., min_length=7, max_length=30)
    full_name: str = Field(..., min_length=2, max_length=100)
    organization: str = Field(..., min_length=2, max_length=120)
    badge_id: Optional[str] = Field(None, max_length=50)
    skills: Optional[str] = Field(None, max_length=150)
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)

    @field_validator("username")
    @classmethod
    def check_username(cls, v: str) -> str:
        cleaned = v.strip()
        if not re.match(r"^[a-zA-Z0-9_.-]+$", cleaned):
            raise ValueError("Username may only contain letters, numbers, underscores, dots, and hyphens.")
        return cleaned

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        has_letter = any(c.isalpha() for c in v)
        has_digit = any(c.isdigit() for c in v)
        if not (has_letter and has_digit):
            raise ValueError("Password must contain at least one letter and at least one digit.")
        return v

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        val = validate_email_format(v)
        if not val:
            raise ValueError("A valid email address is required.")
        return val

    @field_validator("phone")
    @classmethod
    def check_phone(cls, v: str) -> str:
        res = validate_phone_format(v)
        if not res:
            raise ValueError("Phone number is required.")
        return res


class ResponderApplicationResponse(BaseModel):
    id: int
    user_id: int
    responder_id: Optional[int] = None
    applicant_name: str
    email: str
    phone: str
    organization: str
    badge_id: Optional[str] = None
    skills: Optional[str] = None
    status: str
    reviewed_by_id: Optional[int] = None
    review_notes: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ResponderReviewRequest(BaseModel):
    action: str = Field(..., description="'APPROVE' or 'REJECT'")
    review_notes: Optional[str] = Field(None, max_length=500)

    @field_validator("action")
    @classmethod
    def check_action(cls, v: str) -> str:
        action_upper = v.strip().upper()
        if action_upper not in ("APPROVE", "REJECT"):
            raise ValueError("Action must be either 'APPROVE' or 'REJECT'.")
        return action_upper


# --- First-Aid Evidence-Based Knowledge API Schemas (Phase 5E / Day 2) ---

class FirstAidMessageItem(BaseModel):
    role: str = Field(..., description="Message author role: 'user' or 'assistant'")
    content: str = Field(..., min_length=1, max_length=1000, description="Message text content")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if cleaned not in ("user", "assistant"):
            raise ValueError("Message role must be either 'user' or 'assistant'")
        return cleaned


class FirstAidQueryRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500, description="Emergency symptom or first-aid query")
    top_k: Optional[int] = Field(2, ge=1, le=5, description="Number of evidence chunks to retrieve")
    conversation_history: Optional[List[FirstAidMessageItem]] = Field(
        None,
        max_length=6,
        description="Recent conversation exchanges in active session (max 6 items)"
    )
    active_protocol_id: Optional[str] = Field(
        None,
        max_length=64,
        description="Active protocol ID if in ongoing follow-up conversation"
    )

    @field_validator("conversation_history")
    @classmethod
    def validate_history_size(cls, v: Optional[List[FirstAidMessageItem]]) -> Optional[List[FirstAidMessageItem]]:
        if not v:
            return v
        total_len = sum(len(m.content) for m in v)
        if total_len > 4000:
            raise ValueError("Total conversation history content exceeds 4000 character limit")
        return v[-6:]


class FirstAidTopicItem(BaseModel):
    protocol_id: str
    topic: str
    category: str
    source_organization: str
    document_title: str
    url: str
    emergency_call_guidance: str


class FirstAidQueryResponse(BaseModel):
    status: str
    query: Optional[str] = None
    relevance_score: Optional[float] = None
    threshold_required: Optional[float] = None
    matched_protocol: Optional[dict] = None
    emergency_call_guidance: Optional[str] = None
    critical_warnings: Optional[List[str]] = None
    actionable_steps: Optional[List[str]] = None
    what_not_to_do: Optional[List[str]] = None
    evidence_chunks: Optional[List[dict]] = None
    source_citation: Optional[dict] = None
    ambiguity_detected: Optional[bool] = None
    secondary_match: Optional[dict] = None
    negated_concepts_filtered: Optional[List[str]] = None
    message: Optional[str] = None
    emergency_guidance: Optional[str] = None
    disclaimer: str
    latency_ms: float
    synthesized_explanation: Optional[str] = None
    llm_latency_ms: Optional[float] = None
    llm_model: Optional[str] = None
    llm_status: Optional[str] = None
    conversational_reply: Optional[str] = None
    is_follow_up: Optional[bool] = None

