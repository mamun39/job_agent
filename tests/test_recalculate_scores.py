from __future__ import annotations

from job_agent.config import Settings
from job_agent.core.models import JobPosting, ReviewStatus
from job_agent.main import main
from job_agent.storage.db import init_db
from job_agent.storage.jobs_repo import JobsRepository


def _insert_job(
    repo: JobsRepository,
    *,
    url: str,
    source_site: str,
    title: str,
    reviewed: bool | None = None,
) -> JobPosting:
    metadata: dict[str, object] = {"score": 1, "score_explanations": ["old explanation"]}
    if reviewed is not None:
        metadata["reviewed"] = reviewed
    return repo.insert_job(
        JobPosting(
            source_site=source_site,
            source_job_id=url.rsplit("/", 1)[-1],
            url=url,
            title=title,
            company="Example Co",
            location="Remote - Canada",
            description_text="Stored job for rescoring tests.",
            metadata=metadata,
        )
    )


def test_review_rescore_updates_stored_scores_and_explanations(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "rescore.db"
    repo = JobsRepository(init_db(db_path))
    _insert_job(repo, url="https://example.com/jobs/1", source_site="greenhouse", title="Senior Python Engineer")
    monkeypatch.setattr("job_agent.main.load_settings", lambda: Settings(db_path=db_path))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)
    monkeypatch.setattr(
        "job_agent.main.rescore_job_posting",
        lambda job, criteria=None: type("Result", (), {"score": 42, "explanations": ["new explanation"]})(),
    )

    exit_code = main(["review", "rescore"])
    captured = capsys.readouterr()

    stored = repo.fetch_by_url("https://example.com/jobs/1")
    assert exit_code == 0
    assert "Rescored 1 jobs." in captured.out
    assert stored is not None
    assert stored.metadata["score"] == 42
    assert stored.metadata["score_explanations"] == ["new explanation"]


def test_review_rescore_honors_filters(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "rescore.db"
    repo = JobsRepository(init_db(db_path))
    saved_job = _insert_job(
        repo,
        url="https://example.com/jobs/1",
        source_site="greenhouse",
        title="Senior Python Engineer",
        reviewed=True,
    )
    skipped_job = _insert_job(
        repo,
        url="https://example.com/jobs/2",
        source_site="lever",
        title="Product Designer",
        reviewed=False,
    )
    repo.set_review_decision(posting_url=saved_job.url.unicode_string(), decision=ReviewStatus.SAVED)
    repo.set_review_decision(posting_url=skipped_job.url.unicode_string(), decision=ReviewStatus.SKIPPED)
    monkeypatch.setattr("job_agent.main.load_settings", lambda: Settings(db_path=db_path))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)
    monkeypatch.setattr(
        "job_agent.main.rescore_job_posting",
        lambda job, criteria=None: type("Result", (), {"score": 77, "explanations": [f"rescored {job.source_site}"]})(),
    )

    exit_code = main(["review", "rescore", "--source-site", "greenhouse", "--reviewed", "reviewed", "--decision", "saved"])
    captured = capsys.readouterr()

    rescored_saved = repo.fetch_by_url(saved_job.url.unicode_string())
    rescored_skipped = repo.fetch_by_url(skipped_job.url.unicode_string())
    assert exit_code == 0
    assert "Rescored 1 jobs." in captured.out
    assert rescored_saved is not None
    assert rescored_saved.metadata["score"] == 77
    assert rescored_saved.metadata["score_explanations"] == ["rescored greenhouse"]
    assert rescored_skipped is not None
    assert rescored_skipped.metadata["score"] == 1
    assert rescored_skipped.metadata["score_explanations"] == ["old explanation"]


def test_review_rescore_reflects_current_rule_changes(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "rescore.db"
    repo = JobsRepository(init_db(db_path))
    _insert_job(repo, url="https://example.com/jobs/1", source_site="greenhouse", title="Senior Python Engineer")
    monkeypatch.setattr("job_agent.main.load_settings", lambda: Settings(db_path=db_path))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)

    first_scores = iter(
        [
            type("Result", (), {"score": 10, "explanations": ["rule set one"]})(),
            type("Result", (), {"score": 25, "explanations": ["rule set two"]})(),
        ]
    )
    monkeypatch.setattr("job_agent.main.rescore_job_posting", lambda job, criteria=None: next(first_scores))

    first_exit_code = main(["review", "rescore"])
    first_job = repo.fetch_by_url("https://example.com/jobs/1")
    second_exit_code = main(["review", "rescore"])
    second_job = repo.fetch_by_url("https://example.com/jobs/1")
    capsys.readouterr()

    assert first_exit_code == 0
    assert second_exit_code == 0
    assert first_job is not None
    assert second_job is not None
    assert first_job.metadata["score"] == 10
    assert second_job.metadata["score"] == 25
    assert second_job.metadata["score_explanations"] == ["rule set two"]


def test_review_rescore_uses_active_configured_scoring_rules(tmp_path, monkeypatch, capsys) -> None:
    from job_agent.core.models import ScoringRuleSet

    db_path = tmp_path / "rescore.db"
    repo = JobsRepository(init_db(db_path))
    _insert_job(repo, url="https://example.com/jobs/1", source_site="greenhouse", title="Senior Python Engineer")
    settings = Settings(
        db_path=db_path,
        scoring_rules=ScoringRuleSet(
            include_keywords=["python"],
            preferred_companies=["Example Co"],
            preferred_remote_statuses=["remote"],
        ),
    )
    monkeypatch.setattr("job_agent.main.load_settings", lambda: settings)
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)

    exit_code = main(["review", "rescore"])
    captured = capsys.readouterr()
    stored = repo.fetch_by_url("https://example.com/jobs/1")

    assert exit_code == 0
    assert "Rescored 1 jobs." in captured.out
    assert stored is not None
    assert stored.metadata["score"] > 0
    explanations = stored.metadata["score_explanations"]
    assert any("title matched include keyword 'python'" in item for item in explanations)
    assert any("company matched include keyword 'example co'" in item for item in explanations)
