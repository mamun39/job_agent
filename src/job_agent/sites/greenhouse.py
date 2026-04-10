"""Read-only Greenhouse jobs page parser."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

from job_agent.core.models import JobPosting, ParsedJobDetail, ParsedJobListing, SiteCapabilities
from job_agent.sites.base import JobSiteAdapter, SupportsPageContent


class GreenhouseAdapter(JobSiteAdapter):
    """Parse Greenhouse-hosted job listings from HTML."""

    def __init__(self, *, board_url: str | None = None, company_name: str | None = None) -> None:
        self._board_url = board_url
        self._company_name = company_name

    @classmethod
    def from_start_url(cls, start_url: str) -> GreenhouseAdapter:
        """Build an adapter for a configured Greenhouse listing URL."""
        return cls(board_url=start_url)

    @property
    def site_name(self) -> str:
        return "greenhouse"

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
        parser = _GreenhouseListingsParser(base_url=self._board_url)
        parser.feed(document)
        parser.close()

        company_name = self._company_name or parser.company_name or _infer_company_from_board_url(self._board_url)
        listings: list[ParsedJobListing] = []
        for item in parser.items:
            listings.append(
                ParsedJobListing(
                    source_site=self.site_name,
                    url=item["url"],
                    source_job_id=item.get("source_job_id"),
                    title_hint=item.get("title"),
                    company_hint=company_name,
                    location_hint=item.get("location"),
                    department_hint=item.get("department"),
                    metadata={"team": item.get("department")} if item.get("department") else {},
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
            metadata: dict[str, Any] = {}
            if listing.department_hint:
                metadata["team"] = listing.department_hint
            postings.append(
                JobPosting(
                    source_site=self.site_name,
                    source_job_id=listing.source_job_id,
                    url=str(listing.url),
                    title=listing.title_hint or "Unknown title",
                    company=listing.company_hint or "Unknown company",
                    location=listing.location_hint or "Unknown location",
                    description_text="Listing-only discovery from Greenhouse jobs page.",
                    metadata=metadata,
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
        raise NotImplementedError("GreenhouseAdapter does not parse detail pages in this task")


def _resolve_html(*, html: str | None, page: SupportsPageContent | None) -> str:
    if html is not None:
        return html
    if page is not None:
        return page.content()
    raise ValueError("html or page is required")


def _infer_company_from_board_url(board_url: str | None) -> str | None:
    if not board_url:
        return None
    hostname = urlsplit(board_url).hostname or ""
    if hostname.startswith("boards.greenhouse.io"):
        slug = urlsplit(board_url).path.strip("/").split("/", 1)[0]
        if slug:
            return slug.replace("-", " ").replace("_", " ").title()
    return None


class _GreenhouseListingsParser(HTMLParser):
    def __init__(self, *, base_url: str | None) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.items: list[dict[str, str]] = []
        self.company_name: str | None = None
        self._stack: list[str] = []
        self._in_opening = False
        self._opening_text: list[str] = []
        self._current: dict[str, Any] | None = None
        self._capture_field: str | None = None
        self._capture_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        class_attr = attrs_dict.get("class", "") or ""
        self._stack.append(tag)

        if tag == "section" and "level-0" in class_attr:
            self._in_opening = True
            self._opening_text = []

        if tag == "div" and "opening" in class_attr.split():
            self._current = {}

        if self._current is None:
            return

        if tag == "a" and "opening" in class_attr.split():
            href = attrs_dict.get("href")
            if href:
                self._current["url"] = urljoin(self.base_url or "", href)
                source_job_id = attrs_dict.get("data-mapped")
                if source_job_id:
                    self._current["source_job_id"] = source_job_id
            self._capture_field = "title"
            self._capture_buffer = []
            return

        if tag == "span" and "location" in class_attr.split():
            self._capture_field = "location"
            self._capture_buffer = []
            return

        if tag == "span" and ("department" in class_attr.split() or "team" in class_attr.split()):
            self._capture_field = "department"
            self._capture_buffer = []

    def handle_endtag(self, tag: str) -> None:
        if self._capture_field is not None and self._stack and self._stack[-1] == tag:
            value = " ".join(part.strip() for part in self._capture_buffer if part.strip()).strip()
            if value and self._current is not None:
                self._current[self._capture_field] = value
            self._capture_field = None
            self._capture_buffer = []

        if tag == "div" and self._current and self._current.get("url") and self._current.get("title"):
            self.items.append(self._current)
            self._current = None

        if tag == "section" and self._in_opening:
            company_text = " ".join(part.strip() for part in self._opening_text if part.strip()).strip()
            if company_text:
                self.company_name = company_text
            self._in_opening = False
            self._opening_text = []

        if self._stack:
            self._stack.pop()

    def handle_data(self, data: str) -> None:
        if self._in_opening:
            self._opening_text.append(data)
        if self._capture_field is not None:
            self._capture_buffer.append(data)
