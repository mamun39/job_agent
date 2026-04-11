from __future__ import annotations

from datetime import UTC, datetime, timedelta

from job_agent.config import Settings
from job_agent.core.models import JobPosting, JobStatus
from job_agent.main import main
from job_agent.storage.db import init_db
from job_agent.storage.jobs_repo import JobsRepository


def _insert_job(
    repo: JobsRepository,
    *,
    url: str,
    title: str,
    source_site: str = "greenhouse",
    job_status: JobStatus = JobStatus.ACTIVE,
    last_seen_at: datetime | None = None,
) -> JobPosting:
    timestamp = last_seen_at or datetime.now(UTC)
    return repo.insert_job(
        JobPosting(
            source_site=source_site,
            source_job_id=url.rsplit("/", 1)[-1],
            url=url,
            title=title,
            company="Example Co",
            location="Toronto, ON",
            description_text="Stored job for stale job tests.",
            discovered_at=timestamp,
            last_seen_at=timestamp,
            job_status=job_status,
        )
    )


def test_mark_stale_jobs_applies_threshold_and_persists_status(tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "stale.db"))
    now = datetime(2026, 4, 10, tzinfo=UTC)
    old_job = _insert_job(
        repo,
        url="https://example.com/jobs/1",
        title="Old Job",
        last_seen_at=now - timedelta(days=10),
    )
    fresh_job = _insert_job(
        repo,
        url="https://example.com/jobs/2",
        title="Fresh Job",
        last_seen_at=now - timedelta(days=2),
    )

    stale_count = repo.mark_stale_jobs(stale_threshold_days=7, now=now)

    stale_old = repo.fetch_by_url(old_job.url.unicode_string())
    stale_fresh = repo.fetch_by_url(fresh_job.url.unicode_string())
    assert stale_count == 1
    assert stale_old is not None
    assert stale_fresh is not None
    assert stale_old.job_status is JobStatus.STALE
    assert stale_fresh.job_status is JobStatus.ACTIVE


def test_upsert_reactivates_stale_job_when_seen_again(tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "stale.db"))
    old_timestamp = datetime(2026, 4, 1, tzinfo=UTC)
    stale_job = _insert_job(
        repo,
        url="https://example.com/jobs/1",
        title="Old Job",
        job_status=JobStatus.STALE,
        last_seen_at=old_timestamp,
    )

    refreshed = repo.upsert_job(
        stale_job.model_copy(
            update={
                "last_seen_at": datetime(2026, 4, 10, tzinfo=UTC),
                "discovered_at": datetime(2026, 4, 10, tzinfo=UTC),
            }
        )
    )

    assert refreshed.job_status is JobStatus.ACTIVE
    assert refreshed.last_seen_at == datetime(2026, 4, 10, tzinfo=UTC)


def test_review_list_filters_by_job_status(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "stale.db"
    repo = JobsRepository(init_db(db_path))
    _insert_job(repo, url="https://example.com/jobs/1", title="Active Job", job_status=JobStatus.ACTIVE)
    _insert_job(repo, url="https://example.com/jobs/2", title="Stale Job", job_status=JobStatus.STALE)
    _insert_job(repo, url="https://example.com/jobs/3", title="Archived Job", job_status=JobStatus.ARCHIVED)
    monkeypatch.setattr("job_agent.main.load_settings", lambda: Settings(db_path=db_path))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)

    exit_code = main(["review", "list", "--job-status", "stale"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Stale Job" in captured.out
    assert "status=stale" in captured.out
    assert "Active Job" not in captured.out
    assert "Archived Job" not in captured.out


def test_review_mark_stale_command_uses_threshold_and_filters(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "stale.db"
    repo = JobsRepository(init_db(db_path))
    now = datetime(2026, 4, 10, tzinfo=UTC)
    _insert_job(
        repo,
        url="https://example.com/jobs/1",
        title="Greenhouse Old",
        source_site="greenhouse",
        last_seen_at=now - timedelta(days=8),
    )
    _insert_job(
        repo,
        url="https://example.com/jobs/2",
        title="Lever Old",
        source_site="lever",
        last_seen_at=now - timedelta(days=8),
    )
    monkeypatch.setattr("job_agent.main.load_settings", lambda: Settings(db_path=db_path))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)

    class _FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now if tz is not None else now.replace(tzinfo=None)

    monkeypatch.setattr("job_agent.main.datetime", _FixedDateTime)

    exit_code = main(["review", "mark-stale", "--days", "7", "--source-site", "greenhouse"])
    captured = capsys.readouterr()

    greenhouse_job = repo.fetch_by_source_identity("greenhouse", "1")
    lever_job = repo.fetch_by_source_identity("lever", "2")
    assert exit_code == 0
    assert "Marked 1 jobs stale using threshold=7 days." in captured.out
    assert greenhouse_job is not None
    assert lever_job is not None
    assert greenhouse_job.job_status is JobStatus.STALE
    assert lever_job.job_status is JobStatus.ACTIVE
