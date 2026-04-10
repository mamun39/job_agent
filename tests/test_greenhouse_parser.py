from __future__ import annotations

from pathlib import Path

from job_agent.sites.greenhouse import GreenhouseAdapter


def test_greenhouse_adapter_parses_listing_fixture_into_job_postings() -> None:
    fixture_path = Path("tests/fixtures/greenhouse_jobs_sample.html")
    html = fixture_path.read_text(encoding="utf-8")
    adapter = GreenhouseAdapter(board_url="https://boards.greenhouse.io/exampleco")

    postings = adapter.parse_job_postings(html=html)

    assert len(postings) == 2
    assert postings[0].source_site == "greenhouse"
    assert postings[0].title == "Senior Python Engineer"
    assert postings[0].company == "Example Co"
    assert postings[0].location == "Toronto, ON"
    assert postings[0].url.unicode_string() == "https://boards.greenhouse.io/exampleco/jobs/12345"
    assert postings[0].metadata == {"team": "Platform Engineering"}


def test_greenhouse_adapter_handles_missing_optional_fields_gracefully() -> None:
    fixture_path = Path("tests/fixtures/greenhouse_jobs_sample.html")
    html = fixture_path.read_text(encoding="utf-8")
    adapter = GreenhouseAdapter(board_url="https://boards.greenhouse.io/exampleco")

    postings = adapter.parse_job_postings(html=html)

    assert postings[1].title == "Product Analyst"
    assert postings[1].company == "Example Co"
    assert postings[1].location == "Remote - Canada"
    assert postings[1].metadata == {}
    assert postings[1].description_text == "Listing-only discovery from Greenhouse jobs page."
