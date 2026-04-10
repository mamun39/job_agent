"""Repository for storing and querying job postings."""

from __future__ import annotations

from datetime import datetime
import json
import sqlite3
from typing import Any

from job_agent.core.models import JobPosting


class JobsRepository:
    """Repository for CRUD-style job posting persistence."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def initialize_schema(self) -> None:
        """Ensure the jobs table exists for the current connection."""
        from job_agent.storage.db import SCHEMA_STATEMENTS

        for statement in SCHEMA_STATEMENTS:
            self._connection.execute(statement)
        self._connection.commit()

    def insert_job(self, job: JobPosting) -> JobPosting:
        """Insert a job posting and return the stored model."""
        payload = self._job_to_row(job)
        self._connection.execute(
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
            ) VALUES (
                :source_site,
                :source_job_id,
                :url,
                :title,
                :company,
                :location,
                :remote_status,
                :employment_type,
                :seniority,
                :posted_at,
                :discovered_at,
                :description_text,
                :metadata_json
            )
            """,
            payload,
        )
        self._connection.commit()
        stored = self.fetch_by_url(job.url.unicode_string())
        if stored is None:
            raise RuntimeError("insert succeeded but job could not be reloaded")
        return stored

    def upsert_job(self, job: JobPosting) -> JobPosting:
        """Insert or update a job posting using deduplication keys."""
        existing = self.fetch_by_url(job.url.unicode_string())
        if existing is None and job.source_job_id:
            existing = self.fetch_by_source_identity(job.source_site, job.source_job_id)

        if existing is None:
            return self.insert_job(job)

        payload = self._job_to_row(job)
        payload["existing_url"] = existing.url.unicode_string()
        self._connection.execute(
            """
            UPDATE jobs
            SET
                source_site = :source_site,
                source_job_id = :source_job_id,
                url = :url,
                title = :title,
                company = :company,
                location = :location,
                remote_status = :remote_status,
                employment_type = :employment_type,
                seniority = :seniority,
                posted_at = :posted_at,
                discovered_at = :discovered_at,
                description_text = :description_text,
                metadata_json = :metadata_json,
                updated_at = CURRENT_TIMESTAMP
            WHERE url = :existing_url
            """,
            payload,
        )
        self._connection.commit()
        stored = self.fetch_by_url(job.url.unicode_string())
        if stored is None:
            raise RuntimeError("upsert succeeded but job could not be reloaded")
        return stored

    def fetch_by_url(self, url: str) -> JobPosting | None:
        """Fetch a single job posting by canonical URL."""
        row = self._connection.execute(
            "SELECT * FROM jobs WHERE url = ?",
            (url,),
        ).fetchone()
        return self._row_to_job(row) if row else None

    def fetch_by_source_identity(self, source_site: str, source_job_id: str) -> JobPosting | None:
        """Fetch a single job posting by source-specific identity."""
        row = self._connection.execute(
            """
            SELECT * FROM jobs
            WHERE source_site = ? AND source_job_id = ?
            """,
            (source_site, source_job_id),
        ).fetchone()
        return self._row_to_job(row) if row else None

    def list_jobs(
        self,
        *,
        source_site: str | None = None,
        company: str | None = None,
        remote_status: str | None = None,
        employment_type: str | None = None,
        seniority: str | None = None,
        location_contains: str | None = None,
        limit: int = 100,
    ) -> list[JobPosting]:
        """List jobs using simple equality and substring filters."""
        query = "SELECT * FROM jobs"
        clauses: list[str] = []
        params: list[Any] = []

        if source_site is not None:
            clauses.append("source_site = ?")
            params.append(source_site)
        if company is not None:
            clauses.append("company = ?")
            params.append(company)
        if remote_status is not None:
            clauses.append("remote_status = ?")
            params.append(remote_status)
        if employment_type is not None:
            clauses.append("employment_type = ?")
            params.append(employment_type)
        if seniority is not None:
            clauses.append("seniority = ?")
            params.append(seniority)
        if location_contains is not None:
            clauses.append("location LIKE ?")
            params.append(f"%{location_contains}%")

        if clauses:
            query = f"{query} WHERE {' AND '.join(clauses)}"

        query = f"{query} ORDER BY discovered_at DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = self._connection.execute(query, params).fetchall()
        return [self._row_to_job(row) for row in rows]

    def _job_to_row(self, job: JobPosting) -> dict[str, Any]:
        return {
            "source_site": job.source_site,
            "source_job_id": job.source_job_id,
            "url": job.url.unicode_string(),
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "remote_status": job.remote_status.value,
            "employment_type": job.employment_type.value,
            "seniority": job.seniority.value,
            "posted_at": self._serialize_datetime(job.posted_at),
            "discovered_at": self._serialize_datetime(job.discovered_at),
            "description_text": job.description_text,
            "metadata_json": json.dumps(job.metadata, ensure_ascii=True, sort_keys=True),
        }

    def _row_to_job(self, row: sqlite3.Row) -> JobPosting:
        return JobPosting.model_validate(
            {
                "source_site": row["source_site"],
                "source_job_id": row["source_job_id"],
                "url": row["url"],
                "title": row["title"],
                "company": row["company"],
                "location": row["location"],
                "remote_status": row["remote_status"],
                "employment_type": row["employment_type"],
                "seniority": row["seniority"],
                "posted_at": self._parse_datetime(row["posted_at"]),
                "discovered_at": self._parse_datetime(row["discovered_at"]),
                "description_text": row["description_text"],
                "metadata": json.loads(row["metadata_json"]),
            }
        )

    def _serialize_datetime(self, value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    def _parse_datetime(self, value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) if value is not None else None

