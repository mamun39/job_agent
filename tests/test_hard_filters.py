from __future__ import annotations

from datetime import UTC, datetime

from job_agent.core.hard_filters import evaluate_job_against_intent, evaluate_job_filters
from job_agent.core.models import JobPosting, SearchConstraint, SearchIntent


def _make_job(
    *,
    title: str = "Senior Backend Engineer",
    company: str = "Example Co",
    location: str = "Remote - Canada",
    source_site: str = "greenhouse",
    remote_status: str = "remote",
    posted_at: datetime | None = datetime(2026, 4, 10, tzinfo=UTC),
    description_text: str = "Build backend APIs for internal tooling.",
) -> JobPosting:
    return JobPosting(
        source_site=source_site,
        source_job_id="job-1",
        url="https://example.com/jobs/1",
        title=title,
        company=company,
        location=location,
        remote_status=remote_status,
        posted_at=posted_at,
        discovered_at=datetime(2026, 4, 10, tzinfo=UTC),
        last_seen_at=datetime(2026, 4, 10, tzinfo=UTC),
        description_text=description_text,
    )


def test_hard_filters_pass_when_explicit_constraints_are_satisfied() -> None:
    job = _make_job()
    constraints = SearchConstraint(
        location_constraints=["Canada"],
        remote_preference="remote_only",
        source_site_preferences=["greenhouse"],
        freshness_window_days=7,
    )

    result = evaluate_job_filters(job, constraints=constraints, now=datetime(2026, 4, 11, tzinfo=UTC))

    assert result.passed is True
    assert result.rejection_reasons == []


def test_hard_filters_reject_excluded_keyword_with_explicit_reason() -> None:
    job = _make_job(description_text="Build backend APIs for crypto exchange infrastructure.")
    constraints = SearchConstraint(exclude_keywords=["crypto"])

    result = evaluate_job_filters(job, constraints=constraints)

    assert result.passed is False
    assert result.rejection_reasons == ["Excluded keyword 'crypto' matched description"]


def test_hard_filters_reject_location_mismatch_with_explicit_reason() -> None:
    job = _make_job(location="New York, NY")
    constraints = SearchConstraint(location_constraints=["Canada", "Toronto"])

    result = evaluate_job_filters(job, constraints=constraints)

    assert result.passed is False
    assert result.rejection_reasons == [
        "Job location 'New York, NY' did not match any required location constraint [Canada, Toronto]"
    ]


def test_hard_filters_reject_unknown_location_when_location_is_explicitly_required() -> None:
    job = _make_job(location="Unknown Location")
    constraints = SearchConstraint(location_constraints=["Canada"])

    result = evaluate_job_filters(job, constraints=constraints)

    assert result.passed is False
    assert result.rejection_reasons == ["Job location is unknown and cannot satisfy explicit location constraints"]


def test_hard_filters_reject_non_remote_job_for_remote_only_requirement() -> None:
    job = _make_job(remote_status="onsite")
    constraints = SearchConstraint(remote_preference="remote_only")

    result = evaluate_job_filters(job, constraints=constraints)

    assert result.passed is False
    assert result.rejection_reasons == [
        "Job remote status 'onsite' did not satisfy required remote-only constraint"
    ]


def test_hard_filters_reject_unknown_remote_status_for_explicit_hybrid_requirement() -> None:
    job = _make_job(remote_status="unknown")
    constraints = SearchConstraint(remote_preference="hybrid_preferred")

    result = evaluate_job_filters(job, constraints=constraints)

    assert result.passed is False
    assert result.rejection_reasons == [
        "Job remote status is unknown and cannot satisfy explicit requirement 'hybrid_preferred'"
    ]


def test_hard_filters_do_not_reject_unknown_posted_at_for_freshness_rule() -> None:
    job = _make_job(posted_at=None)
    constraints = SearchConstraint(freshness_window_days=7)

    result = evaluate_job_filters(job, constraints=constraints, now=datetime(2026, 4, 11, tzinfo=UTC))

    assert result.passed is True
    assert result.rejection_reasons == []


def test_hard_filters_reject_stale_job_when_posted_at_is_known() -> None:
    job = _make_job(posted_at=datetime(2026, 3, 1, tzinfo=UTC))
    constraints = SearchConstraint(freshness_window_days=7)

    result = evaluate_job_filters(job, constraints=constraints, now=datetime(2026, 4, 11, tzinfo=UTC))

    assert result.passed is False
    assert result.rejection_reasons == [
        "Job posted_at '2026-03-01T00:00:00+00:00' is older than allowed freshness window 7 days"
    ]


def test_hard_filters_reject_excluded_company_with_exact_reason() -> None:
    job = _make_job(company="Meta")
    constraints = SearchConstraint(exclude_companies=["Meta"])

    result = evaluate_job_filters(job, constraints=constraints)

    assert result.passed is False
    assert result.rejection_reasons == ["Company 'Meta' matched excluded company hint 'Meta'"]


def test_hard_filters_reject_source_site_outside_explicit_allowed_sources() -> None:
    job = _make_job(source_site="lever")
    constraints = SearchConstraint(source_site_preferences=["greenhouse"])

    result = evaluate_job_filters(job, constraints=constraints)

    assert result.passed is False
    assert result.rejection_reasons == ["Source site 'lever' is outside allowed source sites [greenhouse]"]


def test_hard_filters_can_evaluate_against_intent_directly() -> None:
    job = _make_job(description_text="General product engineering role.")
    intent = SearchIntent(
        prompt_text="Find jobs excluding product.",
        constraints={"exclude_keywords": ["product"]},
    )

    result = evaluate_job_against_intent(job, intent=intent)

    assert result.passed is False
    assert result.rejection_reasons == ["Excluded keyword 'product' matched description"]
