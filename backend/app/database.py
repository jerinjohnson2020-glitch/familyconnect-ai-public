import os
from typing import Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("FAMILYCONNECT_DB_PATH", os.path.join(BASE_DIR, "familyconnect.db"))


def normalize_postgres_url(url: str) -> str:
    """
    Normalizes PostgreSQL URL scheme for SQLAlchemy 2.0+ and psycopg2 compatibility.

    In SQLAlchemy 2.0+, generic 'postgresql://' URLs default to the 'psycopg' (v3) dialect.
    Because FamilyConnect AI uses 'psycopg2-binary', all PostgreSQL connection URLs must
    explicitly specify the 'postgresql+psycopg2://' dialect before calling create_engine().

    Transformations:
      - 'postgres://...'             -> 'postgresql+psycopg2://...'  (legacy Heroku/Render format)
      - 'postgresql://...'           -> 'postgresql+psycopg2://...'  (generic format)
      - 'postgresql+psycopg://...'   -> 'postgresql+psycopg2://...'  (SQLAlchemy 2.0 / psycopg v3 dialect format)
      - 'postgresql+psycopg2://...'  -> 'postgresql+psycopg2://...'  (preserved intact)

    Rejects:
      - Unsupported drivers like 'postgresql+asyncpg://', 'postgresql+pg8000://', etc.
      - Non-PostgreSQL schemes like 'sqlite://', 'mysql://', 'oracle://'.
    """
    if not url:
        return ""
    trimmed = url.strip().strip("'\"")
    if not trimmed:
        return ""

    # Already explicit psycopg2 driver - preserve intact without double-transforming
    if trimmed.startswith("postgresql+psycopg2://"):
        return trimmed

    # Normalize SQLAlchemy 2.0 psycopg (v3) URL to psycopg2
    if trimmed.startswith("postgresql+psycopg://"):
        return "postgresql+psycopg2://" + trimmed[len("postgresql+psycopg://"):]

    # Normalize legacy Render / Heroku postgres:// to postgresql+psycopg2://
    if trimmed.startswith("postgres://"):
        return "postgresql+psycopg2://" + trimmed[len("postgres://"):]

    # Normalize generic postgresql:// to postgresql+psycopg2://
    if trimmed.startswith("postgresql://"):
        return "postgresql+psycopg2://" + trimmed[len("postgresql://"):]

    # Reject unsupported PostgreSQL dialect schemes safely without leaking credentials
    if trimmed.startswith("postgresql+") or trimmed.startswith("postgres+"):
        prefix = trimmed.split("://")[0] + "://" if "://" in trimmed else trimmed[:30]
        raise ValueError(
            f"Unsupported PostgreSQL dialect scheme: '{prefix}'. "
            "Only 'postgresql://', 'postgres://', 'postgresql+psycopg://', and 'postgresql+psycopg2://' are supported."
        )

    # Any other non-PostgreSQL scheme
    prefix = trimmed.split("://")[0] + "://" if "://" in trimmed else trimmed[:30]
    raise ValueError(
        f"Invalid database URL scheme: '{prefix}'. A PostgreSQL connection URL is required."
    )


def validate_database_url_for_environment(raw_url: Optional[str], environment: str) -> str:
    """
    Validates and normalizes DATABASE_URL based on the active runtime environment.
    When ENVIRONMENT=production:
      - Requires explicitly configured non-empty DATABASE_URL.
      - Requires PostgreSQL scheme; rejects SQLite and malformed/non-PostgreSQL URLs.
      - Normalizes postgres://, plain postgresql://, and postgresql+psycopg:// to postgresql+psycopg2://.
      - Preserves already-explicit drivers like postgresql+psycopg2://.
      - Rejects unsupported drivers (asyncpg, pg8000, etc.) safely without leaking credentials.
      - Fails startup immediately with a clear error without printing credentials or host.
    When ENVIRONMENT!=production (development/test/local):
      - Falls back safely to local SQLite development database if unset.
      - Normalizes postgres://, postgresql://, and postgresql+psycopg:// to postgresql+psycopg2:// when provided.
      - Preserves custom local SQLite URLs.
    """
    env = (environment or "development").strip().lower()

    if env == "production":
        if not raw_url or not raw_url.strip():
            raise RuntimeError(
                "CRITICAL DATABASE CONFIGURATION ERROR: "
                "FamilyConnect AI detected ENVIRONMENT=production, but no DATABASE_URL environment variable was configured. "
                "Application startup halted to prevent data loss."
            )

        trimmed = raw_url.strip().strip("'\"")
        if trimmed.startswith("sqlite"):
            raise RuntimeError(
                "CRITICAL DATABASE CONFIGURATION ERROR: "
                "FamilyConnect AI detected ENVIRONMENT=production, but DATABASE_URL is configured for SQLite. "
                "SQLite is not permitted in production. A persistent PostgreSQL database is required."
            )

        try:
            return normalize_postgres_url(trimmed)
        except ValueError as err:
            raise RuntimeError(
                f"CRITICAL DATABASE CONFIGURATION ERROR: "
                f"FamilyConnect AI detected ENVIRONMENT=production, but DATABASE_URL does not use a valid PostgreSQL scheme: {err}. "
                "Application startup halted."
            )

    # Non-production (development, test) fallback
    if raw_url and raw_url.strip():
        trimmed = raw_url.strip().strip("'\"")
        if trimmed.startswith("sqlite"):
            return trimmed
        try:
            return normalize_postgres_url(trimmed)
        except ValueError:
            return trimmed

    return f"sqlite:///{DB_PATH}"


SQLALCHEMY_DATABASE_URL = validate_database_url_for_environment(
    os.environ.get("DATABASE_URL"),
    os.environ.get("ENVIRONMENT", "development")
)

# Engine configuration with clean separation of dialect-specific settings
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    # PostgreSQL production pooling:
    # pool_pre_ping=True: Tests connection liveness before checkout to prevent dropped connections.
    # pool_recycle=300: Recycles connections idle for >5 minutes to prevent stale TCP sockets.
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
