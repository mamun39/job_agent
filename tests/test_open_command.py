from __future__ import annotations

from job_agent.config import Settings
from job_agent.core.models import JobPosting
from job_agent.main import main
from job_agent.storage.db import init_db
from job_agent.storage.jobs_repo import JobsRepository


def _insert_job(repo: JobsRepository, *, url: str, title: str) -> None:
    repo.insert_job(
        JobPosting(
            source_site="greenhouse",
            source_job_id=url.rsplit("/", 1)[-1],
            url=url,
            title=title,
            company="Example Co",
            location="Toronto, ON",
            description_text="Job for open command tests.",
        )
    )


def test_open_command_opens_stored_job_by_id(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "open.db"
    repo = JobsRepository(init_db(db_path))
    _insert_job(repo, url="https://example.com/jobs/1", title="Open Me")
    monkeypatch.setattr("job_agent.main.load_settings", lambda: Settings(db_path=db_path))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)
    opened: list[str] = []
    monkeypatch.setattr("job_agent.ui.cli.webbrowser.open", lambda url: opened.append(url) or True)

    exit_code = main(["open", "--id", "1"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert opened == ["https://example.com/jobs/1"]
    assert "Opened https://example.com/jobs/1" in captured.out


def test_open_command_opens_stored_job_by_exact_url(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "open.db"
    repo = JobsRepository(init_db(db_path))
    _insert_job(repo, url="https://example.com/jobs/2", title="Open By URL")
    monkeypatch.setattr("job_agent.main.load_settings", lambda: Settings(db_path=db_path))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)
    opened: list[str] = []
    monkeypatch.setattr("job_agent.ui.cli.webbrowser.open", lambda url: opened.append(url) or True)

    exit_code = main(["open", "--url", "https://example.com/jobs/2"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert opened == ["https://example.com/jobs/2"]
    assert "Opened https://example.com/jobs/2" in captured.out


def test_open_command_reports_clear_validation_error_for_missing_url(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "open.db"
    init_db(db_path).close()
    monkeypatch.setattr("job_agent.main.load_settings", lambda: Settings(db_path=db_path))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)
    monkeypatch.setattr("job_agent.ui.cli.webbrowser.open", lambda url: True)

    exit_code = main(["open", "--id", "999"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "Job not found for id: 999" in captured.out
