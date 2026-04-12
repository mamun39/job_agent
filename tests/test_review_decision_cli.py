from __future__ import annotations

from job_agent.config import Settings
from job_agent.core.models import JobPosting
from job_agent.main import main
from job_agent.storage.db import init_db
from job_agent.storage.jobs_repo import JobsRepository


def _insert_job(repo: JobsRepository, *, url: str, title: str) -> JobPosting:
    return repo.insert_job(
        JobPosting(
            source_site="greenhouse",
            source_job_id=url.rsplit("/", 1)[-1],
            url=url,
            title=title,
            company="Example Co",
            location="Toronto, ON",
            description_text="Stored job for review decision CLI tests.",
        )
    )


def test_review_set_decision_by_id_persists_and_is_visible_in_show(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "review_decision_cli.db"
    repo = JobsRepository(init_db(db_path))
    job = _insert_job(repo, url="https://example.com/jobs/1", title="Job One")
    monkeypatch.setattr("job_agent.main.load_settings", lambda: Settings(db_path=db_path))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)

    exit_code = main(["review", "set-decision", "--id", str(job.metadata["db_id"]), "--decision", "saved"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Updated decision for https://example.com/jobs/1: saved" in captured.out

    exit_code = main(["review", "show", "--id", str(job.metadata["db_id"])])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Job ID: 1" in captured.out
    assert "Decision: saved" in captured.out
    assert "Decision History:" in captured.out


def test_review_set_decision_by_url_persists_note_and_view_command_returns_it(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "review_decision_cli.db"
    repo = JobsRepository(init_db(db_path))
    _insert_job(repo, url="https://example.com/jobs/2", title="Job Two")
    monkeypatch.setattr("job_agent.main.load_settings", lambda: Settings(db_path=db_path))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)

    exit_code = main(
        [
            "review",
            "set-decision",
            "--url",
            "https://example.com/jobs/2",
            "--decision",
            "needs_manual_review",
            "--note",
            "Check salary band.",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "needs_manual_review" in captured.out
    assert "note=Check salary band." in captured.out

    exit_code = main(["review", "decision", "--url", "https://example.com/jobs/2"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Decision: needs_manual_review" in captured.out
    assert "Note: Check salary band." in captured.out


def test_review_list_can_filter_by_decision(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "review_decision_cli.db"
    repo = JobsRepository(init_db(db_path))
    saved_job = _insert_job(repo, url="https://example.com/jobs/1", title="Saved Job")
    _insert_job(repo, url="https://example.com/jobs/2", title="Skipped Job")
    repo.set_review_decision(posting_url=saved_job.url.unicode_string(), decision="saved")
    repo.set_review_decision(posting_url="https://example.com/jobs/2", decision="skipped")
    monkeypatch.setattr("job_agent.main.load_settings", lambda: Settings(db_path=db_path))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)

    exit_code = main(["review", "list", "--decision", "saved"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Saved Job" in captured.out
    assert "score=n/a | status=active | saved" in captured.out
    assert "Skipped Job" not in captured.out


def test_review_decision_invalid_input_and_missing_job_errors_are_clear(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "review_decision_cli.db"
    repo = JobsRepository(init_db(db_path))
    _insert_job(repo, url="https://example.com/jobs/1", title="Job One")
    monkeypatch.setattr("job_agent.main.load_settings", lambda: Settings(db_path=db_path))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)

    exit_code = main(["review", "set-decision", "--id", "999", "--decision", "saved"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Job not found for id: 999" in captured.out

    exit_code = main(["review", "set-decision", "--url", "https://example.com/jobs/1", "--decision", "invalid"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Invalid review decision 'invalid'." in captured.out
    assert "saved, skipped, applied_elsewhere, needs_manual_review" in captured.out


def test_review_cleanup_removes_orphaned_review_decisions(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "review_decision_cli.db"
    repo = JobsRepository(init_db(db_path))
    job = _insert_job(repo, url="https://example.com/jobs/1", title="Job One")
    repo.set_review_decision(posting_url=job.url.unicode_string(), decision="saved")
    repo.set_review_decision(posting_url="https://example.com/jobs/orphan", decision="skipped")
    repo._connection.execute(
        """
        INSERT INTO review_decision_history (posting_url, decision, decided_at, note)
        VALUES (?, ?, ?, ?)
        """,
        ("https://example.com/jobs/orphan", "skipped", "2026-04-11T00:00:00+00:00", None),
    )
    repo._connection.execute("DELETE FROM jobs WHERE url = ?", ("https://example.com/jobs/1",))
    repo._connection.commit()
    monkeypatch.setattr("job_agent.main.load_settings", lambda: Settings(db_path=db_path))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)

    exit_code = main(["review", "cleanup"])
    captured = capsys.readouterr()

    remaining = repo._connection.execute("SELECT COUNT(*) FROM review_decisions").fetchone()[0]
    remaining_history = repo._connection.execute("SELECT COUNT(*) FROM review_decision_history").fetchone()[0]
    assert exit_code == 0
    assert "Removed 2 orphaned review decisions and 3 orphaned review history entries." in captured.out
    assert remaining == 0
    assert remaining_history == 0


def test_review_cleanup_reports_zero_when_no_orphans_exist(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "review_decision_cli.db"
    repo = JobsRepository(init_db(db_path))
    job = _insert_job(repo, url="https://example.com/jobs/1", title="Job One")
    repo.set_review_decision(posting_url=job.url.unicode_string(), decision="saved")
    monkeypatch.setattr("job_agent.main.load_settings", lambda: Settings(db_path=db_path))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)

    exit_code = main(["review", "cleanup"])
    captured = capsys.readouterr()

    remaining = repo._connection.execute("SELECT COUNT(*) FROM review_decisions").fetchone()[0]
    remaining_history = repo._connection.execute("SELECT COUNT(*) FROM review_decision_history").fetchone()[0]
    assert exit_code == 0
    assert "Removed 0 orphaned review decisions and 0 orphaned review history entries." in captured.out
    assert remaining == 1
    assert remaining_history == 1
