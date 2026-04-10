from __future__ import annotations

from pathlib import Path

from job_agent.sites.linkedin import LinkedInAdapter


def test_linkedin_adapter_parses_fixture_into_job_postings() -> None:
    html = Path("tests/fixtures/linkedin_jobs_sample.html").read_text(encoding="utf-8")
    adapter = LinkedInAdapter.from_start_url("https://www.linkedin.com/jobs/search/?keywords=python")

    postings = adapter.parse_job_postings(html=html)

    assert len(postings) == 2
    assert postings[0].source_site == "linkedin"
    assert postings[0].source_job_id == "1234567890"
    assert postings[0].title == "Senior Python Engineer"
    assert postings[0].company == "Example Co"
    assert postings[0].location == "Toronto, ON"
    assert postings[0].url.unicode_string() == "https://www.linkedin.com/jobs/view/1234567890/"
    assert postings[0].metadata == {"posted_time": "3 days ago", "workplace_type": "Hybrid"}


def test_linkedin_adapter_handles_missing_optional_metadata_safely() -> None:
    html = Path("tests/fixtures/linkedin_jobs_sample.html").read_text(encoding="utf-8")
    adapter = LinkedInAdapter.from_start_url("https://www.linkedin.com/jobs/search/?keywords=python")

    postings = adapter.parse_job_postings(html=html)

    assert postings[1].source_job_id == "987654321"
    assert postings[1].title == "Product Analyst"
    assert postings[1].company == "Another Co"
    assert postings[1].location == "Remote"
    assert postings[1].metadata == {}
    assert postings[1].description_text == "Listing-only discovery from LinkedIn jobs page."
