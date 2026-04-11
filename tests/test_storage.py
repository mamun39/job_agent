from __future__ import annotations

from datetime import UTC, datetime
import sqlite3

import pytest

from job_agent.core.models import JobPosting
from job_agent.storage.db import init_db
from job_agent.storage.jobs_repo import JobsRepository


def _make_job(
    *,
    url: str = "https://example.com/jobs/1",
    source_site: str = "linkedin",
    source_job_id: str | None = "job-1",
    company: str = "Example Co",
    location: str = "Toronto, ON",
    remote_status: str = "remote",
) -> JobPosting:
    return JobPosting(
        source_site=source_site,
        source_job_id=source_job_id,
        url=url,
        title="Software Engineer",
        company=company,
        location=location,
        remote_status=remote_status,
        employment_type="full_time",
        seniority="mid",
        posted_at=datetime(2026, 4, 1, tzinfo=UTC),
        discovered_at=datetime(2026, 4, 2, tzinfo=UTC),
        description_text="Build automation tools.",
        metadata={"source": "fixture"},
    )


def test_init_db_creates_jobs_table(tmp_path) -> None:
    db_path = tmp_path / "job-agent.db"

    connection = init_db(db_path)
    try:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'jobs'"
        ).fetchone()
    finally:
        connection.close()

    assert row is not None
    assert row["name"] == "jobs"


def test_init_db_upgrades_legacy_jobs_table_with_last_seen_at(tmp_path) -> None:
    db_path = tmp_path / "job-agent.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE jobs (
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
            """
        )
        connection.execute(
            """
            INSERT INTO jobs (
                source_site,
                source_job_id,
                url,
                title,
                company,
                location,
                remote_status,
                employment_type,
                seniority,
                posted_at,
                discovered_at,
                description_text,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "greenhouse",
                "legacy-1",
                "https://example.com/jobs/legacy-1",
                "Legacy Job",
                "Example Co",
                "Toronto, ON",
                "remote",
                "full_time",
                "mid",
                None,
                "2026-04-10T00:00:00+00:00",
                "Legacy description",
                "{}",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    upgraded = init_db(db_path)
    try:
        columns = {
            row["name"]: row
            for row in upgraded.execute("PRAGMA table_info(jobs)").fetchall()
        }
        row = upgraded.execute(
            "SELECT job_status, last_seen_at FROM jobs WHERE url = ?",
            ("https://example.com/jobs/legacy-1",),
        ).fetchone()
    finally:
        upgraded.close()

    assert "job_status" in columns
    assert "last_seen_at" in columns
    assert row is not None
    assert row["job_status"] == "active"
    assert row["last_seen_at"] == "2026-04-10T00:00:00+00:00"


def test_insert_and_fetch_job(tmp_path) -> None:
    connection = init_db(tmp_path / "job-agent.db")
    repo = JobsRepository(connection)

    inserted = repo.insert_job(_make_job())
    fetched_by_url = repo.fetch_by_url("https://example.com/jobs/1")
    fetched_by_source = repo.fetch_by_source_identity("linkedin", "job-1")

    assert inserted.url.unicode_string() == "https://example.com/jobs/1"
    assert fetched_by_url is not None
    assert fetched_by_source is not None
    assert fetched_by_url.company == "Example Co"
    assert fetched_by_source.source_job_id == "job-1"


def test_insert_duplicate_job_raises_integrity_error(tmp_path) -> None:
    connection = init_db(tmp_path / "job-agent.db")
    repo = JobsRepository(connection)
    job = _make_job()

    repo.insert_job(job)

    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_job(job)


def test_upsert_updates_existing_job_without_duplication(tmp_path) -> None:
    connection = init_db(tmp_path / "job-agent.db")
    repo = JobsRepository(connection)
    repo.insert_job(_make_job())

    updated = repo.upsert_job(
        _make_job(
            url="https://example.com/jobs/1-updated",
            source_job_id="job-1",
            company="Updated Co",
            remote_status="hybrid",
        )
    )
    row = connection.execute("SELECT COUNT(*) AS count FROM jobs").fetchone()

    assert row["count"] == 1
    assert updated.company == "Updated Co"
    assert updated.remote_status.value == "hybrid"
    assert repo.fetch_by_url("https://example.com/jobs/1") is None
    assert repo.fetch_by_url("https://example.com/jobs/1-updated") is not None


def test_list_jobs_applies_simple_filters(tmp_path) -> None:
    connection = init_db(tmp_path / "job-agent.db")
    repo = JobsRepository(connection)
    repo.insert_job(_make_job(url="https://example.com/jobs/1", company="Example Co", location="Toronto, ON"))
    repo.insert_job(
        _make_job(
            url="https://example.com/jobs/2",
            source_job_id="job-2",
            company="Other Co",
            location="Remote - Canada",
            remote_status="onsite",
        )
    )

    source_filtered = repo.list_jobs(source_site="linkedin")
    company_filtered = repo.list_jobs(company="Other Co")
    location_filtered = repo.list_jobs(location_contains="Remote")
    remote_filtered = repo.list_jobs(remote_status="remote")

    assert len(source_filtered) == 2
    assert [job.company for job in company_filtered] == ["Other Co"]
    assert [job.location for job in location_filtered] == ["Remote - Canada"]
    assert [job.url.unicode_string() for job in remote_filtered] == ["https://example.com/jobs/1"]
