from __future__ import annotations

from pathlib import Path

from job_agent.core.models import EmploymentType, RemoteStatus
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
    assert postings[0].posted_at is not None


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


def test_linkedin_adapter_parses_detail_fixture_into_enriched_posting() -> None:
    html = Path("tests/fixtures/linkedin_job_detail_sample.html").read_text(encoding="utf-8")
    adapter = LinkedInAdapter.from_start_url("https://www.linkedin.com/jobs/search/?keywords=python")

    detail = adapter.parse_job_detail(
        url="https://www.linkedin.com/jobs/view/1234567890/",
        html=html,
    )

    assert detail.posting.source_site == "linkedin"
    assert detail.posting.source_job_id == "1234567890"
    assert detail.posting.title == "Senior Python Engineer"
    assert detail.posting.company == "Example Co"
    assert detail.posting.location == "Toronto, Ontario, Canada"
    assert detail.posting.remote_status is RemoteStatus.HYBRID
    assert detail.posting.employment_type is EmploymentType.FULL_TIME
    assert "Build automation systems" in detail.posting.description_text
    assert detail.posting.metadata["posted_time"] == "3 days ago"
    assert detail.posting.metadata["workplace_type"] == "Hybrid"
    assert detail.posting.metadata["employment_type_text"] == "Full-time"


def test_linkedin_adapter_parses_authenticated_card_location_variant() -> None:
    html = """
    <html>
      <body>
        <ul>
          <li class="scaffold-layout__list-item">
            <a class="job-card-container__link" href="https://www.linkedin.com/jobs/view/1234567890/?trackingId=abc">Security Engineer</a>
            <div class="artdeco-entity-lockup__subtitle">LinkedIn</div>
            <div class="artdeco-entity-lockup__caption">Toronto, Ontario, Canada</div>
          </li>
        </ul>
      </body>
    </html>
    """
    adapter = LinkedInAdapter.from_start_url("https://www.linkedin.com/jobs/search/?keywords=python")

    postings = adapter.parse_job_postings(html=html)

    assert len(postings) == 1
    assert postings[0].location == "Toronto, Ontario, Canada"
    assert postings[0].source_job_id == "1234567890"
