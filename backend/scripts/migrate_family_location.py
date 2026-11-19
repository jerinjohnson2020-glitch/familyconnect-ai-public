"""
FamilyConnect AI - Safe Family Location Schema Migration Runner (Stage 1.5)

Safely adds the 6 family-location columns to the 'members' table in SQLite:
  1. is_sharing_location  BOOLEAN DEFAULT 0 NOT NULL
  2. latitude             FLOAT
  3. longitude            FLOAT
  4. location_accuracy_m  FLOAT
  5. location_label       VARCHAR(100)
  6. location_updated_at  DATETIME

Safety guarantees:
- Idempotent: checks PRAGMA table_info(members) before altering; never duplicates columns.
- Non-destructive: preserves all existing rows and column values.
- Default-safe: is_sharing_location defaults to 0 (disabled) for all existing and new rows.
- Transactional dry-run: tests ALTER statements in a transaction and rolls back cleanly.
- Strict confirmation: refuses to touch real database 'backend/familyconnect.db' without explicit --confirm flag.
- Zero side-effects: unrelated tables and database backups are never touched.
"""

import os
import sys
import sqlite3
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

# Expected column definitions for Family Location MVP
LOCATION_MIGRATION_COLUMNS: List[Tuple[str, str]] = [
    ("is_sharing_location", "BOOLEAN DEFAULT 0 NOT NULL"),
    ("latitude", "FLOAT"),
    ("longitude", "FLOAT"),
    ("location_accuracy_m", "FLOAT"),
    ("location_label", "VARCHAR(100)"),
    ("location_updated_at", "DATETIME")
]

BASE_DIR = Path(__file__).resolve().parent.parent
REAL_DB_PATH = (BASE_DIR / "familyconnect.db").resolve()


class MigrationSafetyError(Exception):
    """Raised when safety prerequisites or confirmation checks fail."""
    pass


def check_location_columns(conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    Read-only inspection of the 'members' table schema.
    Returns status of each location column, missing columns, and whether migration is complete.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='members';")
    if not cursor.fetchone():
        raise MigrationSafetyError("Table 'members' does not exist in the target database.")

    cursor.execute("PRAGMA table_info(members);")
    existing_cols = {row[1]: {"type": row[2], "notnull": bool(row[3]), "dflt": row[4]} for row in cursor.fetchall()}

    status = {}
    missing = []
    for col_name, col_sql in LOCATION_MIGRATION_COLUMNS:
        present = col_name in existing_cols
        status[col_name] = present
        if not present:
            missing.append((col_name, col_sql))

    return {
        "existing_column_names": list(existing_cols.keys()),
        "location_columns_status": status,
        "missing_columns": missing,
        "is_fully_migrated": len(missing) == 0,
        "total_columns_count": len(existing_cols)
    }


def execute_migration(
    target_db_path: Path,
    dry_run: bool = False,
    confirm: bool = False
) -> Dict[str, Any]:
    """
    Executes the location migration safely against target_db_path.

    Parameters:
      target_db_path: Path to the target SQLite database.
      dry_run: If True, executes inside a transaction that is rolled back (0 permanent changes).
      confirm: Required to be True if target_db_path resolves to the real local database (familyconnect.db).

    Returns a detailed audit report dict.
    """
    target_path = Path(target_db_path).resolve()
    if not target_path.exists():
        raise MigrationSafetyError(f"Target database file not found: {target_path}")

    # Safety Guard: Protect real production / local database
    is_real_db = (target_path == REAL_DB_PATH)
    if is_real_db and not dry_run and not confirm:
        raise MigrationSafetyError(
            "SAFETY GATE ACTIVATED: Refusing to modify real database 'backend/familyconnect.db'. "
            "You must pass explicit --confirm flag to approve applying migration to the real database."
        )

    pre_size = target_path.stat().st_size
    conn = sqlite3.connect(str(target_path))
    cursor = conn.cursor()

    try:
        # Pre-check schema
        pre_info = check_location_columns(conn)
        missing = pre_info["missing_columns"]

        if pre_info["is_fully_migrated"]:
            return {
                "status": "ALREADY_MIGRATED",
                "target_db": str(target_path),
                "is_real_db": is_real_db,
                "dry_run": dry_run,
                "missing_columns_count": 0,
                "columns_added": [],
                "message": "All 6 location columns already exist in 'members' table. No migration required."
            }

        # Count existing rows before migration
        cursor.execute("SELECT count(*) FROM members;")
        pre_row_count = cursor.fetchone()[0]

        executed_statements = []

        if dry_run:
            # Transactional dry run
            conn.isolation_level = None  # Autocommit off, manage manually
            cursor.execute("BEGIN TRANSACTION;")

            for col_name, col_sql in missing:
                stmt = f"ALTER TABLE members ADD COLUMN {col_name} {col_sql};"
                cursor.execute(stmt)
                executed_statements.append(stmt)

            # Validate columns in dry-run transaction
            cursor.execute("PRAGMA table_info(members);")
            post_tx_cols = {row[1] for row in cursor.fetchall()}
            for col_name, _ in missing:
                if col_name not in post_tx_cols:
                    raise MigrationSafetyError(f"Dry-run verification failed: column {col_name} missing after ALTER.")

            # Validate test query over new columns and existing rows
            cursor.execute("SELECT is_sharing_location, latitude, longitude FROM members LIMIT 5;")
            _ = cursor.fetchall()

            # Roll back cleanly
            cursor.execute("ROLLBACK;")
            conn.close()

            post_size = target_path.stat().st_size
            return {
                "status": "DRY_RUN_PASSED",
                "target_db": str(target_path),
                "is_real_db": is_real_db,
                "dry_run": True,
                "pre_migration_columns": pre_info["total_columns_count"],
                "missing_columns_count": len(missing),
                "executed_statements": executed_statements,
                "rows_verified": pre_row_count,
                "pre_size_bytes": pre_size,
                "post_size_bytes": post_size,
                "database_modified": False,
                "message": f"Dry run passed successfully. {len(executed_statements)} statements verified and rolled back cleanly."
            }

        else:
            # Live Migration (Approved)
            for col_name, col_sql in missing:
                stmt = f"ALTER TABLE members ADD COLUMN {col_name} {col_sql};"
                cursor.execute(stmt)
                executed_statements.append(stmt)

            conn.commit()

            # Verify post-migration state
            post_info = check_location_columns(conn)
            cursor.execute("SELECT count(*) FROM members;")
            post_row_count = cursor.fetchone()[0]

            if post_row_count != pre_row_count:
                raise MigrationSafetyError(
                    f"Row count mismatch after migration: pre={pre_row_count}, post={post_row_count}"
                )

            # Verify all existing rows have is_sharing_location=0
            cursor.execute("SELECT count(*) FROM members WHERE is_sharing_location != 0;")
            non_zero_count = cursor.fetchone()[0]
            if non_zero_count > 0:
                raise MigrationSafetyError(
                    f"Security invariant violated: {non_zero_count} rows have non-zero is_sharing_location."
                )

            conn.close()
            post_size = target_path.stat().st_size

            return {
                "status": "APPLIED_SUCCESSFULLY",
                "target_db": str(target_path),
                "is_real_db": is_real_db,
                "dry_run": False,
                "pre_migration_columns": pre_info["total_columns_count"],
                "post_migration_columns": post_info["total_columns_count"],
                "columns_added": [c[0] for c in missing],
                "executed_statements": executed_statements,
                "rows_preserved": post_row_count,
                "pre_size_bytes": pre_size,
                "post_size_bytes": post_size,
                "message": f"Successfully added {len(executed_statements)} location columns to 'members'. All {post_row_count} rows preserved."
            }

    finally:
        try:
            conn.close()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(
        description="FamilyConnect AI - Safe Family Location Schema Migration Runner (Stage 1.5)"
    )
    parser.add_argument(
        "--target-db",
        type=str,
        required=True,
        help="Path to the SQLite database file to inspect or migrate."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Read-only schema check: inspect whether location columns exist."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Transactional dry run: test ALTER statements and rollback (0 permanent changes)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the migration live."
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Explicit confirmation required to apply migration to the real database."
    )

    args = parser.parse_args()
    db_path = Path(args.target_db).resolve()

    if not db_path.exists():
        print(f"[ERROR] Database file not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    if args.check:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            info = check_location_columns(conn)
            print(f"[Check] Target database: {db_path}")
            print(f"[Check] Fully migrated: {info['is_fully_migrated']}")
            print(f"[Check] Total columns on 'members': {info['total_columns_count']}")
            for col_name, present in info["location_columns_status"].items():
                status_str = "EXISTS" if present else "MISSING"
                print(f"  - {col_name:24s}: {status_str}")
            sys.exit(0 if info["is_fully_migrated"] else 2)
        finally:
            conn.close()

    elif args.dry_run:
        print(f"[Dry Run] Running transactional dry-run migration on: {db_path}...")
        res = execute_migration(db_path, dry_run=True)
        print(f"[Dry Run] Status: {res['status']}")
        print(f"[Dry Run] Missing columns: {res.get('missing_columns_count', 0)}")
        for stmt in res.get("executed_statements", []):
            print(f"  SQL: {stmt}")
        print(f"[Dry Run] {res['message']}")
        sys.exit(0)

    elif args.apply:
        print(f"[Apply] Running live migration on: {db_path}...")
        res = execute_migration(db_path, dry_run=False, confirm=args.confirm)
        print(f"[Apply] Status: {res['status']}")
        for stmt in res.get("executed_statements", []):
            print(f"  Executed SQL: {stmt}")
        print(f"[Apply] {res['message']}")
        sys.exit(0)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
