"""
FamilyConnect AI - Authentication & Token Security Services
===========================================================
Secure password hashing (PBKDF2-HMAC-SHA256) and signed bearer token validation.
Zero external fragile dependencies; standard Python cryptographic primitives only.

Token Architecture Notice:
FamilyConnect AI implements a custom, lightweight two-part HMAC-SHA256 signed bearer
token (<b64_payload>.<signature_hex>) containing user identity, tenant boundaries,
expiration timestamps, and cryptographic nonces (jti).
This design eliminates external JWT library attack vectors (such as 'none' algorithm
confusion or RSA/HMAC key confusion attacks) by strictly enforcing constant-time
HMAC-SHA256 signature verification. It is an internal bearer token protocol,
not an RFC 7519 three-part JSON Web Token.
"""

import os
import time
import json
import base64
import hmac
import hashlib
import secrets
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from fastapi import HTTPException, status

# Process-level ephemeral development secret generated once at startup.
# Eliminates static hardcoded secrets in source code while ensuring consistent tokens
# across all token generation and verification calls within the process lifetime.
_EPHEMERAL_DEV_SECRET: str = secrets.token_hex(32)

# Backward-compatible reference for tests and validator checks
DEV_FALLBACK_SECRET: str = _EPHEMERAL_DEV_SECRET
SECRET_KEY: str = os.environ.get("JWT_SECRET_KEY") or os.environ.get("SECRET_KEY") or _EPHEMERAL_DEV_SECRET
IS_DEV_SECRET: bool = (SECRET_KEY == _EPHEMERAL_DEV_SECRET)


def validate_production_jwt_secret(secret: Optional[str]) -> None:
    """
    Strictly enforce production token secret security:
    - Refuse missing, empty, or whitespace secrets.
    - Refuse development fallbacks, ephemeral development keys, or insecure dev patterns.
    - Enforce minimum length of 32 characters (256-bit entropy recommendation).
    - Never expose or print secret values in logs or exception messages.
    """
    if not secret or not secret.strip():
        raise RuntimeError(
            "CRITICAL SECURITY CONFIGURATION ERROR: "
            "FamilyConnect AI detected ENVIRONMENT=production, but no secure JWT_SECRET_KEY was provided. "
            "Application startup halted to prevent unauthorized access."
        )
    val = secret.strip()
    if (
        val == _EPHEMERAL_DEV_SECRET
        or "dev-insecure" in val.lower()
        or "change-in-production" in val.lower()
        or "ephemeral-dev" in val.lower()
    ):
        raise RuntimeError(
            "CRITICAL SECURITY CONFIGURATION ERROR: "
            "Insecure development fallback JWT secret detected in production environment. "
            "Set a cryptographically strong, unique JWT_SECRET_KEY."
        )
    if len(val) < 32:
        raise RuntimeError(
            "CRITICAL SECURITY CONFIGURATION ERROR: "
            f"JWT_SECRET_KEY is too short ({len(val)} characters). "
            "Production security requires a key of at least 32 characters (e.g. 256 bits)."
        )
    weak_patterns = {"password", "secret", "12345678", "admin", "familyconnect"}
    if val.lower() in weak_patterns:
        raise RuntimeError(
            "CRITICAL SECURITY CONFIGURATION ERROR: "
            "Trivially guessable JWT_SECRET_KEY detected in production. "
            "Use a high-entropy random key."
        )


def get_jwt_secret() -> str:
    """
    Dynamically retrieve and validate the active token signing secret for the current environment.
    Strictly rejects insecure fallbacks when ENVIRONMENT=production.
    When in development and no secret is configured, uses the process-lifetime ephemeral secret.
    """
    env = os.environ.get("ENVIRONMENT", "development").lower()
    raw = os.environ.get("JWT_SECRET_KEY") or os.environ.get("SECRET_KEY")
    if env == "production":
        validate_production_jwt_secret(raw)
        return raw.strip()
    if raw and raw.strip():
        return raw.strip()
    return _EPHEMERAL_DEV_SECRET

TOKEN_EXPIRE_HOURS = 24  # Default token lifespan for demo operations
HASH_ITERATIONS = 100_000


def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """
    Hash a password securely using PBKDF2-HMAC-SHA256 with 100,000 iterations
    and a cryptographically secure 16-byte random salt.
    Returns (hex_hash, salt_hex).
    """
    if not password:
        raise ValueError("Password cannot be empty")
    if not salt:
        salt = secrets.token_hex(16)
    hashed_bytes = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        HASH_ITERATIONS
    )
    return hashed_bytes.hex(), salt


def verify_password(plain_password: str, hashed_password: str, salt: str) -> bool:
    """
    Safely verify a candidate password against an existing hash and salt
    using constant-time HMAC comparison to prevent timing attacks.
    """
    if not plain_password or not hashed_password or not salt:
        return False
    expected_bytes = hashlib.pbkdf2_hmac(
        "sha256",
        plain_password.encode("utf-8"),
        salt.encode("utf-8"),
        HASH_ITERATIONS
    )
    return hmac.compare_digest(expected_bytes.hex(), hashed_password)


def _b64_url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64_url_decode(data: str) -> bytes:
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("utf-8"))


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Generate an HMAC-SHA256 signed bearer token containing claims and expiration timestamp.
    Token structure: <b64_payload>.<signature_hex>
    """
    to_encode = data.copy()
    now_ts = int(time.time())
    if expires_delta:
        expire_ts = now_ts + int(expires_delta.total_seconds())
    else:
        expire_ts = now_ts + (TOKEN_EXPIRE_HOURS * 3600)

    to_encode.update({
        "iat": now_ts,
        "exp": expire_ts,
        "jti": secrets.token_hex(16)
    })

    payload_json = json.dumps(to_encode, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _b64_url_encode(payload_json)

    # Compute HMAC-SHA256 signature
    secret_key = get_jwt_secret()
    signature = hmac.new(
        secret_key.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return f"{payload_b64}.{signature}"


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Validate and decode a signed bearer token.
    Enforces signature validity and expiration.
    Raises HTTPException 401 if invalid or expired.
    """
    if not token or "." not in token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token format",
            headers={"WWW-Authenticate": "Bearer"}
        )

    parts = token.split(".")
    if len(parts) != 2:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed authentication token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    payload_b64, signature = parts

    # Constant-time signature verification
    secret_key = get_jwt_secret()
    expected_sig = hmac.new(
        secret_key.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token signature",
            headers={"WWW-Authenticate": "Bearer"}
        )

    try:
        payload_bytes = _b64_url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to parse token payload",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Validate expiration
    exp = payload.get("exp")
    if not exp or int(exp) < int(time.time()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return payload


# --- FastAPI Authorization Dependencies ---
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .database import get_db
from .models import User, RevokedToken
import logging

logger = logging.getLogger("familyconnect.security")
http_bearer = HTTPBearer(auto_error=False)


def hash_token(token: str) -> str:
    """Compute SHA-256 hash of a token string for safe lookup and storage without leaking tokens."""
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def is_token_revoked(token: str, db: Session) -> bool:
    """Check if a token's cryptographic hash exists in the revoked_tokens blocklist."""
    if not token:
        return True
    t_hash = hash_token(token)
    now = datetime.utcnow()
    entry = db.query(RevokedToken).filter(
        RevokedToken.token_hash == t_hash,
        (RevokedToken.expires_at >= now) | (RevokedToken.expires_at.is_(None)) | (RevokedToken.reason == "exposed_test_token_revocation")
    ).first()
    return entry is not None


def revoke_token(token: str, db: Session, user_id: Optional[int] = None, reason: str = "logout") -> bool:
    """Safely revoke a token by storing its SHA-256 hash in the database blocklist."""
    if not token:
        return False
    t_hash = hash_token(token)
    now = datetime.utcnow()
    expires_at = now + timedelta(hours=TOKEN_EXPIRE_HOURS)
    try:
        parts = token.split(".")
        if len(parts) == 2:
            payload_bytes = _b64_url_decode(parts[0])
            payload = json.loads(payload_bytes.decode("utf-8"))
            exp_ts = payload.get("exp")
            if exp_ts:
                expires_at = datetime.utcfromtimestamp(exp_ts)
            if not user_id:
                user_id = payload.get("user_id")
    except Exception:
        pass

    existing = db.query(RevokedToken).filter(RevokedToken.token_hash == t_hash).first()
    if not existing:
        revocation = RevokedToken(
            token_hash=t_hash,
            user_id=user_id,
            revoked_at=now,
            expires_at=expires_at,
            reason=reason
        )
        db.add(revocation)
        db.commit()
    return True


def check_production_security():
    """Fail safely when deploying in production with default development secrets, weak keys, or invalid database/CORS configuration."""
    env = os.environ.get("ENVIRONMENT", "development").lower()
    if env == "production":
        raw_secret = os.environ.get("JWT_SECRET_KEY") or os.environ.get("SECRET_KEY")
        validate_production_jwt_secret(raw_secret)
        from .database import validate_database_url_for_environment
        validate_database_url_for_environment(
            os.environ.get("DATABASE_URL"),
            env
        )
        # Verify that explicit CORS origins are configured for production
        raw_origins = (os.environ.get("ALLOWED_ORIGINS") or os.environ.get("CORS_ORIGINS") or "").strip()
        frontend_pub = (os.environ.get("FRONTEND_PUBLIC_URL") or "").strip()
        has_origins = bool((raw_origins and raw_origins != "*") or (frontend_pub and frontend_pub.startswith(("http://", "https://"))))
        if not has_origins:
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: "
                "FamilyConnect AI detected ENVIRONMENT=production, but no trusted frontend origins were configured. "
                "Set ALLOWED_ORIGINS, CORS_ORIGINS, or FRONTEND_PUBLIC_URL."
            )


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer),
    db: Session = Depends(get_db)
) -> User:
    """
    Authenticate the caller using the Bearer token in Authorization header.
    Validates token signature, expiration, revocation status, and user binding integrity.
    """
    if not credentials or not credentials.credentials:
        logger.warning("[Security Audit] Unauthenticated access attempt: No Bearer token provided.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"}
        )

    raw_token = credentials.credentials

    # Check server-side revocation blocklist
    if is_token_revoked(raw_token, db):
        logger.warning("[Security Audit] Authentication rejected: Token has been revoked.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has been revoked",
            headers={"WWW-Authenticate": "Bearer"}
        )

    payload = decode_access_token(raw_token)
    user_id = payload.get("user_id")
    token_username = payload.get("sub")

    if not user_id:
        logger.warning("[Security Audit] Authentication rejected: Missing user_id claim in token.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
            headers={"WWW-Authenticate": "Bearer"}
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.warning(f"[Security Audit] Authentication rejected: User ID {user_id} not found in database.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or deactivated",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Subject binding integrity check:
    # Ensures a token cannot be reused if an account ID was reassigned to a different username
    if token_username and user.username != token_username:
        logger.warning(
            f"[Security Audit] Subject mismatch: Token issued for '{token_username}' "
            f"does not match current account username '{user.username}' (ID: {user_id})."
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account binding mismatch",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if not getattr(user, "is_active", True):
        logger.warning(f"[Security Audit] Authentication rejected: User '{user.username}' is disabled.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account has been disabled",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if getattr(user, "verification_status", "APPROVED") != "APPROVED":
        logger.warning(f"[Security Audit] Authentication rejected: User '{user.username}' verification status is '{user.verification_status}'.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account verification pending approval",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return user


def require_roles(allowed_roles: list[str]):
    """
    Dependency factory that enforces least-privilege role-based access.
    Logs unauthorized role escalation attempts without leaking payload data.
    """
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            logger.warning(
                f"[Security Audit] Access Denied: User '{current_user.username}' (role: '{current_user.role}') "
                f"attempted to access endpoint restricted to {allowed_roles}."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: role '{current_user.role}' lacks sufficient privileges for this resource"
            )
        return current_user
    return role_checker


require_admin = require_roles(["admin"])
require_member_or_admin = require_roles(["admin", "member"])


def require_platform_reviewer(current_user: User = Depends(get_current_user)) -> User:
    """
    Enforces that caller is an authorized platform reviewer.
    Ordinary household admins do not have global responder review authority.
    """
    if not getattr(current_user, "is_platform_reviewer", False):
        logger.warning(
            f"[Security Audit] Access Denied: User '{current_user.username}' (role: '{current_user.role}') "
            f"attempted to access reviewer endpoint without reviewer authorization."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Platform administrator privileges required"
        )
    return current_user



# --- Sensitive-Data Redaction Helpers ---

def mask_phone_number(phone: Optional[str]) -> Optional[str]:
    """
    Mask phone numbers for restricted views (e.g. responders or unprivileged roles):
    '+1 (555) 234-5678' -> '+1 (555) ***-5678'
    """
    if not phone:
        return phone
    cleaned = phone.strip()
    if len(cleaned) <= 6:
        return "***-***"
    return f"{cleaned[:8]}***{cleaned[-4:]}"

