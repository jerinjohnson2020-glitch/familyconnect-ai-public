"""
FamilyConnect AI - Database URL Normalization & Production Guard Unit Tests
Validates:
1. Conversion of plain 'postgresql://' to explicit 'postgresql+psycopg2://'
2. Conversion of legacy 'postgres://' to explicit 'postgresql+psycopg2://'
3. Conversion of SQLAlchemy 2.0 'postgresql+psycopg://' to 'postgresql+psycopg2://'
4. Strict preservation of already-explicit 'postgresql+psycopg2://' without double-transformation
5. Quoted URL handling (stripping single and double quotes)
6. Safe rejection of unsupported drivers (asyncpg, pg8000, pygresql, etc.) without credential leakage
7. Safe rejection of non-PostgreSQL schemes in production
8. Mandatory DATABASE_URL in production (rejection of None, empty, and whitespace)
9. Rejection of SQLite URLs when ENVIRONMENT=production
10. Engine dialect resolution: SQLAlchemy 2.0 loads PGDialect_psycopg2 (psycopg2-binary)
"""

import os
import sys
import unittest
from pathlib import Path

# Add backend directory to path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.database import normalize_postgres_url, validate_database_url_for_environment
from sqlalchemy import create_engine


class TestDatabaseUrlNormalization(unittest.TestCase):
    """Unit tests for normalize_postgres_url function."""

    def test_01_plain_postgresql_normalized_to_psycopg2(self):
        url = "postgresql://dbuser:mypassword@postgres.example.com:5432/production_db?sslmode=require"
        expected = "postgresql+psycopg2://dbuser:mypassword@postgres.example.com:5432/production_db?sslmode=require"
        self.assertEqual(normalize_postgres_url(url), expected)

    def test_02_legacy_postgres_normalized_to_psycopg2(self):
        url = "postgres://dbuser:mypassword@postgres.example.com:5432/production_db?sslmode=require"
        expected = "postgresql+psycopg2://dbuser:mypassword@postgres.example.com:5432/production_db?sslmode=require"
        self.assertEqual(normalize_postgres_url(url), expected)

    def test_03_sqlalchemy_psycopg_normalized_to_psycopg2(self):
        url = "postgresql+psycopg://dbuser:mypassword@postgres.example.com:5432/production_db?sslmode=require"
        expected = "postgresql+psycopg2://dbuser:mypassword@postgres.example.com:5432/production_db?sslmode=require"
        self.assertEqual(normalize_postgres_url(url), expected)

    def test_04_already_explicit_psycopg2_preserved_intact(self):
        url = "postgresql+psycopg2://dbuser:mypassword@postgres.example.com:5432/production_db?sslmode=require"
        self.assertEqual(normalize_postgres_url(url), url)

    def test_05_idempotent_normalization(self):
        url = "postgresql://dbuser:mypassword@localhost:5432/production_db"
        first = normalize_postgres_url(url)
        second = normalize_postgres_url(first)
        third = normalize_postgres_url(second)
        self.assertEqual(first, "postgresql+psycopg2://dbuser:mypassword@localhost:5432/production_db")
        self.assertEqual(second, first)
        self.assertEqual(third, first)
        # Verify no double-prefixing occurred
        self.assertNotIn("psycopg2+psycopg2", third)

    def test_06_quoted_url_stripped_and_normalized(self):
        double_quoted = '"postgresql://dbuser:mypassword@localhost:5432/production_db"'
        single_quoted = "'postgresql+psycopg://dbuser:mypassword@localhost:5432/production_db'"
        expected = "postgresql+psycopg2://dbuser:mypassword@localhost:5432/production_db"
        self.assertEqual(normalize_postgres_url(double_quoted), expected)
        self.assertEqual(normalize_postgres_url(single_quoted), expected)

    def test_07_empty_or_whitespace_returns_empty_string(self):
        self.assertEqual(normalize_postgres_url(""), "")
        self.assertEqual(normalize_postgres_url("   "), "")
        self.assertEqual(normalize_postgres_url(None), "")

    def test_08_unsupported_postgresql_dialects_rejected(self):
        unsupported = [
            "postgresql+asyncpg://dbuser:secret123@host:5432/db",
            "postgresql+pg8000://dbuser:secret123@host:5432/db",
            "postgresql+pygresql://dbuser:secret123@host:5432/db",
            "postgres+customdriver://dbuser:secret123@host:5432/db"
        ]
        for bad_url in unsupported:
            with self.assertRaises(ValueError) as ctx:
                normalize_postgres_url(bad_url)
            err_msg = str(ctx.exception)
            self.assertIn("Unsupported PostgreSQL dialect scheme", err_msg)
            # Guarantee password is never leaked in error message
            self.assertNotIn("secret123", err_msg)
            self.assertNotIn("dbuser", err_msg)

    def test_09_non_postgresql_schemes_rejected(self):
        bad_schemes = [
            "sqlite:///test.db",
            "mysql://dbuser:secret123@host:3306/db",
            "oracle://dbuser:secret123@host:1521/db",
            "http://example.com"
        ]
        for bad_url in bad_schemes:
            with self.assertRaises(ValueError) as ctx:
                normalize_postgres_url(bad_url)
            self.assertIn("Invalid database URL scheme", str(ctx.exception))


class TestEnvironmentDatabaseUrlValidation(unittest.TestCase):
    """Unit tests for validate_database_url_for_environment function."""

    def test_01_production_rejects_missing_or_empty_url(self):
        for empty_val in [None, "", "   "]:
            with self.assertRaises(RuntimeError) as ctx:
                validate_database_url_for_environment(empty_val, "production")
            self.assertIn("no DATABASE_URL environment variable was configured", str(ctx.exception))

    def test_02_production_rejects_sqlite_url(self):
        for sqlite_url in ["sqlite:///familyconnect.db", "sqlite:////var/data/app.db", "sqlite:///:memory:"]:
            with self.assertRaises(RuntimeError) as ctx:
                validate_database_url_for_environment(sqlite_url, "production")
            self.assertIn("SQLite is not permitted in production", str(ctx.exception))

    def test_03_production_normalizes_plain_postgresql(self):
        raw = "postgresql://user:pass@postgres.example.com:5432/production_db?sslmode=require"
        normalized = validate_database_url_for_environment(raw, "production")
        self.assertEqual(normalized, "postgresql+psycopg2://user:pass@postgres.example.com:5432/production_db?sslmode=require")

    def test_04_production_normalizes_legacy_postgres(self):
        raw = "postgres://user:pass@postgres.example.com:5432/production_db?sslmode=require"
        normalized = validate_database_url_for_environment(raw, "production")
        self.assertEqual(normalized, "postgresql+psycopg2://user:pass@postgres.example.com:5432/production_db?sslmode=require")

    def test_05_production_normalizes_sqlalchemy_psycopg(self):
        raw = "postgresql+psycopg://user:pass@postgres.example.com:5432/production_db?sslmode=require"
        normalized = validate_database_url_for_environment(raw, "production")
        self.assertEqual(normalized, "postgresql+psycopg2://user:pass@postgres.example.com:5432/production_db?sslmode=require")

    def test_06_production_preserves_explicit_psycopg2(self):
        raw = "postgresql+psycopg2://user:pass@postgres.example.com:5432/production_db?sslmode=require"
        normalized = validate_database_url_for_environment(raw, "production")
        self.assertEqual(normalized, raw)

    def test_07_production_rejects_unsupported_drivers(self):
        unsupported = [
            "postgresql+asyncpg://user:supersecret@host/db",
            "postgresql+pg8000://user:supersecret@host/db",
            "mysql://user:supersecret@host/db"
        ]
        for bad in unsupported:
            with self.assertRaises(RuntimeError) as ctx:
                validate_database_url_for_environment(bad, "production")
            err = str(ctx.exception)
            self.assertIn("CRITICAL DATABASE CONFIGURATION ERROR", err)
            # Never leak password in exception
            self.assertNotIn("supersecret", err)

    def test_08_development_mode_falls_back_to_sqlite(self):
        dev_res = validate_database_url_for_environment(None, "development")
        self.assertTrue(dev_res.startswith("sqlite:///"))
        self.assertIn("familyconnect.db", dev_res)

    def test_09_development_mode_preserves_custom_sqlite_url(self):
        custom = "sqlite:///custom_dev.db"
        dev_res = validate_database_url_for_environment(custom, "development")
        self.assertEqual(dev_res, custom)

    def test_10_development_mode_normalizes_postgresql_urls(self):
        raw = "postgresql://user:pass@localhost:5432/devdb"
        dev_res = validate_database_url_for_environment(raw, "development")
        self.assertEqual(dev_res, "postgresql+psycopg2://user:pass@localhost:5432/devdb")

    def test_11_sqlalchemy_engine_loads_psycopg2_driver(self):
        url = "postgresql://testuser:testpass@localhost:5432/testdb"
        normalized = normalize_postgres_url(url)
        engine = create_engine(normalized)
        self.assertEqual(engine.dialect.name, "postgresql")
        self.assertEqual(engine.dialect.driver, "psycopg2")
        self.assertEqual(engine.dialect.__class__.__name__, "PGDialect_psycopg2")


if __name__ == "__main__":
    unittest.main()
