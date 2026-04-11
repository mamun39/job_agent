from __future__ import annotations

from pathlib import Path

from job_agent.config import Settings
from job_agent.core.models import DiscoveryOptions, DiscoveryQuery
from job_agent.flows.discover import build_adapter_for_query, run_discovery_query
from job_agent.main import main
from job_agent.storage.db import init_db
from job_agent.storage.jobs_repo import JobsRepository


class _FakeSession:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_build_adapter_for_query_selects_supported_adapter() -> None:
    greenhouse_query = DiscoveryQuery(
        source_site="greenhouse",
        label="Greenhouse jobs",
        start_url="https://boards.greenhouse.io/exampleco",
    )
    lever_query = DiscoveryQuery(
        source_site="lever",
        label="Lever jobs",
        start_url="https://jobs.lever.co/exampleco",
    )

    assert build_adapter_for_query(greenhouse_query).site_name == "greenhouse"
    assert build_adapter_for_query(lever_query).site_name == "lever"


def test_run_discovery_query_fetches_parses_and_stores_jobs(tmp_path, monkeypatch) -> None:
    query = DiscoveryQuery(
        source_site="greenhouse",
        label="Example engineering",
        start_url="https://boards.greenhouse.io/exampleco",
    )
    html = Path("tests/fixtures/greenhouse_jobs_sample.html").read_text(encoding="utf-8")
    monkeypatch.setattr("job_agent.flows.discover.fetch_listing_page_html", lambda **_: html)
    repo = JobsRepository(init_db(tmp_path / "discover.db"))

    result = run_discovery_query(
        query=query,
        session=_FakeSession(),
        jobs_repo=repo,
    )

    assert result.source_site == "greenhouse"
    assert result.metadata["label"] == "Example engineering"
    assert result.metadata["stored_count"] == 2
    assert len(repo.list_jobs(source_site="greenhouse")) == 2


def test_cli_discover_prints_summary_and_surfaces_failures(tmp_path, monkeypatch, capsys) -> None:
    greenhouse_html = Path("tests/fixtures/greenhouse_jobs_sample.html").read_text(encoding="utf-8")
    settings = Settings(
        db_path=tmp_path / "cli.db",
        discovery_queries=[
            DiscoveryQuery(
                source_site="greenhouse",
                label="Greenhouse ok",
                start_url="https://boards.greenhouse.io/exampleco",
            ),
            DiscoveryQuery(
                source_site="lever",
                label="Lever fail",
                start_url="https://jobs.lever.co/exampleco",
            ),
        ],
    )

    def fake_fetch(*, session, url, screenshot_name=None, wait_until="networkidle", wait_delay_ms=0):  # noqa: ARG001
        if "greenhouse" in url:
            return greenhouse_html
        raise RuntimeError("fetch failed")

    monkeypatch.setattr("job_agent.main.load_settings", lambda: settings)
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)
    monkeypatch.setattr("job_agent.flows.discover.fetch_listing_page_html", fake_fetch)
    monkeypatch.setattr("job_agent.main.BrowserSessionManager.from_settings", lambda settings: _FakeSession())

    exit_code = main(["discover"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert (
        "[ok] Greenhouse ok (greenhouse) queries=1 pages=1 failed_pages=0 jobs=2 "
        "inserted=2 updated=0 duplicates=0 detail_pages=0 detail_failures=0"
    ) in captured.out
    assert "[error] Lever fail (lever) fetch failed" in captured.out
    assert (
        "[summary] queries=1 pages=1 failed_pages=0 jobs=2 inserted=2 updated=0 "
        "duplicates=0 detail_pages=0 detail_failures=0"
    ) in captured.out


def test_cli_discover_passes_runtime_detail_enrichment_options(tmp_path, monkeypatch, capsys) -> None:
    settings = Settings(
        db_path=tmp_path / "cli.db",
        discovery_queries=[
            DiscoveryQuery(
                source_site="greenhouse",
                label="Greenhouse details",
                start_url="https://boards.greenhouse.io/exampleco",
            )
        ],
        discovery_options=DiscoveryOptions(),
    )
    recorded_options: list[DiscoveryOptions] = []

    def fake_run_discovery_query(*, query, session, jobs_repo, screenshot_name=None, options=None, **kwargs):  # noqa: ARG001
        recorded_options.append(options)
        return type(
            "Result",
            (),
            {
                "metadata": {
                    "parsed_count": 0,
                    "stored_count": 0,
                    "inserted_count": 0,
                    "updated_count": 0,
                    "duplicate_count": 0,
                    "queries_attempted": 1,
                    "pages_fetched": 1,
                    "pages_failed": 0,
                    "jobs_parsed": 0,
                    "jobs_inserted": 0,
                    "jobs_updated": 0,
                    "jobs_skipped_duplicates": 0,
                    "detail_pages_fetched": 0,
                    "detail_parse_failures": 0,
                }
            },
        )()

    monkeypatch.setattr("job_agent.main.load_settings", lambda: settings)
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)
    monkeypatch.setattr("job_agent.main.run_discovery_query", fake_run_discovery_query)
    monkeypatch.setattr("job_agent.main.BrowserSessionManager.from_settings", lambda settings: _FakeSession())

    exit_code = main(["discover", "--greenhouse-details", "--lever-details"])
    capsys.readouterr()

    assert exit_code == 0
    assert len(recorded_options) == 1
    assert recorded_options[0] == DiscoveryOptions(
        enrich_greenhouse_details=True,
        enrich_lever_details=True,
    )


def test_cli_discover_uses_configured_detail_enrichment_options(tmp_path, monkeypatch, capsys) -> None:
    settings = Settings(
        db_path=tmp_path / "cli.db",
        discovery_queries=[
            DiscoveryQuery(
                source_site="lever",
                label="Lever details",
                start_url="https://jobs.lever.co/exampleco",
            )
        ],
        discovery_options=DiscoveryOptions(enrich_lever_details=True),
    )
    recorded_options: list[DiscoveryOptions] = []

    def fake_run_discovery_query(*, query, session, jobs_repo, screenshot_name=None, options=None, **kwargs):  # noqa: ARG001
        recorded_options.append(options)
        return type(
            "Result",
            (),
            {
                "metadata": {
                    "parsed_count": 0,
                    "stored_count": 0,
                    "inserted_count": 0,
                    "updated_count": 0,
                    "duplicate_count": 0,
                    "queries_attempted": 1,
                    "pages_fetched": 1,
                    "pages_failed": 0,
                    "jobs_parsed": 0,
                    "jobs_inserted": 0,
                    "jobs_updated": 0,
                    "jobs_skipped_duplicates": 0,
                    "detail_pages_fetched": 0,
                    "detail_parse_failures": 0,
                }
            },
        )()

    monkeypatch.setattr("job_agent.main.load_settings", lambda: settings)
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)
    monkeypatch.setattr("job_agent.main.run_discovery_query", fake_run_discovery_query)
    monkeypatch.setattr("job_agent.main.BrowserSessionManager.from_settings", lambda settings: _FakeSession())

    exit_code = main(["discover"])
    capsys.readouterr()

    assert exit_code == 0
    assert len(recorded_options) == 1
    assert recorded_options[0] == DiscoveryOptions(
        enrich_greenhouse_details=False,
        enrich_lever_details=True,
    )
