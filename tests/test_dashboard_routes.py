from __future__ import annotations

from fastapi.testclient import TestClient

from job_agent.core.models import JobPosting
from job_agent.storage.db import init_db
from job_agent.storage.jobs_repo import JobsRepository
from job_agent.ui.dashboard import create_dashboard_app


def _insert_job(
    repo: JobsRepository,
    *,
    url: str,
    title: str,
    source_site: str = "greenhouse",
    score: int | None = None,
    company: str = "Example Co",
    location: str = "Toronto, ON",
    score_explanations: list[str] | None = None,
) -> JobPosting:
    metadata = {}
    if score is not None:
        metadata["score"] = score
    if score_explanations is not None:
        metadata["score_explanations"] = score_explanations
    return repo.insert_job(
        JobPosting(
            source_site=source_site,
            source_job_id=url.rsplit("/", 1)[-1],
            url=url,
            title=title,
            company=company,
            location=location,
            description_text="Stored job for dashboard tests.",
            metadata=metadata,
        )
    )


def test_dashboard_lists_and_filters_jobs(tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "dashboard.db"))
    _insert_job(repo, url="https://example.com/jobs/1", title="Backend Engineer", source_site="greenhouse", score=90)
    _insert_job(repo, url="https://example.com/jobs/2", title="Designer", source_site="lever", score=20)
    client = TestClient(create_dashboard_app(db_path=tmp_path / "dashboard.db"))

    response = client.get("/jobs", params={"source_site": "greenhouse", "min_score": "50"})

    assert response.status_code == 200
    assert "Backend Engineer" in response.text
    assert "Designer" not in response.text
    assert "Apply Filters" in response.text


def test_dashboard_ignores_empty_min_score_filter(tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "dashboard.db"))
    _insert_job(repo, url="https://example.com/jobs/1", title="Backend Engineer", score=90)
    client = TestClient(create_dashboard_app(db_path=tmp_path / "dashboard.db"))

    response = client.get("/jobs", params={"min_score": ""})

    assert response.status_code == 200
    assert "Backend Engineer" in response.text


def test_dashboard_shows_friendly_error_for_invalid_min_score(tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "dashboard.db"))
    _insert_job(repo, url="https://example.com/jobs/1", title="Backend Engineer", score=90)
    client = TestClient(create_dashboard_app(db_path=tmp_path / "dashboard.db"))

    response = client.get("/jobs", params={"min_score": "not-a-number"})

    assert response.status_code == 200
    assert "Min Score must be a valid number." in response.text
    assert "Backend Engineer" in response.text


def test_dashboard_supports_pagination(tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "dashboard.db"))
    for index in range(1, 4):
        _insert_job(repo, url=f"https://example.com/jobs/{index}", title=f"Job {index}")
    client = TestClient(create_dashboard_app(db_path=tmp_path / "dashboard.db"))

    first_page = client.get("/jobs", params={"per_page": "2", "page": "1", "sort_by": "title", "sort_dir": "asc"})
    second_page = client.get("/jobs", params={"per_page": "2", "page": "2", "sort_by": "title", "sort_dir": "asc"})

    assert first_page.status_code == 200
    assert "Job 1" in first_page.text
    assert "Job 2" in first_page.text
    assert "Job 3" not in first_page.text
    assert "Page 1 of 2" in first_page.text
    assert second_page.status_code == 200
    assert "Job 3" in second_page.text
    assert "Page 2 of 2" in second_page.text


def test_dashboard_supports_sorting_by_score(tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "dashboard.db"))
    _insert_job(repo, url="https://example.com/jobs/1", title="Lower", score=10)
    _insert_job(repo, url="https://example.com/jobs/2", title="Higher", score=90)
    client = TestClient(create_dashboard_app(db_path=tmp_path / "dashboard.db"))

    response = client.get("/jobs", params={"sort_by": "score", "sort_dir": "desc"})

    assert response.status_code == 200
    assert response.text.index("Higher") < response.text.index("Lower")


def test_dashboard_detail_shows_score_explanations(tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "dashboard.db"))
    job = _insert_job(
        repo,
        url="https://example.com/jobs/1",
        title="Backend Engineer",
        score=90,
        score_explanations=["+15 title matched include keyword 'backend'"],
    )
    client = TestClient(create_dashboard_app(db_path=tmp_path / "dashboard.db"))

    response = client.get(f"/jobs/{job.metadata['db_id']}")

    assert response.status_code == 200
    assert "Score Explanations" in response.text
    assert "+15 title matched include keyword &#39;backend&#39;" in response.text


def test_dashboard_shows_job_detail_and_updates_review_decision(tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "dashboard.db"))
    job = _insert_job(repo, url="https://example.com/jobs/1", title="Backend Engineer")
    job_id = int(job.metadata["db_id"])
    client = TestClient(create_dashboard_app(db_path=tmp_path / "dashboard.db"))

    detail_response = client.get(f"/jobs/{job_id}")

    assert detail_response.status_code == 200
    assert "Backend Engineer" in detail_response.text
    assert "Save Review Decision" in detail_response.text

    post_response = client.post(
        f"/jobs/{job_id}/decision",
        data={"decision": "saved", "note": "Strong local match."},
        follow_redirects=False,
    )

    assert post_response.status_code == 303
    assert post_response.headers["location"] == f"/jobs/{job_id}?updated=1"
    stored = repo.get_review_decision(posting_url=job.url.unicode_string())
    assert stored is not None
    assert stored.decision.value == "saved"
    assert stored.note == "Strong local match."


def test_dashboard_quick_review_action_redirects_back_to_list(tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "dashboard.db"))
    job = _insert_job(repo, url="https://example.com/jobs/1", title="Backend Engineer")
    job_id = int(job.metadata["db_id"])
    client = TestClient(create_dashboard_app(db_path=tmp_path / "dashboard.db"))

    post_response = client.post(
        f"/jobs/{job_id}/decision",
        data={"decision": "skipped", "redirect_to": "/jobs?page=2"},
        follow_redirects=False,
    )

    assert post_response.status_code == 303
    assert post_response.headers["location"] == "/jobs?page=2&updated=1"
    stored = repo.get_review_decision(posting_url=job.url.unicode_string())
    assert stored is not None
    assert stored.decision.value == "skipped"
    assert stored.note is None


def test_dashboard_detail_shows_review_history_from_persisted_decisions(tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "dashboard.db"))
    job = _insert_job(repo, url="https://example.com/jobs/1", title="Backend Engineer")
    repo.set_review_decision(posting_url=job.url.unicode_string(), decision="saved", note="first")
    repo.set_review_decision(posting_url=job.url.unicode_string(), decision="needs_manual_review", note="second")
    client = TestClient(create_dashboard_app(db_path=tmp_path / "dashboard.db"))

    response = client.get(f"/jobs/{job.metadata['db_id']}")

    assert response.status_code == 200
    assert "Review History" in response.text
    assert "needs_manual_review" in response.text
    assert "saved" in response.text


def test_dashboard_returns_not_found_for_unknown_job(tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "dashboard.db"))
    client = TestClient(create_dashboard_app(db_path=tmp_path / "dashboard.db"))

    response = client.get("/jobs/999")

    assert response.status_code == 404
    assert "Job not found." in response.text
