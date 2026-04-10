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


def test_lever_adapter_parses_live_posting_markup() -> None:
    html = """
    <div class="main-header-text">WHOOP</div>
    <div class="postings-group">
      <div class="posting-category-title large-category-label">Engineering</div>
      <div class="posting" data-qa-posting-id="abc-123">
        <div class="posting-apply"><a class="posting-btn-submit" href="https://jobs.lever.co/whoop/abc-123">Apply</a></div>
        <a class="posting-title" href="https://jobs.lever.co/whoop/abc-123">
          <h5 data-qa="posting-name">Software Engineer II</h5>
          <div class="posting-categories">
            <span class="display-inline-block small-category-label workplaceTypes">On-site — </span>
            <span class="sort-by-location posting-category small-category-label location">Boston, MA</span>
          </div>
        </a>
      </div>
    </div>
    """
    adapter = LeverAdapter(board_url="https://jobs.lever.co/whoop")

    postings = adapter.parse_job_postings(html=html)

    assert len(postings) == 1
    assert postings[0].title == "Software Engineer II"
    assert postings[0].company == "WHOOP"
    assert postings[0].location == "Boston, MA"
    assert postings[0].source_job_id == "abc-123"
    assert postings[0].metadata == {"team": "Engineering"}
