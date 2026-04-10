"""Initial synchronous discovery flow."""

from __future__ import annotations

from collections.abc import Sequence

from job_agent.browser.fetch import fetch_listing_page_html
from job_agent.browser.session import BrowserSessionManager
from job_agent.config import load_max_pages_per_query
from job_agent.core.dedupe import deduplicate_job_postings
from job_agent.core.models import CrawlResult, DiscoveryQuery, JobPosting, SearchQuery
from job_agent.sites.greenhouse import GreenhouseAdapter
from job_agent.sites.lever import LeverAdapter
from job_agent.sites.base import JobSiteAdapter
from job_agent.storage.jobs_repo import JobsRepository


def run_discovery(
    *,
    adapter: JobSiteAdapter,
    jobs_repo: JobsRepository,
    html: str | None = None,
    parsed_postings: Sequence[JobPosting] | None = None,
) -> CrawlResult:
    """Parse, deduplicate, and store jobs for one adapter run."""
    if parsed_postings is None and html is None:
        raise ValueError("html or parsed_postings is required")

    jobs_repo.initialize_schema()

    extracted_postings = list(parsed_postings) if parsed_postings is not None else adapter.parse_job_postings(html=html)
    deduplicated_postings = deduplicate_job_postings(extracted_postings)

    stored_postings: list[JobPosting] = []
    inserted_count = 0
    updated_count = 0
    for posting in deduplicated_postings:
        stored, inserted = jobs_repo.upsert_job_with_status(posting)
        stored_postings.append(stored)
        if inserted:
            inserted_count += 1
        else:
            updated_count += 1

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
            "inserted_count": inserted_count,
            "updated_count": updated_count,
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
) -> CrawlResult:
    """Fetch a configured listing page, parse it with the matching adapter, and store jobs."""
    adapter = build_adapter_for_query(query)
    if isinstance(adapter, GreenhouseAdapter):
        result = _run_greenhouse_discovery_query(
            adapter=adapter,
            query=query,
            session=session,
            jobs_repo=jobs_repo,
            screenshot_name=screenshot_name,
            max_pages_per_query=max_pages_per_query or load_max_pages_per_query(),
        )
    else:
        html = fetch_listing_page_html(
            session=session,
            url=str(query.start_url),
            screenshot_name=screenshot_name,
        )
        result = run_discovery(adapter=adapter, jobs_repo=jobs_repo, html=html)
        result.metadata.update(
            {
                "pages_fetched": 1,
                "pages_parsed": 1 if result.metadata["parsed_count"] > 0 else 0,
            }
        )
    result.metadata.update(
        {
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
            if pages_fetched == 0:
                raise
            break

        visited_urls.add(next_url)
        pages_fetched += 1

        postings = adapter.parse_job_postings(html=html)
        if postings:
            aggregated_postings.extend(postings)
            pages_parsed += 1
        elif pages_parsed > 0:
            break

        candidate_next_url = adapter.find_next_page_url(html=html, current_url=next_url)
        if candidate_next_url is None or candidate_next_url in visited_urls:
            break
        next_url = candidate_next_url

    result = run_discovery(adapter=adapter, jobs_repo=jobs_repo, parsed_postings=aggregated_postings)
    result.metadata.update(
        {
            "pages_fetched": pages_fetched,
            "pages_parsed": pages_parsed,
        }
    )
    return result
