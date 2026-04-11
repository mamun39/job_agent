from __future__ import annotations

import io
import json
import logging
from pathlib import Path

from job_agent.core.models import CrawlResult, DiscoveryOptions, DiscoveryQuery
from job_agent.flows.discover import run_discovery_query
from job_agent.logging import JsonFormatter
from job_agent.storage.db import init_db
from job_agent.storage.jobs_repo import JobsRepository
from job_agent.ui.cli import render_discovery_summary


class _FakeSession:
    def close(self) -> None:
        return None


def test_discovery_telemetry_aggregates_summary_fields_for_successful_run(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "telemetry.db"
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
        "https://boards.greenhouse.io/exampleco/jobs/67890": detail_html,
    }

    monkeypatch.setattr("job_agent.flows.discover.fetch_listing_page_html", lambda **kwargs: pages[kwargs["url"]])

    result = run_discovery_query(
        query=query,
        session=_FakeSession(),
        jobs_repo=repo,
        options=DiscoveryOptions(enrich_greenhouse_details=True),
    )

    assert result.metadata["queries_attempted"] == 1
    assert result.metadata["pages_fetched"] == 1
    assert result.metadata["pages_failed"] == 0
    assert result.metadata["jobs_parsed"] == 2
    assert result.metadata["jobs_inserted"] == 2
    assert result.metadata["jobs_updated"] == 0
    assert result.metadata["jobs_skipped_duplicates"] == 0
    assert result.metadata["detail_pages_fetched"] == 2
    assert result.metadata["detail_parse_failures"] == 0

    summary = render_discovery_summary(result)
    assert "queries=1" in summary
    assert "pages=1" in summary
    assert "jobs=2" in summary
    assert "detail_pages=2" in summary


def test_discovery_telemetry_accounts_for_representative_failures_and_logs_them(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "telemetry.db"
    repo = JobsRepository(init_db(db_path))
    query = DiscoveryQuery(
        source_site="greenhouse",
        label="Example engineering",
        start_url="https://boards.greenhouse.io/exampleco",
    )
    listing_html = """
    <html><body>
      <section class="level-0">Example Co</section>
      <div class="opening">
        <a class="opening" href="/exampleco/jobs/12345">Backend Engineer</a>
        <span class="location">Remote</span>
      </div>
      <nav><a class="pagination__next" href="?page=2">Next</a></nav>
    </body></html>
    """
    pages = {
        "https://boards.greenhouse.io/exampleco": listing_html,
        "https://boards.greenhouse.io/exampleco?page=2": RuntimeError("next page fetch failed"),
        "https://boards.greenhouse.io/exampleco/jobs/12345": RuntimeError("detail parse fetch failed"),
    }

    def fake_fetch(**kwargs):
        response = pages[kwargs["url"]]
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr("job_agent.flows.discover.fetch_listing_page_html", fake_fetch)

    logger = logging.getLogger("job_agent")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)

    try:
        result = run_discovery_query(
            query=query,
            session=_FakeSession(),
            jobs_repo=repo,
            options=DiscoveryOptions(enrich_greenhouse_details=True),
            max_pages_per_query=2,
        )
    finally:
        root_logger.handlers = original_handlers
        root_logger.setLevel(original_level)

    assert result.metadata["queries_attempted"] == 1
    assert result.metadata["pages_fetched"] == 1
    assert result.metadata["pages_failed"] == 1
    assert result.metadata["jobs_parsed"] == 1
    assert result.metadata["jobs_inserted"] == 1
    assert result.metadata["jobs_updated"] == 0
    assert result.metadata["jobs_skipped_duplicates"] == 0
    assert result.metadata["detail_pages_fetched"] == 0
    assert result.metadata["detail_parse_failures"] == 1

    log_lines = [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]
    events = {(line.get("event"), line.get("reason"), line.get("stage")) for line in log_lines}
    assert ("fetch_failed", None, "listing_fetch") in events
    assert ("skipped_page", "fetch_failed", None) in events
    assert ("fetch_failed", None, "detail_fetch") in events


def test_render_discovery_summary_uses_new_telemetry_fields() -> None:
    result = CrawlResult(
        query={},
        source_site="greenhouse",
        metadata={
            "queries_attempted": 1,
            "pages_fetched": 2,
            "pages_failed": 1,
            "jobs_parsed": 4,
            "jobs_inserted": 2,
            "jobs_updated": 1,
            "jobs_skipped_duplicates": 1,
            "detail_pages_fetched": 3,
            "detail_parse_failures": 1,
        },
    )

    summary = render_discovery_summary(result)

    assert summary == (
        "queries=1 pages=2 failed_pages=1 jobs=4 inserted=2 updated=1 duplicates=1 "
        "detail_pages=3 detail_failures=1"
    )
