from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from job_agent import JobPosting
from job_agent.core.models import CrawlResult, EmploymentType, RemoteStatus, SearchQuery, SeniorityLevel


def test_job_posting_accepts_valid_input() -> None:
    posting = JobPosting(
        source_site="LinkedIn",
        source_job_id="  abc-123  ",
        url="https://example.com/jobs/abc-123",
        title=" Senior Python Engineer ",
        company=" Example Co ",
        location=" Toronto, ON ",
        remote_status="remote",
        employment_type="full_time",
        seniority="senior",
        posted_at=datetime(2026, 4, 1, tzinfo=UTC),
        discovered_at=datetime(2026, 4, 2, tzinfo=UTC),
        description_text=" Build internal automation systems. ",
        metadata={"team": "platform"},
    )

    assert posting.source_site == "linkedin"
    assert posting.source_job_id == "abc-123"
    assert posting.title == "Senior Python Engineer"
    assert posting.company == "Example Co"
    assert posting.location == "Toronto, ON"
    assert posting.remote_status is RemoteStatus.REMOTE
    assert posting.employment_type is EmploymentType.FULL_TIME
    assert posting.seniority is SeniorityLevel.SENIOR
    assert posting.metadata == {"team": "platform"}


def test_job_posting_handles_optional_fields_and_defaults() -> None:
    posting = JobPosting(
        source_site="company_site",
        url="https://example.com/jobs/1",
        title="Software Developer",
        company="Example Co",
        location="Remote - Canada",
        description_text="Work on automation tools.",
    )

    assert posting.source_job_id is None
    assert posting.posted_at is None
    assert posting.remote_status is RemoteStatus.UNKNOWN
    assert posting.employment_type is EmploymentType.UNKNOWN
    assert posting.seniority is SeniorityLevel.UNKNOWN
    assert posting.metadata == {}
    assert isinstance(posting.discovered_at, datetime)


def test_job_posting_rejects_empty_required_text() -> None:
    with pytest.raises(ValidationError) as exc_info:
        JobPosting(
            source_site="linkedin",
            url="https://example.com/jobs/1",
            title="   ",
            company="Example Co",
            location="Toronto",
            description_text="Useful description",
        )

    assert "value must not be empty" in str(exc_info.value)


def test_job_posting_rejects_invalid_date_order() -> None:
    with pytest.raises(ValidationError) as exc_info:
        JobPosting(
            source_site="linkedin",
            url="https://example.com/jobs/1",
            title="Software Engineer",
            company="Example Co",
            location="Toronto",
            posted_at=datetime(2026, 4, 3, tzinfo=UTC),
            discovered_at=datetime(2026, 4, 2, tzinfo=UTC),
            description_text="Useful description",
        )

    assert "posted_at cannot be later than discovered_at" in str(exc_info.value)


def test_search_query_normalizes_lists_and_defaults() -> None:
    query = SearchQuery(
        keywords=" python  developer ",
        companies=[" Example Co ", " Another Co "],
        remote_only=True,
        employment_types=["contract"],
    )

    assert query.keywords == ["python developer"]
    assert query.companies == ["Example Co", "Another Co"]
    assert query.remote_only is True
    assert query.page_limit == 1
    assert query.employment_types == [EmploymentType.CONTRACT]


def test_crawl_result_requires_error_message_on_failure() -> None:
    query = SearchQuery(keywords=["python"])

    with pytest.raises(ValidationError) as exc_info:
        CrawlResult(
            query=query,
            source_site="linkedin",
            success=False,
        )

    assert "error_message is required when success is false" in str(exc_info.value)
