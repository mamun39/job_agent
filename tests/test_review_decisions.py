from __future__ import annotations

from job_agent.core.models import JobPosting, ReviewStatus
from job_agent.storage.db import init_db
from job_agent.storage.jobs_repo import JobsRepository
from job_agent.ui.cli import format_review_update_result, render_job_detail, render_review_decision


def _insert_job(repo: JobsRepository, url: str) -> JobPosting:
    return repo.insert_job(
        JobPosting(
            source_site="greenhouse",
            source_job_id=url.rsplit("/", 1)[-1],
            url=url,
            title="Review Target",
            company="Example Co",
            location="Toronto, ON",
            description_text="Job used for review decision tests.",
        )
    )


def test_review_decision_persists_and_is_retrievable(tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "review_decisions.db"))
    job = _insert_job(repo, "https://example.com/jobs/1")

    stored = repo.set_review_decision(
        posting_url=job.url.unicode_string(),
        decision=ReviewStatus.SAVED,
        note="Strong match for current search.",
    )
    fetched = repo.get_review_decision(posting_url=job.url.unicode_string())

    assert stored.decision is ReviewStatus.SAVED
    assert stored.note == "Strong match for current search."
    assert fetched is not None
    assert fetched.decision is ReviewStatus.SAVED
    assert fetched.note == "Strong match for current search."


def test_review_decision_writes_append_history_entries(tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "review_decisions.db"))
    job = _insert_job(repo, "https://example.com/jobs/1")

    repo.set_review_decision(posting_url=job.url.unicode_string(), decision=ReviewStatus.SAVED, note="first")
    repo.set_review_decision(posting_url=job.url.unicode_string(), decision=ReviewStatus.SKIPPED, note="second")
    history = repo.get_review_decision_history(posting_url=job.url.unicode_string())

    assert [entry.decision for entry in history] == [ReviewStatus.SKIPPED, ReviewStatus.SAVED]
    assert [entry.note for entry in history] == ["second", "first"]


def test_list_jobs_can_filter_by_decision_status(tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "review_decisions.db"))
    saved_job = _insert_job(repo, "https://example.com/jobs/1")
    skipped_job = _insert_job(repo, "https://example.com/jobs/2")
    unreviewed_job = _insert_job(repo, "https://example.com/jobs/3")

    repo.set_review_decision(posting_url=saved_job.url.unicode_string(), decision=ReviewStatus.SAVED)
    repo.set_review_decision(posting_url=skipped_job.url.unicode_string(), decision=ReviewStatus.SKIPPED)

    saved_jobs = repo.list_jobs(decision=ReviewStatus.SAVED)
    reviewed_jobs = repo.list_jobs(reviewed=True)
    unreviewed_jobs = repo.list_jobs(reviewed=False)

    assert [job.url.unicode_string() for job in saved_jobs] == [saved_job.url.unicode_string()]
    assert sorted(job.url.unicode_string() for job in reviewed_jobs) == sorted(
        [saved_job.url.unicode_string(), skipped_job.url.unicode_string()]
    )
    assert [job.url.unicode_string() for job in unreviewed_jobs] == [unreviewed_job.url.unicode_string()]


def test_reviewed_filter_ignores_legacy_metadata_only_review_flag(tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "review_decisions.db"))
    legacy_job = repo.insert_job(
        JobPosting(
            source_site="greenhouse",
            source_job_id="legacy",
            url="https://example.com/jobs/legacy",
            title="Legacy Review Flag",
            company="Example Co",
            location="Toronto, ON",
            description_text="Legacy metadata reviewed flag only.",
            metadata={"reviewed": True},
        )
    )

    reviewed_jobs = repo.list_jobs(reviewed=True)
    unreviewed_jobs = repo.list_jobs(reviewed=False)

    assert reviewed_jobs == []
    assert [job.url.unicode_string() for job in unreviewed_jobs] == [legacy_job.url.unicode_string()]


def test_review_cli_renderers_show_persisted_decision_and_note(tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "review_decisions.db"))
    job = _insert_job(repo, "https://example.com/jobs/1")
    decision = repo.set_review_decision(
        posting_url=job.url.unicode_string(),
        decision=ReviewStatus.NEEDS_MANUAL_REVIEW,
        note="Check compensation details manually.",
    )

    history = repo.get_review_decision_history(posting_url=job.url.unicode_string())
    detail = render_job_detail(job, decision=decision, decision_history=history)
    decision_text = render_review_decision(decision)
    confirmation = format_review_update_result(decision)

    assert "Decision: needs_manual_review" in detail
    assert "Decision Note: Check compensation details manually." in detail
    assert "Decision History:" in detail
    assert "Decision: needs_manual_review" in decision_text
    assert "Updated decision for https://example.com/jobs/1: needs_manual_review" in confirmation
