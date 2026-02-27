"""
SQLite database layer for the NYC Music Teacher Finder bot.

Tables:
- teachers            — scraped/approved teachers
- pending_submissions — user-submitted teachers awaiting review
"""

import json
import sqlite3
from typing import Optional


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(db_path: str) -> None:
    """Create tables and indexes. Safe to call on every startup."""
    with _connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS teachers (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                name           TEXT NOT NULL,
                instruments    TEXT,
                remote_virtual TEXT DEFAULT 'In-Person',
                address        TEXT,
                email          TEXT,
                website        TEXT,
                phone          TEXT,
                rates          TEXT,
                source         TEXT NOT NULL,
                city           TEXT NOT NULL DEFAULT 'New York City',
                created_at     TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(name, phone),
                UNIQUE(website)
            );

            CREATE TABLE IF NOT EXISTS pending_submissions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT NOT NULL,
                instruments  TEXT,
                remote_virtual TEXT DEFAULT 'In-Person',
                address      TEXT,
                email        TEXT,
                website      TEXT NOT NULL,
                phone        TEXT NOT NULL,
                rates        TEXT,
                submitted_by INTEGER,
                submitted_at TEXT NOT NULL DEFAULT (datetime('now')),
                reviewed     INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_teachers_instruments
                ON teachers(instruments);
            CREATE INDEX IF NOT EXISTS idx_teachers_name
                ON teachers(name);
            CREATE INDEX IF NOT EXISTS idx_pending_reviewed
                ON pending_submissions(reviewed);
            """
        )


def upsert_teacher(
    db_path: str,
    name: str,
    instruments: list[str],
    remote_virtual: str,
    address: Optional[str],
    email: Optional[str],
    website: Optional[str],
    phone: Optional[str],
    rates: Optional[str],
    source: str,
) -> None:
    """
    Insert a teacher record, ignoring duplicates.

    Dedup priority:
    1. website (UNIQUE constraint)
    2. (name, phone) composite UNIQUE constraint
    """
    instruments_json = json.dumps(instruments) if instruments else None
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO teachers
                (name, instruments, remote_virtual, address, email,
                 website, phone, rates, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                instruments_json,
                remote_virtual,
                address,
                email,
                website,
                phone,
                rates,
                source,
            ),
        )


def search_teachers(
    db_path: str,
    instrument: Optional[str] = None,
    remote_only: bool = False,
    name_query: Optional[str] = None,
    limit: int = 10,
) -> list[dict]:
    """
    Search teachers with optional filters.

    - instrument: substring match against the instruments JSON column
    - remote_only: if True, only return Remote or Both teachers
    - name_query:  substring match against name
    """
    conditions = []
    params: list = []

    if instrument:
        conditions.append("instruments LIKE ?")
        params.append(f"%{instrument}%")

    if remote_only:
        conditions.append("remote_virtual IN ('Remote', 'Both')")

    if name_query:
        conditions.append("name LIKE ?")
        params.append(f"%{name_query}%")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)

    with _connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM teachers {where} ORDER BY name LIMIT ?",
            params,
        ).fetchall()

    return [dict(row) for row in rows]


def get_teacher(db_path: str, teacher_id: int) -> Optional[dict]:
    """Return a single teacher record by ID, or None if not found."""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM teachers WHERE id = ?", (teacher_id,)
        ).fetchone()
    return dict(row) if row else None


def list_instruments(db_path: str) -> list[str]:
    """
    Return a sorted, deduplicated list of all instruments in the DB.

    Instruments are stored as JSON arrays; this parses them all out.
    """
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT instruments FROM teachers WHERE instruments IS NOT NULL"
        ).fetchall()

    seen: set[str] = set()
    for row in rows:
        try:
            for instr in json.loads(row["instruments"]):
                seen.add(instr.strip())
        except (json.JSONDecodeError, TypeError):
            pass

    return sorted(seen)


def add_pending_submission(
    db_path: str,
    name: str,
    instruments: list[str],
    phone: str,
    website: str,
    remote_virtual: str = "In-Person",
    address: Optional[str] = None,
    email: Optional[str] = None,
    rates: Optional[str] = None,
    submitted_by: Optional[int] = None,
) -> int:
    """Insert a pending teacher submission. Returns the new row ID."""
    instruments_json = json.dumps(instruments) if instruments else None
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO pending_submissions
                (name, instruments, remote_virtual, address, email,
                 website, phone, rates, submitted_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                instruments_json,
                remote_virtual,
                address,
                email,
                website,
                phone,
                rates,
                submitted_by,
            ),
        )
    return cursor.lastrowid
