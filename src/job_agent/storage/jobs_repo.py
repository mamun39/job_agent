"""Repository for storing and querying job postings."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import sqlite3
from typing import Any

from job_agent.core.models import JobPosting, JobStatus, ReviewDecision, ReviewStatus


class JobsRepository:
    """Repository for CRUD-style job posting persistence."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def initialize_schema(self) -> None:
        """Ensure the jobs table exists for the current connection."""
        from job_agent.storage.db import SCHEMA_STATEMENTS, _ensure_jobs_columns

        for statement in SCHEMA_STATEMENTS:
            self._connection.execute(statement)
        _ensure_jobs_columns(self._connection)
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
                job_status,
                posted_at,
                discovered_at,
                last_seen_at,
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
                :job_status,
                :posted_at,
                :discovered_at,
                :last_seen_at,
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
        stored, _ = self.upsert_job_with_status(job)
        return stored

    def upsert_job_with_status(self, job: JobPosting) -> tuple[JobPosting, bool]:
        """Insert or update a job posting and report whether it was newly inserted."""
        existing = self.fetch_by_url(job.url.unicode_string())
        if existing is None and job.source_job_id:
            existing = self.fetch_by_source_identity(job.source_site, job.source_job_id)

        if existing is None:
            return self.insert_job(job), True

        merged = self._merge_with_existing(existing, job)
        payload = self._job_to_row(merged)
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
                job_status = :job_status,
                posted_at = :posted_at,
                discovered_at = :discovered_at,
                last_seen_at = :last_seen_at,
                description_text = :description_text,
                metadata_json = :metadata_json,
                updated_at = CURRENT_TIMESTAMP
            WHERE url = :existing_url
            """,
            payload,
        )
        self._connection.commit()
        stored = self.fetch_by_url(merged.url.unicode_string())
        if stored is None:
            raise RuntimeError("upsert succeeded but job could not be reloaded")
        return stored, False

    def fetch_by_url(self, url: str) -> JobPosting | None:
        """Fetch a single job posting by canonical URL."""
        row = self._connection.execute(
            "SELECT * FROM jobs WHERE url = ?",
            (url,),
        ).fetchone()
        return self._row_to_job(row) if row else None

    def fetch_by_id(self, job_id: int) -> JobPosting | None:
        """Fetch a single job posting by database id."""
        row = self._connection.execute(
            "SELECT * FROM jobs WHERE id = ?",
            (job_id,),
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
        min_score: float | None = None,
        reviewed: bool | None = None,
        decision: ReviewStatus | str | None = None,
        job_status: JobStatus | str | None = None,
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
        if job_status is not None:
            normalized_status = job_status if isinstance(job_status, JobStatus) else JobStatus(job_status)
            clauses.append("job_status = ?")
            params.append(normalized_status.value)
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
        jobs = [self._row_to_job(row) for row in rows]
        return self._filter_review_fields(jobs, min_score=min_score, reviewed=reviewed, decision=decision)

    def fetch_for_review(self, *, job_id: int | None = None, url: str | None = None) -> JobPosting | None:
        """Fetch one stored job for CLI review output by id or exact URL."""
        if job_id is None and url is None:
            raise ValueError("Provide either --id or --url.")
        if job_id is not None and url is not None:
            raise ValueError("Provide only one of --id or --url.")
        if job_id is not None:
            return self.fetch_by_id(job_id)
        return self.fetch_by_url(str(url))

    def set_review_decision(
        self,
        *,
        posting_url: str,
        decision: ReviewStatus | str,
        note: str | None = None,
        decided_at: datetime | None = None,
    ) -> ReviewDecision:
        """Persist or update a review decision for a stored job."""
        normalized_decision = decision if isinstance(decision, ReviewStatus) else ReviewStatus(decision)
        timestamp = decided_at or datetime.now(UTC)
        payload = {
            "posting_url": posting_url,
            "decision": normalized_decision.value,
            "decided_at": self._serialize_datetime(timestamp),
            "note": note,
        }
        self._connection.execute(
            """
            INSERT INTO review_decisions (
                posting_url,
                decision,
                decided_at,
                note
            ) VALUES (
                :posting_url,
                :decision,
                :decided_at,
                :note
            )
            ON CONFLICT(posting_url) DO UPDATE SET
                decision = excluded.decision,
                decided_at = excluded.decided_at,
                note = excluded.note,
                updated_at = CURRENT_TIMESTAMP
            """,
            payload,
        )
        self._connection.commit()
        stored = self.get_review_decision(posting_url=posting_url)
        if stored is None:
            raise RuntimeError("review decision write succeeded but could not be reloaded")
        return stored

    def get_review_decision(self, *, posting_url: str) -> ReviewDecision | None:
        """Fetch the persisted review decision for a posting URL."""
        row = self._connection.execute(
            """
            SELECT posting_url, decision, decided_at, note
            FROM review_decisions
            WHERE posting_url = ?
            """,
            (posting_url,),
        ).fetchone()
        if row is None:
            return None
        return ReviewDecision.model_validate(
            {
                "posting_url": row["posting_url"],
                "decision": row["decision"],
                "decided_at": self._parse_datetime(row["decided_at"]),
                "note": row["note"],
            }
        )

    def get_review_decisions_by_url(self, posting_urls: Any) -> dict[str, ReviewDecision]:
        """Fetch persisted review decisions for a set of posting URLs."""
        urls = list(dict.fromkeys(str(url) for url in posting_urls))
        if not urls:
            return {}
        placeholders = ", ".join("?" for _ in urls)
        rows = self._connection.execute(
            f"""
            SELECT posting_url, decision, decided_at, note
            FROM review_decisions
            WHERE posting_url IN ({placeholders})
            """,
            urls,
        ).fetchall()
        return {
            str(row["posting_url"]): ReviewDecision.model_validate(
                {
                    "posting_url": row["posting_url"],
                    "decision": row["decision"],
                    "decided_at": self._parse_datetime(row["decided_at"]),
                    "note": row["note"],
                }
            )
            for row in rows
        }

    def update_job_score(
        self,
        *,
        posting_url: str,
        score: int,
        explanations: list[str],
    ) -> JobPosting:
        """Persist refreshed deterministic scoring fields for one stored job."""
        job = self.fetch_by_url(posting_url)
        if job is None:
            raise ValueError(f"Job not found for url: {posting_url}")

        metadata = dict(job.metadata)
        metadata["score"] = score
        metadata["score_explanations"] = list(explanations)
        payload = dict(self._job_to_row(job.model_copy(update={"metadata": metadata})))
        payload["posting_url"] = posting_url
        self._connection.execute(
            """
            UPDATE jobs
            SET
                metadata_json = :metadata_json,
                updated_at = CURRENT_TIMESTAMP
            WHERE url = :posting_url
            """,
            payload,
        )
        self._connection.commit()
        stored = self.fetch_by_url(posting_url)
        if stored is None:
            raise RuntimeError("score update succeeded but job could not be reloaded")
        return stored

    def update_job_status(self, *, posting_url: str, job_status: JobStatus | str) -> JobPosting:
        """Persist a refreshed job lifecycle status for one stored job."""
        normalized_status = job_status if isinstance(job_status, JobStatus) else JobStatus(job_status)
        self._connection.execute(
            """
            UPDATE jobs
            SET
                job_status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE url = ?
            """,
            (normalized_status.value, posting_url),
        )
        self._connection.commit()
        stored = self.fetch_by_url(posting_url)
        if stored is None:
            raise RuntimeError("job status update succeeded but job could not be reloaded")
        return stored

    def mark_stale_jobs(
        self,
        *,
        stale_threshold_days: int,
        source_site: str | None = None,
        reviewed: bool | None = None,
        decision: ReviewStatus | str | None = None,
        job_status: JobStatus | str | None = None,
        now: datetime | None = None,
        limit: int = 100000,
    ) -> int:
        """Mark active jobs stale when they have not been seen within the threshold."""
        if stale_threshold_days < 1:
            raise ValueError("stale_threshold_days must be at least 1")

        active_status = JobStatus.ACTIVE
        candidates = self.list_jobs(
            source_site=source_site,
            reviewed=reviewed,
            decision=decision,
            job_status=job_status or active_status,
            limit=limit,
        )
        threshold = (now or datetime.now(UTC)) - timedelta(days=stale_threshold_days)
        updated_count = 0
        for job in candidates:
            if job.job_status is JobStatus.ARCHIVED:
                continue
            if job.last_seen_at < threshold:
                self.update_job_status(posting_url=job.url.unicode_string(), job_status=JobStatus.STALE)
                updated_count += 1
        return updated_count

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
            "job_status": job.job_status.value,
            "posted_at": self._serialize_datetime(job.posted_at),
            "discovered_at": self._serialize_datetime(job.discovered_at),
            "last_seen_at": self._serialize_datetime(job.last_seen_at),
            "description_text": job.description_text,
            "metadata_json": json.dumps(job.metadata, ensure_ascii=True, sort_keys=True),
        }

    def _row_to_job(self, row: sqlite3.Row) -> JobPosting:
        metadata = json.loads(row["metadata_json"])
        metadata.setdefault("db_id", row["id"])
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
                "job_status": row["job_status"],
                "posted_at": self._parse_datetime(row["posted_at"]),
                "discovered_at": self._parse_datetime(row["discovered_at"]),
                "last_seen_at": self._parse_datetime(row["last_seen_at"]),
                "description_text": row["description_text"],
                "metadata": metadata,
            }
        )

    def _serialize_datetime(self, value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    def _parse_datetime(self, value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) if value is not None else None

    def _filter_review_fields(
        self,
        jobs: list[JobPosting],
        *,
        min_score: float | None,
        reviewed: bool | None,
        decision: ReviewStatus | str | None,
    ) -> list[JobPosting]:
        filtered = jobs
        if min_score is not None:
            filtered = [
                job
                for job in filtered
                if isinstance(job.metadata.get("score"), (int, float))
                and not isinstance(job.metadata.get("score"), bool)
                and float(job.metadata["score"]) >= min_score
            ]
        normalized_decision = None
        if decision is not None:
            normalized_decision = decision if isinstance(decision, ReviewStatus) else ReviewStatus(decision)
            filtered = [
                job
                for job in filtered
                if (review_decision := self.get_review_decision(posting_url=job.url.unicode_string())) is not None
                and review_decision.decision is normalized_decision
            ]
        if reviewed is not None:
            if reviewed:
                filtered = [
                    job
                    for job in filtered
                    if self.get_review_decision(posting_url=job.url.unicode_string()) is not None
                    or job.metadata.get("reviewed") is True
                ]
            else:
                filtered = [
                    job
                    for job in filtered
                    if self.get_review_decision(posting_url=job.url.unicode_string()) is None
                    and job.metadata.get("reviewed") is not True
                ]
        return filtered

    def _merge_with_existing(self, existing: JobPosting, incoming: JobPosting) -> JobPosting:
        metadata = dict(existing.metadata)
        metadata.update(incoming.metadata)

        return incoming.model_copy(
            update={
                "source_job_id": incoming.source_job_id or existing.source_job_id,
                "location": _prefer_text(incoming.location, existing.location),
                "remote_status": _prefer_enum(incoming.remote_status, existing.remote_status, unknown_value="unknown"),
                "employment_type": _prefer_enum(
                    incoming.employment_type,
                    existing.employment_type,
                    unknown_value="unknown",
                ),
                "seniority": _prefer_enum(incoming.seniority, existing.seniority, unknown_value="unknown"),
                "job_status": JobStatus.ACTIVE,
                "last_seen_at": incoming.last_seen_at if incoming.last_seen_at >= existing.last_seen_at else existing.last_seen_at,
                "description_text": _prefer_description(incoming.description_text, existing.description_text),
                "metadata": metadata,
            }
        )


def _prefer_text(incoming: str, existing: str) -> str:
    if _is_unknown_text(incoming):
        return existing
    return incoming


def _prefer_enum(incoming: Any, existing: Any, *, unknown_value: str) -> Any:
    if getattr(incoming, "value", None) == unknown_value:
        return existing
    return incoming


def _prefer_description(incoming: str, existing: str) -> str:
    if incoming.startswith("Listing-only discovery from ") and existing and not existing.startswith("Listing-only discovery from "):
        return existing
    return incoming


def _is_unknown_text(value: str) -> bool:
    normalized = value.strip().casefold()
    return normalized in {"unknown location", "unknown company", "unknown title"}
