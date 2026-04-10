"""Read-only Indeed listing page parser."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit

from job_agent.core.models import JobPosting, ParsedJobDetail, ParsedJobListing, SiteCapabilities
from job_agent.sites.base import JobSiteAdapter, SupportsPageContent


class IndeedAdapter(JobSiteAdapter):
    """Parse Indeed listing pages from saved HTML."""

    def __init__(self, *, board_url: str | None = None) -> None:
        self._board_url = board_url

    @classmethod
    def from_start_url(cls, start_url: str) -> IndeedAdapter:
        """Build an adapter for a configured Indeed listing URL."""
        return cls(board_url=start_url)

    @property
    def site_name(self) -> str:
        return "indeed"

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
        parser = _IndeedListingsParser(base_url=self._board_url)
        parser.feed(document)
        parser.close()

        listings: list[ParsedJobListing] = []
        for item in parser.items:
            metadata: dict[str, Any] = {}
            if item.get("snippet"):
                metadata["snippet"] = item["snippet"]
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
                    description_text="Listing-only discovery from Indeed jobs page.",
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
        raise NotImplementedError("IndeedAdapter does not parse detail pages in this task")


def _resolve_html(*, html: str | None, page: SupportsPageContent | None) -> str:
    if html is not None:
        return html
    if page is not None:
        return page.content()
    raise ValueError("html or page is required")


class _IndeedListingsParser(HTMLParser):
    def __init__(self, *, base_url: str | None) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url or "https://www.indeed.com"
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

        if tag == "div" and ("job_seen_beacon" in classes or "slider_item" in classes):
            self._current = {}
            self._card_depth = 1
            return

        if self._current is None:
            return

        if tag == "div":
            self._card_depth += 1

        if tag == "a" and (
            "jcs-JobTitle" in classes
            or "jobTitle" in classes
            or attrs_dict.get("data-jk") is not None
        ):
            href = attrs_dict.get("href")
            if href:
                resolved_url = urljoin(self.base_url, href)
                self._current["url"] = resolved_url
                source_job_id = attrs_dict.get("data-jk") or _extract_jk_from_url(resolved_url)
                if source_job_id:
                    self._current["source_job_id"] = source_job_id
            self._capture_field = "title"
            self._capture_tag = "a"
            self._capture_buffer = []
            return

        if tag == "span" and ("companyName" in classes or "company" in classes):
            self._capture_field = "company"
            self._capture_tag = "span"
            self._capture_buffer = []
            return

        if tag == "div" and ("companyLocation" in classes or "locationsContainer" in classes):
            self._capture_field = "location"
            self._capture_tag = "div"
            self._capture_buffer = []
            return

        if tag == "div" and ("job-snippet" in classes or "jobMetaDataGroup" in classes):
            self._capture_field = "snippet"
            self._capture_tag = "div"
            self._capture_buffer = []

    def handle_endtag(self, tag: str) -> None:
        if self._capture_field is not None and self._capture_tag == tag:
            value = " ".join(part.strip() for part in self._capture_buffer if part.strip()).strip()
            if value and self._current is not None:
                existing = self._current.get(self._capture_field)
                if existing and self._capture_field == "snippet":
                    self._current[self._capture_field] = f"{existing} {value}"
                else:
                    self._current[self._capture_field] = value
            self._capture_field = None
            self._capture_tag = None
            self._capture_buffer = []

        if tag == "div" and self._current is not None:
            self._card_depth -= 1
            if self._card_depth == 0:
                if self._current.get("url") and self._current.get("title"):
                    self.items.append(self._current)
                self._current = None

    def handle_data(self, data: str) -> None:
        if self._capture_field is not None:
            self._capture_buffer.append(data)


def _extract_jk_from_url(url: str) -> str | None:
    query = parse_qs(urlsplit(url).query)
    values = query.get("jk")
    if values:
        return values[0]
    path = urlsplit(url).path.rstrip("/").split("/")
    if path and path[-1] == "viewjob" and values:
        return values[0]
    return None
