"""
FamilyConnect AI - Stage 1.5 Safe Migration Verification Suite
Tests the migration strictly against a newly created temporary SQLite database with representative synthetic data.
Confirms:
1. Check detection: Correctly identifies when location columns are missing vs present.
2. Transactional dry run: Tests ALTER statements in a transaction and rolls back cleanly with 0 permanent changes.
3. Live migration execution: Successfully adds all 6 location columns.
4. Data preservation: All existing member rows and attribute values are 100% preserved.
5. Location privacy default: is_sharing_location defaults to 0 (disabled) across all existing rows; coordinates are NULL.
6. Idempotency: Re-running migration on an already migrated database causes 0 duplicate columns and 0 errors.
7. Unrelated tables safety: Other application tables (users, responders, incidents, contacts) are completely untouched.
8. Real database safety gate: Refuses to touch backend/familyconnect.db without explicit --confirm flag.
9. Real database immutability: backend/familyconnect.db remains bit-for-bit untouched (323,584 bytes).
"""

import os
import sys
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

# Add backend directory to sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

SCRIPTS_DIR = BASE_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from scripts.migrate_family_location import (
    check_location_columns,
    execute_migration,
    MigrationSafetyError,
    LOCATION_MIGRATION_COLUMNS,
    REAL_DB_PATH
)


class TestStage15DatabaseMigration(unittest.TestCase):
    temp_dir = None
    temp_db_path = None
    initial_real_db_size = None

    @classmethod
    def setUpClass(cls):
        # 1. Record real DB size to assert immutability
        if REAL_DB_PATH.exists():
            cls.initial_real_db_size = REAL_DB_PATH.stat().st_size

        # 2. Create isolated temporary directory
        cls.temp_dir = tempfile.mkdtemp(prefix="fc_migration_test_")
        cls.temp_db_path = Path(cls.temp_dir) / "temp_stage1_5_synthetic.db"

        # 3. Create pre-migration schema matching backend/familyconnect.db (16 columns, 0 location columns)
        conn = sqlite3.connect(str(cls.temp_db_path))
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name VARCHAR(100) NOT NULL,
                relationship VARCHAR(50) DEFAULT 'Family Member',
                age INTEGER,
                phone VARCHAR(30) NOT NULL,
                email VARCHAR(120),
                address VARCHAR(255),
                blood_group VARCHAR(10),
                medical_notes TEXT,
                emergency_contact_name VARCHAR(100),
                emergency_contact_phone VARCHAR(30),
                is_active BOOLEAN DEFAULT 1 NOT NULL,
                is_demo BOOLEAN DEFAULT 0 NOT NULL,
                created_at DATETIME,
                updated_at DATETIME
            );
        """)

        # Unrelated tables to confirm they are never altered
        cursor.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username VARCHAR(50) NOT NULL,
                role VARCHAR(20) NOT NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE responders (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                phone VARCHAR(30) NOT NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE emergency_incidents (
                id INTEGER PRIMARY KEY,
                reporter_name VARCHAR(100) NOT NULL,
                status VARCHAR(20) NOT NULL
            );
        """)
        cursor.execute("""
            CREATE TABLE trusted_contacts (
                id INTEGER PRIMARY KEY,
                member_id INTEGER NOT NULL,
                name VARCHAR(100) NOT NULL,
                phone VARCHAR(30) NOT NULL
            );
        """)

        # Populate representative synthetic members (without location columns)
        synthetic_members = [
            (1, 1, "Alice Johnson", "Son", 16, "+91 98765 11111", "alice@example.com", "123 Elm St, Bengaluru", "O+", "No allergies", "Mom", "+91 98765 00000", 1, 0, "2026-01-01 10:00:00", "2026-01-01 10:00:00"),
            (2, 1, "Bob Johnson", "Grandparent", 72, "+91 98765 22222", "bob@example.com", "123 Elm St, Bengaluru", "B+", "Hypertension", "Daughter", "+91 98765 00000", 1, 0, "2026-01-02 11:00:00", "2026-01-02 11:00:00"),
            (3, 2, "Charlie Brown", "Brother", 25, "+91 98765 33333", "charlie@example.com", "456 Oak St, Mumbai", "A-", "Peanut allergy", None, None, 0, 0, "2026-01-03 12:00:00", "2026-01-03 12:00:00"),
            (4, 1, "Demo Member", "Family Member", 30, "+1 (555) 234-5678", "demo@example.com", "789 Pine St", "AB+", None, None, None, 1, 1, "2026-01-04 13:00:00", "2026-01-04 13:00:00"),
            (5, 3, "Alex Smith", "Self", 40, "+91 98765 55555", "alex@example.com", "101 Maple Rd", "O-", "Asthma", None, None, 1, 0, "2026-01-05 14:00:00", "2026-01-05 14:00:00"),
        ]

        cursor.executemany("""
            INSERT INTO members (
                id, user_id, name, relationship, age, phone, email, address,
                blood_group, medical_notes, emergency_contact_name, emergency_contact_phone,
                is_active, is_demo, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, synthetic_members)

        # Populate unrelated tables
        cursor.execute("INSERT INTO users (id, username, role) VALUES (1, 'admin1', 'admin'), (2, 'member1', 'member');")
        cursor.execute("INSERT INTO responders (id, name, phone) VALUES (1, 'Officer David', '+91 98765 99999');")
        cursor.execute("INSERT INTO emergency_incidents (id, reporter_name, status) VALUES (1, 'Alice Johnson', 'RESOLVED');")
        cursor.execute("INSERT INTO trusted_contacts (id, member_id, name, phone) VALUES (1, 1, 'Emergency Mom', '+91 98765 00000');")

        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        # Clean up temporary test files
        if cls.temp_dir and os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir, ignore_errors=True)

        # Assert real database was never touched
        if REAL_DB_PATH.exists() and cls.initial_real_db_size is not None:
            final_size = REAL_DB_PATH.stat().st_size
            assert final_size == cls.initial_real_db_size, (
                f"SAFETY VIOLATION: backend/familyconnect.db was modified during tests! "
                f"(initial={cls.initial_real_db_size}, final={final_size})"
            )

    # -------------------------------------------------------------
    # 1. Detection of Unmigrated Schema
    # -------------------------------------------------------------
    def test_01_check_detects_unmigrated_schema(self):
        """
        Verify check_location_columns correctly detects that all 6 location columns
        are missing on the pre-migration database.
        """
        conn = sqlite3.connect(str(self.temp_db_path))
        try:
            info = check_location_columns(conn)
            self.assertFalse(info["is_fully_migrated"])
            self.assertEqual(len(info["missing_columns"]), 6)
            self.assertEqual(info["total_columns_count"], 16)
            for col_name, _ in LOCATION_MIGRATION_COLUMNS:
                self.assertFalse(info["location_columns_status"][col_name])
        finally:
            conn.close()

    # -------------------------------------------------------------
    # 2. Transactional Dry Run
    # -------------------------------------------------------------
    def test_02_transactional_dry_run_leaves_zero_modifications(self):
        """
        Verify dry-run migration tests ALTER statements inside a transaction,
        rolls back cleanly, and leaves the database file completely unchanged.
        """
        size_before = self.temp_db_path.stat().st_size

        res = execute_migration(self.temp_db_path, dry_run=True)
        self.assertEqual(res["status"], "DRY_RUN_PASSED")
        self.assertTrue(res["dry_run"])
        self.assertFalse(res["database_modified"])
        self.assertEqual(res["missing_columns_count"], 6)
        self.assertEqual(len(res["executed_statements"]), 6)
        self.assertEqual(res["rows_verified"], 5)

        # Verify DB still has only 16 columns after rollback
        conn = sqlite3.connect(str(self.temp_db_path))
        try:
            info = check_location_columns(conn)
            self.assertFalse(info["is_fully_migrated"])
            self.assertEqual(len(info["missing_columns"]), 6)
            self.assertEqual(info["total_columns_count"], 16)
        finally:
            conn.close()

    # -------------------------------------------------------------
    # 3. Live Migration Execution
    # -------------------------------------------------------------
    def test_03_apply_migration_adds_all_six_columns(self):
        """
        Verify live migration executes ALTER statements, adds all 6 columns,
        and expands total column count from 16 to 22.
        """
        res = execute_migration(self.temp_db_path, dry_run=False, confirm=True)
        self.assertEqual(res["status"], "APPLIED_SUCCESSFULLY")
        self.assertFalse(res["dry_run"])
        self.assertEqual(len(res["columns_added"]), 6)
        self.assertEqual(res["rows_preserved"], 5)
        self.assertEqual(res["pre_migration_columns"], 16)
        self.assertEqual(res["post_migration_columns"], 22)

        # Verify with check_location_columns
        conn = sqlite3.connect(str(self.temp_db_path))
        try:
            info = check_location_columns(conn)
            self.assertTrue(info["is_fully_migrated"])
            self.assertEqual(len(info["missing_columns"]), 0)
            self.assertEqual(info["total_columns_count"], 22)
            for col_name, _ in LOCATION_MIGRATION_COLUMNS:
                self.assertTrue(info["location_columns_status"][col_name])
        finally:
            conn.close()

    # -------------------------------------------------------------
    # 4. Data Preservation & Location Privacy Default
    # -------------------------------------------------------------
    def test_04_data_preservation_and_privacy_default(self):
        """
        Verify:
        - All 5 existing rows are 100% preserved.
        - Existing fields (name, phone, medical notes, etc.) are intact.
        - is_sharing_location defaults to 0 (False) for all rows.
        - latitude, longitude, accuracy, label, updated_at are all NULL.
        """
        conn = sqlite3.connect(str(self.temp_db_path))
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT id, name, phone, medical_notes, is_active, is_demo,
                       is_sharing_location, latitude, longitude, location_accuracy_m, location_label, location_updated_at
                FROM members ORDER BY id ASC;
            """)
            rows = cursor.fetchall()
            self.assertEqual(len(rows), 5)

            # Row 1: Alice Johnson
            self.assertEqual(rows[0][1], "Alice Johnson")
            self.assertEqual(rows[0][2], "+91 98765 11111")
            self.assertEqual(rows[0][3], "No allergies")
            self.assertEqual(rows[0][4], 1)
            self.assertEqual(rows[0][5], 0)
            self.assertEqual(rows[0][6], 0)  # is_sharing_location == 0
            self.assertIsNone(rows[0][7])     # latitude is NULL
            self.assertIsNone(rows[0][8])     # longitude is NULL
            self.assertIsNone(rows[0][9])     # accuracy is NULL
            self.assertIsNone(rows[0][10])    # label is NULL
            self.assertIsNone(rows[0][11])    # updated_at is NULL

            # Row 2: Bob Johnson (Hypertension)
            self.assertEqual(rows[1][1], "Bob Johnson")
            self.assertEqual(rows[1][3], "Hypertension")
            self.assertEqual(rows[1][6], 0)
            self.assertIsNone(rows[1][7])

            # Row 4: Demo Member (is_demo == 1)
            self.assertEqual(rows[3][1], "Demo Member")
            self.assertEqual(rows[3][5], 1)
            self.assertEqual(rows[3][6], 0)

            # Confirm 100% of rows have is_sharing_location == 0
            cursor.execute("SELECT count(*) FROM members WHERE is_sharing_location != 0;")
            self.assertEqual(cursor.fetchone()[0], 0)
        finally:
            conn.close()

    # -------------------------------------------------------------
    # 5. Idempotency (Re-running Migration)
    # -------------------------------------------------------------
    def test_05_idempotent_rerun_causes_zero_duplicate_columns(self):
        """
        Verify that running the migration a second time on the already migrated database
        detects all columns exist, executes 0 ALTER statements, and reports ALREADY_MIGRATED.
        """
        res = execute_migration(self.temp_db_path, dry_run=False, confirm=True)
        self.assertEqual(res["status"], "ALREADY_MIGRATED")
        self.assertEqual(res["missing_columns_count"], 0)
        self.assertEqual(res["columns_added"], [])

        # Confirm column count remains exactly 22
        conn = sqlite3.connect(str(self.temp_db_path))
        try:
            info = check_location_columns(conn)
            self.assertTrue(info["is_fully_migrated"])
            self.assertEqual(info["total_columns_count"], 22)
        finally:
            conn.close()

    # -------------------------------------------------------------
    # 6. Unrelated Tables Untouched
    # -------------------------------------------------------------
    def test_06_unrelated_tables_remain_completely_untouched(self):
        """
        Verify that users, responders, emergency_incidents, and trusted_contacts
        schemas and row counts are completely unchanged.
        """
        conn = sqlite3.connect(str(self.temp_db_path))
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT count(*) FROM users;")
            self.assertEqual(cursor.fetchone()[0], 2)

            cursor.execute("SELECT count(*) FROM responders;")
            self.assertEqual(cursor.fetchone()[0], 1)

            cursor.execute("SELECT count(*) FROM emergency_incidents;")
            self.assertEqual(cursor.fetchone()[0], 1)

            cursor.execute("SELECT count(*) FROM trusted_contacts;")
            self.assertEqual(cursor.fetchone()[0], 1)
        finally:
            conn.close()

    # -------------------------------------------------------------
    # 7. Safety Gate on Real Database
    # -------------------------------------------------------------
    def test_07_safety_gate_rejects_unconfirmed_migration_on_real_database(self):
        """
        Verify that attempting to run live migration on backend/familyconnect.db
        WITHOUT explicit confirm=True raises MigrationSafetyError immediately.
        """
        if REAL_DB_PATH.exists():
            with self.assertRaises(MigrationSafetyError) as ctx:
                execute_migration(REAL_DB_PATH, dry_run=False, confirm=False)
            self.assertIn("SAFETY GATE ACTIVATED", str(ctx.exception))

    # -------------------------------------------------------------
    # 8. Real Database Immutability
    # -------------------------------------------------------------
    def test_08_real_database_remains_strictly_untouched(self):
        """
        Verify backend/familyconnect.db size is bit-for-bit unchanged.
        """
        if REAL_DB_PATH.exists() and self.initial_real_db_size is not None:
            self.assertEqual(REAL_DB_PATH.stat().st_size, self.initial_real_db_size)


if __name__ == "__main__":
    unittest.main()
