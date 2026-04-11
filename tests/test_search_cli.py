from __future__ import annotations

from datetime import UTC, datetime

from job_agent.config import Settings
from job_agent.core.models import JobPosting, PromptSearchResult, RejectedJobMatch, SearchIntent, SearchPlan
from job_agent.main import main
from job_agent.storage.db import init_db
from job_agent.storage.jobs_repo import JobsRepository


class _FakeSession:
    def close(self) -> None:
        return None


def _matched_job(*, url: str = "https://boards.greenhouse.io/example/jobs/1") -> JobPosting:
    return JobPosting(
        source_site="greenhouse",
        source_job_id=url.rsplit("/", 1)[-1],
        url=url,
        title="AI Security Engineer",
        company="Example Co",
        location="Remote - Canada",
        remote_status="remote",
        discovered_at=datetime(2026, 4, 11, tzinfo=UTC),
        last_seen_at=datetime(2026, 4, 11, tzinfo=UTC),
        description_text="Build AI security tooling.",
    )


def _prompt_result(*, matched_jobs: list[JobPosting], rejected_jobs: list[RejectedJobMatch]) -> PromptSearchResult:
    intent = SearchIntent(
        prompt_text="Find AI security roles in Canada",
        constraints={
            "target_titles": ["AI Security Engineer"],
            "location_constraints": ["Canada"],
            "include_keywords": ["security"],
        },
    )
    plan = SearchPlan(
        intent=intent,
        constraints=intent.constraints,
        queries=[
            {
                "source_site": "greenhouse",
                "label": "Greenhouse Example AI Security Engineer",
                "company_name": "Example Co",
                "board_url": "https://boards.greenhouse.io/example",
                "target_titles": ["AI Security Engineer"],
                "location_constraints": ["Canada"],
                "include_keywords": ["security"],
                "notes": ["Resolved board seed for Example Co: https://boards.greenhouse.io/example"],
            }
        ],
        notes=["Board seed URLs were selected from the local registry using explicit intent constraints only."],
    )
    return PromptSearchResult(
        intent=intent,
        plan=plan,
        discovered_jobs_count=len(matched_jobs) + len(rejected_jobs),
        matched_jobs=matched_jobs,
        rejected_jobs=rejected_jobs,
    )


def test_search_command_accepts_inline_prompt_and_shows_summary(monkeypatch, tmp_path, capsys) -> None:
    db_path = tmp_path / "search.db"
    monkeypatch.setattr("job_agent.main.load_settings", lambda: Settings(db_path=db_path))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)
    monkeypatch.setattr("job_agent.main.BrowserSessionManager.from_settings", lambda settings: _FakeSession())
    monkeypatch.setattr(
        "job_agent.main.run_prompt_search",
        lambda **kwargs: _prompt_result(matched_jobs=[_matched_job()], rejected_jobs=[]),
    )

    exit_code = main(["search", "Find AI security roles in Canada"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Intent: titles=AI Security Engineer | include=security | locations=Canada" in captured.out
    assert "Summary: boards=1 discovered=1 matched=1 rejected=0" in captured.out
    assert "AI Security Engineer | Example Co | Remote - Canada" in captured.out


def test_search_command_accepts_prompt_file_and_can_show_rejections(monkeypatch, tmp_path, capsys) -> None:
    db_path = tmp_path / "search.db"
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("Find AI security roles in Canada", encoding="utf-8")
    captured_prompt: dict[str, str] = {}

    def fake_run_prompt_search(**kwargs):
        captured_prompt["prompt_text"] = kwargs["prompt_text"]
        rejected = RejectedJobMatch(
            job=_matched_job(url="https://boards.greenhouse.io/example/jobs/2"),
            rejection_reasons=["Excluded keyword 'crypto' matched description"],
        )
        return _prompt_result(matched_jobs=[], rejected_jobs=[rejected])

    monkeypatch.setattr("job_agent.main.load_settings", lambda: Settings(db_path=db_path))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)
    monkeypatch.setattr("job_agent.main.BrowserSessionManager.from_settings", lambda settings: _FakeSession())
    monkeypatch.setattr("job_agent.main.run_prompt_search", fake_run_prompt_search)

    exit_code = main(["search", "--prompt-file", str(prompt_path), "--show-rejected"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured_prompt["prompt_text"] == "Find AI security roles in Canada"
    assert "Summary: boards=1 discovered=1 matched=0 rejected=1" in captured.out
    assert "Rejected Jobs:" in captured.out
    assert "Excluded keyword 'crypto' matched description" in captured.out


def test_search_command_can_store_new_matches(monkeypatch, tmp_path, capsys) -> None:
    db_path = tmp_path / "search.db"
    repo = JobsRepository(init_db(db_path))
    stored_job = _matched_job(url="https://boards.greenhouse.io/example/jobs/1")
    repo.insert_job(stored_job)
    new_job = _matched_job(url="https://boards.greenhouse.io/example/jobs/2")

    monkeypatch.setattr("job_agent.main.load_settings", lambda: Settings(db_path=db_path))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)
    monkeypatch.setattr("job_agent.main.BrowserSessionManager.from_settings", lambda settings: _FakeSession())
    monkeypatch.setattr(
        "job_agent.main.run_prompt_search",
        lambda **kwargs: _prompt_result(matched_jobs=[stored_job, new_job], rejected_jobs=[]),
    )

    exit_code = main(["search", "Find AI security roles in Canada", "--store-matches"])
    captured = capsys.readouterr()

    stored_urls = {job.url.unicode_string() for job in repo.list_jobs(limit=10)}
    assert exit_code == 0
    assert "Stored 1 new matched jobs out of 2 matched." in captured.out
    assert stored_urls == {
        "https://boards.greenhouse.io/example/jobs/1",
        "https://boards.greenhouse.io/example/jobs/2",
    }
