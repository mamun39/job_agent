from __future__ import annotations

from job_agent.core.models import JobPosting, ParsedJobDetail, ParsedJobListing, SiteCapabilities
from job_agent.sites.base import JobSiteAdapter


class _ExampleAdapter(JobSiteAdapter):
    @property
    def site_name(self) -> str:
        return "example_jobs"

    @property
    def capabilities(self) -> SiteCapabilities:
        return SiteCapabilities(
            supports_listing_html_parse=True,
            supports_listing_page_parse=True,
            supports_detail_html_parse=True,
            supports_detail_page_parse=True,
        )

    def parse_listings(
        self,
        *,
        html: str | None = None,
        page: object | None = None,
    ) -> list[ParsedJobListing]:
        assert html is not None or page is not None
        return [
            ParsedJobListing(
                source_site=self.site_name,
                url="https://example.com/jobs/1",
                source_job_id="job-1",
                title_hint="Software Engineer",
            )
        ]

    def parse_job_detail(
        self,
        *,
        url: str,
        html: str | None = None,
        page: object | None = None,
    ) -> ParsedJobDetail:
        listing = ParsedJobListing(
            source_site=self.site_name,
            url=url,
            source_job_id="job-1",
            title_hint="Software Engineer",
        )
        posting = JobPosting(
            source_site=self.site_name,
            source_job_id="job-1",
            url=url,
            title="Software Engineer",
            company="Example Co",
            location="Toronto, ON",
            description_text="Build internal tooling.",
        )
        return ParsedJobDetail(listing=listing, posting=posting, raw_html=html)


def test_adapter_contract_exposes_site_name_and_capabilities() -> None:
    adapter = _ExampleAdapter()

    assert adapter.site_name == "example_jobs"
    assert adapter.capabilities.supports_listing_html_parse is True
    assert adapter.capabilities.supports_detail_page_parse is True


def test_adapter_parse_methods_return_structured_results() -> None:
    adapter = _ExampleAdapter()

    listings = adapter.parse_listings(html="<html></html>")
    detail = adapter.parse_job_detail(url="https://example.com/jobs/1", html="<html></html>")

    assert len(listings) == 1
    assert listings[0].source_site == "example_jobs"
    assert detail.listing.url.unicode_string() == "https://example.com/jobs/1"
    assert detail.posting.title == "Software Engineer"

