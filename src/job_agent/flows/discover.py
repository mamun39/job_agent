"""Initial synchronous discovery flow."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
import logging
from pathlib import Path

from job_agent.browser.fetch import capture_debug_artifacts, fetch_listing_page_html
from job_agent.browser.session import BrowserSessionManager
from job_agent.config import load_max_pages_per_query, load_settings
from job_agent.core.dedupe import canonicalize_url
from job_agent.core.dedupe import deduplicate_job_postings
from job_agent.core.models import CrawlResult, DiscoveryOptions, DiscoveryQuery, DiscoveryTelemetry, JobPosting, SearchQuery
from job_agent.sites.greenhouse import GreenhouseAdapter
from job_agent.sites.base import JobSiteAdapter
from job_agent.sites.lever import LeverAdapter
from job_agent.sites.linkedin import LinkedInAdapter
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
    if query.source_site == "linkedin":
        return LinkedInAdapter.from_start_url(str(query.start_url))
    raise ValueError(f"Unsupported source_site: {query.source_site}")


def run_discovery_query(
    *,
    query: DiscoveryQuery,
    session: BrowserSessionManager,
    jobs_repo: JobsRepository,
    screenshot_name: str | None = None,
    max_pages_per_query: int | None = None,
    options: DiscoveryOptions | None = None,
    debug_artifacts_on_failure: bool | None = None,
    debug_artifacts_dir: str | Path | None = None,
) -> CrawlResult:
    """Fetch a configured listing page, parse it with the matching adapter, and store jobs."""
    adapter = build_adapter_for_query(query)
    options = options or DiscoveryOptions()
    settings = load_settings() if debug_artifacts_on_failure is None or debug_artifacts_dir is None else None
    capture_failure_artifacts = (
        debug_artifacts_on_failure
        if debug_artifacts_on_failure is not None
        else bool(settings and settings.debug_artifacts_on_failure)
    )
    artifact_dir = Path(debug_artifacts_dir) if debug_artifacts_dir is not None else (
        settings.debug_artifacts_dir if settings is not None else Path("./data/debug_artifacts")
    )
    telemetry = DiscoveryTelemetry(queries_attempted=1)
    artifact_timestamp = datetime.now(UTC)
    if isinstance(adapter, GreenhouseAdapter):
        result = _run_greenhouse_discovery_query(
            adapter=adapter,
            query=query,
            session=session,
            jobs_repo=jobs_repo,
            screenshot_name=screenshot_name,
            max_pages_per_query=max_pages_per_query or load_max_pages_per_query(),
            enrich_details=options.enrich_greenhouse_details,
            selective_detail_enrichment=options.selective_detail_enrichment,
            min_listing_stage_score=options.min_listing_stage_score_for_detail_enrichment,
            telemetry=telemetry,
            capture_failure_artifacts=capture_failure_artifacts,
            artifact_dir=artifact_dir,
            artifact_timestamp=artifact_timestamp,
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
            selective_detail_enrichment=options.selective_detail_enrichment,
            min_listing_stage_score=options.min_listing_stage_score_for_detail_enrichment,
            telemetry=telemetry,
            capture_failure_artifacts=capture_failure_artifacts,
            artifact_dir=artifact_dir,
            artifact_timestamp=artifact_timestamp,
        )
    elif isinstance(adapter, LinkedInAdapter):
        result = _run_linkedin_discovery_query(
            adapter=adapter,
            query=query,
            session=session,
            jobs_repo=jobs_repo,
            screenshot_name=screenshot_name,
            telemetry=telemetry,
            capture_failure_artifacts=capture_failure_artifacts,
            artifact_dir=artifact_dir,
            artifact_timestamp=artifact_timestamp,
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
            captured_dir = _capture_failure_artifacts(
                enabled=capture_failure_artifacts,
                session=session,
                artifact_dir=artifact_dir,
                site_name=adapter.site_name,
                query_label=query.label,
                artifact_name="listing_fetch_failure",
                artifact_timestamp=artifact_timestamp,
            )
            if captured_dir is not None:
                setattr(exc := _current_exception(), "debug_artifact_dir", str(captured_dir))
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


def _run_linkedin_discovery_query(
    *,
    adapter: LinkedInAdapter,
    query: DiscoveryQuery,
    session: BrowserSessionManager,
    jobs_repo: JobsRepository,
    screenshot_name: str | None,
    telemetry: DiscoveryTelemetry,
    capture_failure_artifacts: bool,
    artifact_dir: Path,
    artifact_timestamp: datetime,
) -> CrawlResult:
    if getattr(session, "auth_mode", None) is None:
        raise RuntimeError(
            "LinkedIn live discovery requires authenticated local Chromium reuse. "
            "Use --auth-browser profile or --auth-browser attach."
        )

    artifact_dirs: set[str] = set()
    try:
        listing_html = _fetch_linkedin_live_listing_html(
            session=session,
            adapter=adapter,
            url=str(query.start_url),
            screenshot_name=screenshot_name,
        )
        telemetry.pages_fetched += 1
    except Exception:
        LOGGER.exception(
            "fetch_failed",
            extra={"event": "fetch_failed", "source_site": adapter.site_name, "url": str(query.start_url), "stage": "listing_fetch"},
        )
        telemetry.pages_failed += 1
        captured_dir = _capture_failure_artifacts(
            enabled=capture_failure_artifacts,
            session=session,
            artifact_dir=artifact_dir,
            site_name=adapter.site_name,
            query_label=query.label,
            artifact_name="listing_fetch_failure_page_1",
            artifact_timestamp=artifact_timestamp,
        )
        if captured_dir is not None:
            artifact_dirs.add(str(captured_dir))
            setattr(exc := _current_exception(), "debug_artifact_dir", str(captured_dir))
        raise

    try:
        listing_postings = adapter.parse_job_postings(html=listing_html)
    except Exception:
        LOGGER.exception(
            "parse_failed",
            extra={"event": "parse_failed", "source_site": adapter.site_name, "stage": "listing_parse", "url": str(query.start_url)},
        )
        captured_dir = _capture_failure_artifacts(
            enabled=capture_failure_artifacts,
            session=session,
            artifact_dir=artifact_dir,
            site_name=adapter.site_name,
            query_label=query.label,
            artifact_name="listing_parse_failure_page_1",
            html=listing_html,
            artifact_timestamp=artifact_timestamp,
        )
        if captured_dir is not None:
            artifact_dirs.add(str(captured_dir))
            setattr(exc := _current_exception(), "debug_artifact_dir", str(captured_dir))
        raise

    enriched_postings: list[JobPosting] = []
    if listing_postings:
        telemetry.detail_enrichment_selected += len(listing_postings)
    for posting in listing_postings:
        detail_url = canonicalize_url(posting.url.unicode_string(), source_site=adapter.site_name)
        telemetry.detail_fetch_attempts += 1
        try:
            detail_html = _fetch_linkedin_live_detail_html(
                session=session,
                adapter=adapter,
                url=detail_url,
            )
            telemetry.detail_pages_fetched += 1
        except Exception:
            LOGGER.exception(
                "fetch_failed",
                extra={"event": "fetch_failed", "source_site": adapter.site_name, "url": detail_url, "stage": "detail_fetch"},
            )
            telemetry.detail_parse_failures += 1
            captured_dir = _capture_failure_artifacts(
                enabled=capture_failure_artifacts,
                session=session,
                artifact_dir=artifact_dir,
                site_name=adapter.site_name,
                query_label=query.label,
                artifact_name=f"detail_fetch_failure_{posting.source_job_id or 'job'}",
                artifact_timestamp=artifact_timestamp,
            )
            if captured_dir is not None:
                artifact_dirs.add(str(captured_dir))
            enriched_postings.append(posting)
            continue
        try:
            detail = adapter.parse_job_detail(url=detail_url, html=detail_html)
            telemetry.detail_enrichment_successes += 1
            enriched_postings.append(_merge_detail_into_listing(posting, detail.posting))
        except Exception:
            LOGGER.exception(
                "parse_failed",
                extra={"event": "parse_failed", "source_site": adapter.site_name, "stage": "detail_parse", "url": detail_url},
            )
            telemetry.detail_parse_failures += 1
            captured_dir = _capture_failure_artifacts(
                enabled=capture_failure_artifacts,
                session=session,
                artifact_dir=artifact_dir,
                site_name=adapter.site_name,
                query_label=query.label,
                artifact_name=f"detail_parse_failure_{posting.source_job_id or 'job'}",
                html=detail_html,
                artifact_timestamp=artifact_timestamp,
            )
            if captured_dir is not None:
                artifact_dirs.add(str(captured_dir))
            enriched_postings.append(posting)

    result = _run_discovery_with_telemetry(
        adapter=adapter,
        jobs_repo=jobs_repo,
        parsed_postings=enriched_postings or listing_postings,
        telemetry=telemetry,
    )
    result.metadata.update(
        {
            "pages_parsed": 1 if listing_postings else 0,
            "debug_artifact_count": len(artifact_dirs),
            "debug_artifact_dirs": sorted(artifact_dirs),
        }
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
    selective_detail_enrichment: bool,
    min_listing_stage_score: int,
    telemetry: DiscoveryTelemetry,
    capture_failure_artifacts: bool,
    artifact_dir: Path,
    artifact_timestamp: datetime,
) -> CrawlResult:
    page_limit = max(1, max_pages_per_query)
    next_url: str | None = str(query.start_url)
    visited_urls: set[str] = set()
    aggregated_postings: list[JobPosting] = []
    pages_fetched = 0
    pages_parsed = 0
    artifact_dirs: set[str] = set()

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
            captured_dir = _capture_failure_artifacts(
                enabled=capture_failure_artifacts,
                session=session,
                artifact_dir=artifact_dir,
                site_name=adapter.site_name,
                query_label=query.label,
                artifact_name=f"listing_fetch_failure_page_{pages_fetched + 1}",
                artifact_timestamp=artifact_timestamp,
            )
            if captured_dir is not None:
                artifact_dirs.add(str(captured_dir))
                setattr(exc := _current_exception(), "debug_artifact_dir", str(captured_dir))
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
            captured_dir = _capture_failure_artifacts(
                enabled=capture_failure_artifacts,
                session=session,
                artifact_dir=artifact_dir,
                site_name=adapter.site_name,
                query_label=query.label,
                artifact_name=f"listing_parse_failure_page_{pages_fetched}",
                html=html,
                artifact_timestamp=artifact_timestamp,
            )
            if captured_dir is not None:
                artifact_dirs.add(str(captured_dir))
                setattr(exc := _current_exception(), "debug_artifact_dir", str(captured_dir))
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
            query=query,
            session=session,
            postings=aggregated_postings,
            telemetry=telemetry,
            capture_failure_artifacts=capture_failure_artifacts,
            artifact_dir=artifact_dir,
            query_label=query.label,
            artifact_timestamp=artifact_timestamp,
            artifact_dirs=artifact_dirs,
            selective=selective_detail_enrichment,
            min_listing_stage_score=min_listing_stage_score,
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
            "debug_artifact_count": len(artifact_dirs),
            "debug_artifact_dirs": sorted(artifact_dirs),
        }
    )
    return result


def _enrich_greenhouse_postings(
    *,
    adapter: GreenhouseAdapter,
    query: DiscoveryQuery,
    session: BrowserSessionManager,
    postings: list[JobPosting],
    telemetry: DiscoveryTelemetry,
    capture_failure_artifacts: bool,
    artifact_dir: Path,
    query_label: str,
    artifact_timestamp: datetime,
    artifact_dirs: set[str],
    selective: bool,
    min_listing_stage_score: int,
) -> list[JobPosting]:
    enriched_postings: list[JobPosting] = []
    selected_postings = _select_postings_for_detail_enrichment(
        query=query,
        postings=postings,
        selective=selective,
        min_listing_stage_score=min_listing_stage_score,
    )
    telemetry.detail_enrichment_selected += len(selected_postings)
    selected_urls = {posting.url.unicode_string() for posting in selected_postings}
    for posting in postings:
        if posting.url.unicode_string() not in selected_urls:
            enriched_postings.append(posting)
            continue
        telemetry.detail_fetch_attempts += 1
        try:
            html = fetch_listing_page_html(session=session, url=posting.url.unicode_string())
            telemetry.detail_pages_fetched += 1
        except Exception:
            LOGGER.exception(
                "fetch_failed",
                extra={"event": "fetch_failed", "source_site": adapter.site_name, "url": posting.url.unicode_string(), "stage": "detail_fetch"},
            )
            telemetry.detail_parse_failures += 1
            captured_dir = _capture_failure_artifacts(
                enabled=capture_failure_artifacts,
                session=session,
                artifact_dir=artifact_dir,
                site_name=adapter.site_name,
                query_label=query_label,
                artifact_name=f"detail_fetch_failure_{posting.source_job_id or 'job'}",
                artifact_timestamp=artifact_timestamp,
            )
            if captured_dir is not None:
                artifact_dirs.add(str(captured_dir))
            enriched_postings.append(posting)
            continue
        try:
            detail = adapter.parse_job_detail(url=posting.url.unicode_string(), html=html)
            telemetry.detail_enrichment_successes += 1
            enriched_postings.append(_merge_detail_into_listing(posting, detail.posting))
        except Exception:
            LOGGER.exception(
                "parse_failed",
                extra={"event": "parse_failed", "source_site": adapter.site_name, "stage": "detail_parse", "url": posting.url.unicode_string()},
            )
            telemetry.detail_parse_failures += 1
            captured_dir = _capture_failure_artifacts(
                enabled=capture_failure_artifacts,
                session=session,
                artifact_dir=artifact_dir,
                site_name=adapter.site_name,
                query_label=query_label,
                artifact_name=f"detail_parse_failure_{posting.source_job_id or 'job'}",
                html=html,
                artifact_timestamp=artifact_timestamp,
            )
            if captured_dir is not None:
                artifact_dirs.add(str(captured_dir))
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
    selective_detail_enrichment: bool,
    min_listing_stage_score: int,
    telemetry: DiscoveryTelemetry,
    capture_failure_artifacts: bool,
    artifact_dir: Path,
    artifact_timestamp: datetime,
) -> CrawlResult:
    page_limit = max(1, max_pages_per_query)
    next_url: str | None = str(query.start_url)
    visited_urls: set[str] = set()
    aggregated_postings: list[JobPosting] = []
    pages_fetched = 0
    pages_parsed = 0
    artifact_dirs: set[str] = set()

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
            captured_dir = _capture_failure_artifacts(
                enabled=capture_failure_artifacts,
                session=session,
                artifact_dir=artifact_dir,
                site_name=adapter.site_name,
                query_label=query.label,
                artifact_name=f"listing_fetch_failure_page_{pages_fetched + 1}",
                artifact_timestamp=artifact_timestamp,
            )
            if captured_dir is not None:
                artifact_dirs.add(str(captured_dir))
                setattr(exc := _current_exception(), "debug_artifact_dir", str(captured_dir))
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
            captured_dir = _capture_failure_artifacts(
                enabled=capture_failure_artifacts,
                session=session,
                artifact_dir=artifact_dir,
                site_name=adapter.site_name,
                query_label=query.label,
                artifact_name=f"listing_parse_failure_page_{pages_fetched}",
                html=html,
                artifact_timestamp=artifact_timestamp,
            )
            if captured_dir is not None:
                artifact_dirs.add(str(captured_dir))
                setattr(exc := _current_exception(), "debug_artifact_dir", str(captured_dir))
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
            query=query,
            session=session,
            postings=aggregated_postings,
            telemetry=telemetry,
            capture_failure_artifacts=capture_failure_artifacts,
            artifact_dir=artifact_dir,
            query_label=query.label,
            artifact_timestamp=artifact_timestamp,
            artifact_dirs=artifact_dirs,
            selective=selective_detail_enrichment,
            min_listing_stage_score=min_listing_stage_score,
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
            "debug_artifact_count": len(artifact_dirs),
            "debug_artifact_dirs": sorted(artifact_dirs),
        }
    )
    return result


def _enrich_lever_postings(
    *,
    adapter: LeverAdapter,
    query: DiscoveryQuery,
    session: BrowserSessionManager,
    postings: list[JobPosting],
    telemetry: DiscoveryTelemetry,
    capture_failure_artifacts: bool,
    artifact_dir: Path,
    query_label: str,
    artifact_timestamp: datetime,
    artifact_dirs: set[str],
    selective: bool,
    min_listing_stage_score: int,
) -> list[JobPosting]:
    enriched_postings: list[JobPosting] = []
    selected_postings = _select_postings_for_detail_enrichment(
        query=query,
        postings=postings,
        selective=selective,
        min_listing_stage_score=min_listing_stage_score,
    )
    telemetry.detail_enrichment_selected += len(selected_postings)
    selected_urls = {posting.url.unicode_string() for posting in selected_postings}
    for posting in postings:
        if posting.url.unicode_string() not in selected_urls:
            enriched_postings.append(posting)
            continue
        telemetry.detail_fetch_attempts += 1
        try:
            html = fetch_listing_page_html(session=session, url=posting.url.unicode_string())
            telemetry.detail_pages_fetched += 1
        except Exception:
            LOGGER.exception(
                "fetch_failed",
                extra={"event": "fetch_failed", "source_site": adapter.site_name, "url": posting.url.unicode_string(), "stage": "detail_fetch"},
            )
            telemetry.detail_parse_failures += 1
            captured_dir = _capture_failure_artifacts(
                enabled=capture_failure_artifacts,
                session=session,
                artifact_dir=artifact_dir,
                site_name=adapter.site_name,
                query_label=query_label,
                artifact_name=f"detail_fetch_failure_{posting.source_job_id or 'job'}",
                artifact_timestamp=artifact_timestamp,
            )
            if captured_dir is not None:
                artifact_dirs.add(str(captured_dir))
            enriched_postings.append(posting)
            continue
        try:
            detail = adapter.parse_job_detail(url=posting.url.unicode_string(), html=html)
            telemetry.detail_enrichment_successes += 1
            enriched_postings.append(_merge_detail_into_listing(posting, detail.posting))
        except Exception:
            LOGGER.exception(
                "parse_failed",
                extra={"event": "parse_failed", "source_site": adapter.site_name, "stage": "detail_parse", "url": posting.url.unicode_string()},
            )
            telemetry.detail_parse_failures += 1
            captured_dir = _capture_failure_artifacts(
                enabled=capture_failure_artifacts,
                session=session,
                artifact_dir=artifact_dir,
                site_name=adapter.site_name,
                query_label=query_label,
                artifact_name=f"detail_parse_failure_{posting.source_job_id or 'job'}",
                html=html,
                artifact_timestamp=artifact_timestamp,
            )
            if captured_dir is not None:
                artifact_dirs.add(str(captured_dir))
            enriched_postings.append(posting)
    return enriched_postings


def _capture_failure_artifacts(
    *,
    enabled: bool,
    session: BrowserSessionManager,
    artifact_dir: Path,
    site_name: str,
    query_label: str,
    artifact_name: str,
    html: str | None = None,
    artifact_timestamp: datetime,
) -> Path | None:
    if not enabled:
        return None
    artifacts = capture_debug_artifacts(
        session=session,
        base_dir=artifact_dir,
        site_name=site_name,
        query_label=query_label,
        artifact_name=artifact_name,
        html=html,
        timestamp=artifact_timestamp,
    )
    if not artifacts:
        return None
    return next(iter(artifacts.values())).parent


def _fetch_linkedin_live_listing_html(
    *,
    session: BrowserSessionManager,
    adapter: LinkedInAdapter,
    url: str,
    screenshot_name: str | None,
) -> str:
    page = session.open_url(url, wait_until="domcontentloaded")
    adapter.wait_for_live_listing_page(page)
    if screenshot_name is not None:
        session.take_screenshot(name=screenshot_name, page=page)
    return page.content()


def _fetch_linkedin_live_detail_html(
    *,
    session: BrowserSessionManager,
    adapter: LinkedInAdapter,
    url: str,
) -> str:
    page = session.open_url(url, wait_until="domcontentloaded")
    adapter.wait_for_live_detail_page(page)
    return page.content()


def _current_exception() -> Exception:
    exc = __import__("sys").exc_info()[1]
    if isinstance(exc, Exception):
        return exc
    return RuntimeError("unknown discovery failure")


def _select_postings_for_detail_enrichment(
    *,
    query: DiscoveryQuery,
    postings: list[JobPosting],
    selective: bool,
    min_listing_stage_score: int,
) -> list[JobPosting]:
    if not selective:
        return postings
    selected: list[JobPosting] = []
    for posting in postings:
        score = _score_listing_stage_match(query=query, posting=posting)
        if score >= min_listing_stage_score:
            selected.append(posting)
    return selected


def _score_listing_stage_match(*, query: DiscoveryQuery, posting: JobPosting) -> int:
    score = 0
    title_text = posting.title.casefold()
    company_text = posting.company.casefold()
    location_text = posting.location.casefold()
    description_text = posting.description_text.casefold()

    for keyword in query.include_keywords:
        normalized = keyword.casefold()
        if normalized in title_text:
            score += 3
        elif normalized in description_text or normalized in company_text:
            score += 1

    for location_hint in query.location_hints:
        normalized = location_hint.casefold()
        if normalized in location_text:
            score += 2
        elif normalized in title_text or normalized in description_text:
            score += 1

    for keyword in query.exclude_keywords:
        normalized = keyword.casefold()
        if normalized in title_text or normalized in location_text:
            score -= 3
        elif normalized in description_text:
            score -= 1

    return score
