"""Initial synchronous discovery flow."""

from __future__ import annotations

from collections.abc import Sequence
import logging

from job_agent.browser.fetch import fetch_listing_page_html
from job_agent.browser.session import BrowserSessionManager
from job_agent.config import load_max_pages_per_query
from job_agent.core.dedupe import deduplicate_job_postings
from job_agent.core.models import CrawlResult, DiscoveryOptions, DiscoveryQuery, DiscoveryTelemetry, JobPosting, SearchQuery
from job_agent.sites.greenhouse import GreenhouseAdapter
from job_agent.sites.lever import LeverAdapter
from job_agent.sites.base import JobSiteAdapter
from job_agent.storage.jobs_repo import JobsRepository

LOGGER = logging.getLogger(__name__)


def run_discovery(
    *,
    adapter: JobSiteAdapter,
    jobs_repo: JobsRepository,
    html: str | None = None,
    parsed_postings: Sequence[JobPosting] | None = None,
) -> CrawlResult:
    """Parse, deduplicate, and store jobs for one adapter run."""
    telemetry = DiscoveryTelemetry(queries_attempted=1)
    return _run_discovery_with_telemetry(
        adapter=adapter,
        jobs_repo=jobs_repo,
        html=html,
        parsed_postings=parsed_postings,
        telemetry=telemetry,
    )


def _run_discovery_with_telemetry(
    *,
    adapter: JobSiteAdapter,
    jobs_repo: JobsRepository,
    html: str | None = None,
    parsed_postings: Sequence[JobPosting] | None = None,
    telemetry: DiscoveryTelemetry,
) -> CrawlResult:
    """Parse, deduplicate, and store jobs for one adapter run."""
    if parsed_postings is None and html is None:
        raise ValueError("html or parsed_postings is required")

    jobs_repo.initialize_schema()

    try:
        extracted_postings = list(parsed_postings) if parsed_postings is not None else adapter.parse_job_postings(html=html)
    except Exception:
        LOGGER.exception(
            "parse_failed",
            extra={"event": "parse_failed", "source_site": adapter.site_name, "stage": "listing_parse"},
        )
        raise
    deduplicated_postings = deduplicate_job_postings(extracted_postings)
    telemetry.jobs_parsed = len(extracted_postings)
    telemetry.jobs_skipped_duplicates = len(extracted_postings) - len(deduplicated_postings)

    stored_postings: list[JobPosting] = []
    for posting in deduplicated_postings:
        try:
            stored, inserted = jobs_repo.upsert_job_with_status(posting)
        except Exception:
            LOGGER.exception(
                "storage_failed",
                extra={
                    "event": "storage_failed",
                    "source_site": adapter.site_name,
                    "url": posting.url.unicode_string(),
                    "source_job_id": posting.source_job_id,
                },
            )
            raise
        stored_postings.append(stored)
        if inserted:
            telemetry.jobs_inserted += 1
        else:
            telemetry.jobs_updated += 1

    return CrawlResult(
        query=SearchQuery(),
        postings=stored_postings,
        source_site=adapter.site_name,
        success=True,
        metadata={
            "parsed_count": len(extracted_postings),
            "deduplicated_count": len(deduplicated_postings),
            "duplicate_count": len(extracted_postings) - len(deduplicated_postings),
            "stored_count": len(stored_postings),
            "inserted_count": telemetry.jobs_inserted,
            "updated_count": telemetry.jobs_updated,
            **telemetry.as_metadata(),
        },
    )


def build_adapter_for_query(query: DiscoveryQuery) -> JobSiteAdapter:
    """Create the matching site adapter for a configured discovery query."""
    if query.source_site == "greenhouse":
        return GreenhouseAdapter.from_start_url(str(query.start_url))
    if query.source_site == "lever":
        return LeverAdapter.from_start_url(str(query.start_url))
    raise ValueError(f"Unsupported source_site: {query.source_site}")


def run_discovery_query(
    *,
    query: DiscoveryQuery,
    session: BrowserSessionManager,
    jobs_repo: JobsRepository,
    screenshot_name: str | None = None,
    max_pages_per_query: int | None = None,
    options: DiscoveryOptions | None = None,
) -> CrawlResult:
    """Fetch a configured listing page, parse it with the matching adapter, and store jobs."""
    adapter = build_adapter_for_query(query)
    options = options or DiscoveryOptions()
    telemetry = DiscoveryTelemetry(queries_attempted=1)
    if isinstance(adapter, GreenhouseAdapter):
        result = _run_greenhouse_discovery_query(
            adapter=adapter,
            query=query,
            session=session,
            jobs_repo=jobs_repo,
            screenshot_name=screenshot_name,
            max_pages_per_query=max_pages_per_query or load_max_pages_per_query(),
            enrich_details=options.enrich_greenhouse_details,
            telemetry=telemetry,
        )
    elif isinstance(adapter, LeverAdapter):
        result = _run_lever_discovery_query(
            adapter=adapter,
            query=query,
            session=session,
            jobs_repo=jobs_repo,
            screenshot_name=screenshot_name,
            max_pages_per_query=max_pages_per_query or load_max_pages_per_query(),
            enrich_details=options.enrich_lever_details,
            telemetry=telemetry,
        )
    else:
        try:
            html = fetch_listing_page_html(
                session=session,
                url=str(query.start_url),
                screenshot_name=screenshot_name,
            )
            telemetry.pages_fetched += 1
        except Exception:
            telemetry.pages_failed += 1
            raise
        result = _run_discovery_with_telemetry(adapter=adapter, jobs_repo=jobs_repo, html=html, telemetry=telemetry)
        result.metadata.update({"pages_parsed": 1 if result.metadata["parsed_count"] > 0 else 0})
    result.metadata.update(
        {
            **telemetry.as_metadata(),
            "label": query.label,
            "start_url": str(query.start_url),
            "include_keywords": list(query.include_keywords),
            "exclude_keywords": list(query.exclude_keywords),
            "location_hints": list(query.location_hints),
        }
    )
    result.query = SearchQuery(
        keywords=list(query.include_keywords),
        location=query.location_hints[0] if query.location_hints else None,
    )
    return result


def _run_greenhouse_discovery_query(
    *,
    adapter: GreenhouseAdapter,
    query: DiscoveryQuery,
    session: BrowserSessionManager,
    jobs_repo: JobsRepository,
    screenshot_name: str | None,
    max_pages_per_query: int,
    enrich_details: bool,
    telemetry: DiscoveryTelemetry,
) -> CrawlResult:
    page_limit = max(1, max_pages_per_query)
    next_url: str | None = str(query.start_url)
    visited_urls: set[str] = set()
    aggregated_postings: list[JobPosting] = []
    pages_fetched = 0
    pages_parsed = 0

    while next_url is not None and pages_fetched < page_limit:
        if next_url in visited_urls:
            break

        try:
            html = fetch_listing_page_html(
                session=session,
                url=next_url,
                screenshot_name=screenshot_name if pages_fetched == 0 else None,
            )
        except Exception:
            LOGGER.exception(
                "fetch_failed",
                extra={"event": "fetch_failed", "source_site": adapter.site_name, "url": next_url, "stage": "listing_fetch"},
            )
            telemetry.pages_failed += 1
            if pages_fetched == 0:
                raise
            LOGGER.warning(
                "skipped_page",
                extra={"event": "skipped_page", "source_site": adapter.site_name, "url": next_url, "reason": "fetch_failed"},
            )
            break

        visited_urls.add(next_url)
        pages_fetched += 1
        telemetry.pages_fetched += 1

        try:
            postings = adapter.parse_job_postings(html=html)
        except Exception:
            LOGGER.exception(
                "parse_failed",
                extra={"event": "parse_failed", "source_site": adapter.site_name, "stage": "listing_parse", "url": next_url},
            )
            raise
        if postings:
            aggregated_postings.extend(postings)
            pages_parsed += 1
        elif pages_parsed > 0:
            LOGGER.warning(
                "skipped_page",
                extra={"event": "skipped_page", "source_site": adapter.site_name, "url": next_url, "reason": "empty_parse_after_success"},
            )
            break

        candidate_next_url = adapter.find_next_page_url(html=html, current_url=next_url)
        if candidate_next_url is None:
            break
        if candidate_next_url in visited_urls:
            LOGGER.warning(
                "skipped_page",
                extra={"event": "skipped_page", "source_site": adapter.site_name, "url": candidate_next_url, "reason": "repeated_page"},
            )
            break
        next_url = candidate_next_url

    if enrich_details and aggregated_postings:
        aggregated_postings = _enrich_greenhouse_postings(
            adapter=adapter,
            session=session,
            postings=aggregated_postings,
            telemetry=telemetry,
        )

    result = _run_discovery_with_telemetry(
        adapter=adapter,
        jobs_repo=jobs_repo,
        parsed_postings=aggregated_postings,
        telemetry=telemetry,
    )
    result.metadata.update(
        {
            "pages_parsed": pages_parsed,
        }
    )
    return result


def _enrich_greenhouse_postings(
    *,
    adapter: GreenhouseAdapter,
    session: BrowserSessionManager,
    postings: list[JobPosting],
    telemetry: DiscoveryTelemetry,
) -> list[JobPosting]:
    enriched_postings: list[JobPosting] = []
    for posting in postings:
        try:
            html = fetch_listing_page_html(session=session, url=posting.url.unicode_string())
            telemetry.detail_pages_fetched += 1
        except Exception:
            LOGGER.exception(
                "fetch_failed",
                extra={"event": "fetch_failed", "source_site": adapter.site_name, "url": posting.url.unicode_string(), "stage": "detail_fetch"},
            )
            telemetry.detail_parse_failures += 1
            enriched_postings.append(posting)
            continue
        try:
            detail = adapter.parse_job_detail(url=posting.url.unicode_string(), html=html)
            enriched_postings.append(_merge_detail_into_listing(posting, detail.posting))
        except Exception:
            LOGGER.exception(
                "parse_failed",
                extra={"event": "parse_failed", "source_site": adapter.site_name, "stage": "detail_parse", "url": posting.url.unicode_string()},
            )
            telemetry.detail_parse_failures += 1
            enriched_postings.append(posting)
    return enriched_postings


def _merge_detail_into_listing(listing_posting: JobPosting, detail_posting: JobPosting) -> JobPosting:
    metadata = dict(listing_posting.metadata)
    metadata.update(detail_posting.metadata)
    return listing_posting.model_copy(
        update={
            "location": _prefer_detail_text(detail_posting.location, listing_posting.location),
            "remote_status": _prefer_detail_enum(detail_posting.remote_status, listing_posting.remote_status),
            "employment_type": _prefer_detail_enum(detail_posting.employment_type, listing_posting.employment_type),
            "seniority": _prefer_detail_enum(detail_posting.seniority, listing_posting.seniority),
            "description_text": _prefer_detail_description(detail_posting.description_text, listing_posting.description_text),
            "metadata": metadata,
        }
    )


def _prefer_detail_text(detail_value: str, listing_value: str) -> str:
    if detail_value.strip().casefold().startswith("unknown"):
        return listing_value
    return detail_value


def _prefer_detail_enum(detail_value: object, listing_value: object) -> object:
    if getattr(detail_value, "value", None) == "unknown":
        return listing_value
    return detail_value


def _prefer_detail_description(detail_value: str, listing_value: str) -> str:
    if detail_value.startswith("Listing-only discovery from "):
        return listing_value
    return detail_value


def _run_lever_discovery_query(
    *,
    adapter: LeverAdapter,
    query: DiscoveryQuery,
    session: BrowserSessionManager,
    jobs_repo: JobsRepository,
    screenshot_name: str | None,
    max_pages_per_query: int,
    enrich_details: bool,
    telemetry: DiscoveryTelemetry,
) -> CrawlResult:
    page_limit = max(1, max_pages_per_query)
    next_url: str | None = str(query.start_url)
    visited_urls: set[str] = set()
    aggregated_postings: list[JobPosting] = []
    pages_fetched = 0
    pages_parsed = 0

    while next_url is not None and pages_fetched < page_limit:
        if next_url in visited_urls:
            break

        try:
            html = fetch_listing_page_html(
                session=session,
                url=next_url,
                screenshot_name=screenshot_name if pages_fetched == 0 else None,
            )
        except Exception:
            LOGGER.exception(
                "fetch_failed",
                extra={"event": "fetch_failed", "source_site": adapter.site_name, "url": next_url, "stage": "listing_fetch"},
            )
            telemetry.pages_failed += 1
            if pages_fetched == 0:
                raise
            LOGGER.warning(
                "skipped_page",
                extra={"event": "skipped_page", "source_site": adapter.site_name, "url": next_url, "reason": "fetch_failed"},
            )
            break

        visited_urls.add(next_url)
        pages_fetched += 1
        telemetry.pages_fetched += 1

        try:
            postings = adapter.parse_job_postings(html=html)
        except Exception:
            LOGGER.exception(
                "parse_failed",
                extra={"event": "parse_failed", "source_site": adapter.site_name, "stage": "listing_parse", "url": next_url},
            )
            raise
        if postings:
            aggregated_postings.extend(postings)
            pages_parsed += 1
        elif pages_parsed > 0:
            LOGGER.warning(
                "skipped_page",
                extra={"event": "skipped_page", "source_site": adapter.site_name, "url": next_url, "reason": "empty_parse_after_success"},
            )
            break

        candidate_next_url = adapter.find_next_page_url(html=html, current_url=next_url)
        if candidate_next_url is None:
            break
        if candidate_next_url in visited_urls:
            LOGGER.warning(
                "skipped_page",
                extra={"event": "skipped_page", "source_site": adapter.site_name, "url": candidate_next_url, "reason": "repeated_page"},
            )
            break
        next_url = candidate_next_url

    if enrich_details and aggregated_postings:
        aggregated_postings = _enrich_lever_postings(
            adapter=adapter,
            session=session,
            postings=aggregated_postings,
            telemetry=telemetry,
        )

    result = _run_discovery_with_telemetry(
        adapter=adapter,
        jobs_repo=jobs_repo,
        parsed_postings=aggregated_postings,
        telemetry=telemetry,
    )
    result.metadata.update(
        {
            "pages_parsed": pages_parsed,
        }
    )
    return result


def _enrich_lever_postings(
    *,
    adapter: LeverAdapter,
    session: BrowserSessionManager,
    postings: list[JobPosting],
    telemetry: DiscoveryTelemetry,
) -> list[JobPosting]:
    enriched_postings: list[JobPosting] = []
    for posting in postings:
        try:
            html = fetch_listing_page_html(session=session, url=posting.url.unicode_string())
            telemetry.detail_pages_fetched += 1
        except Exception:
            LOGGER.exception(
                "fetch_failed",
                extra={"event": "fetch_failed", "source_site": adapter.site_name, "url": posting.url.unicode_string(), "stage": "detail_fetch"},
            )
            telemetry.detail_parse_failures += 1
            enriched_postings.append(posting)
            continue
        try:
            detail = adapter.parse_job_detail(url=posting.url.unicode_string(), html=html)
            enriched_postings.append(_merge_detail_into_listing(posting, detail.posting))
        except Exception:
            LOGGER.exception(
                "parse_failed",
                extra={"event": "parse_failed", "source_site": adapter.site_name, "stage": "detail_parse", "url": posting.url.unicode_string()},
            )
            telemetry.detail_parse_failures += 1
            enriched_postings.append(posting)
    return enriched_postings
