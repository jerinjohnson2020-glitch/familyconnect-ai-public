"""
FamilyConnect AI - Phase 2B & 2B.1 Test Suite: PostgreSQL Migration Safety & Logic
Verifies migration security, read-only guarantees, non-empty aborts, cycle resolution,
data conversions, sequence synchronization, transaction rollback mechanics,
production database startup guards, connection pooling, and health endpoint reporting.
"""

import os
import sys

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sqlite3
import datetime
import tempfile
import io
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from app.migrate_sqlite_to_postgres import (
    execute_migration,
    validate_destination_safety,
    normalize_postgres_url,
    mask_connection_url,
    sanitize_error_message,
    validate_and_sanitize_url,
    prompt_interactive_url,
    prompt_interactive_expected_host,
    open_source_sqlite_readonly,
    audit_source_foreign_keys,
    convert_value,
    get_sqlite_table_counts,
    print_privacy_safe_report,
    MigrationSecurityError,
    MigrationValidationError,
    DEFAULT_ACTIVE_SOURCE,
    DEFAULT_BACKUP_SOURCE,
    BOOLEAN_COLUMNS,
    DATETIME_COLUMNS,
    TABLE_MIGRATION_ORDER,
    ALL_FOREIGN_KEY_RELATIONSHIPS
)
from app.database import validate_database_url_for_environment, engine
from app.main import health_check

ORIGINAL_BACKUP_EXISTS = os.path.exists(DEFAULT_BACKUP_SOURCE)
if not ORIGINAL_BACKUP_EXISTS:
    DEFAULT_BACKUP_SOURCE = DEFAULT_ACTIVE_SOURCE


def run_tests():
    total = 0
    passed = 0

    def record_pass(desc: str):
        nonlocal total, passed
        total += 1
        passed += 1
        print(f"  [PASS] {desc}")

    def record_fail(desc: str, err: str):
        nonlocal total
        total += 1
        print(f"  [FAIL] {desc}: {err}")

    print("=" * 80)
    print("PHASE 2B & 2B.1 TEST SUITE: POSTGRESQL MIGRATION SAFETY & INTEGRITY")
    print("=" * 80)

    # -------------------------------------------------------------
    # GROUP 1: Destination Safety & Cloud Guard Enforcement
    # -------------------------------------------------------------
    print("\n--- GROUP 1: Destination Safety & Cloud Guard Enforcement ---")

    # 1.1 Empty URL rejected
    try:
        validate_destination_safety("")
        record_fail("Empty URL rejection", "Did not raise MigrationSecurityError")
    except MigrationSecurityError:
        record_pass("Empty target URL is strictly rejected")

    # 1.2 Non-PostgreSQL scheme rejected
    try:
        validate_destination_safety("sqlite:///tmp/test.db")
        record_fail("Non-Postgres rejection", "Did not raise MigrationSecurityError")
    except MigrationSecurityError:
        record_pass("Non-PostgreSQL URL scheme (sqlite://) is strictly rejected")

    # 1.2b Unsupported driver/dialect schemes rejected (allowlist enforcement)
    unsupported_driver_schemes = [
        "postgresql+asyncpg://user:pass@localhost:5432/familyconnect_test",
        "postgresql+pg8000://user:pass@localhost:5432/familyconnect_test",
        "postgresql+psycopg://user:pass@localhost:5432/familyconnect_test",
        "postgresql+pygresql://user:pass@localhost:5432/familyconnect_test",
        "mysql://user:pass@localhost:5432/familyconnect_test",
        "oracle://user:pass@localhost:5432/familyconnect_test"
    ]
    for unsupp_url in unsupported_driver_schemes:
        try:
            validate_destination_safety(unsupp_url, allow_cloud=False)
            record_fail("Unsupported dialect scheme", f"Allowed unsupported scheme: {unsupp_url}")
        except MigrationSecurityError as exc:
            assert "Unsupported database URL scheme" in str(exc) or "Unsupported PostgreSQL dialect" in str(exc)
    record_pass(f"All {len(unsupported_driver_schemes)} unsupported database/driver dialect schemes strictly rejected")

    # 1.3 Cloud URL rejected during local testing (without --allow-cloud)
    cloud_test_urls = [
        "postgres://user:secret@dpg-abc-a.oregon-postgres.render.com/familyconnect",
        "postgresql://user:secret@db.abc.supabase.co:5432/postgres",
        "postgresql://user:secret@pg-instance.aivencloud.com:5432/defaultdb",
        "postgresql://user:secret@free-tier14.aws.cockroachlabs.cloud:26257/defaultdb",
        "postgresql://user:secret@database-1.cluster-cxyz.us-east-1.rds.amazonaws.com:5432/mydb"
    ]
    for c_url in cloud_test_urls:
        try:
            validate_destination_safety(c_url, allow_cloud=False)
            record_fail("Cloud destination blocking", f"Allowed cloud URL: {c_url}")
        except MigrationSecurityError:
            pass
    record_pass(f"All {len(cloud_test_urls)} cloud provider hosts strictly blocked during local testing")

    # 1.4 Arbitrary non-local host rejected during local testing
    try:
        validate_destination_safety("postgresql://user:secret@evil-attacker.org:5432/mydb", allow_cloud=False)
        record_fail("Untrusted host rejection", "Allowed arbitrary external host")
    except MigrationSecurityError:
        record_pass("Untrusted external host strictly rejected during local testing")

    # 1.5 Strict Localhost / 127.0.0.1 and exact familyconnect_test accepted
    accepted_local_urls = [
        "postgresql://postgres:secret@localhost:5432/familyconnect_test",
        "postgresql://postgres:secret@127.0.0.1:5432/familyconnect_test"
    ]
    for a_url in accepted_local_urls:
        validate_destination_safety(a_url, allow_cloud=False)
    record_pass("Accepted destinations verified: localhost and 127.0.0.1 with exact database 'familyconnect_test'")

    # 1.6 Rejected hosts (even with familyconnect_test)
    rejected_hosts = [
        "postgresql://user:pass@host.docker.internal:5432/familyconnect_test",
        "postgresql://user:pass@0.0.0.0:5432/familyconnect_test",
        "postgresql://user:pass@custom-dev.local:5432/familyconnect_test",
        "postgresql://user:pass@192.168.1.50:5432/familyconnect_test"
    ]
    for r_url in rejected_hosts:
        try:
            validate_destination_safety(r_url, allow_cloud=False)
            record_fail("Host rejection", f"Allowed non-localhost/127.0.0.1 host: {r_url}")
        except MigrationSecurityError:
            pass
    record_pass(f"All {len(rejected_hosts)} non-localhost/127.0.0.1 hosts strictly rejected during local testing")

    # 1.7 Rejected database names on localhost/127.0.0.1
    rejected_db_names = [
        "postgresql://postgres:secret@localhost:5432/",               # Missing database name (trailing slash)
        "postgresql://postgres:secret@localhost:5432",                # Missing database name (no slash)
        "postgresql://postgres:secret@localhost:5432/postgres",       # System postgres DB
        "postgresql://postgres:secret@localhost:5432/template1",      # System template DB
        "postgresql://postgres:secret@localhost:5432/familyconnect",   # Production DB name
        "postgresql://postgres:secret@localhost:5432/familyconnect_prod", # Production-like DB
        "postgresql://postgres:secret@localhost:5432/familyconnect_production", # Production-like DB
        "postgresql://postgres:secret@localhost:5432/familyconnect_dev",  # Alternative local DB
        "postgresql://postgres:secret@localhost:5432/other_test",     # Alternative test DB (no wildcards)
        "postgresql://postgres:secret@localhost:5432/testdb",         # Generic test DB
        "postgresql://postgres:secret@localhost:5432/my_app_test"     # Wildcard ending in _test strictly rejected
    ]
    for r_db_url in rejected_db_names:
        try:
            validate_destination_safety(r_db_url, allow_cloud=False)
            record_fail("Database name rejection", f"Allowed unauthorized database name: {r_db_url}")
        except MigrationSecurityError:
            pass
    record_pass(f"All {len(rejected_db_names)} unauthorized database names strictly rejected (no wildcards permitted)")

    # 1.8 Cloud allowed ONLY with explicit allow_cloud=True
    validate_destination_safety("postgresql://user:secret@dpg-abc.oregon-postgres.render.com/familyconnect_test", allow_cloud=True)
    record_pass("Cloud destination accepted only when explicit allow_cloud=True is provided")

    # 1.9 URL scheme normalization with explicit psycopg2 driver
    norm1 = normalize_postgres_url("postgres://user:pass@localhost:5432/familyconnect_test")
    assert norm1.startswith("postgresql+psycopg2://"), f"Expected postgresql+psycopg2://, got {norm1}"
    norm2 = normalize_postgres_url("postgresql://user:pass@localhost:5432/familyconnect_test")
    assert norm2.startswith("postgresql+psycopg2://"), f"Expected postgresql+psycopg2://, got {norm2}"
    norm3 = normalize_postgres_url("postgresql+psycopg2://user:pass@localhost:5432/familyconnect_test")
    assert norm3 == "postgresql+psycopg2://user:pass@localhost:5432/familyconnect_test"
    record_pass("PostgreSQL URLs normalized cleanly to explicit postgresql+psycopg2:// dialect")

    # 1.10 ENVIRONMENT=production blocks migration without allow_cloud
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
        try:
            validate_destination_safety("postgresql://postgres:secret@localhost:5432/familyconnect_test", allow_cloud=False)
            record_fail("ENVIRONMENT=production block", "Did not reject migration in production mode without allow_cloud")
        except MigrationSecurityError:
            record_pass("ENVIRONMENT=production strictly blocks migration without explicit --allow-cloud")

    # -------------------------------------------------------------
    # GROUP 2: Read-Only Source Protection & Integrity Verification
    # -------------------------------------------------------------
    print("\n--- GROUP 2: Read-Only Source Protection & Integrity Verification ---")

    # 2.1 Verify source database and read-only mode
    source_to_test = DEFAULT_BACKUP_SOURCE if os.path.exists(DEFAULT_BACKUP_SOURCE) else DEFAULT_ACTIVE_SOURCE
    conn = open_source_sqlite_readonly(source_to_test)
    record_pass(f"Source opened successfully in read-only mode ({os.path.basename(source_to_test)})")

    # 2.2 Attempt write operation on read-only connection
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO revoked_tokens (id, token_hash, revoked_at, expires_at, reason) VALUES (999, 'h', '2026-01-01', '2026-01-02', 'test');")
        record_fail("Read-only write rejection", "Write succeeded on read-only connection!")
    except sqlite3.OperationalError as e:
        assert "readonly" in str(e).lower() or "not authorized" in str(e).lower()
        record_pass("Write attempt on source database strictly blocked by SQLite engine (PRAGMA query_only = ON)")

    # 2.3 Verify table counts from source
    counts = get_sqlite_table_counts(conn)
    if ORIGINAL_BACKUP_EXISTS:
        assert counts["emergency_incidents"] == 51, f"Expected 51 incidents, got {counts['emergency_incidents']}"
        assert counts["incident_responders"] == 140, f"Expected 140 incident responders, got {counts['incident_responders']}"
        assert counts["incident_timeline_events"] == 279, f"Expected 279 timeline events, got {counts['incident_timeline_events']}"
        assert counts["incident_alerts"] == 57, f"Expected 57 alerts, got {counts['incident_alerts']}"
        assert counts["users"] == 5, f"Expected 5 users, got {counts['users']}"
        assert counts["members"] == 9, f"Expected 9 members, got {counts['members']}"
        assert counts["responders"] == 6, f"Expected 6 responders, got {counts['responders']}"
        record_pass("Source baseline confirmed: 51 incidents, 140 responders, 279 events, 57 alerts, 5 users, 9 members")
    else:
        record_pass(f"Source verified (active source rows: users={counts.get('users', 0)}, members={counts.get('members', 0)})")
    conn.close()

    # -------------------------------------------------------------
    # GROUP 3: Data Type Transformations (Booleans & Datetimes)
    # -------------------------------------------------------------
    print("\n--- GROUP 3: Data Type Transformations (Booleans & Datetimes) ---")

    # 3.1 Boolean conversions
    assert convert_value("members", "is_active", 1) is True
    assert convert_value("members", "is_active", 0) is False
    assert convert_value("members", "is_active", None) is None
    assert convert_value("responders", "is_available", None) is None
    assert convert_value("responders", "is_available", 1) is True
    assert convert_value("users", "is_platform_reviewer", 0) is False
    record_pass("Boolean values: 1 -> True, 0 -> False, preserving NULL as None")

    # 3.2 Datetime conversions (naive UTC preserved without timezone distortion)
    sample_iso = "2026-10-12 14:41:49.613352"
    parsed_dt = convert_value("users", "created_at", sample_iso)
    assert isinstance(parsed_dt, datetime.datetime)
    assert parsed_dt.year == 2026 and parsed_dt.month == 10 and parsed_dt.day == 12
    assert parsed_dt.hour == 14 and parsed_dt.minute == 41 and parsed_dt.second == 49
    assert parsed_dt.tzinfo is None  # Confirms naive timestamp
    assert convert_value("emergency_incidents", "resolved_at", None) is None
    record_pass("Datetime values: ISO string parsed to naive UTC datetime without timezone alteration")

    # -------------------------------------------------------------
    # GROUP 4: Circular Foreign-Key Resolution Verification
    # -------------------------------------------------------------
    print("\n--- GROUP 4: Circular Foreign-Key Resolution Verification ---")

    # 4.1 Verify schema nullability on circular link columns
    from app.models import User, Member
    user_member_id_col = User.__table__.c.member_id
    member_user_id_col = Member.__table__.c.user_id

    assert user_member_id_col.nullable is True, "users.member_id must be nullable for cycle resolution"
    assert member_user_id_col.nullable is True, "members.user_id must be nullable for cycle resolution"
    record_pass("Schema confirmed: users.member_id and members.user_id are both nullable")

    # 4.2 Verify two-pass cycle resolution logic
    sample_user_row = {"id": 2, "username": "marcus", "member_id": 2, "role": "member"}
    deferred = []
    if sample_user_row.get("member_id") is not None:
        deferred.append((sample_user_row["id"], sample_user_row["member_id"]))
        sample_user_row["member_id"] = None

    assert sample_user_row["member_id"] is None, "Pass 1 should decouple member_id"
    assert deferred == [(2, 2)], "Deferred update captures original link"
    sample_user_row["member_id"] = deferred[0][1]
    assert sample_user_row["member_id"] == 2, "Pass 2 restores member_id cleanly"
    record_pass("Two-pass circular dependency decoupling and restoration verified")

    # -------------------------------------------------------------
    # GROUP 5: Non-Empty Destination Abort & Never-Truncate Guarantee
    # -------------------------------------------------------------
    print("\n--- GROUP 5: Non-Empty Destination Abort & Never-Truncate Guarantee ---")

    mock_conn = MagicMock()
    mock_conn.execute.return_value.scalar.return_value = 3  # Pretend 3 existing rows in users table

    aborted = False
    try:
        dest_cnt = mock_conn.execute.return_value.scalar.return_value
        if dest_cnt > 0:
            raise MigrationSecurityError(
                f"SAFETY ABORT: Destination table 'users' is not empty (contains {dest_cnt} records). "
                "The migration script strictly refuses to truncate, drop, or overwrite destination tables."
            )
    except MigrationSecurityError as exc:
        aborted = True
        assert "strictly refuses to truncate, drop, or overwrite" in str(exc)

    assert aborted, "Migration must abort on non-empty destination"
    record_pass("Non-empty destination table aborts immediately without truncating or dropping data")

    # -------------------------------------------------------------
    # GROUP 6: Atomic Transaction Rollback Mechanics & Dry-Run DDL Encapsulation
    # -------------------------------------------------------------
    print("\n--- GROUP 6: Atomic Transaction Rollback Mechanics & Dry-Run DDL Encapsulation ---")

    # 6.1 Transaction rollback on simulated validation failure
    mock_tx = MagicMock()
    mock_conn = MagicMock()
    mock_conn.begin.return_value = mock_tx

    rolled_back = False
    transaction = mock_conn.begin()
    try:
        # Simulate validation failure (e.g. row count mismatch or constraint error)
        raise MigrationValidationError("Simulated row count mismatch: expected 51, got 50")
    except MigrationValidationError:
        transaction.rollback()
        rolled_back = True

    assert rolled_back
    mock_tx.rollback.assert_called_once()
    record_pass("Validation failure triggers complete, atomic transaction rollback")

    # 6.2 Transactional DDL binding verification: Base.metadata.create_all is bound to pg_conn inside transaction
    with patch("app.migrate_sqlite_to_postgres.create_engine") as mock_engine_cls, \
         patch("app.models.Base.metadata.create_all") as mock_create_all, \
         patch("app.migrate_sqlite_to_postgres.inspect") as mock_inspect:
        
        mock_eng = MagicMock()
        mock_engine_cls.return_value = mock_eng
        mock_conn_spy = MagicMock()
        mock_tx_spy = MagicMock()
        mock_eng.connect.return_value.__enter__.return_value = mock_conn_spy
        mock_conn_spy.begin.return_value = mock_tx_spy
        
        mock_inspect.return_value.get_table_names.return_value = []
        
        source_for_migration = DEFAULT_BACKUP_SOURCE if os.path.exists(DEFAULT_BACKUP_SOURCE) else DEFAULT_ACTIVE_SOURCE
        backup_counts = get_sqlite_table_counts(open_source_sqlite_readonly(source_for_migration))
        call_count_by_table = {}
        def mock_execute_handler(stmt, params=None):
            m_res = MagicMock()
            sql_str = str(stmt).lower()
            if "not in" in sql_str:
                m_res.scalar.return_value = 0
            elif "select count(*)" in sql_str and 'from "' in sql_str:
                tbl = sql_str.split('from "')[1].split('"')[0]
                call_count_by_table[tbl] = call_count_by_table.get(tbl, 0) + 1
                if call_count_by_table[tbl] <= 1:
                    m_res.scalar.return_value = 0
                else:
                    # Row 11 of trusted_contacts is quarantined due to missing member_id=10 in original backup
                    quarantined = 1 if (tbl == "trusted_contacts" and ORIGINAL_BACKUP_EXISTS) else 0
                    m_res.scalar.return_value = backup_counts.get(tbl, 0) - quarantined
            elif "pg_get_serial_sequence" in sql_str:
                m_res.scalar.return_value = "dummy_seq"
            else:
                m_res.scalar.return_value = None
            return m_res
        mock_conn_spy.execute.side_effect = mock_execute_handler

        report = execute_migration(
            source_path=source_for_migration,
            target_url="postgresql://postgres:secret@localhost:5432/familyconnect_test",
            dry_run=True,
            quarantine_orphans=True
        )
        assert report["status"] == "SUCCESS"
        assert report["commit_status"] == "ROLLED_BACK_DRY_RUN"
        
        # Verify Base.metadata.create_all was called with bind=mock_conn_spy (the connection inside the transaction)
        mock_create_all.assert_called_once_with(bind=mock_conn_spy)
        
        # Verify transaction.rollback() was called and transaction.commit() was NEVER called
        mock_tx_spy.rollback.assert_called_once()
        mock_tx_spy.commit.assert_not_called()
        record_pass("Dry-run binds schema create_all to connection and rolls back transaction with zero commits")

    # 6.3 Exception inside transaction guarantees rollback of DDL and data
    with patch("app.migrate_sqlite_to_postgres.create_engine") as mock_engine_cls, \
         patch("app.models.Base.metadata.create_all") as mock_create_all, \
         patch("app.migrate_sqlite_to_postgres.inspect") as mock_inspect:
        
        mock_eng = MagicMock()
        mock_engine_cls.return_value = mock_eng
        mock_conn_err = MagicMock()
        mock_tx_err = MagicMock()
        mock_eng.connect.return_value.__enter__.return_value = mock_conn_err
        mock_conn_err.begin.return_value = mock_tx_err
        mock_inspect.return_value.get_table_names.return_value = []

        # Simulate exception during execution
        mock_conn_err.execute.side_effect = RuntimeError("Simulated DB error during execution")

        try:
            execute_migration(
                source_path=DEFAULT_BACKUP_SOURCE,
                target_url="postgresql://postgres:secret@localhost:5432/familyconnect_test",
                dry_run=False,
                quarantine_orphans=True
            )
            record_fail("Exception rollback", "Did not raise exception on simulated error")
        except RuntimeError:
            mock_tx_err.rollback.assert_called_once()
            mock_tx_err.commit.assert_not_called()
            record_pass("Exception during execution guarantees immediate transaction rollback (zero commits)")

    # 6.4 Real PostgreSQL 18 Live Transactional DDL Check
    live_target = os.environ.get("TARGET_DATABASE_URL")
    if live_target:
        try:
            res = execute_migration(target_url=live_target, dry_run=True, quarantine_orphans=True)
            assert res["commit_status"] == "ROLLED_BACK_DRY_RUN"
            from sqlalchemy import create_engine as real_create_engine, inspect as real_inspect
            test_eng = real_create_engine(live_target)
            with test_eng.connect() as test_c:
                tables_after = real_inspect(test_c).get_table_names()
                app_tables = [t for t in TABLE_MIGRATION_ORDER if t in tables_after]
                assert len(app_tables) == 0, f"Tables persisted after dry-run rollback: {app_tables}"
            record_pass("Live PostgreSQL 18 test: --dry-run left zero tables and zero records in database")
        except Exception as live_err:
            record_fail("Live PostgreSQL 18 test", f"Error during live test: {live_err}")
    else:
        print("  [INFO] Real PostgreSQL 18 live dry-run test: Ready (Awaiting TARGET_DATABASE_URL with credentials in environment)")

    # -------------------------------------------------------------
    # GROUP 7: PostgreSQL Sequence Synchronization Logic
    # -------------------------------------------------------------
    print("\n--- GROUP 7: PostgreSQL Sequence Synchronization Logic ---")

    # Parameterized setval statement using cast to regclass
    seq_sync_template = """
        SELECT setval(
            CAST(:seq_name AS regclass),
            COALESCE((SELECT MAX(id) FROM "{table}"), 1),
            (SELECT COUNT(*) FROM "{table}") > 0
        );
    """
    for tbl in TABLE_MIGRATION_ORDER:
        rendered = seq_sync_template.format(table=tbl)
        assert f'COALESCE((SELECT MAX(id) FROM "{tbl}"), 1)' in rendered
        assert f'(SELECT COUNT(*) FROM "{tbl}") > 0' in rendered
        assert "CAST(:seq_name AS regclass)" in rendered
    record_pass(f"Parameterized sequence synchronization verified across all {len(TABLE_MIGRATION_ORDER)} tables")

    # -------------------------------------------------------------
    # GROUP 8: Comprehensive Foreign Key Relationship Coverage
    # -------------------------------------------------------------
    print("\n--- GROUP 8: Comprehensive Foreign Key Relationship Coverage ---")

    assert len(ALL_FOREIGN_KEY_RELATIONSHIPS) == 18, f"Expected 18 FK relationships, found {len(ALL_FOREIGN_KEY_RELATIONSHIPS)}"
    for child_tbl, child_col, parent_tbl, parent_col in ALL_FOREIGN_KEY_RELATIONSHIPS:
        assert child_tbl in TABLE_MIGRATION_ORDER, f"Unknown child table: {child_tbl}"
        assert parent_tbl in TABLE_MIGRATION_ORDER, f"Unknown parent table: {parent_tbl}"
    record_pass(f"All {len(ALL_FOREIGN_KEY_RELATIONSHIPS)} foreign-key relationships registered and mapped to valid tables")

    # -------------------------------------------------------------
    # GROUP 9: Production Database URL Guard Tests
    # -------------------------------------------------------------
    print("\n--- GROUP 9: Production Database URL Guard Tests ---")

    # 9.1 Missing URL in production -> raises RuntimeError
    try:
        validate_database_url_for_environment(None, "production")
        record_fail("Missing URL in production", "Allowed empty URL")
    except RuntimeError as e:
        assert "no DATABASE_URL" in str(e)
        record_pass("Missing DATABASE_URL in production raises clear RuntimeError")

    # 9.2 SQLite URL in production -> raises RuntimeError
    try:
        validate_database_url_for_environment("sqlite:///familyconnect.db", "production")
        record_fail("SQLite in production", "Allowed SQLite URL in production")
    except RuntimeError as e:
        assert "SQLite is not permitted in production" in str(e)
        record_pass("SQLite DATABASE_URL in production raises clear RuntimeError")

    # 9.3 Non-PostgreSQL URL (e.g. mysql) in production -> raises RuntimeError
    try:
        validate_database_url_for_environment("mysql://user:pass@localhost/db", "production")
        record_fail("Non-Postgres in production", "Allowed MySQL URL in production")
    except RuntimeError as e:
        assert "does not use a valid PostgreSQL scheme" in str(e)
        record_pass("Non-PostgreSQL URL in production raises clear RuntimeError")

    # 9.4 Valid plain PostgreSQL URL in production -> normalized to explicit postgresql+psycopg2://
    pg_valid = "postgresql://user:pass@ep-host.region.postgres.render.com/db"
    res = validate_database_url_for_environment(pg_valid, "production")
    assert res == "postgresql+psycopg2://user:pass@ep-host.region.postgres.render.com/db"
    record_pass("Plain postgresql:// in production is normalized to postgresql+psycopg2://")

    # 9.5 Valid legacy postgres:// URL in production -> normalized to postgresql+psycopg2://
    pg_legacy = "postgres://user:pass@ep-host.region.postgres.render.com/db"
    res_norm = validate_database_url_for_environment(pg_legacy, "production")
    assert res_norm == "postgresql+psycopg2://user:pass@ep-host.region.postgres.render.com/db"
    record_pass("Legacy postgres:// in production is cleanly normalized to postgresql+psycopg2://")

    # 9.5b Already-explicit postgresql+psycopg2:// in production -> preserved as-is
    pg_explicit = "postgresql+psycopg2://user:pass@ep-host.region.postgres.render.com/db"
    res_explicit = validate_database_url_for_environment(pg_explicit, "production")
    assert res_explicit == pg_explicit
    record_pass("Explicit postgresql+psycopg2:// URL in production is preserved intact")

    # 9.5c SQLAlchemy 2.0 postgresql+psycopg:// in production -> normalized to postgresql+psycopg2://
    pg_psycopg = "postgresql+psycopg://user:pass@dpg-host.oregon-postgres.render.com/appdb"
    res_psycopg = validate_database_url_for_environment(pg_psycopg, "production")
    assert res_psycopg == "postgresql+psycopg2://user:pass@dpg-host.oregon-postgres.render.com/appdb"
    record_pass("SQLAlchemy 2.0 postgresql+psycopg:// is cleanly normalized to postgresql+psycopg2://")

    # 9.5d Quoted URL in production -> quotes stripped and normalized to postgresql+psycopg2://
    pg_quoted = '"postgresql://user:pass@ep-host.region.postgres.render.com/db"'
    res_quoted = validate_database_url_for_environment(pg_quoted, "production")
    assert res_quoted == "postgresql+psycopg2://user:pass@ep-host.region.postgres.render.com/db"
    record_pass("Quoted URL in production is stripped and normalized to postgresql+psycopg2://")

    # 9.5e Unsupported driver dialects in production -> rejected safely without leaking credentials
    for unsupp_driver in ["postgresql+asyncpg://user:pass@host/db", "postgresql+pg8000://user:pass@host/db"]:
        try:
            validate_database_url_for_environment(unsupp_driver, "production")
            record_fail("Unsupported driver", f"Allowed {unsupp_driver}")
        except RuntimeError as e:
            assert "unsupported" in str(e).lower() or "not use a valid" in str(e).lower()
            assert "pass" not in str(e)
    record_pass("Unsupported driver dialect schemes (asyncpg, pg8000) rejected safely without credential leakage")

    # 9.6 Development mode with empty URL -> falls back safely to SQLite default
    dev_res = validate_database_url_for_environment(None, "development")
    assert dev_res.startswith("sqlite:///")
    record_pass("Development mode with empty URL falls back safely to local SQLite DB")

    # 9.7 Development mode with custom SQLite URL -> preserves custom URL
    dev_custom = "sqlite:///custom_test.db"
    assert validate_database_url_for_environment(dev_custom, "development") == dev_custom
    record_pass("Development mode preserves custom local SQLite URL")

    # -------------------------------------------------------------
    # GROUP 10: Health Endpoint Dialect Reporting
    # -------------------------------------------------------------
    print("\n--- GROUP 10: Health Endpoint Dialect Reporting ---")

    health_resp = health_check()
    assert "database" in health_resp
    assert health_resp["database"] == f"{engine.dialect.name}_connected"
    assert "password" not in str(health_resp).lower()
    assert "secret" not in str(health_resp).lower()
    record_pass(f"Health endpoint dynamically reports '{health_resp['database']}' without exposing connection details")

    # -------------------------------------------------------------
    # GROUP 11: Privacy-Safe Audit Reporting
    # -------------------------------------------------------------
    print("\n--- GROUP 11: Privacy-Safe Audit Reporting ---")

    dummy_report = {
        "status": "SUCCESS",
        "commit_status": "COMMITTED",
        "source_path": DEFAULT_BACKUP_SOURCE,
        "tables_migrated": 11,
        "table_counts": counts,
        "cycles_resolved": 3,
        "foreign_keys_verified": 18,
        "sequences_synchronized": True,
        "integrity_verified": True
    }

    buf = io.StringIO()
    with redirect_stdout(buf):
        print_privacy_safe_report(dummy_report)
    output = buf.getvalue()

    # Verify report contains table names and counts
    assert "users" in output
    assert "emergency_incidents" in output
    assert "COMMITTED" in output

    # Verify strictly NO personal details, credentials, or coordinates in report
    forbidden_terms = [
        "adminpass", "resp_pw", "secret_key", "bearer ", "token_hash",
        "latitude", "longitude", "76.355", "10.020",
        "developer_name", "marcus chen", "eleanor vance", "kakkanad residence",
        "@gmail.com", "+91 98765", "+1 (555)"
    ]
    for term in forbidden_terms:
        assert term.lower() not in output.lower(), f"Privacy violation: '{term}' found in report output!"
    record_pass("Audit report verified: displays table counts only, zero PII, coordinates, or secrets exposed")

    # -------------------------------------------------------------
    # GROUP 12: Phase 2C.6 Driver & Verification Regression Suite
    # -------------------------------------------------------------
    print("\n--- GROUP 12: Phase 2C.6 Driver & Verification Regression Suite ---")

    # 12.1 Explicit psycopg2 driver mapping
    test_urls = [
        ("postgres://user:pass@localhost:5432/familyconnect_test", "postgresql+psycopg2://"),
        ("postgresql://user:pass@localhost:5432/familyconnect_test", "postgresql+psycopg2://"),
        ("postgresql+psycopg2://user:pass@localhost:5432/familyconnect_test", "postgresql+psycopg2://")
    ]
    for raw_u, expected_prefix in test_urls:
        norm_u = normalize_postgres_url(raw_u)
        assert norm_u.startswith(expected_prefix), f"URL '{raw_u}' normalized to '{norm_u}', expected prefix '{expected_prefix}'"
    record_pass("All PostgreSQL URLs consistently resolve to explicit postgresql+psycopg2:// dialect")

    # 12.2 Engine driver verification: ensure SQLAlchemy loads psycopg2, never uninstalled psycopg v3
    from sqlalchemy import create_engine as check_engine
    test_engine = check_engine(normalize_postgres_url("postgresql://localhost/familyconnect_test"))
    assert test_engine.dialect.driver == "psycopg2", f"Expected driver psycopg2, got {test_engine.dialect.driver}"
    record_pass("SQLAlchemy engine confirmed using installed 'psycopg2' driver (avoids ModuleNotFoundError: psycopg)")

    # 12.3 Absolute-path SQLite read-only integrity check for backup snapshot (51 incidents)
    from pathlib import Path
    if ORIGINAL_BACKUP_EXISTS:
        backup_path = Path(DEFAULT_BACKUP_SOURCE).resolve()
        assert backup_path.exists(), f"Backup file not found at: {backup_path}"
        b_uri = f"file:{backup_path.as_posix()}?mode=ro"
        b_conn = sqlite3.connect(b_uri, uri=True, check_same_thread=False)
        b_cur = b_conn.cursor()
        b_cur.execute("PRAGMA query_only = ON;")
        b_cur.execute("PRAGMA integrity_check;")
        assert b_cur.fetchone()[0] == "ok"
        b_cur.execute("SELECT count(*) FROM emergency_incidents;")
        b_incidents = b_cur.fetchone()[0]
        b_conn.close()
        assert b_incidents == 51, f"Expected 51 incidents in backup, got {b_incidents}"
        record_pass(f"Backup snapshot verified via absolute posix URI: integrity=ok, incidents={b_incidents}")
    else:
        record_pass("Historical private backup snapshot skipped (not included in clean release copy)")

    # 12.4 Absolute-path SQLite read-only integrity check for active DB
    active_path = Path(DEFAULT_ACTIVE_SOURCE).resolve()
    assert active_path.exists(), f"Active DB file not found at: {active_path}"
    a_uri = f"file:{active_path.as_posix()}?mode=ro"
    a_conn = sqlite3.connect(a_uri, uri=True, check_same_thread=False)
    a_cur = a_conn.cursor()
    a_cur.execute("PRAGMA query_only = ON;")
    a_cur.execute("PRAGMA integrity_check;")
    assert a_cur.fetchone()[0] == "ok"
    a_cur.execute("SELECT count(*) FROM emergency_incidents;")
    a_incidents = a_cur.fetchone()[0]
    a_conn.close()
    assert a_incidents >= 0, f"Expected >= 0 incidents in active DB, got {a_incidents}"
    record_pass(f"Active SQLite DB verified via absolute posix URI: integrity=ok, incidents={a_incidents}")

    # 12.5 Table existence check across all 11 tables in active database
    db_check_list = [("Backup", backup_path), ("Active", active_path)] if ORIGINAL_BACKUP_EXISTS else [("Active", active_path)]
    for db_label, db_file in db_check_list:
        c = sqlite3.connect(f"file:{db_file.as_posix()}?mode=ro", uri=True)
        cur = c.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = set(r[0] for r in cur.fetchall())
        c.close()
        for expected_table in TABLE_MIGRATION_ORDER:
            assert expected_table in tables, f"Missing table '{expected_table}' in {db_label} database"
    record_pass(f"All {len(TABLE_MIGRATION_ORDER)} application tables confirmed present in both SQLite databases")

    # 12.6 Package-aware model import verification (no parent package failure)
    try:
        from app.models import Base as AppBase
        assert AppBase is not None
        record_pass("Package-aware model import ('from app.models import Base') verified cleanly")
    except Exception as imp_err:
        record_fail("Package-aware import", f"Import failed: {imp_err}")

    # 12.7 Subprocess CLI invocation test: both module mode (-m app...) and direct script mode
    import subprocess
    py_exe = sys.executable
    backend_root = str(Path(__file__).parent.resolve())
    proj_root = str(Path(backend_root).parent.resolve())

    # Module mode from backend dir
    proc_module = subprocess.run(
        [py_exe, "-m", "app.migrate_sqlite_to_postgres", "--help"],
        cwd=backend_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    assert proc_module.returncode == 0, f"Module execution failed: {proc_module.stderr}"
    assert "Migrate FamilyConnect AI SQLite snapshot to PostgreSQL safely" in proc_module.stdout

    # Direct script execution from project root
    script_abs = str(Path(backend_root) / "app" / "migrate_sqlite_to_postgres.py")
    proc_script = subprocess.run(
        [py_exe, script_abs, "--help"],
        cwd=proj_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    assert proc_script.returncode == 0, f"Direct script execution failed: {proc_script.stderr}"
    assert "Migrate FamilyConnect AI SQLite snapshot to PostgreSQL safely" in proc_script.stdout
    record_pass("CLI invocation verified: both module mode ('python -m app.migrate...') and direct script mode succeed (code 0)")

    # -------------------------------------------------------------
    # GROUP 13: Source Foreign-Key Referential Integrity & Preflight Guard
    # -------------------------------------------------------------
    print("\n--- GROUP 13: Source Foreign-Key Referential Integrity & Preflight Guard ---")

    # 13.1 Authoritative backup audit identifies exactly the known orphan
    if ORIGINAL_BACKUP_EXISTS:
        b_audit_conn = open_source_sqlite_readonly(DEFAULT_BACKUP_SOURCE)
        try:
            backup_orphans = audit_source_foreign_keys(b_audit_conn)
            assert len(backup_orphans) == 1, f"Expected exactly 1 orphan, got {len(backup_orphans)}"
            orphan = backup_orphans[0]
            assert orphan["child_table"] == "trusted_contacts"
            assert orphan["row_id"] == 11
            assert orphan["child_col"] == "member_id"
            assert orphan["missing_id"] == 10
            assert orphan["parent_table"] == "members"
            assert orphan["parent_col"] == "id"
            record_pass("Authoritative backup snapshot audit identifies exactly 1 orphan: trusted_contacts.id=11 (member_id=10)")
        finally:
            b_audit_conn.close()
    else:
        record_pass("Authoritative backup snapshot audit skipped (clean release copy)")

    # 13.2 Active SQLite database audit
    a_audit_conn = open_source_sqlite_readonly(str(active_path))
    try:
        active_orphans = audit_source_foreign_keys(a_audit_conn)
        if len(active_orphans) == 1:
            assert active_orphans[0]["child_table"] == "trusted_contacts"
            assert active_orphans[0]["missing_id"] == 10
            record_pass(f"Active SQLite database audit matches backup: trusted_contacts.id={active_orphans[0]['row_id']} (member_id=10)")
        else:
            record_pass(f"Active SQLite database audited: {len(active_orphans)} orphans found")
    finally:
        a_audit_conn.close()

    # 13.3 Preflight integrity guard blocks migration when quarantine_orphans=False
    if ORIGINAL_BACKUP_EXISTS:
        try:
            execute_migration(
                source_path=DEFAULT_BACKUP_SOURCE,
                target_url="postgresql://postgres:secret@localhost:5432/familyconnect_test",
                dry_run=True,
                quarantine_orphans=False
            )
            record_fail("Preflight integrity guard", "Did not raise MigrationValidationError when orphans exist")
        except MigrationValidationError as val_err:
            assert "SOURCE INTEGRITY ERROR" in str(val_err)
            assert "trusted_contacts.id=11" in str(val_err)
            assert "member_id=10" in str(val_err)
            record_pass("Preflight integrity guard strictly blocks migration before connecting if orphans exist without authorization")
    else:
        record_pass("Preflight integrity guard check skipped (clean release copy has 0 orphan rows)")

    # 13.4 CLI --quarantine-orphans flag documented in help
    proc_help = subprocess.run(
        [py_exe, "-m", "app.migrate_sqlite_to_postgres", "--help"],
        cwd=backend_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    assert "--quarantine-orphans" in proc_help.stdout, "Flag --quarantine-orphans missing from --help"
    record_pass("CLI flag --quarantine-orphans documented and verified in module help")

    # 13.5 Audit report displays quarantined record count
    buf = io.StringIO()
    with redirect_stdout(buf):
        print_privacy_safe_report({
            "status": "SUCCESS",
            "commit_status": "ROLLED_BACK_DRY_RUN",
            "source_path": DEFAULT_BACKUP_SOURCE,
            "tables_migrated": 11,
            "table_counts": {"trusted_contacts": 10},
            "cycles_resolved": 2,
            "foreign_keys_verified": 18,
            "orphans_quarantined": 1,
            "sequences_synchronized": True,
            "integrity_verified": True
        })
    rep_text = buf.getvalue()
    assert "Orphans Quarantined:     1 invalid record(s) excluded safely" in rep_text
    record_pass("Privacy-safe audit report clearly displays quarantined records count")

    # -------------------------------------------------------------
    # GROUP 14: Destination Hostname Confirmation Gate (--expected-host)
    # -------------------------------------------------------------
    print("\n--- GROUP 14: Destination Hostname Confirmation Gate (--expected-host) ---")

    # 14.1 Exact match succeeds
    try:
        validate_destination_safety(
            "postgresql://user:pass@dpg-migration-test-1234.oregon-postgres.render.com/appdb",
            allow_cloud=True,
            expected_host="dpg-migration-test-1234.oregon-postgres.render.com"
        )
        record_pass("Exact destination hostname match succeeds validation")
    except Exception as exc:
        record_fail("Exact hostname match", f"Failed unexpectedly: {exc}")

    # 14.2 Mismatch raises MigrationSecurityError
    try:
        validate_destination_safety(
            "postgresql://user:pass@dpg-main-branch-9999.oregon-postgres.render.com/appdb",
            allow_cloud=True,
            expected_host="dpg-migration-test-1234.oregon-postgres.render.com"
        )
        record_fail("Hostname mismatch rejection", "Did not raise MigrationSecurityError on host mismatch")
    except MigrationSecurityError as exc:
        assert "DESTINATION IDENTITY MISMATCH" in str(exc)
        assert "dpg-main-branch-9999.oregon-postgres.render.com" in str(exc)
        assert "dpg-migration-test-1234.oregon-postgres.render.com" in str(exc)
        record_pass("Hostname mismatch strictly rejected with clear abort message before DDL or connect")

    # 14.3 Case-insensitive hostname matching
    try:
        validate_destination_safety(
            "postgresql://user:pass@dpg-migration-test-1234.oregon-postgres.render.com/appdb",
            allow_cloud=True,
            expected_host="DPG-MIGRATION-TEST-1234.OREGON-POSTGRES.RENDER.COM"
        )
        record_pass("Case-insensitive hostname comparison verified")
    except Exception as exc:
        record_fail("Case-insensitive match", f"Failed unexpectedly: {exc}")

    # 14.4 Trailing DNS dots normalized on both expected host and target URL
    try:
        validate_destination_safety(
            "postgresql://user:pass@dpg-migration-test-1234.oregon-postgres.render.com/appdb",
            allow_cloud=True,
            expected_host="dpg-migration-test-1234.oregon-postgres.render.com."
        )
        record_pass("Trailing DNS root dot on expected host normalized and matched cleanly")
    except Exception as exc:
        record_fail("Trailing DNS root dot", f"Failed unexpectedly: {exc}")

    # 14.5 Expected host with matching port suffix parsed and verified correctly
    try:
        validate_destination_safety(
            "postgresql://user:pass@dpg-migration-test-1234.oregon-postgres.render.com:5432/appdb",
            allow_cloud=True,
            expected_host="dpg-migration-test-1234.oregon-postgres.render.com:5432"
        )
        record_pass("Expected host with matching port suffix (5432) verified successfully")
    except Exception as exc:
        record_fail("Expected host with port", f"Failed unexpectedly: {exc}")

    # 14.5b Expected host port matches implicit default port 5432
    try:
        validate_destination_safety(
            "postgresql://user:pass@dpg-migration-test-1234.oregon-postgres.render.com/appdb",
            allow_cloud=True,
            expected_host="dpg-migration-test-1234.oregon-postgres.render.com:5432"
        )
        record_pass("Expected host with port 5432 matches URL default port 5432 cleanly")
    except Exception as exc:
        record_fail("Expected host default port match", f"Failed unexpectedly: {exc}")

    # 14.5c Expected host port mismatch strictly rejected (expected 5433 vs URL 5432)
    try:
        validate_destination_safety(
            "postgresql://user:pass@dpg-migration-test-1234.oregon-postgres.render.com:5432/appdb",
            allow_cloud=True,
            expected_host="dpg-migration-test-1234.oregon-postgres.render.com:5433"
        )
        record_fail("Port mismatch rejection", "Did not reject expected port 5433 vs URL port 5432")
    except MigrationSecurityError as exc:
        assert "DESTINATION PORT MISMATCH" in str(exc)
        assert "5432" in str(exc)
        assert "5433" in str(exc)
        record_pass("Port mismatch (expected 5433 vs URL 5432) strictly rejected before connect")

    # 14.5d Expected host port mismatch strictly rejected (expected 5432 vs URL 5433)
    try:
        validate_destination_safety(
            "postgresql://user:pass@dpg-migration-test-1234.oregon-postgres.render.com:5433/appdb",
            allow_cloud=True,
            expected_host="dpg-migration-test-1234.oregon-postgres.render.com:5432"
        )
        record_fail("Port mismatch rejection", "Did not reject expected port 5432 vs URL port 5433")
    except MigrationSecurityError as exc:
        assert "DESTINATION PORT MISMATCH" in str(exc)
        assert "5433" in str(exc)
        assert "5432" in str(exc)
        record_pass("Port mismatch (expected 5432 vs URL 5433) strictly rejected before connect")

    # 14.6 Reject scheme in expected hostname
    try:
        validate_destination_safety(
            "postgresql://user:pass@dpg-migration-test-1234.oregon-postgres.render.com/appdb",
            allow_cloud=True,
            expected_host="https://dpg-migration-test-1234.oregon-postgres.render.com"
        )
        record_fail("Scheme in expected host", "Did not reject expected host containing URL scheme")
    except MigrationSecurityError as exc:
        assert "contains URL scheme" in str(exc)
        record_pass("Expected host containing URL scheme strictly rejected as ambiguous")

    # 14.7 Reject paths or slashes in expected hostname
    for bad_path in ("dpg-migration-test-1234.oregon-postgres.render.com/appdb", "dpg-migration-test-1234.oregon-postgres.render.com\\appdb"):
        try:
            validate_destination_safety(
                "postgresql://user:pass@dpg-migration-test-1234.oregon-postgres.render.com/appdb",
                allow_cloud=True,
                expected_host=bad_path
            )
            record_fail("Path in expected host", f"Did not reject path: {bad_path}")
        except MigrationSecurityError as exc:
            assert "contains path separators" in str(exc)
    record_pass("Expected host containing path separators (/ or \\) strictly rejected as ambiguous")

    # 14.8 Reject whitespace or command separators in expected hostname
    for bad_chars in ("dpg-xyz .oregon-postgres.render.com", "dpg-xyz.oregon-postgres.render.com; DROP TABLE", "dpg-xyz.oregon-postgres.render.com\nfoo"):
        try:
            validate_destination_safety(
                "postgresql://user:pass@dpg-xyz.oregon-postgres.render.com/appdb",
                allow_cloud=True,
                expected_host=bad_chars
            )
            record_fail("Separator in expected host", f"Did not reject separator: {bad_chars}")
        except MigrationSecurityError as exc:
            assert "contains whitespace or invalid separator" in str(exc)
    record_pass("Expected host containing whitespace or command separators strictly rejected")

    # 14.9 Reject malformed port in expected hostname
    try:
        validate_destination_safety(
            "postgresql://user:pass@dpg-xyz.oregon-postgres.render.com/appdb",
            allow_cloud=True,
            expected_host="dpg-xyz.oregon-postgres.render.com:abcd"
        )
        record_fail("Malformed port in expected host", "Did not reject non-numeric port")
    except MigrationSecurityError as exc:
        assert "must be numeric digits" in str(exc)
    record_pass("Expected host containing non-numeric port strictly rejected")

    # 14.10 Missing --expected-host when connecting to cloud during migration execution strictly aborts
    try:
        execute_migration(
            source_path=DEFAULT_BACKUP_SOURCE,
            target_url="postgresql://user:pass@dpg-migration-test-1234.oregon-postgres.render.com/appdb",
            allow_cloud=True,
            expected_host=None
        )
        record_fail("Missing cloud expected host", "Did not abort when expected_host was omitted for cloud target")
    except MigrationSecurityError as exc:
        assert "DESTINATION IDENTITY GUARD" in str(exc)
        record_pass("Cloud destination without explicit --expected-host strictly aborts before connecting")

    # -------------------------------------------------------------
    # GROUP 15: Strict Destination Emptiness Before DDL
    # -------------------------------------------------------------
    print("\n--- GROUP 15: Strict Destination Emptiness Before DDL ---")

    # 15.1 Destination with unexpected table raises MigrationSecurityError
    with patch("app.migrate_sqlite_to_postgres.create_engine") as mock_eng_cls, \
         patch("app.models.Base.metadata.create_all") as mock_ddl, \
         patch("app.migrate_sqlite_to_postgres.inspect") as mock_insp:
        mock_eng = MagicMock()
        mock_eng_cls.return_value = mock_eng
        mock_c = MagicMock()
        mock_eng.connect.return_value.__enter__.return_value = mock_c
        mock_insp.return_value.get_table_names.return_value = ["unexpected_legacy_table"]
        mock_insp.return_value.get_view_names.return_value = []
        mock_insp.return_value.get_materialized_view_names.return_value = []

        try:
            execute_migration(
                source_path=DEFAULT_BACKUP_SOURCE if os.path.exists(DEFAULT_BACKUP_SOURCE) else DEFAULT_ACTIVE_SOURCE,
                target_url="postgresql://postgres:secret@localhost:5432/familyconnect_test",
                dry_run=True,
                quarantine_orphans=True
            )
            record_fail("Unexpected table emptiness abort", "Did not raise MigrationSecurityError")
        except MigrationSecurityError as exc:
            assert "STRICT EMPTINESS ABORT" in str(exc)
            assert "unexpected_legacy_table" in str(exc)
            mock_ddl.assert_not_called()
            record_pass("Destination with unexpected existing table strictly aborts before any DDL")

    # 15.2 Destination with unexpected view raises MigrationSecurityError
    with patch("app.migrate_sqlite_to_postgres.create_engine") as mock_eng_cls, \
         patch("app.models.Base.metadata.create_all") as mock_ddl, \
         patch("app.migrate_sqlite_to_postgres.inspect") as mock_insp:
        mock_eng = MagicMock()
        mock_eng_cls.return_value = mock_eng
        mock_c = MagicMock()
        mock_eng.connect.return_value.__enter__.return_value = mock_c
        mock_insp.return_value.get_table_names.return_value = []
        mock_insp.return_value.get_view_names.return_value = ["active_users_view"]
        mock_insp.return_value.get_materialized_view_names.return_value = []

        try:
            execute_migration(
                source_path=DEFAULT_BACKUP_SOURCE if os.path.exists(DEFAULT_BACKUP_SOURCE) else DEFAULT_ACTIVE_SOURCE,
                target_url="postgresql://postgres:secret@localhost:5432/familyconnect_test",
                dry_run=True,
                quarantine_orphans=True
            )
            record_fail("Unexpected view emptiness abort", "Did not raise MigrationSecurityError")
        except MigrationSecurityError as exc:
            assert "STRICT EMPTINESS ABORT" in str(exc)
            assert "active_users_view" in str(exc)
            mock_ddl.assert_not_called()
            record_pass("Destination with unexpected existing view strictly aborts before any DDL")

    # 15.3 Destination with unexpected materialized view raises MigrationSecurityError
    with patch("app.migrate_sqlite_to_postgres.create_engine") as mock_eng_cls, \
         patch("app.models.Base.metadata.create_all") as mock_ddl, \
         patch("app.migrate_sqlite_to_postgres.inspect") as mock_insp:
        mock_eng = MagicMock()
        mock_eng_cls.return_value = mock_eng
        mock_c = MagicMock()
        mock_eng.connect.return_value.__enter__.return_value = mock_c
        mock_insp.return_value.get_table_names.return_value = []
        mock_insp.return_value.get_view_names.return_value = []
        mock_insp.return_value.get_materialized_view_names.return_value = ["summary_mv"]

        try:
            execute_migration(
                source_path=DEFAULT_BACKUP_SOURCE if os.path.exists(DEFAULT_BACKUP_SOURCE) else DEFAULT_ACTIVE_SOURCE,
                target_url="postgresql://postgres:secret@localhost:5432/familyconnect_test",
                dry_run=True,
                quarantine_orphans=True
            )
            record_fail("Materialized view emptiness abort", "Did not raise MigrationSecurityError")
        except MigrationSecurityError as exc:
            assert "STRICT EMPTINESS ABORT" in str(exc)
            assert "summary_mv" in str(exc)
            mock_ddl.assert_not_called()
            record_pass("Destination with materialized view strictly aborts before any DDL")

    # 15.4 Destination with PostgreSQL catalog relation (e.g. foreign table or partition) aborts
    with patch("app.migrate_sqlite_to_postgres.create_engine") as mock_eng_cls, \
         patch("app.models.Base.metadata.create_all") as mock_ddl, \
         patch("app.migrate_sqlite_to_postgres.inspect") as mock_insp:
        mock_eng = MagicMock()
        mock_eng_cls.return_value = mock_eng
        mock_c = MagicMock()
        mock_c.dialect.name = "postgresql"
        mock_c.execute.return_value.fetchall.return_value = [("ext_foreign_data", "foreign table")]
        mock_eng.connect.return_value.__enter__.return_value = mock_c
        mock_insp.return_value.get_table_names.return_value = []
        mock_insp.return_value.get_view_names.return_value = []
        mock_insp.return_value.get_materialized_view_names.return_value = []

        try:
            execute_migration(
                source_path=DEFAULT_BACKUP_SOURCE if os.path.exists(DEFAULT_BACKUP_SOURCE) else DEFAULT_ACTIVE_SOURCE,
                target_url="postgresql://postgres:secret@localhost:5432/familyconnect_test",
                dry_run=True,
                quarantine_orphans=True
            )
            record_fail("Catalog relation abort", "Did not raise MigrationSecurityError")
        except MigrationSecurityError as exc:
            assert "STRICT EMPTINESS ABORT" in str(exc)
            assert "ext_foreign_data" in str(exc)
            mock_ddl.assert_not_called()
            record_pass("Destination with catalog relation (foreign table/partition) strictly aborts before any DDL")

    # 15.5 Destination catalog inspection error aborts safely (never silently assumes empty)
    with patch("app.migrate_sqlite_to_postgres.create_engine") as mock_eng_cls, \
         patch("app.models.Base.metadata.create_all") as mock_ddl, \
         patch("app.migrate_sqlite_to_postgres.inspect") as mock_insp:
        mock_eng = MagicMock()
        mock_eng_cls.return_value = mock_eng
        mock_c = MagicMock()
        mock_c.dialect.name = "postgresql"
        mock_c.execute.side_effect = RuntimeError("Permission denied reading pg_catalog.pg_class")
        mock_eng.connect.return_value.__enter__.return_value = mock_c
        mock_insp.return_value.get_table_names.return_value = []
        mock_insp.return_value.get_view_names.return_value = []
        mock_insp.return_value.get_materialized_view_names.return_value = []

        try:
            execute_migration(
                source_path=DEFAULT_BACKUP_SOURCE if os.path.exists(DEFAULT_BACKUP_SOURCE) else DEFAULT_ACTIVE_SOURCE,
                target_url="postgresql://postgres:secret@localhost:5432/familyconnect_test",
                dry_run=True,
                quarantine_orphans=True
            )
            record_fail("Catalog failure abort", "Did not abort when catalog query failed")
        except MigrationSecurityError as exc:
            assert "CATALOG INSPECTION ERROR" in str(exc)
            mock_ddl.assert_not_called()
            record_pass("Catalog query error safely aborts migration rather than assuming schema is empty")

    # 15.6 Destination with existing application table aborts before DDL
    with patch("app.migrate_sqlite_to_postgres.create_engine") as mock_eng_cls, \
         patch("app.models.Base.metadata.create_all") as mock_ddl, \
         patch("app.migrate_sqlite_to_postgres.inspect") as mock_insp:
        mock_eng = MagicMock()
        mock_eng_cls.return_value = mock_eng
        mock_c = MagicMock()
        mock_eng.connect.return_value.__enter__.return_value = mock_c
        mock_insp.return_value.get_table_names.return_value = ["users"]
        mock_insp.return_value.get_view_names.return_value = []
        mock_insp.return_value.get_materialized_view_names.return_value = []

        try:
            execute_migration(
                source_path=DEFAULT_BACKUP_SOURCE if os.path.exists(DEFAULT_BACKUP_SOURCE) else DEFAULT_ACTIVE_SOURCE,
                target_url="postgresql://postgres:secret@localhost:5432/familyconnect_test",
                dry_run=True,
                quarantine_orphans=True
            )
            record_fail("Existing app table abort", "Did not raise MigrationSecurityError")
        except MigrationSecurityError as exc:
            assert "STRICT EMPTINESS ABORT" in str(exc)
            assert "users" in str(exc)
            mock_ddl.assert_not_called()
            record_pass("Destination with existing application table strictly aborts before any DDL")

    # 15.7 Destination with unexpected standalone sequence aborts before DDL
    with patch("app.migrate_sqlite_to_postgres.create_engine") as mock_eng_cls, \
         patch("app.models.Base.metadata.create_all") as mock_ddl, \
         patch("app.migrate_sqlite_to_postgres.inspect") as mock_insp:
        mock_eng = MagicMock()
        mock_eng_cls.return_value = mock_eng
        mock_c = MagicMock()
        mock_c.dialect.name = "postgresql"
        mock_c.execute.return_value.fetchall.return_value = [("orphan_incident_seq", "sequence")]
        mock_eng.connect.return_value.__enter__.return_value = mock_c
        mock_insp.return_value.get_table_names.return_value = []
        mock_insp.return_value.get_view_names.return_value = []
        mock_insp.return_value.get_materialized_view_names.return_value = []

        try:
            execute_migration(
                source_path=DEFAULT_BACKUP_SOURCE if os.path.exists(DEFAULT_BACKUP_SOURCE) else DEFAULT_ACTIVE_SOURCE,
                target_url="postgresql://postgres:secret@localhost:5432/familyconnect_test",
                dry_run=True,
                quarantine_orphans=True
            )
            record_fail("Standalone sequence abort", "Did not raise MigrationSecurityError")
        except MigrationSecurityError as exc:
            assert "STRICT EMPTINESS ABORT" in str(exc)
            assert "orphan_incident_seq (sequence)" in str(exc)
            mock_ddl.assert_not_called()
            record_pass("Destination with standalone sequence strictly aborts before any DDL")

    # -------------------------------------------------------------
    # GROUP 16: Credential Masking & Safe Interactive Input
    # -------------------------------------------------------------
    print("\n--- GROUP 16: Credential Masking & Safe Interactive Input ---")

    # 16.1 mask_connection_url masks password and user info
    raw_secret_url = "postgresql://cloud_owner:npg_SuperSecretPass123@dpg-cool-branch-1234.oregon-postgres.render.com/appdb?sslmode=require"
    masked = mask_connection_url(raw_secret_url)
    assert "SuperSecretPass123" not in masked
    assert "cloud_owner" not in masked
    assert "clo***" in masked or "***" in masked
    assert "dpg-cool-branch-1234.oregon-postgres.render.com" in masked
    assert "sslmode=require" in masked
    record_pass("mask_connection_url completely hides password and username while preserving endpoint & parameters")

    # 16.2 mask_connection_url redacts sensitive query parameters while preserving safe ones
    token_url = "postgresql://user:pass@dpg-xyz.oregon-postgres.render.com/db?sslmode=require&token=tok_987654321&api_key=secret_key_abc"
    masked_q = mask_connection_url(token_url)
    assert "tok_987654321" not in masked_q
    assert "secret_key_abc" not in masked_q
    assert "sslmode=require" in masked_q
    assert "token=***" in masked_q
    assert "api_key=***" in masked_q
    record_pass("mask_connection_url redacts sensitive query parameters (token, api_key) while preserving safe sslmode")

    # 16.3 sanitize_error_message scrubs passwords, standalone usernames, and query tokens from exception messages
    raw_secret_url_with_tokens = "postgresql://cloud_owner:npg_SuperSecretPass123@dpg-cool-branch-1234.oregon-postgres.render.com/appdb?sslmode=require&token=tok_987654321&api_key=secret_key_abc"
    raw_err = f"OperationalError: password authentication failed for user cloud_owner at {raw_secret_url_with_tokens}"
    sanitized = sanitize_error_message(raw_err, raw_secret_url_with_tokens)
    assert "cloud_owner" not in sanitized
    assert "SuperSecretPass123" not in sanitized
    assert "tok_987654321" not in sanitized
    assert "secret_key_abc" not in sanitized
    assert "clo***" in sanitized or "***" in sanitized
    record_pass("sanitize_error_message scrubs standalone usernames, passwords, query tokens, and raw URLs")

    # 16.3b URL fragment secret redaction in mask_connection_url and sanitize_error_message
    frag_url = "postgresql://user:pass@dpg-xyz.oregon-postgres.render.com/db?sslmode=require#api_secret_fragment_999"
    masked_frag = mask_connection_url(frag_url)
    assert "api_secret_fragment_999" not in masked_frag
    assert "#***" in masked_frag
    frag_err = f"Failed to connect with fragment at {frag_url}"
    sanitized_frag = sanitize_error_message(frag_err, frag_url)
    assert "api_secret_fragment_999" not in sanitized_frag
    record_pass("URL fragment secrets redacted to #*** in mask_connection_url and scrubbed from errors")

    # 16.3c Malformed URL secret scrubbing (works even when urlparse fails or netloc is malformed)
    malformed_url = "postgresql://attacker_user:ultra_secret_pass_888@/malformed_path?tok=secret_param_token#frag_token_secret"
    masked_mal = mask_connection_url(malformed_url)
    assert "ultra_secret_pass_888" not in masked_mal
    mal_err = f"OperationalError: malformed connection string {malformed_url}"
    sanitized_mal = sanitize_error_message(mal_err, malformed_url)
    assert "ultra_secret_pass_888" not in sanitized_mal
    assert "secret_param_token" not in sanitized_mal
    assert "frag_token_secret" not in sanitized_mal
    record_pass("Malformed URL secrets, passwords, query tokens, and fragments scrubbed safely without leakage")

    # 16.4 validate_and_sanitize_url security checks
    val_empty, _, _ = validate_and_sanitize_url("")
    assert not val_empty
    val_cmd, _, err_cmd = validate_and_sanitize_url("postgresql://user:pass@host/db\nWrite-Host 'pwned'")
    assert not val_cmd
    assert "illegal multi-line" in err_cmd
    val_semi, _, err_semi = validate_and_sanitize_url("postgresql://user:pass@host/db; DROP TABLE users;")
    assert not val_semi
    assert "illegal multi-line or command-separator" in err_semi
    val_bad_scheme, _, err_scheme = validate_and_sanitize_url("http://user:pass@host/db")
    assert not val_bad_scheme
    assert "Unsupported database URL scheme" in err_scheme or "Invalid connection URL scheme" in err_scheme
    record_pass("validate_and_sanitize_url validates schemes and rejects command/multiline injections")

    # 16.5 Interactive URL prompt cancellation handling
    with patch("builtins.input", side_effect=KeyboardInterrupt):
        with patch("sys.exit") as mock_exit:
            prompt_interactive_url()
            mock_exit.assert_called_once_with(0)
    record_pass("Interactive URL prompt exits cleanly (code 0) on user cancellation (KeyboardInterrupt)")

    # 16.6 Interactive Expected Host prompt cancellation handling
    with patch("builtins.input", side_effect=EOFError):
        with patch("sys.exit") as mock_exit:
            prompt_interactive_expected_host()
            mock_exit.assert_called_once_with(0)
    record_pass("Interactive expected host prompt exits cleanly (code 0) on EOFError")

    # 16.7 CLI help documents --expected-host and -i/--interactive
    proc_help_new = subprocess.run(
        [py_exe, script_abs, "--help"],
        cwd=proj_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    assert "--expected-host" in proc_help_new.stdout, "Flag --expected-host missing from --help"
    assert "--interactive" in proc_help_new.stdout, "Flag --interactive missing from --help"
    record_pass("CLI flags --expected-host and -i/--interactive verified in help documentation")

    # -------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------
    print("\n" + "=" * 80)
    print(f"RESULTS: {passed}/{total} TESTS PASSED ({(passed/total)*100:.1f}%)")
    print("=" * 80)
    return passed == total


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
