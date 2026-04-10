from __future__ import annotations

from pathlib import Path

from job_agent.sites.lever import LeverAdapter


def test_lever_adapter_parses_listing_fixture_into_job_postings() -> None:
    fixture_path = Path("tests/fixtures/lever_jobs_sample.html")
    html = fixture_path.read_text(encoding="utf-8")
    adapter = LeverAdapter(board_url="https://jobs.lever.co/exampleco")

    postings = adapter.parse_job_postings(html=html)

    assert len(postings) == 2
    assert postings[0].source_site == "lever"
    assert postings[0].title == "Senior Backend Engineer"
    assert postings[0].company == "Example Co"
    assert postings[0].location == "Toronto, ON"
    assert postings[0].url.unicode_string() == "https://jobs.lever.co/exampleco/abc123"
    assert postings[0].metadata == {"team": "Platform"}


def test_lever_adapter_handles_missing_optional_fields_cleanly() -> None:
    fixture_path = Path("tests/fixtures/lever_jobs_sample.html")
    html = fixture_path.read_text(encoding="utf-8")
    adapter = LeverAdapter(board_url="https://jobs.lever.co/exampleco")

    postings = adapter.parse_job_postings(html=html)

    assert postings[1].title == "Product Designer"
    assert postings[1].company == "Example Co"
    assert postings[1].location == "Remote - Canada"
    assert postings[1].metadata == {}
    assert postings[1].description_text == "Listing-only discovery from Lever jobs page."
