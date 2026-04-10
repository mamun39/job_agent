from __future__ import annotations

from pathlib import Path

from job_agent.sites.indeed import IndeedAdapter


def test_indeed_adapter_parses_fixture_into_job_postings() -> None:
    html = Path("tests/fixtures/indeed_jobs_sample.html").read_text(encoding="utf-8")
    adapter = IndeedAdapter.from_start_url("https://www.indeed.com/jobs?q=python")

    postings = adapter.parse_job_postings(html=html)

    assert len(postings) == 2
    assert postings[0].source_site == "indeed"
    assert postings[0].source_job_id == "abc123"
    assert postings[0].title == "Senior Python Engineer"
    assert postings[0].company == "Example Co"
    assert postings[0].location == "Toronto, ON"
    assert postings[0].url.unicode_string() == "https://www.indeed.com/viewjob?jk=abc123"
    assert postings[0].metadata == {"snippet": "Build internal automation tools."}


def test_indeed_adapter_handles_missing_optional_metadata_safely() -> None:
    html = Path("tests/fixtures/indeed_jobs_sample.html").read_text(encoding="utf-8")
    adapter = IndeedAdapter.from_start_url("https://www.indeed.com/jobs?q=python")

    postings = adapter.parse_job_postings(html=html)

    assert postings[1].source_job_id == "xyz789"
    assert postings[1].title == "Product Analyst"
    assert postings[1].company == "Another Co"
    assert postings[1].location == "Remote"
    assert postings[1].metadata == {}
    assert postings[1].description_text == "Listing-only discovery from Indeed jobs page."
