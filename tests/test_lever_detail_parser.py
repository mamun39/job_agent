from __future__ import annotations

from pathlib import Path

from job_agent.core.models import DiscoveryOptions, DiscoveryQuery, EmploymentType, RemoteStatus
from job_agent.flows.discover import run_discovery_query
from job_agent.sites.lever import LeverAdapter
from job_agent.storage.db import init_db
from job_agent.storage.jobs_repo import JobsRepository


class _FakeSession:
    def close(self) -> None:
        return None


def test_lever_adapter_parses_detail_fixture_into_enriched_job_fields() -> None:
    html = Path("tests/fixtures/lever_job_detail_sample.html").read_text(encoding="utf-8")
    adapter = LeverAdapter(board_url="https://jobs.lever.co/exampleco")

    detail = adapter.parse_job_detail(url="https://jobs.lever.co/exampleco/abc123", html=html)

    assert detail.posting.title == "Senior Backend Engineer"
    assert detail.posting.company == "Example Co"
    assert detail.posting.location == "Toronto, ON"
    assert detail.posting.employment_type is EmploymentType.FULL_TIME
    assert detail.posting.remote_status is RemoteStatus.REMOTE
    assert detail.posting.metadata["team"] == "Platform Engineering"
    assert detail.posting.metadata["employment_type_text"] == "Full-time"
    assert "Build backend services used across the product." in detail.posting.description_text
    assert "Design APIs" in detail.posting.description_text


def test_lever_discovery_detail_enrichment_updates_stored_job_when_enabled(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "lever_detail.db"
    repo = JobsRepository(init_db(db_path))
    query = DiscoveryQuery(
        source_site="lever",
        label="Example engineering",
        start_url="https://jobs.lever.co/exampleco",
    )
    listing_html = Path("tests/fixtures/lever_jobs_sample.html").read_text(encoding="utf-8")
    detail_html = Path("tests/fixtures/lever_job_detail_sample.html").read_text(encoding="utf-8")

    pages = {
        "https://jobs.lever.co/exampleco": listing_html,
        "https://jobs.lever.co/exampleco/abc123": detail_html,
        "https://jobs.lever.co/exampleco/xyz789": RuntimeError("detail fetch failed"),
    }

    def fake_fetch(*, session, url, screenshot_name=None, wait_until="networkidle", wait_delay_ms=0):  # noqa: ARG001
        response = pages[url]
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr("job_agent.flows.discover.fetch_listing_page_html", fake_fetch)

    result = run_discovery_query(
        query=query,
        session=_FakeSession(),
        jobs_repo=repo,
        options=DiscoveryOptions(enrich_lever_details=True),
    )

    assert result.metadata["parsed_count"] == 2
    stored_jobs = repo.list_jobs(source_site="lever")
    enriched = next(job for job in stored_jobs if job.source_job_id == "abc123")
    fallback = next(job for job in stored_jobs if job.source_job_id == "xyz789")

    assert enriched.description_text.startswith("Build backend services used across the product.")
    assert enriched.metadata["team"] == "Platform Engineering"
    assert enriched.employment_type is EmploymentType.FULL_TIME
    assert fallback.description_text == "Listing-only discovery from Lever jobs page."


def test_lever_discovery_detail_enrichment_keeps_listing_data_when_disabled(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "lever_detail.db"
    repo = JobsRepository(init_db(db_path))
    query = DiscoveryQuery(
        source_site="lever",
        label="Example engineering",
        start_url="https://jobs.lever.co/exampleco",
    )
    listing_html = Path("tests/fixtures/lever_jobs_sample.html").read_text(encoding="utf-8")

    monkeypatch.setattr("job_agent.flows.discover.fetch_listing_page_html", lambda **_: listing_html)

    run_discovery_query(
        query=query,
        session=_FakeSession(),
        jobs_repo=repo,
        options=DiscoveryOptions(enrich_lever_details=False),
    )

    stored_job = repo.fetch_by_source_identity("lever", "abc123")

    assert stored_job is not None
    assert stored_job.description_text == "Listing-only discovery from Lever jobs page."
