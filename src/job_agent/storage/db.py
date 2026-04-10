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
        posted_at TEXT,
        discovered_at TEXT NOT NULL,
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
    connection.commit()
    return connection

