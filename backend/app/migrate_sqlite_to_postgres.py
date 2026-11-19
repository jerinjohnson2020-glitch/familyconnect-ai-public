"""
FamilyConnect AI - Safe SQLite-to-PostgreSQL Migration Utility
Phase 2B & 2B.1 Hardened Implementation

Strict Safety Architecture:
1. Read-only SQLite source access (?mode=ro + PRAGMA query_only=ON on canonical resolved path).
2. Local-only destination guard (blocks cloud / production URLs during local testing).
3. Transaction-enclosed destination-empty check (eliminates race conditions, strictly refuses overwrite/truncate).
4. Atomic transaction isolation (full rollback if any step or validation fails).
5. Topological cycle resolution for users <-> members without disabling triggers.
6. Explicit boolean and datetime parsing (preserves NULLs, standardizes naive UTC).
7. Safe sequence synchronization with parameterized regclass identifiers for populated and empty tables.
8. Comprehensive pre-commit integrity and row-count verification covering 100% of foreign-key relationships.
9. Privacy-safe audit reporting (zero PII, credentials, tokens, or coordinates exposed).
"""

import os
import sys

# Ensure parent backend directory is in sys.path for direct script execution
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

import sqlite3
import datetime
import argparse
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import re
from urllib.parse import urlparse, urlunparse, parse_qs
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import declarative_base

# Configure logging
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("familyconnect.migration")

SAFE_QUERY_PARAMS = {"sslmode", "channel_binding", "connect_timeout"}
ALLOWED_POSTGRES_SCHEMES = ("postgresql://", "postgres://", "postgresql+psycopg2://")

DEFAULT_ACTIVE_SOURCE = os.path.join(_backend_dir, "familyconnect.db")
DEFAULT_BACKUP_SOURCE = os.path.join(
    _backend_dir,
    "backups",
    "familyconnect_backup_phase1_pre_cloud_20261023_104405.db"
)

# Ordered tables: dependencies flow downwards
# Circular dependency between users and members is resolved via two-pass insertion:
# 1. users inserted with member_id = NULL
# 2. members inserted with user_id
# 3. users.member_id updated to actual value
TABLE_MIGRATION_ORDER = [
    "responders",
    "users",
    "members",
    "trusted_contacts",
    "emergency_incidents",
    "incident_responders",
    "incident_timeline_events",
    "incident_alerts",
    "revoked_tokens",
    "household_invitations",
    "responder_applications"
]

# Comprehensive foreign key relationships across the 11 tables
ALL_FOREIGN_KEY_RELATIONSHIPS = [
    ("users", "household_id", "users", "id"),
    ("users", "member_id", "members", "id"),
    ("users", "responder_id", "responders", "id"),
    ("members", "user_id", "users", "id"),
    ("trusted_contacts", "member_id", "members", "id"),
    ("emergency_incidents", "user_id", "users", "id"),
    ("emergency_incidents", "member_id", "members", "id"),
    ("incident_responders", "incident_id", "emergency_incidents", "id"),
    ("incident_responders", "responder_id", "responders", "id"),
    ("incident_timeline_events", "incident_id", "emergency_incidents", "id"),
    ("incident_alerts", "incident_id", "emergency_incidents", "id"),
    ("incident_alerts", "contact_id", "trusted_contacts", "id"),
    ("revoked_tokens", "user_id", "users", "id"),
    ("household_invitations", "household_id", "users", "id"),
    ("household_invitations", "member_id", "members", "id"),
    ("responder_applications", "user_id", "users", "id"),
    ("responder_applications", "responder_id", "responders", "id"),
    ("responder_applications", "reviewed_by_id", "users", "id"),
]

BOOLEAN_COLUMNS = {
    "members": ["is_active", "is_demo"],
    "trusted_contacts": ["is_active", "is_demo"],
    "responders": ["is_available", "is_active", "is_demo"],
    "users": ["is_active", "is_platform_reviewer"]
}

DATETIME_COLUMNS = {
    "members": ["created_at", "updated_at"],
    "trusted_contacts": ["created_at", "updated_at"],
    "responders": ["location_updated_at", "created_at", "updated_at"],
    "emergency_incidents": ["created_at", "resolved_at", "location_updated_at"],
    "incident_responders": ["assigned_at", "accepted_at", "en_route_at", "arrived_at", "updated_at"],
    "incident_timeline_events": ["timestamp"],
    "incident_alerts": ["sent_at", "acknowledged_at", "last_attempt_at", "delivered_at"],
    "users": ["created_at"],
    "revoked_tokens": ["revoked_at", "expires_at"],
    "household_invitations": ["expires_at", "created_at", "accepted_at"],
    "responder_applications": ["reviewed_at", "created_at"]
}

KNOWN_CLOUD_DOMAINS = [
    "render.com",
    "aws.com",
    "amazonaws.com",
    "supabase.co",
    "neon.tech",
    "elephantsql.com",
    "cockroachlabs.cloud",
    "aivencloud.com"
]


class MigrationSecurityError(Exception):
    """Raised when destination fails cloud or security validation."""
    pass


class MigrationValidationError(Exception):
    """Raised when data integrity or row count verification fails."""
    pass


def mask_connection_url(raw_url: str) -> str:
    """Masks password, username, sensitive query parameters, and fragments in connection URL."""
    if not raw_url:
        return "<EMPTY>"
    try:
        clean_url = raw_url.strip()
        if clean_url.startswith("postgresql+psycopg2://"):
            clean_url = "postgresql://" + clean_url[len("postgresql+psycopg2://"):]
        elif clean_url.startswith("postgres://"):
            clean_url = "postgresql://" + clean_url[len("postgres://"):]

        parsed = urlparse(clean_url)
        username = parsed.username or ""
        masked_user = f"{username[:3]}***" if len(username) > 3 else "***"
        hostname = parsed.hostname or "<unknown-host>"
        masked_netloc = f"{masked_user}:***@{hostname}"
        if parsed.port:
            masked_netloc += f":{parsed.port}"

        # Sanitize query parameters: preserve only known safe keys, mask all other values
        masked_query = ""
        if parsed.query:
            query_params = parse_qs(parsed.query, keep_blank_values=True)
            masked_query_parts = []
            for q_key, q_vals in query_params.items():
                k_lower = q_key.lower().strip()
                if k_lower in SAFE_QUERY_PARAMS:
                    for v in q_vals:
                        masked_query_parts.append(f"{q_key}={v}")
                else:
                    masked_query_parts.append(f"{q_key}=***")
            masked_query = "&".join(masked_query_parts)

        # Redact URL fragment if present to prevent any fragment secret leakage
        masked_fragment = "***" if parsed.fragment else ""

        masked = urlunparse((
            parsed.scheme,
            masked_netloc,
            parsed.path,
            parsed.params,
            masked_query,
            masked_fragment
        ))
        return masked
    except Exception:
        try:
            fallback = re.sub(r'://([^/@:]+)(?::([^/@]*))?@', r'://***:***@', raw_url.strip())
            if "?" in fallback:
                base, q = fallback.split("?", 1)
                fallback = base + "?***"
            if "#" in fallback:
                base, f = fallback.split("#", 1)
                fallback = base + "#***"
            return fallback
        except Exception:
            return "postgresql://***:***@<masked-host>/<db>"


def sanitize_error_message(err_msg: str, raw_url: Optional[str] = None) -> str:
    """Removes sensitive credentials, passwords, usernames, query secrets, fragments, and raw connection URLs from error strings."""
    if not err_msg:
        return ""
    sanitized = str(err_msg)
    if raw_url:
        # Regex credential extraction: works even on malformed URLs where urlparse fails
        try:
            cred_match = re.search(r'://([^/@:]+)(?::([^/@]+))?@', raw_url)
            if cred_match:
                u = cred_match.group(1)
                p = cred_match.group(2)
                if p and p in sanitized and len(p) >= 3:
                    sanitized = sanitized.replace(p, "***")
                if u and len(u) >= 3 and u in sanitized:
                    masked_u = f"{u[:3]}***" if len(u) > 3 else "***"
                    sanitized = sanitized.replace(u, masked_u)

            # Scrub sensitive query parameters
            if "?" in raw_url:
                q_part = raw_url.split("?", 1)[1].split("#", 1)[0]
                for param in q_part.split("&"):
                    if "=" in param:
                        pk, pv = param.split("=", 1)
                        if pk.lower().strip() not in SAFE_QUERY_PARAMS and pv and len(pv) >= 3:
                            if pv in sanitized:
                                sanitized = sanitized.replace(pv, "***")

            # Scrub fragment secrets
            if "#" in raw_url:
                f_val = raw_url.split("#", 1)[1]
                if f_val and len(f_val) >= 3 and f_val in sanitized:
                    sanitized = sanitized.replace(f_val, "***")

            # Replace unmasked URLs
            clean = raw_url.strip()
            masked_clean = mask_connection_url(clean)
            if raw_url in sanitized:
                sanitized = sanitized.replace(raw_url, masked_clean)
            if clean in sanitized:
                sanitized = sanitized.replace(clean, masked_clean)
        except Exception:
            pass

        # Structured parse scrubbing if possible
        try:
            clean = raw_url.strip()
            if clean.startswith("postgresql+psycopg2://"):
                clean = "postgresql://" + clean[len("postgresql+psycopg2://"):]
            elif clean.startswith("postgres://"):
                clean = "postgresql://" + clean[len("postgres://"):]
            parsed = urlparse(clean)

            if parsed.password:
                sanitized = sanitized.replace(f":{parsed.password}@", ":***@")
                if parsed.password in sanitized and len(parsed.password) >= 3:
                    sanitized = sanitized.replace(parsed.password, "***")

            if parsed.username:
                masked_uname = f"{parsed.username[:3]}***" if len(parsed.username) > 3 else "***"
                if parsed.username in sanitized:
                    sanitized = sanitized.replace(parsed.username, masked_uname)
        except Exception:
            pass

    return sanitized


def validate_and_sanitize_url(raw_url: str) -> Tuple[bool, str, str]:
    """
    Validates the connection URL before attempting any network connection.
    Rejects empty strings, accidental terminal/PowerShell commands, and non-whitelisted schemes.
    Never returns or prints the raw input or credentials if validation fails.
    Returns: (is_valid, cleaned_url, error_message)
    """
    if not raw_url:
        return False, "", "Connection URL cannot be empty."

    cleaned = raw_url.strip().strip("'\"")
    if not cleaned:
        return False, "", "Connection URL cannot be empty or whitespace only."

    # Detect illegal control / newline / multi-line command characters
    if any(c in cleaned for c in ('\n', '\r', ';')):
        return False, "", "Connection URL contains illegal multi-line or command-separator characters."

    # Validate scheme against explicit allowlist
    if not any(cleaned.startswith(prefix) for prefix in ALLOWED_POSTGRES_SCHEMES):
        scheme_found = cleaned.split("://")[0] + "://" if "://" in cleaned else "<none>"
        return (
            False,
            "",
            f"Unsupported database URL scheme '{scheme_found}'. "
            "Only explicit PostgreSQL schemes ('postgresql://', 'postgres://', 'postgresql+psycopg2://') are supported. "
            "Alternative drivers (such as asyncpg, pg8000, psycopg v3) are strictly prohibited."
        )

    # Normalize temporary string for host inspection
    inspect_url = cleaned
    if inspect_url.startswith("postgresql+psycopg2://"):
        inspect_url = "postgresql://" + inspect_url[len("postgresql+psycopg2://"):]
    elif inspect_url.startswith("postgres://"):
        inspect_url = "postgresql://" + inspect_url[len("postgres://"):]

    try:
        parsed = urlparse(inspect_url)
    except Exception:
        return False, "", "Connection URL could not be parsed as a valid URI."

    hostname = (parsed.hostname or "").strip()
    if not hostname:
        return False, "", "Connection URL does not specify a valid database hostname or endpoint."

    if " " in hostname or " " in (parsed.path or ""):
        return False, "", "Connection URL contains invalid whitespace in host or path."

    return True, cleaned, ""


def normalize_postgres_url(url: str) -> str:
    """
    Normalize PostgreSQL URL scheme for SQLAlchemy 2.0+ compatibility.
    Explicitly selects the installed psycopg2 driver (postgresql+psycopg2://)
    when generic postgresql:// or legacy postgres:// schemes are supplied,
    preventing SQLAlchemy 2.0+ from defaulting to uninstalled psycopg (v3).
    Rejects any unsupported schemes.
    """
    if not url:
        return ""
    trimmed = url.strip()
    if trimmed.startswith("postgres://"):
        return trimmed.replace("postgres://", "postgresql+psycopg2://", 1)
    if trimmed.startswith("postgresql://"):
        return trimmed.replace("postgresql://", "postgresql+psycopg2://", 1)
    if trimmed.startswith("postgresql+psycopg2://"):
        return trimmed
    raise MigrationSecurityError(
        f"Unsupported PostgreSQL dialect scheme: '{trimmed.split('://')[0]}://'. "
        "Only 'postgresql://', 'postgres://', and 'postgresql+psycopg2://' are permitted."
    )


def validate_destination_safety(
    target_url: str,
    allow_cloud: bool = False,
    expected_host: Optional[str] = None,
    require_expected_host_for_cloud: bool = False
) -> None:
    """
    Validates that target_url is an allowed destination.
    During local testing, strictly blocks cloud databases and enforces hostname localhost/127.0.0.1
    and exactly database name 'familyconnect_test'.
    When allow_cloud is True, verifies expected_host against the parsed URL hostname.
    """
    is_valid, cleaned, err = validate_and_sanitize_url(target_url)
    if not is_valid:
        raise MigrationSecurityError(f"Target URL validation failed: {err}")

    normalized = normalize_postgres_url(cleaned)
    parsed = urlparse(normalized)
    hostname = (parsed.hostname or "").lower()

    # Reject cloud domains during local testing
    is_cloud = any(cloud_dom in hostname for cloud_dom in KNOWN_CLOUD_DOMAINS) or not (hostname in ["localhost", "127.0.0.1"])
    if is_cloud and not allow_cloud:
        raise MigrationSecurityError(
            f"SECURITY REJECTION: Target host '{hostname}' appears to be a cloud database. "
            "Local testing is prohibited from connecting to cloud instances without explicit --allow-cloud flag."
        )

    # If ENVIRONMENT=production is active, require explicit --allow-cloud flag
    env = os.environ.get("ENVIRONMENT", "development").lower()
    if env == "production" and not allow_cloud:
        raise MigrationSecurityError(
            "SECURITY REJECTION: ENVIRONMENT=production is set. "
            "Cannot connect to or run migration without explicit --allow-cloud authorization."
        )

    # Validate database name presence
    raw_path = (parsed.path or "").strip()
    db_name = raw_path.lstrip("/").split("?")[0]
    if not db_name:
        raise MigrationSecurityError("Target URL does not specify a database name. A valid database name is required.")

    # Local testing strict enforcement (when allow_cloud is False)
    if not allow_cloud:
        # Require hostname localhost or 127.0.0.1
        allowed_hosts = ["localhost", "127.0.0.1"]
        if hostname not in allowed_hosts:
            raise MigrationSecurityError(
                f"SECURITY REJECTION: Target host '{hostname}' is not permitted for local migration testing. "
                "Only 'localhost' or '127.0.0.1' is permitted."
            )

        # Allow exactly database name 'familyconnect_test'
        # Reject postgres, production-like names, alternative local names, and wildcards (*_test)
        if db_name != "familyconnect_test":
            raise MigrationSecurityError(
                f"SECURITY REJECTION: Target database '{db_name}' is not permitted for local migration testing. "
                "Only exactly 'familyconnect_test' is permitted. "
                "(System databases like 'postgres', production names, and alternative local database names are strictly rejected.)"
            )

    # Destination host confirmation gate
    if expected_host:
        raw_exp = expected_host.strip()
        if not raw_exp:
            raise MigrationSecurityError("Expected destination hostname cannot be empty or whitespace only.")

        # Reject ambiguous or malformed input (schemes, paths, slashes, whitespace, command separators)
        if "://" in raw_exp:
            raise MigrationSecurityError(
                f"Invalid expected hostname '{raw_exp}': contains URL scheme. "
                "Provide only the domain hostname (e.g. 'postgres.example.com' or 'db.cloud-provider.com')."
            )
        if "/" in raw_exp or "\\" in raw_exp:
            raise MigrationSecurityError(
                f"Invalid expected hostname '{raw_exp}': contains path separators. "
                "Provide only the domain hostname without paths or slashes."
            )
        if any(c in raw_exp for c in (" ", "\t", "\n", "\r", ";")):
            raise MigrationSecurityError(
                f"Invalid expected hostname '{raw_exp}': contains whitespace or invalid separator characters."
            )

        # Handle optional port (e.g. db.example.com:5432)
        exp_parts = raw_exp.split(":")
        if len(exp_parts) > 2:
            raise MigrationSecurityError(f"Invalid expected hostname '{raw_exp}': malformed port specification.")
        clean_exp = exp_parts[0].lower().rstrip(".")
        exp_port_val: Optional[int] = None
        if len(exp_parts) == 2:
            exp_port_str = exp_parts[1].strip()
            if not exp_port_str.isdigit():
                raise MigrationSecurityError(f"Invalid port in expected hostname '{raw_exp}': must be numeric digits.")
            exp_port_val = int(exp_port_str)

        if not clean_exp:
            raise MigrationSecurityError("Normalized expected hostname is empty.")

        clean_host = (parsed.hostname or "").lower().rstrip(".").strip()

        if clean_host != clean_exp:
            raise MigrationSecurityError(
                f"DESTINATION IDENTITY MISMATCH: Parsed connection hostname '{clean_host}' does not match "
                f"expected host '{clean_exp}'. Migration aborted before connecting or creating tables."
            )

        # Port validation: If expected port is supplied, verify against parsed destination port
        if exp_port_val is not None:
            dest_port = parsed.port if parsed.port is not None else 5432
            if exp_port_val != dest_port:
                raise MigrationSecurityError(
                    f"DESTINATION PORT MISMATCH: Parsed connection port '{dest_port}' does not match "
                    f"expected port '{exp_port_val}'. Migration aborted before connecting or creating tables."
                )
            logger.info(f"Destination hostname and port verified against expected host: '{clean_host}:{dest_port}'.")
        else:
            logger.info(f"Destination hostname verified against expected host: '{clean_host}'.")

        logger.info(
            "Notice: Hostname matching verifies alignment with the operator-specified endpoint, "
            "but does not autonomously query cloud management APIs to prove branch identity. "
            "Operator must verify in their cloud database console that this endpoint belongs to the intended instance."
        )
    elif allow_cloud and is_cloud and require_expected_host_for_cloud:
        raise MigrationSecurityError(
            "DESTINATION IDENTITY GUARD: Connecting to a cloud database requires explicit --expected-host verification. "
            "Please copy the endpoint hostname from your cloud database console (e.g. postgres.example.com) "
            "and pass --expected-host <hostname> (or provide it interactively) to confirm you are targeting the intended instance."
        )


def open_source_sqlite_readonly(source_path: str) -> sqlite3.Connection:
    """
    Opens the SQLite database in strict read-only mode using URI parameters
    and enforces PRAGMA query_only = ON to prevent any write operations.
    """
    resolved_path = Path(source_path).resolve()
    if not resolved_path.exists() or not resolved_path.is_file():
        raise FileNotFoundError(f"Source database file not found at: {resolved_path}")

    # Open with canonical file URI in read-only mode
    uri_path = f"file:{resolved_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri_path, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Enforce SQLite engine-level read-only mode
    cur = conn.cursor()
    cur.execute("PRAGMA query_only = ON;")
    cur.execute("PRAGMA integrity_check;")
    result = cur.fetchone()[0]
    if result != "ok":
        conn.close()
        raise MigrationValidationError(f"Source SQLite database failed PRAGMA integrity_check: {result}")

    return conn


def get_sqlite_table_counts(conn: sqlite3.Connection) -> Dict[str, int]:
    """Capture row counts for all expected tables from source SQLite database."""
    cur = conn.cursor()
    counts = {}
    for table in TABLE_MIGRATION_ORDER:
        cur.execute(f"SELECT COUNT(*) FROM \"{table}\";")
        counts[table] = cur.fetchone()[0]
    return counts


def audit_source_foreign_keys(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """
    Audits all 18 declared foreign-key relationships in the SQLite source database.
    Returns a list of any detected orphan records.
    """
    cur = conn.cursor()
    orphans = []
    for child_tbl, child_col, parent_tbl, parent_col in ALL_FOREIGN_KEY_RELATIONSHIPS:
        query = f"""
            SELECT id, "{child_col}" FROM "{child_tbl}"
            WHERE "{child_col}" IS NOT NULL
              AND "{child_col}" NOT IN (SELECT "{parent_col}" FROM "{parent_tbl}");
        """
        cur.execute(query)
        rows = cur.fetchall()
        for r_id, val in rows:
            orphans.append({
                "child_table": child_tbl,
                "row_id": r_id,
                "child_col": child_col,
                "missing_id": val,
                "parent_table": parent_tbl,
                "parent_col": parent_col
            })
    return orphans


def convert_value(table: str, col_name: str, raw_val: Any) -> Any:
    """
    Converts SQLite raw values to PostgreSQL-compatible types:
    1. Booleans: integers 0/1 are converted to bool True/False, preserving None/NULL.
    2. Datetimes: ISO-formatted strings are parsed into naive UTC datetime objects.
    """
    if raw_val is None:
        return None

    # Handle Booleans
    if table in BOOLEAN_COLUMNS and col_name in BOOLEAN_COLUMNS[table]:
        if isinstance(raw_val, bool):
            return raw_val
        if isinstance(raw_val, (int, float)):
            return bool(raw_val)
        if isinstance(raw_val, str):
            clean = raw_val.strip().lower()
            if clean in ("1", "true", "t", "yes", "y"):
                return True
            if clean in ("0", "false", "f", "no", "n"):
                return False
        return bool(raw_val)

    # Handle Datetimes
    # Note: FamilyConnect AI stores naive UTC timestamps (generated via datetime.utcnow()).
    # These are parsed into datetime objects without altering timezone metadata.
    if table in DATETIME_COLUMNS and col_name in DATETIME_COLUMNS[table]:
        if isinstance(raw_val, datetime.datetime):
            return raw_val
        if isinstance(raw_val, str):
            clean = raw_val.strip()
            try:
                return datetime.datetime.fromisoformat(clean)
            except ValueError:
                for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                    try:
                        return datetime.datetime.strptime(clean, fmt)
                    except ValueError:
                        pass
                return clean

    return raw_val


def execute_migration(
    source_path: str = DEFAULT_ACTIVE_SOURCE,
    target_url: Optional[str] = None,
    allow_cloud: bool = False,
    dry_run: bool = False,
    quarantine_orphans: bool = False,
    expected_host: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executes atomic migration from SQLite source to PostgreSQL destination.
    Returns migration audit report dictionary.
    """
    if not target_url:
        target_url = os.environ.get("TARGET_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not target_url:
        raise MigrationSecurityError("No target database URL provided. Pass --target-url or set TARGET_DATABASE_URL.")

    resolved_source_path = str(Path(source_path).resolve())

    # 1. Security & Environment Validations
    validate_destination_safety(
        target_url,
        allow_cloud=allow_cloud,
        expected_host=expected_host,
        require_expected_host_for_cloud=True
    )
    target_url = normalize_postgres_url(target_url)
    logger.info(f"Target connection validated: {mask_connection_url(target_url)}")

    # 2. Open read-only SQLite source
    sqlite_conn = open_source_sqlite_readonly(source_path)
    try:
        source_counts = get_sqlite_table_counts(sqlite_conn)
        logger.info("Source SQLite database verified intact (PRAGMA integrity_check: ok).")

        # 2b. Preflight Source Foreign-Key Referential Integrity Check
        # Audits all 18 relationships in the source database before connecting or writing to destination.
        source_orphans = audit_source_foreign_keys(sqlite_conn)
        if source_orphans and not quarantine_orphans:
            orphan_details = "; ".join([
                f"{o['child_table']}.id={o['row_id']} ({o['child_col']}={o['missing_id']} -> missing {o['parent_table']}.{o['parent_col']})"
                for o in source_orphans
            ])
            raise MigrationValidationError(
                f"SOURCE INTEGRITY ERROR: Detected {len(source_orphans)} orphaned foreign-key reference(s) in SQLite source database before migration: {orphan_details}. "
                "Migration aborted before connecting to or modifying destination database. "
                "Resolve the source integrity issue or pass quarantine_orphans=True with explicit authorization."
            )

        # 3. Connect to PostgreSQL
        pg_engine = create_engine(target_url, echo=False)

        with pg_engine.connect() as pg_conn:
            # 4. Open Isolated Transaction BEFORE schema creation and data migration
            # Wrapping schema creation, emptiness check, inserts, and validation inside the same
            # transaction guarantees atomic rollback of tables, sequences, constraints, and data
            # during --dry-run or if any error occurs.
            transaction = pg_conn.begin()
            try:
                try:
                    from .models import Base
                except (ImportError, ValueError):
                    from app.models import Base

                # 4a. Strict Destination Emptiness Check: Inspect all tables, views, materialized views,
                # foreign tables, and partitioned tables before any DDL
                inspector = inspect(pg_conn)
                raw_tables = inspector.get_table_names() if hasattr(inspector, "get_table_names") else []
                existing_tables = [t for t in (raw_tables or []) if isinstance(t, str)]

                raw_views = inspector.get_view_names() if hasattr(inspector, "get_view_names") else []
                existing_views = [v for v in (raw_views or []) if isinstance(v, str)]

                raw_mviews = []
                if hasattr(inspector, "get_materialized_view_names"):
                    try:
                        raw_mviews = inspector.get_materialized_view_names() or []
                    except Exception as m_err:
                        raise MigrationSecurityError(
                            f"CATALOG INSPECTION ERROR: Failed to inspect materialized views: {m_err}. "
                            "Aborting migration for safety."
                        )
                existing_mviews = [m for m in (raw_mviews or []) if isinstance(m, str)]

                # Query PostgreSQL catalog for all relations in target schema
                catalog_objects: List[Tuple[str, str]] = []
                is_postgres = getattr(getattr(pg_conn, "dialect", None), "name", None) == "postgresql"
                if is_postgres:
                    try:
                        cat_query = text("""
                            SELECT c.relname,
                                   CASE c.relkind
                                       WHEN 'r' THEN 'ordinary table'
                                       WHEN 'v' THEN 'view'
                                       WHEN 'm' THEN 'materialized view'
                                       WHEN 'f' THEN 'foreign table'
                                       WHEN 'p' THEN 'partitioned table'
                                       WHEN 'S' THEN 'sequence'
                                       ELSE 'other relation'
                                   END AS object_type
                            FROM pg_catalog.pg_class c
                            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                            WHERE n.nspname = current_schema()
                              AND c.relkind IN ('r', 'v', 'm', 'f', 'p', 'S');
                        """)
                        rows = pg_conn.execute(cat_query).fetchall()
                        for r_name, r_type in rows:
                            catalog_objects.append((str(r_name), str(r_type)))
                    except Exception as cat_err:
                        raise MigrationSecurityError(
                            f"CATALOG INSPECTION ERROR: Failed to query pg_catalog.pg_class for destination schema objects: {cat_err}. "
                            "Aborting migration for safety rather than assuming destination schema is empty."
                        )

                # Aggregate all detected objects across high-level inspector and system catalog
                all_detected = {}
                for t in existing_tables:
                    all_detected[t] = "table"
                for v in existing_views:
                    all_detected[v] = "view"
                for m in existing_mviews:
                    all_detected[m] = "materialized view"
                for r_name, r_type in catalog_objects:
                    all_detected[r_name] = r_type

                if all_detected:
                    sorted_details = [f"{name} ({kind})" for name, kind in sorted(all_detected.items())]
                    found_str = ", ".join(sorted_details)
                    raise MigrationSecurityError(
                        f"STRICT EMPTINESS ABORT: Destination schema is not empty before migration. "
                        f"Found {len(all_detected)} existing object(s): {found_str}. "
                        "The migration script requires a completely clean destination schema before executing DDL or data loading. "
                        "Dropping, truncating, or modifying existing objects is strictly prohibited."
                    )

                # 4b. Ensure schema tables exist on destination via metadata BOUND TO pg_conn
                # In PostgreSQL, DDL is transactional: binding create_all to pg_conn inside the
                # transaction ensures that table creation DDL rolls back cleanly on dry-run or error.
                Base.metadata.create_all(bind=pg_conn)

                # 4c. Verify destination tables are completely empty prior to data insertion
                for table in TABLE_MIGRATION_ORDER:
                    dest_cnt = pg_conn.execute(text(f'SELECT COUNT(*) FROM "{table}";')).scalar()
                    if dest_cnt and dest_cnt > 0:
                        raise MigrationSecurityError(
                            f"SAFETY ABORT: Destination table '{table}' is not empty (contains {dest_cnt} records). "
                            "The migration script strictly refuses to truncate, drop, or overwrite destination tables."
                        )

                user_member_deferred_updates: List[Tuple[int, int]] = []
                quarantined_records: List[Tuple[str, int]] = []

                # 6. Insert data in topological order
                for table in TABLE_MIGRATION_ORDER:
                    cur = sqlite_conn.cursor()
                    cur.execute(f'SELECT * FROM "{table}" ORDER BY id;')
                    rows = cur.fetchall()
                    if not rows:
                        continue

                    col_names = [col[0] for col in cur.description]
                    inserted_count = 0

                    for row in rows:
                        # Check if this row is a quarantined orphan
                        if quarantine_orphans and any(
                            o["child_table"] == table and o["row_id"] == row["id"] for o in source_orphans
                        ):
                            quarantined_records.append((table, row["id"]))
                            logger.warning(
                                f"QUARANTINED ORPHAN: Skipping {table} id={row['id']} "
                                f"referencing missing parent record."
                            )
                            continue

                        row_dict = {col: convert_value(table, col, row[col]) for col in col_names}

                        # Cycle resolution: For users, defer member_id to step 2
                        if table == "users":
                            original_member_id = row_dict.get("member_id")
                            if original_member_id is not None:
                                user_member_deferred_updates.append((row_dict["id"], original_member_id))
                                row_dict["member_id"] = None

                        cols_str = ", ".join([f'"{c}"' for c in row_dict.keys()])
                        placeholders = ", ".join([f":{c}" for c in row_dict.keys()])
                        stmt = text(f'INSERT INTO "{table}" ({cols_str}) VALUES ({placeholders});')
                        pg_conn.execute(stmt, row_dict)
                        inserted_count += 1

                    logger.info(f"Loaded {inserted_count} records into '{table}'.")

                # Step 2 of cycle resolution: Update users.member_id with deferred values
                if user_member_deferred_updates:
                    for uid, mid in user_member_deferred_updates:
                        pg_conn.execute(
                            text('UPDATE "users" SET member_id = :mid WHERE id = :uid;'),
                            {"mid": mid, "uid": uid}
                        )
                    logger.info(f"Resolved mutual dependency: Updated {len(user_member_deferred_updates)} user member_id references.")

                # 7. Resynchronize PostgreSQL Sequences with Parameterized setval
                for table in TABLE_MIGRATION_ORDER:
                    seq_query = text("SELECT pg_get_serial_sequence(:tbl, 'id');")
                    seq_name = pg_conn.execute(seq_query, {"tbl": table}).scalar()
                    if seq_name:
                        sync_stmt = text(f"""
                            SELECT setval(
                                CAST(:seq_name AS regclass),
                                COALESCE((SELECT MAX(id) FROM "{table}"), 1),
                                (SELECT COUNT(*) FROM "{table}") > 0
                            );
                        """)
                        pg_conn.execute(sync_stmt, {"seq_name": seq_name})
                        logger.info(f"Synchronized sequence for table '{table}'.")
                    else:
                        logger.info(f"Notice: Table '{table}' has no auto-increment sequence attached to 'id'; skipping sequence sync.")

                # 8. Post-Migration Verification before Commit
                post_counts = {}
                for table in TABLE_MIGRATION_ORDER:
                    cnt = pg_conn.execute(text(f'SELECT COUNT(*) FROM "{table}";')).scalar()
                    post_counts[table] = cnt
                    quarantined_in_table = sum(1 for t, _ in quarantined_records if t == table)
                    expected = source_counts[table] - quarantined_in_table
                    if cnt != expected:
                        raise MigrationValidationError(
                            f"Row count mismatch on table '{table}': expected {expected}, got {cnt} in PostgreSQL."
                        )

                # Comprehensive Foreign Key Integrity Verification across all 18 relationships
                for child_tbl, child_col, parent_tbl, parent_col in ALL_FOREIGN_KEY_RELATIONSHIPS:
                    orphan_check_sql = text(f"""
                        SELECT COUNT(*) FROM "{child_tbl}"
                        WHERE "{child_col}" IS NOT NULL
                          AND "{child_col}" NOT IN (SELECT "{parent_col}" FROM "{parent_tbl}");
                    """)
                    orphans = pg_conn.execute(orphan_check_sql).scalar()
                    if orphans and orphans > 0:
                        raise MigrationValidationError(
                            f"Foreign-key check failed: {orphans} orphaned records in {child_tbl}.{child_col} referencing {parent_tbl}.{parent_col}."
                        )

                if dry_run:
                    transaction.rollback()
                    logger.info("DRY-RUN completed successfully. Transaction rolled back cleanly.")
                    commit_status = "ROLLED_BACK_DRY_RUN"
                else:
                    transaction.commit()
                    logger.info("Migration transaction committed successfully.")
                    commit_status = "COMMITTED"

                return {
                    "status": "SUCCESS",
                    "commit_status": commit_status,
                    "source_path": resolved_source_path,
                    "tables_migrated": len(TABLE_MIGRATION_ORDER),
                    "table_counts": post_counts,
                    "cycles_resolved": len(user_member_deferred_updates),
                    "foreign_keys_verified": len(ALL_FOREIGN_KEY_RELATIONSHIPS),
                    "orphans_quarantined": len(quarantined_records),
                    "sequences_synchronized": True,
                    "integrity_verified": True
                }

            except Exception as e:
                transaction.rollback()
                sanitized_err = sanitize_error_message(str(e), target_url)
                logger.error(f"Migration failed; transaction rolled back completely. Error: {sanitized_err}")
                raise e

    finally:
        sqlite_conn.close()


def print_privacy_safe_report(report: Dict[str, Any]) -> None:
    """Prints a privacy-safe migration audit report without any sensitive or personal data."""
    print("\n" + "=" * 65)
    print("FAMILYCONNECT AI — POSTGRESQL MIGRATION AUDIT REPORT")
    print("=" * 65)
    print(f"Overall Status:          {report['status']}")
    print(f"Transaction State:       {report['commit_status']}")
    print(f"Source Type:             SQLite (Read-Only Verified)")
    print(f"Foreign Keys Checked:    {report.get('foreign_keys_verified', len(ALL_FOREIGN_KEY_RELATIONSHIPS))} relationships verified")
    if report.get("orphans_quarantined", 0) > 0:
        print(f"Orphans Quarantined:     {report['orphans_quarantined']} invalid record(s) excluded safely")
    print(f"Sequences Synchronized:  {report['sequences_synchronized']}")
    print(f"Integrity Check:         {report['integrity_verified']}")
    print(f"Circular Cycles Handled: {report['cycles_resolved']} mutual references")
    print("-" * 65)
    print(f"{'Table Name':<28} | {'Migrated Row Count':<18}")
    print("-" * 65)
    for table, count in report["table_counts"].items():
        print(f"{table:<28} | {count:<18}")
    print("=" * 65 + "\n")


def prompt_interactive_url() -> str:
    """Safely prompts the operator for the destination PostgreSQL connection URL."""
    print("\n" + "=" * 70)
    print("FAMILYCONNECT AI — SECURE MIGRATION DESTINATION INPUT")
    print("=" * 70)
    print("Please paste your PostgreSQL destination connection string below.")
    print("SECURITY NOTICE: The connection string will be visible in this terminal")
    print("window as you type or paste it. It will NEVER be printed to logs,")
    print("saved to disk, or stored in Git.")
    print("-" * 70)
    entered = ""
    try:
        entered = input("Destination PostgreSQL URL: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n[CANCELLED] Migration cancelled by user.")
        sys.exit(0)
        return ""
    return entered


def prompt_interactive_expected_host() -> str:
    """Safely prompts the operator for the expected cloud hostname from console."""
    print("\n" + "-" * 70)
    print("DESTINATION HOST CONFIRMATION GATE")
    print("Please enter the expected hostname copied from your cloud database console")
    print("(e.g. postgres.example.com or db.cloud-provider.com):")
    print("-" * 70)
    entered = ""
    try:
        entered = input("Expected Hostname: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n[CANCELLED] Migration cancelled by user.")
        sys.exit(0)
        return ""
    return entered


def main():
    parser = argparse.ArgumentParser(description="Migrate FamilyConnect AI SQLite snapshot to PostgreSQL safely.")
    parser.add_argument("--source", default=DEFAULT_ACTIVE_SOURCE, help="Path to source SQLite database file (default: backend/familyconnect.db [54 incidents])")
    parser.add_argument("--target-url", help="Target PostgreSQL connection URL (e.g. postgresql://user:pass@localhost:5432/dbname)")
    parser.add_argument("-i", "--interactive", action="store_true", help="Prompt interactively for connection URL to keep secrets out of command history")
    parser.add_argument("--expected-host", help="Expected PostgreSQL destination hostname (e.g. postgres.example.com). Required for cloud targets.")
    parser.add_argument("--allow-cloud", action="store_true", help="Explicitly authorize connection to a cloud database")
    parser.add_argument("--dry-run", action="store_true", help="Perform full migration in a transaction then rollback")
    parser.add_argument("--quarantine-orphans", action="store_true", help="Quarantine and skip known source orphan records during migration")

    args = parser.parse_args()

    target_url = args.target_url
    expected_host = args.expected_host

    if args.interactive:
        target_url = prompt_interactive_url()
        if args.allow_cloud and not expected_host:
            expected_host = prompt_interactive_expected_host()
    elif not target_url:
        target_url = os.environ.get("TARGET_DATABASE_URL") or os.environ.get("DATABASE_URL")
        if not target_url:
            print("[ERROR] No target database URL provided.", file=sys.stderr)
            print("Please provide --target-url, set TARGET_DATABASE_URL, or use -i / --interactive.", file=sys.stderr)
            sys.exit(1)

    try:
        report = execute_migration(
            source_path=args.source,
            target_url=target_url,
            allow_cloud=args.allow_cloud,
            dry_run=args.dry_run,
            quarantine_orphans=args.quarantine_orphans,
            expected_host=expected_host
        )
        print_privacy_safe_report(report)
    except Exception as exc:
        sanitized = sanitize_error_message(str(exc), target_url)
        print(f"\n[MIGRATION ERROR] {sanitized}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
