"""Read-only LinkedIn listing page parser."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit

from job_agent.core.models import JobPosting, ParsedJobDetail, ParsedJobListing, SiteCapabilities
from job_agent.sites.base import JobSiteAdapter, SupportsPageContent


class LinkedInAdapter(JobSiteAdapter):
    """Parse LinkedIn job listing pages from saved HTML."""

    def __init__(self, *, board_url: str | None = None) -> None:
        self._board_url = board_url

    @classmethod
    def from_start_url(cls, start_url: str) -> LinkedInAdapter:
        """Build an adapter for a configured LinkedIn listing URL."""
        return cls(board_url=start_url)

    @property
    def site_name(self) -> str:
        return "linkedin"

    @property
    def capabilities(self) -> SiteCapabilities:
        return SiteCapabilities(
            supports_listing_html_parse=True,
            supports_listing_page_parse=True,
            supports_detail_html_parse=False,
            supports_detail_page_parse=False,
        )

    def parse_listings(
        self,
        *,
        html: str | None = None,
        page: SupportsPageContent | None = None,
    ) -> list[ParsedJobListing]:
        document = _resolve_html(html=html, page=page)
        parser = _LinkedInListingsParser(base_url=self._board_url)
        parser.feed(document)
        parser.close()

        listings: list[ParsedJobListing] = []
        for item in parser.items:
            metadata: dict[str, Any] = {}
            if item.get("posted_time"):
                metadata["posted_time"] = item["posted_time"]
            if item.get("workplace_type"):
                metadata["workplace_type"] = item["workplace_type"]
            listings.append(
                ParsedJobListing(
                    source_site=self.site_name,
                    url=item["url"],
                    source_job_id=item.get("source_job_id"),
                    title_hint=item.get("title"),
                    company_hint=item.get("company"),
                    location_hint=item.get("location"),
                    metadata=metadata,
                )
            )
        return listings

    def parse_job_postings(
        self,
        *,
        html: str | None = None,
        page: SupportsPageContent | None = None,
    ) -> list[JobPosting]:
        postings: list[JobPosting] = []
        for listing in self.parse_listings(html=html, page=page):
            postings.append(
                JobPosting(
                    source_site=self.site_name,
                    source_job_id=listing.source_job_id,
                    url=str(listing.url),
                    title=listing.title_hint or "Unknown title",
                    company=listing.company_hint or "Unknown company",
                    location=listing.location_hint or "Unknown location",
                    description_text="Listing-only discovery from LinkedIn jobs page.",
                    metadata=dict(listing.metadata),
                )
            )
        return postings

    def parse_job_detail(
        self,
        *,
        url: str,
        html: str | None = None,
        page: SupportsPageContent | None = None,
    ) -> ParsedJobDetail:
        raise NotImplementedError("LinkedInAdapter does not parse detail pages in this task")


def _resolve_html(*, html: str | None, page: SupportsPageContent | None) -> str:
    if html is not None:
        return html
    if page is not None:
        return page.content()
    raise ValueError("html or page is required")


class _LinkedInListingsParser(HTMLParser):
    def __init__(self, *, base_url: str | None) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url or "https://www.linkedin.com"
        self.items: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._card_depth = 0
        self._capture_field: str | None = None
        self._capture_tag: str | None = None
        self._capture_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        class_attr = attrs_dict.get("class", "") or ""
        classes = set(class_attr.split())

        if tag == "li" and ("jobs-search-results__list-item" in classes or "jobs-search-results-list__list-item" in classes):
            self._current = {}
            self._card_depth = 1
            return

        if self._current is None:
            return

        if tag == "li":
            self._card_depth += 1

        if tag == "a" and (
            "base-card__full-link" in classes
            or "job-card-container__link" in classes
            or "job-search-card__title-link" in classes
        ):
            href = attrs_dict.get("href")
            if href:
                resolved_url = urljoin(self.base_url, href)
                self._current["url"] = resolved_url
                source_job_id = _extract_linkedin_job_id(resolved_url)
                if source_job_id:
                    self._current["source_job_id"] = source_job_id
            self._capture_field = "title"
            self._capture_tag = "a"
            self._capture_buffer = []
            return

        if tag in {"h4", "a"} and ("base-search-card__subtitle" in classes or "hidden-nested-link" in classes):
            self._capture_field = "company"
            self._capture_tag = tag
            self._capture_buffer = []
            return

        if tag == "span" and ("job-search-card__location" in classes or "base-search-card__metadata" in classes):
            self._capture_field = "location"
            self._capture_tag = "span"
            self._capture_buffer = []
            return

        if tag == "time":
            self._capture_field = "posted_time"
            self._capture_tag = "time"
            self._capture_buffer = []
            return

        if tag == "span" and ("job-search-card__workplace-type" in classes or "job-search-card__workplace-type-label" in classes):
            self._capture_field = "workplace_type"
            self._capture_tag = "span"
            self._capture_buffer = []

    def handle_endtag(self, tag: str) -> None:
        if self._capture_field is not None and self._capture_tag == tag:
            value = " ".join(part.strip() for part in self._capture_buffer if part.strip()).strip()
            if value and self._current is not None and self._capture_field not in self._current:
                self._current[self._capture_field] = value
            self._capture_field = None
            self._capture_tag = None
            self._capture_buffer = []

        if tag == "li" and self._current is not None:
            self._card_depth -= 1
            if self._card_depth == 0:
                if self._current.get("url") and self._current.get("title"):
                    self.items.append(self._current)
                self._current = None

    def handle_data(self, data: str) -> None:
        if self._capture_field is not None:
            self._capture_buffer.append(data)


def _extract_linkedin_job_id(url: str) -> str | None:
    path_parts = [part for part in urlsplit(url).path.split("/") if part]
    if "view" in path_parts and "jobs" in path_parts:
        try:
            index = path_parts.index("view")
            return path_parts[index + 1]
        except (ValueError, IndexError):
            return None
    query_values = parse_qs(urlsplit(url).query).get("currentJobId")
    if query_values:
        return query_values[0]
    return None
