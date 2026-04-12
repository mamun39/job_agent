"""Read-only LinkedIn Jobs parser and authenticated live helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit

from job_agent.core.models import EmploymentType, JobPosting, ParsedJobDetail, ParsedJobListing, RemoteStatus, SiteCapabilities
from job_agent.sites.base import JobSiteAdapter, SupportsPageContent


_LISTING_READY_SELECTOR = ",".join(
    [
        "li.jobs-search-results__list-item",
        "li.jobs-search-results-list__list-item",
        "li.scaffold-layout__list-item",
        "div.job-card-container",
    ]
)
_DETAIL_READY_SELECTOR = ",".join(
    [
        "h1",
        "div.show-more-less-html__markup",
        "div.jobs-description__content",
        "section.jobs-box__html-content",
    ]
)
_LINKEDIN_WAIT_TIMEOUT_MS = 8000
_LINKEDIN_SETTLE_DELAY_MS = 500


class LinkedInAdapter(JobSiteAdapter):
    """Parse LinkedIn Jobs listing and detail pages."""

    def __init__(self, *, board_url: str | None = None) -> None:
        self._board_url = board_url

    @classmethod
    def from_start_url(cls, start_url: str) -> "LinkedInAdapter":
        """Build an adapter for a configured LinkedIn jobs URL."""
        return cls(board_url=start_url)

    @property
    def site_name(self) -> str:
        return "linkedin"

    @property
    def capabilities(self) -> SiteCapabilities:
        return SiteCapabilities(
            supports_listing_html_parse=True,
            supports_listing_page_parse=True,
            supports_detail_html_parse=True,
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
        document = _resolve_html(html=html, page=page)
        parser = _LinkedInListingsParser(base_url=self._board_url)
        parser.feed(document)
        parser.close()

        postings: list[JobPosting] = []
        for item in parser.items:
            metadata: dict[str, Any] = {}
            if item.get("posted_time"):
                metadata["posted_time"] = item["posted_time"]
            if item.get("workplace_type"):
                metadata["workplace_type"] = item["workplace_type"]
            workplace_type = item.get("workplace_type")
            postings.append(
                JobPosting(
                    source_site=self.site_name,
                    source_job_id=item.get("source_job_id"),
                    url=item["url"],
                    title=item.get("title") or "Unknown title",
                    company=item.get("company") or "Unknown company",
                    location=item.get("location") or "Unknown location",
                    remote_status=_infer_remote_status(workplace_type or item.get("location")),
                    posted_at=_coerce_posted_at(item.get("posted_at")),
                    description_text="Listing-only discovery from LinkedIn jobs page.",
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
        document = _resolve_html(html=html, page=page)
        parser = _LinkedInJobDetailParser(base_url=url)
        parser.feed(document)
        parser.close()

        insight_fields = _extract_detail_insight_fields(
            primary_text=parser.primary_description_text,
            insight_texts=parser.insight_texts,
        )
        title = parser.title or "Unknown title"
        company = parser.company_name or "Unknown company"
        location = parser.location or insight_fields["location"] or "Unknown location"
        workplace_type = parser.workplace_type or insight_fields["workplace_type"]
        employment_text = parser.employment_type_text or insight_fields["employment_type_text"]
        posted_time = parser.posted_time or insight_fields["posted_time"]
        metadata: dict[str, Any] = {}
        if parser.department:
            metadata["team"] = parser.department
        if workplace_type:
            metadata["workplace_type"] = workplace_type
        if employment_text:
            metadata["employment_type_text"] = employment_text
        if posted_time:
            metadata["posted_time"] = posted_time

        posting = JobPosting(
            source_site=self.site_name,
            source_job_id=_extract_linkedin_job_id(url),
            url=url,
            title=title,
            company=company,
            location=location,
            remote_status=_infer_remote_status(workplace_type or location),
            employment_type=_infer_employment_type(employment_text),
            posted_at=_coerce_posted_at(parser.posted_at),
            description_text=parser.description_text or "Listing-only discovery from LinkedIn jobs page.",
            metadata=metadata,
        )
        listing = ParsedJobListing(
            source_site=self.site_name,
            url=url,
            source_job_id=posting.source_job_id,
            title_hint=title,
            company_hint=company,
            location_hint=location,
            metadata=dict(metadata),
        )
        return ParsedJobDetail(
            listing=listing,
            posting=posting,
            raw_html=document,
            metadata={"detail_parsed": True},
        )

    def wait_for_live_listing_page(self, page: Any) -> None:
        """Wait for a LinkedIn jobs search page to expose readable cards."""
        try:
            page.wait_for_selector(_LISTING_READY_SELECTOR, timeout=_LINKEDIN_WAIT_TIMEOUT_MS)
            page.wait_for_timeout(_LINKEDIN_SETTLE_DELAY_MS)
        except Exception as exc:
            raise RuntimeError(self._build_listing_wait_error(page)) from exc

    def wait_for_live_detail_page(self, page: Any) -> None:
        """Wait for a LinkedIn jobs detail page to expose readable detail content."""
        try:
            page.wait_for_selector(_DETAIL_READY_SELECTOR, timeout=_LINKEDIN_WAIT_TIMEOUT_MS)
            page.wait_for_timeout(_LINKEDIN_SETTLE_DELAY_MS)
        except Exception as exc:
            raise RuntimeError(self._build_detail_wait_error(page)) from exc

    def _build_listing_wait_error(self, page: Any) -> str:
        html = page.content().casefold()
        if "sign in" in html or "join now" in html or "login" in html:
            return (
                "LinkedIn live discovery requires an authenticated local LinkedIn Jobs browser session. "
                "The current page did not expose readable job cards."
            )
        return (
            "LinkedIn jobs search page did not expose readable job cards in the current local browser session."
        )

    def _build_detail_wait_error(self, page: Any) -> str:
        html = page.content().casefold()
        if "sign in" in html or "join now" in html or "login" in html:
            return (
                "LinkedIn job detail page was not readable from the current local authenticated browser session."
            )
        return "LinkedIn job detail page did not expose readable title or description content."


def _resolve_html(*, html: str | None, page: SupportsPageContent | None) -> str:
    if html is not None:
        return html
    if page is not None:
        return page.content()
    raise ValueError("html or page is required")


def _coerce_posted_at(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    return None


def _parse_posted_at(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


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


def _infer_remote_status(value: str | None) -> RemoteStatus:
    normalized = (value or "").casefold()
    if "hybrid" in normalized:
        return RemoteStatus.HYBRID
    if "remote" in normalized:
        return RemoteStatus.REMOTE
    if normalized:
        return RemoteStatus.ONSITE
    return RemoteStatus.UNKNOWN


def _infer_employment_type(value: str | None) -> EmploymentType:
    normalized = (value or "").casefold()
    if "full" in normalized:
        return EmploymentType.FULL_TIME
    if "part" in normalized:
        return EmploymentType.PART_TIME
    if "contract" in normalized:
        return EmploymentType.CONTRACT
    if "intern" in normalized:
        return EmploymentType.INTERNSHIP
    if "temp" in normalized:
        return EmploymentType.TEMPORARY
    if "freelance" in normalized:
        return EmploymentType.FREELANCE
    return EmploymentType.UNKNOWN


def _is_posted_time_hint(value: str) -> bool:
    normalized = value.casefold()
    return bool(
        re.search(r"\b\d+\s+(minute|hour|day|week|month|year)s?\s+ago\b", normalized)
        or re.search(r"\breposted\b", normalized)
        or re.search(r"\bposted\b", normalized)
        or normalized == "just now"
    )


def _extract_detail_insight_fields(*, primary_text: str | None, insight_texts: list[str]) -> dict[str, str | None]:
    candidates: list[str] = []
    if primary_text:
        candidates.extend(part.strip() for part in re.split(r"[|·]", primary_text) if part.strip())
    candidates.extend(text for text in insight_texts if text)

    location: str | None = None
    workplace_type: str | None = None
    employment_type_text: str | None = None
    posted_time: str | None = None

    for raw_value in candidates:
        value = " ".join(raw_value.split())
        lowered = value.casefold()
        if posted_time is None and _is_posted_time_hint(value):
            posted_time = value
            continue
        if workplace_type is None and any(token in lowered for token in ("remote", "hybrid", "on-site", "onsite")):
            workplace_type = value
            continue
        if employment_type_text is None and any(
            token in lowered for token in ("full-time", "full time", "part-time", "part time", "contract", "intern", "temporary", "freelance")
        ):
            employment_type_text = value
            continue
        if location is None and not value.casefold().startswith("over ") and not value.casefold().startswith("more than "):
            location = value

    return {
        "location": location,
        "workplace_type": workplace_type,
        "employment_type_text": employment_type_text,
        "posted_time": posted_time,
    }


def _normalize_description_text(parts: list[str]) -> str:
    raw = "".join(parts)
    lines = [" ".join(line.split()) for line in raw.splitlines()]
    normalized_lines = [line for line in lines if line]
    return "\n".join(normalized_lines)


class _LinkedInListingsParser(HTMLParser):
    def __init__(self, *, base_url: str | None) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url or "https://www.linkedin.com"
        self.items: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None
        self._card_depth = 0
        self._capture_field: str | None = None
        self._capture_tag: str | None = None
        self._capture_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        class_attr = attrs_dict.get("class", "") or ""
        classes = set(class_attr.split())

        if tag == "li" and (
            "jobs-search-results__list-item" in classes
            or "jobs-search-results-list__list-item" in classes
            or "scaffold-layout__list-item" in classes
        ):
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
            or "job-card-list__title" in classes
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

        if tag in {"h4", "a", "div", "span"} and (
            "base-search-card__subtitle" in classes
            or "hidden-nested-link" in classes
            or "artdeco-entity-lockup__subtitle" in classes
        ):
            self._capture_field = "company"
            self._capture_tag = tag
            self._capture_buffer = []
            return

        if tag in {"span", "div"} and (
            "job-search-card__location" in classes
            or "base-search-card__metadata" in classes
            or "job-card-container__metadata-item" in classes
            or "artdeco-entity-lockup__caption" in classes
            or "job-card-container__metadata-wrapper" in classes
            or "job-card-list__footer-wrapper" in classes
        ):
            self._capture_field = "location"
            self._capture_tag = tag
            self._capture_buffer = []
            return

        if tag == "time":
            datetime_value = attrs_dict.get("datetime")
            if datetime_value:
                self._current["posted_at"] = _parse_posted_at(datetime_value)
            self._capture_field = "posted_time"
            self._capture_tag = "time"
            self._capture_buffer = []
            return

        if tag == "span" and (
            "job-search-card__workplace-type" in classes
            or "job-search-card__workplace-type-label" in classes
            or "job-card-container__metadata-item--workplace-type" in classes
        ):
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


class _LinkedInJobDetailParser(HTMLParser):
    def __init__(self, *, base_url: str | None) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title: str | None = None
        self.company_name: str | None = None
        self.location: str | None = None
        self.department: str | None = None
        self.workplace_type: str | None = None
        self.employment_type_text: str | None = None
        self.posted_time: str | None = None
        self.posted_at: datetime | None = None
        self.primary_description_text: str | None = None
        self.insight_texts: list[str] = []
        self.description_text = ""
        self._capture_field: str | None = None
        self._capture_tag: str | None = None
        self._capture_buffer: list[str] = []
        self._description_depth = 0
        self._description_parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        class_attr = attrs_dict.get("class", "") or ""
        identifier = " ".join(
            filter(None, [class_attr, attrs_dict.get("id", "") or "", attrs_dict.get("data-test-id", "") or ""])
        ).casefold()

        if tag in {"script", "style"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return

        if self._description_depth == 0 and tag in {"div", "section", "article"} and any(
            token in identifier
            for token in (
                "show-more-less-html__markup",
                "jobs-description__content",
                "jobs-box__html-content",
                "jobs-description-content",
                "description__text",
            )
        ):
            self._description_depth = 1
        elif self._description_depth > 0 and tag in {"div", "section", "article", "p", "ul", "ol", "li", "br"}:
            self._description_depth += 1

        if self.title is None and tag == "h1":
            self._start_capture("title", "h1")
            return

        if self.company_name is None and tag in {"a", "span", "div"} and any(
            token in identifier
            for token in (
                "jobs-unified-top-card__company-name",
                "jobs-details-top-card__company-url",
                "topcard__org-name-link",
                "company-name",
            )
        ):
            self._start_capture("company", tag)
            return

        if tag in {"span", "div"} and "jobs-unified-top-card__bullet" in identifier:
            self._start_capture("insight", tag)
            return

        if tag in {"span", "div"} and any(
            token in identifier
            for token in (
                "jobs-unified-top-card__primary-description",
                "job-details-jobs-unified-top-card__primary-description",
                "jobs-unified-top-card__subtitle-primary-grouping",
                "topcard__flavor",
            )
        ):
            self._start_capture("primary_description", tag)
            return

        if tag in {"span", "li", "div"} and any(
            token in identifier
            for token in (
                "job-insight",
                "job-criteria",
                "job-details-preferences-and-skills",
                "description__job-criteria-item",
                "job-details-jobs-unified-top-card__job-insight",
                "jobs-unified-top-card__job-insight",
            )
        ):
            self._start_capture("insight", tag)
            return

        if tag == "time":
            datetime_value = attrs_dict.get("datetime")
            if datetime_value:
                self.posted_at = _parse_posted_at(datetime_value)
            self._start_capture("posted_time", "time")

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth:
            if tag in {"script", "style"}:
                self._skip_depth -= 1
            return

        if self._capture_field is not None and self._capture_tag == tag:
            value = " ".join(part.strip() for part in self._capture_buffer if part.strip()).strip()
            if value:
                if self._capture_field == "title":
                    self.title = self.title or value
                elif self._capture_field == "company":
                    self.company_name = self.company_name or value
                elif self._capture_field == "primary_description":
                    self.primary_description_text = self.primary_description_text or value
                elif self._capture_field == "insight":
                    self.insight_texts.append(value)
                elif self._capture_field == "posted_time":
                    self.posted_time = self.posted_time or value
            self._capture_field = None
            self._capture_tag = None
            self._capture_buffer = []

        if self._description_depth > 0 and tag in {"div", "section", "article", "p", "ul", "ol", "li", "br"}:
            self._description_depth -= 1
            if tag in {"p", "li", "br"}:
                self._description_parts.append("\n")

        if self._description_depth == 0 and self._description_parts:
            self.description_text = _normalize_description_text(self._description_parts)

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._capture_field is not None:
            self._capture_buffer.append(data)
        if self._description_depth > 0:
            self._description_parts.append(data)

    def _start_capture(self, field: str, tag: str) -> None:
        self._capture_field = field
        self._capture_tag = tag
        self._capture_buffer = []
