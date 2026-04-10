from __future__ import annotations

from pathlib import Path

from job_agent.flows.discover import run_discovery
from job_agent.sites.greenhouse import GreenhouseAdapter
from job_agent.sites.lever import LeverAdapter
from job_agent.storage.db import init_db
from job_agent.storage.jobs_repo import JobsRepository


def test_discovery_flow_parses_and_stores_greenhouse_jobs(tmp_path) -> None:
    html = Path("tests/fixtures/greenhouse_jobs_sample.html").read_text(encoding="utf-8")
    adapter = GreenhouseAdapter(board_url="https://boards.greenhouse.io/exampleco")
    repo = JobsRepository(init_db(tmp_path / "discover.db"))

    result = run_discovery(adapter=adapter, jobs_repo=repo, html=html)

    assert result.success is True
    assert result.source_site == "greenhouse"
    assert len(result.postings) == 2
    assert result.metadata["parsed_count"] == 2
    assert result.metadata["deduplicated_count"] == 2
    assert result.metadata["stored_count"] == 2
    assert result.metadata["inserted_count"] == 2
    assert result.metadata["updated_count"] == 0
    assert len(repo.list_jobs(source_site="greenhouse")) == 2


def test_discovery_flow_deduplicates_and_upserts_repeat_jobs(tmp_path) -> None:
    html = Path("tests/fixtures/lever_jobs_sample.html").read_text(encoding="utf-8")
    adapter = LeverAdapter(board_url="https://jobs.lever.co/exampleco")
    repo = JobsRepository(init_db(tmp_path / "discover.db"))

    first = run_discovery(adapter=adapter, jobs_repo=repo, html=html)
    second = run_discovery(adapter=adapter, jobs_repo=repo, html=html)

    assert first.metadata["inserted_count"] == 2
    assert second.metadata["parsed_count"] == 2
    assert second.metadata["deduplicated_count"] == 2
    assert second.metadata["duplicate_count"] == 0
    assert second.metadata["stored_count"] == 2
    assert second.metadata["inserted_count"] == 0
    assert second.metadata["updated_count"] == 2
    assert len(repo.list_jobs(source_site="lever")) == 2


def test_discovery_flow_deduplicates_parsed_postings_before_storage(tmp_path) -> None:
    html = Path("tests/fixtures/greenhouse_jobs_sample.html").read_text(encoding="utf-8")
    adapter = GreenhouseAdapter(board_url="https://boards.greenhouse.io/exampleco")
    postings = adapter.parse_job_postings(html=html)
    duplicate_postings = [postings[0], postings[0], postings[1]]
    repo = JobsRepository(init_db(tmp_path / "discover.db"))

    result = run_discovery(adapter=adapter, jobs_repo=repo, parsed_postings=duplicate_postings)

    assert result.metadata["parsed_count"] == 3
    assert result.metadata["deduplicated_count"] == 2
    assert result.metadata["duplicate_count"] == 1
    assert result.metadata["stored_count"] == 2
    assert len(repo.list_jobs(source_site="greenhouse")) == 2
