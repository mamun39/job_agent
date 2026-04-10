from __future__ import annotations

from pathlib import Path

from job_agent.config import Settings
from job_agent.core.models import JobPosting
from job_agent.main import main
from job_agent.storage.db import init_db
from job_agent.storage.jobs_repo import JobsRepository


def _insert_job(
    repo: JobsRepository,
    *,
    url: str,
    source_site: str,
    title: str,
    score: int | None,
    reviewed: bool | None,
) -> None:
    metadata = {}
    if score is not None:
        metadata["score"] = score
    if reviewed is not None:
        metadata["reviewed"] = reviewed
    repo.insert_job(
        JobPosting(
            source_site=source_site,
            source_job_id=url.rsplit("/", 1)[-1],
            url=url,
            title=title,
            company="Example Co",
            location="Toronto, ON",
            description_text="Stored job for review tests.",
            metadata=metadata,
        )
    )


def test_review_list_filters_by_source_score_and_review_state(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "review.db"
    repo = JobsRepository(init_db(db_path))
    _insert_job(repo, url="https://example.com/jobs/1", source_site="greenhouse", title="Job One", score=80, reviewed=True)
    _insert_job(repo, url="https://example.com/jobs/2", source_site="greenhouse", title="Job Two", score=40, reviewed=False)
    _insert_job(repo, url="https://example.com/jobs/3", source_site="lever", title="Job Three", score=90, reviewed=True)
    monkeypatch.setattr("job_agent.main.load_settings", lambda: Settings(db_path=db_path))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)

    exit_code = main(["review", "list", "--source-site", "greenhouse", "--min-score", "60", "--reviewed", "reviewed"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Job One" in captured.out
    assert "Job Two" not in captured.out
    assert "Job Three" not in captured.out


def test_review_show_renders_single_job_detail(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "review.db"
    repo = JobsRepository(init_db(db_path))
    _insert_job(repo, url="https://example.com/jobs/1", source_site="greenhouse", title="Job One", score=80, reviewed=True)
    monkeypatch.setattr("job_agent.main.load_settings", lambda: Settings(db_path=db_path))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)

    exit_code = main(["review", "show", "--url", "https://example.com/jobs/1"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Title: Job One" in captured.out
    assert "Reviewed: yes" in captured.out


def test_review_export_writes_filtered_csv(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "review.db"
    export_path = tmp_path / "exports" / "jobs.csv"
    repo = JobsRepository(init_db(db_path))
    _insert_job(repo, url="https://example.com/jobs/1", source_site="greenhouse", title="Job One", score=80, reviewed=True)
    _insert_job(repo, url="https://example.com/jobs/2", source_site="greenhouse", title="Job Two", score=20, reviewed=False)
    monkeypatch.setattr("job_agent.main.load_settings", lambda: Settings(db_path=db_path))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)

    exit_code = main(["review", "export", "--min-score", "50", "--output", str(export_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert f"Exported 1 jobs to {export_path}" in captured.out
    content = export_path.read_text(encoding="utf-8")
    assert "Job One" in content
    assert "Job Two" not in content
