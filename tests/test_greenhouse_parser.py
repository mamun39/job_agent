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


def test_greenhouse_adapter_parses_live_table_style_listing_rows() -> None:
    html = """
    <section class="level-0"><h1>Stripe</h1></section>
    <table>
      <tr class="TableRow">
        <td class="JobsListings__tableCell JobsListings__tableCell--title">
          <a class="Link JobsListings__link" href="https://stripe.com/jobs/listing/software-engineer/7686224">
            Software Engineer
          </a>
        </td>
        <td class="JobsListings__tableCell JobsListings__tableCell--departments">
          <ul><li class="JobsListings__departmentsListItem">Engineering</li></ul>
        </td>
        <td class="JobsListings__tableCell JobsListings__tableCell--country">
          <span class="JobsListings__locationDisplayName">Toronto</span>
        </td>
      </tr>
    </table>
    """
    adapter = GreenhouseAdapter(board_url="https://boards.greenhouse.io/stripe")

    postings = adapter.parse_job_postings(html=html)

    assert len(postings) == 1
    assert postings[0].title == "Software Engineer"
    assert postings[0].company == "Stripe"
    assert postings[0].location == "Toronto"
    assert postings[0].source_job_id == "7686224"
    assert postings[0].metadata == {"team": "Engineering"}


def test_greenhouse_adapter_parses_new_hosted_board_job_posts() -> None:
    html = """
    <h1 class="page-header font-primary">Current openings at Grafana Labs</h1>
    <div class="job-posts">
      <div class="job-posts--table--department">
        <h3 class="section-header font-primary">Finance</h3>
        <table>
          <tbody>
            <tr class="job-post">
              <td class="cell">
                <a href="https://job-boards.greenhouse.io/grafanalabs/jobs/5859517004" target="_top">
                  <p class="body body--medium">Director of Internal Audit | United States | Remote</p>
                  <p class="body body__secondary body--metadata">United States (Remote)</p>
                </a>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    """
    adapter = GreenhouseAdapter(board_url="https://boards.greenhouse.io/grafanalabs")

    postings = adapter.parse_job_postings(html=html)

    assert len(postings) == 1
    assert postings[0].title == "Director of Internal Audit | United States | Remote"
    assert postings[0].company == "Grafanalabs"
    assert postings[0].location == "United States (Remote)"
    assert postings[0].source_job_id == "5859517004"
    assert postings[0].metadata == {"team": "Finance"}
