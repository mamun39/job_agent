from __future__ import annotations

from pathlib import Path

from job_agent.core.models import DiscoveryOptions, DiscoveryQuery, EmploymentType, RemoteStatus
from job_agent.flows.discover import run_discovery_query
from job_agent.sites.greenhouse import GreenhouseAdapter
from job_agent.storage.db import init_db
from job_agent.storage.jobs_repo import JobsRepository


class _FakeSession:
    def close(self) -> None:
        return None


def test_greenhouse_adapter_parses_detail_fixture_into_enriched_job_fields() -> None:
    html = Path("tests/fixtures/greenhouse_job_detail_sample.html").read_text(encoding="utf-8")
    adapter = GreenhouseAdapter(board_url="https://boards.greenhouse.io/exampleco")

    detail = adapter.parse_job_detail(url="https://boards.greenhouse.io/exampleco/jobs/12345", html=html)

    assert detail.posting.title == "Senior Python Engineer"
    assert detail.posting.company == "Example Co"
    assert detail.posting.location == "Toronto, ON"
    assert detail.posting.employment_type is EmploymentType.FULL_TIME
    assert detail.posting.remote_status is RemoteStatus.HYBRID
    assert detail.posting.metadata["team"] == "Platform Engineering"
    assert detail.posting.metadata["employment_type_text"] == "Full-time"
    assert "Build backend services for the platform team." in detail.posting.description_text
    assert "Design Python services" in detail.posting.description_text


def test_greenhouse_discovery_detail_enrichment_updates_stored_job_when_enabled(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "greenhouse_detail.db"
    repo = JobsRepository(init_db(db_path))
    query = DiscoveryQuery(
        source_site="greenhouse",
        label="Example engineering",
        start_url="https://boards.greenhouse.io/exampleco",
    )
    listing_html = Path("tests/fixtures/greenhouse_jobs_sample.html").read_text(encoding="utf-8")
    detail_html = Path("tests/fixtures/greenhouse_job_detail_sample.html").read_text(encoding="utf-8")

    pages = {
        "https://boards.greenhouse.io/exampleco": listing_html,
        "https://boards.greenhouse.io/exampleco/jobs/12345": detail_html,
        "https://boards.greenhouse.io/exampleco/jobs/67890": RuntimeError("detail fetch failed"),
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
        options=DiscoveryOptions(enrich_greenhouse_details=True),
    )

    assert result.metadata["parsed_count"] == 2
    stored_jobs = repo.list_jobs(source_site="greenhouse")
    enriched = next(job for job in stored_jobs if job.source_job_id == "12345")
    fallback = next(job for job in stored_jobs if job.source_job_id == "67890")

    assert enriched.description_text.startswith("Build backend services")
    assert enriched.metadata["team"] == "Platform Engineering"
    assert enriched.employment_type is EmploymentType.FULL_TIME
    assert fallback.description_text == "Listing-only discovery from Greenhouse jobs page."
    assert result.metadata["detail_enrichment_selected"] == 2
    assert result.metadata["detail_fetch_attempts"] == 2
    assert result.metadata["detail_enrichment_successes"] == 1
    assert result.metadata["detail_parse_failures"] == 1


def test_greenhouse_discovery_detail_enrichment_keeps_listing_data_when_disabled(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "greenhouse_detail.db"
    repo = JobsRepository(init_db(db_path))
    query = DiscoveryQuery(
        source_site="greenhouse",
        label="Example engineering",
        start_url="https://boards.greenhouse.io/exampleco",
    )
    listing_html = Path("tests/fixtures/greenhouse_jobs_sample.html").read_text(encoding="utf-8")

    monkeypatch.setattr("job_agent.flows.discover.fetch_listing_page_html", lambda **_: listing_html)

    run_discovery_query(
        query=query,
        session=_FakeSession(),
        jobs_repo=repo,
        options=DiscoveryOptions(enrich_greenhouse_details=False),
    )

    stored_job = repo.fetch_by_source_identity("greenhouse", "12345")

    assert stored_job is not None
    assert stored_job.description_text == "Listing-only discovery from Greenhouse jobs page."
    assert stored_job.metadata["team"] == "Platform Engineering"


def test_greenhouse_selective_detail_enrichment_only_fetches_promising_listing_candidates(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "greenhouse_selective.db"
    repo = JobsRepository(init_db(db_path))
    query = DiscoveryQuery(
        source_site="greenhouse",
        label="Backend roles",
        start_url="https://boards.greenhouse.io/exampleco",
        include_keywords=["Python"],
    )
    listing_html = Path("tests/fixtures/greenhouse_jobs_sample.html").read_text(encoding="utf-8")
    detail_html = Path("tests/fixtures/greenhouse_job_detail_sample.html").read_text(encoding="utf-8")
    fetched_urls: list[str] = []

    pages = {
        "https://boards.greenhouse.io/exampleco": listing_html,
        "https://boards.greenhouse.io/exampleco/jobs/12345": detail_html,
    }

    def fake_fetch(*, session, url, screenshot_name=None, wait_until="networkidle", wait_delay_ms=0):  # noqa: ARG001
        fetched_urls.append(url)
        return pages[url]

    monkeypatch.setattr("job_agent.flows.discover.fetch_listing_page_html", fake_fetch)

    result = run_discovery_query(
        query=query,
        session=_FakeSession(),
        jobs_repo=repo,
        options=DiscoveryOptions(
            enrich_greenhouse_details=True,
            selective_detail_enrichment=True,
            min_listing_stage_score_for_detail_enrichment=3,
        ),
    )

    assert fetched_urls == [
        "https://boards.greenhouse.io/exampleco",
        "https://boards.greenhouse.io/exampleco/jobs/12345",
    ]
    assert result.metadata["jobs_parsed"] == 2
    assert result.metadata["detail_enrichment_selected"] == 1
    assert result.metadata["detail_fetch_attempts"] == 1
    assert result.metadata["detail_enrichment_successes"] == 1
    assert result.metadata["detail_parse_failures"] == 0

    enriched = repo.fetch_by_source_identity("greenhouse", "12345")
    skipped = repo.fetch_by_source_identity("greenhouse", "67890")
    assert enriched is not None
    assert skipped is not None
    assert enriched.description_text.startswith("Build backend services")
    assert skipped.description_text == "Listing-only discovery from Greenhouse jobs page."
