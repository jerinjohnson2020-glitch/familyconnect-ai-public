"""
Phase 5E: Safe Online SQLite Backup & Integrity Verification Utility.
Uses sqlite3.Connection.backup() to create consistent hot backups without locking or data loss.
"""

import os
import sys
import sqlite3
import datetime
from pathlib import Path
from .database import DB_PATH


def create_hot_backup(backup_dir: str = None) -> dict:
    src_path = Path(DB_PATH).resolve()
    if not src_path.exists():
        raise FileNotFoundError(f"Database file not found at {src_path}")

    target_dir = Path(backup_dir).resolve() if backup_dir else src_path.parent / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    dest_path = target_dir / f"familyconnect_backup_{ts}.db"

    src_conn = sqlite3.connect(str(src_path))
    dest_conn = sqlite3.connect(str(dest_path))
    try:
        with dest_conn:
            src_conn.backup(dest_conn)

        # Verify integrity of backup
        cur = dest_conn.cursor()
        cur.execute("PRAGMA integrity_check;")
        integrity = cur.fetchone()[0]

        counts = {}
        for table in ["users", "members", "trusted_contacts", "responders", "emergency_incidents", "incident_alerts", "incident_timeline_events"]:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                counts[table] = cur.fetchone()[0]
            except Exception:
                counts[table] = 0
    finally:
        dest_conn.close()
        src_conn.close()

    return {
        "source_db": str(src_path),
        "backup_file": str(dest_path),
        "size_bytes": dest_path.stat().st_size,
        "integrity_check": integrity,
        "row_counts": counts,
        "timestamp_utc": ts
    }


if __name__ == "__main__":
    info = create_hot_backup()
    print(f"[Backup] Created verified hot backup: {info['backup_file']} ({info['size_bytes']} bytes)")
    print(f"[Backup] Integrity: {info['integrity_check']} | Counts: {info['row_counts']}")
