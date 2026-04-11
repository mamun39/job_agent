"""SQLite database bootstrap for job-agent."""

from __future__ import annotations

from pathlib import Path
import sqlite3


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_site TEXT NOT NULL,
        source_job_id TEXT,
        url TEXT NOT NULL,
        title TEXT NOT NULL,
        company TEXT NOT NULL,
        location TEXT NOT NULL,
        remote_status TEXT NOT NULL,
        employment_type TEXT NOT NULL,
        seniority TEXT NOT NULL,
        job_status TEXT NOT NULL DEFAULT 'active',
        posted_at TEXT,
        discovered_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        description_text TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_url_unique ON jobs(url)",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_source_identity_unique
    ON jobs(source_site, source_job_id)
    WHERE source_job_id IS NOT NULL AND source_job_id != ''
    """,
    "CREATE INDEX IF NOT EXISTS idx_jobs_source_site ON jobs(source_site)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_remote_status ON jobs(remote_status)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_posted_at ON jobs(posted_at)",
    """
    CREATE TABLE IF NOT EXISTS review_decisions (
        posting_url TEXT PRIMARY KEY,
        decision TEXT NOT NULL,
        decided_at TEXT NOT NULL,
        note TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_review_decisions_decision ON review_decisions(decision)",
)


def connect_db(db_path: str | Path) -> sqlite3.Connection:
    """Create a SQLite connection with row access by column name."""
    path = Path(db_path)
    if path != Path(":memory:"):
        path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(db_path: str | Path) -> sqlite3.Connection:
    """Create the database file if needed and initialize the schema."""
    connection = connect_db(db_path)
    for statement in SCHEMA_STATEMENTS:
        connection.execute(statement)
    _ensure_jobs_columns(connection)
    connection.commit()
    return connection


def _ensure_jobs_columns(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
    }
    if "job_status" not in existing_columns:
        connection.execute("ALTER TABLE jobs ADD COLUMN job_status TEXT NOT NULL DEFAULT 'active'")
    if "last_seen_at" not in existing_columns:
        connection.execute("ALTER TABLE jobs ADD COLUMN last_seen_at TEXT")
        connection.execute(
            """
            UPDATE jobs
            SET last_seen_at = COALESCE(last_seen_at, discovered_at, posted_at, CURRENT_TIMESTAMP)
            WHERE last_seen_at IS NULL
            """
        )
