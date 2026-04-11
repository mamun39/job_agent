from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from job_agent import JobPosting
from job_agent.core.models import (
    CrawlResult,
    EmploymentType,
    MatchExplanation,
    RemotePreference,
    RemoteStatus,
    SearchConstraint,
    SearchIntent,
    SearchPlan,
    SearchPlanQuery,
    SearchQuery,
    SeniorityLevel,
)


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


def test_search_constraint_normalizes_lists_and_optional_defaults() -> None:
    constraints = SearchConstraint(
        target_titles=" Senior Python Engineer ",
        include_keywords=[" backend ", " distributed systems "],
        exclude_keywords=None,
        location_constraints=" Remote - Canada ",
        remote_preference="remote_preferred",
        seniority_preferences=["senior", "staff"],
        source_site_preferences=[" Greenhouse ", "lever"],
        include_companies=" Example Co ",
    )

    assert constraints.target_titles == ["Senior Python Engineer"]
    assert constraints.include_keywords == ["backend", "distributed systems"]
    assert constraints.exclude_keywords == []
    assert constraints.location_constraints == ["Remote - Canada"]
    assert constraints.remote_preference is RemotePreference.REMOTE_PREFERRED
    assert constraints.seniority_preferences == [SeniorityLevel.SENIOR, SeniorityLevel.STAFF]
    assert constraints.source_site_preferences == ["greenhouse", "lever"]
    assert constraints.include_companies == ["Example Co"]
    assert constraints.exclude_companies == []
    assert constraints.freshness_window_days is None


def test_search_intent_accepts_realistic_prompt_payload() -> None:
    intent = SearchIntent(
        prompt_text="Find senior backend Python roles in Canada, preferably remote, avoid crypto companies.",
        summary="Senior remote-leaning backend search in Canada.",
        constraints={
            "target_titles": ["Backend Engineer", "Platform Engineer"],
            "include_keywords": ["python", "api"],
            "exclude_keywords": ["crypto"],
            "location_constraints": ["Canada", "Remote"],
            "remote_preference": "remote_only",
            "seniority_preferences": ["senior"],
            "source_site_preferences": ["Greenhouse", "Lever"],
            "freshness_window_days": 14,
            "exclude_companies": ["Speculative Labs"],
        },
    )

    assert intent.prompt_text.startswith("Find senior backend Python roles")
    assert intent.summary == "Senior remote-leaning backend search in Canada."
    assert intent.constraints.remote_preference is RemotePreference.REMOTE_ONLY
    assert intent.constraints.freshness_window_days == 14
    assert intent.constraints.source_site_preferences == ["greenhouse", "lever"]


def test_search_plan_validates_supported_executable_queries() -> None:
    intent = SearchIntent(
        prompt_text="Find senior platform roles.",
        constraints={"target_titles": ["Platform Engineer"], "include_keywords": ["python"]},
    )
    plan = SearchPlan(
        intent=intent,
        constraints=intent.constraints,
        queries=[
            {
                "source_site": "Greenhouse",
                "label": "Greenhouse Platform Engineer",
                "target_titles": ["Platform Engineer"],
                "include_keywords": ["python", "backend"],
                "location_constraints": ["Canada"],
                "remote_preference": "remote_preferred",
                "seniority_preferences": ["senior"],
                "freshness_window_days": 7,
            },
            {
                "source_site": "lever",
                "label": "Lever Backend Engineer",
                "target_titles": ["Backend Engineer"],
                "exclude_keywords": ["manager"],
                "include_companies": ["Example Co"],
            },
        ],
    )

    assert len(plan.queries) == 2
    assert plan.queries[0].source_site == "greenhouse"
    assert plan.queries[0].remote_preference is RemotePreference.REMOTE_PREFERRED
    assert plan.queries[1].include_companies == ["Example Co"]


def test_search_plan_query_rejects_unsupported_source_site() -> None:
    with pytest.raises(ValidationError) as exc_info:
        SearchPlanQuery(label="LinkedIn Python Roles", source_site="linkedin", include_keywords=["python"])

    assert "source_site must be one of: greenhouse, lever" in str(exc_info.value)


def test_search_plan_requires_at_least_one_query() -> None:
    with pytest.raises(ValidationError) as exc_info:
        SearchPlan(
            intent=SearchIntent(prompt_text="Find jobs."),
            queries=[],
        )

    assert "queries must contain at least one executable query" in str(exc_info.value)


def test_search_constraint_rejects_invalid_list_shape_with_clear_error() -> None:
    with pytest.raises(ValidationError) as exc_info:
        SearchConstraint(include_keywords=123)

    assert "value must be a list of strings" in str(exc_info.value)


def test_match_explanation_handles_defaults_and_normalizes_text() -> None:
    explanation = MatchExplanation(
        summary=" Strong title and keyword match ",
        matched_titles=" Senior Python Engineer ",
        matched_keywords=[" python ", " backend "],
        notes=None,
    )

    assert explanation.summary == "Strong title and keyword match"
    assert explanation.matched_titles == ["Senior Python Engineer"]
    assert explanation.matched_keywords == ["python", "backend"]
    assert explanation.notes == []
    assert explanation.location_match is None
