"""Initial synchronous discovery flow."""

from __future__ import annotations

from collections.abc import Sequence

from job_agent.core.dedupe import deduplicate_job_postings
from job_agent.core.models import CrawlResult, JobPosting, SearchQuery
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
