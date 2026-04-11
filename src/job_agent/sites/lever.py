"""Read-only Lever jobs page parser."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

from job_agent.core.models import JobPosting, ParsedJobDetail, ParsedJobListing, SiteCapabilities
from job_agent.sites.base import JobSiteAdapter, SupportsPageContent


class LeverAdapter(JobSiteAdapter):
    """Parse Lever-hosted job listings from HTML."""

    def __init__(self, *, board_url: str | None = None, company_name: str | None = None) -> None:
        self._board_url = board_url
        self._company_name = company_name

    @classmethod
    def from_start_url(cls, start_url: str) -> LeverAdapter:
        """Build an adapter for a configured Lever listing URL."""
        return cls(board_url=start_url)

    @property
    def site_name(self) -> str:
        return "lever"

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
        parser = _LeverListingsParser(base_url=self._board_url)
        parser.feed(document)
        parser.close()

        company_name = self._company_name or parser.company_name or _infer_company_from_board_url(self._board_url)
        listings: list[ParsedJobListing] = []
        for item in parser.items:
            metadata: dict[str, Any] = {}
            if item.get("department"):
                metadata["team"] = item["department"]
            listings.append(
                ParsedJobListing(
                    source_site=self.site_name,
                    url=item["url"],
                    source_job_id=item.get("source_job_id"),
                    title_hint=item.get("title"),
                    company_hint=company_name,
                    location_hint=item.get("location"),
                    department_hint=item.get("department"),
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
            metadata = dict(listing.metadata)
            postings.append(
                JobPosting(
                    source_site=self.site_name,
                    source_job_id=listing.source_job_id,
                    url=str(listing.url),
                    title=listing.title_hint or "Unknown title",
                    company=listing.company_hint or "Unknown company",
                    location=listing.location_hint or "Unknown location",
                    description_text="Listing-only discovery from Lever jobs page.",
                    metadata=metadata,
                )
            )
        return postings

    def find_next_page_url(
        self,
        *,
        html: str | None = None,
        page: SupportsPageContent | None = None,
        current_url: str | None = None,
    ) -> str | None:
        """Return the next listing page URL when pagination is exposed."""
        document = _resolve_html(html=html, page=page)
        parser = _LeverPaginationParser(base_url=current_url or self._board_url)
        parser.feed(document)
        parser.close()
        return parser.next_page_url

    def parse_job_detail(
        self,
        *,
        url: str,
        html: str | None = None,
        page: SupportsPageContent | None = None,
    ) -> ParsedJobDetail:
        raise NotImplementedError("LeverAdapter does not parse detail pages in this task")


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
    if hostname.startswith("jobs.lever.co"):
        slug = urlsplit(board_url).path.strip("/").split("/", 1)[0]
        if slug:
            return slug.replace("-", " ").replace("_", " ").title()
    return None


class _LeverListingsParser(HTMLParser):
    def __init__(self, *, base_url: str | None) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.items: list[dict[str, str]] = []
        self.company_name: str | None = None
        self._current: dict[str, str] | None = None
        self._current_depth = 0
        self._pending_url: str | None = None
        self._pending_source_job_id: str | None = None
        self._capture_field: str | None = None
        self._capture_tag: str | None = None
        self._capture_buffer: list[str] = []
        self._capture_company = False
        self._company_buffer: list[str] = []
        self._current_department: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        class_attr = attrs_dict.get("class", "") or ""
        classes = set(class_attr.split())

        if tag in {"h2", "h3", "div"} and ("main-header-text" in classes or "posting-headline" in classes):
            self._capture_company = True
            self._company_buffer = []

        if tag == "div" and "posting-category-title" in classes:
            self._capture_field = "group_department"
            self._capture_tag = "div"
            self._capture_buffer = []
            return

        if tag == "a" and "posting-btn-submit" in classes and self._current is None:
            href = attrs_dict.get("href")
            if href:
                resolved_url = urljoin(self.base_url or "", href)
                self._pending_url = resolved_url
                self._pending_source_job_id = resolved_url.rstrip("/").split("/")[-1]
            return

        if tag == "div" and "posting" in classes and self._current is None:
            self._current = {}
            self._current_depth = 1
            if self._pending_url:
                self._current["url"] = self._pending_url
            if self._pending_source_job_id:
                self._current["source_job_id"] = self._pending_source_job_id
            posting_id = attrs_dict.get("data-qa-posting-id")
            if posting_id:
                self._current["source_job_id"] = posting_id
            if self._current_department:
                self._current["department"] = self._current_department
            return

        if self._current is None:
            return

        if tag == "div":
            self._current_depth += 1

        if tag == "a" and ("posting-title" in classes or "posting-btn-submit" in classes):
            href = attrs_dict.get("href")
            if href and "url" not in self._current:
                resolved_url = urljoin(self.base_url or "", href)
                self._current["url"] = resolved_url
                self._current.setdefault("source_job_id", resolved_url.rstrip("/").split("/")[-1])
            return

        if tag == "h5" and ("posting-name" in classes or attrs_dict.get("data-qa") == "posting-name"):
            self._capture_field = "title"
            self._capture_tag = "h5"
            self._capture_buffer = []
            return

        if tag == "span" and "sort-by-location" in classes:
            self._capture_field = "location"
            self._capture_tag = "span"
            self._capture_buffer = []
            return

        if tag == "span" and "workplaceTypes" in classes:
            self._capture_field = "workplace_type"
            self._capture_tag = "span"
            self._capture_buffer = []
            return

        if tag == "span" and ("sort-by-team" in classes or "sort-by-commitment" in classes):
            if "department" not in self._current:
                self._capture_field = "department"
                self._capture_tag = "span"
                self._capture_buffer = []

    def handle_endtag(self, tag: str) -> None:
        if self._capture_field is not None and self._capture_tag == tag:
            value = " ".join(part.strip() for part in self._capture_buffer if part.strip()).strip()
            if value:
                if self._capture_field == "group_department":
                    self._current_department = value
                elif self._current is not None:
                    self._current[self._capture_field] = value
            self._capture_field = None
            self._capture_tag = None
            self._capture_buffer = []

        if tag == "div" and self._current is not None:
            self._current_depth -= 1
            if self._current_depth == 0:
                if self._current.get("url") and self._current.get("title"):
                    self.items.append(self._current)
                self._current = None
                self._pending_url = None
                self._pending_source_job_id = None

        if self._capture_company and tag in {"h2", "h3", "div"}:
            company_text = " ".join(part.strip() for part in self._company_buffer if part.strip()).strip()
            if company_text:
                self.company_name = company_text
            self._capture_company = False
            self._company_buffer = []

    def handle_data(self, data: str) -> None:
        if self._capture_field is not None:
            self._capture_buffer.append(data)
        if self._capture_company:
            self._company_buffer.append(data)


class _LeverPaginationParser(HTMLParser):
    def __init__(self, *, base_url: str | None) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.next_page_url: str | None = None
        self._capture_anchor = False
        self._anchor_text: list[str] = []
        self._anchor_href: str | None = None
        self._anchor_has_next_hint = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.next_page_url is not None or tag != "a":
            return

        attrs_dict = dict(attrs)
        href = attrs_dict.get("href")
        if not href:
            return

        class_attr = attrs_dict.get("class", "") or ""
        rel_attr = attrs_dict.get("rel", "") or ""
        aria_label = attrs_dict.get("aria-label", "") or ""
        title_attr = attrs_dict.get("title", "") or ""
        data_qa = attrs_dict.get("data-qa", "") or ""
        hint_tokens = " ".join([class_attr, rel_attr, aria_label, title_attr, data_qa]).casefold()

        self._capture_anchor = True
        self._anchor_text = []
        self._anchor_href = href
        self._anchor_has_next_hint = "next" in hint_tokens

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._capture_anchor or self._anchor_href is None:
            return

        anchor_text = " ".join(part.strip() for part in self._anchor_text if part.strip()).casefold()
        if self._anchor_has_next_hint or anchor_text.startswith("next"):
            self.next_page_url = urljoin(self.base_url or "", self._anchor_href)

        self._capture_anchor = False
        self._anchor_text = []
        self._anchor_href = None
        self._anchor_has_next_hint = False

    def handle_data(self, data: str) -> None:
        if self._capture_anchor:
            self._anchor_text.append(data)
