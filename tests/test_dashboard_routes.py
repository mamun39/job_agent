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
) -> JobPosting:
    metadata = {}
    if score is not None:
        metadata["score"] = score
    return repo.insert_job(
        JobPosting(
            source_site=source_site,
            source_job_id=url.rsplit("/", 1)[-1],
            url=url,
            title=title,
            company="Example Co",
            location="Toronto, ON",
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


def test_dashboard_returns_not_found_for_unknown_job(tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "dashboard.db"))
    client = TestClient(create_dashboard_app(db_path=tmp_path / "dashboard.db"))

    response = client.get("/jobs/999")

    assert response.status_code == 404
    assert "Job not found." in response.text
