"""Deterministic hard constraint filtering for job postings."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from job_agent.core.models import HardFilterResult, JobPosting, RemotePreference, SearchConstraint, SearchIntent


def evaluate_job_filters(
    job: JobPosting,
    *,
    constraints: SearchConstraint,
    now: datetime | None = None,
) -> HardFilterResult:
    """Evaluate one job against explicit hard constraints only."""
    rejection_reasons: list[str] = []

    rejection_reasons.extend(_check_excluded_keywords(job, constraints))
    rejection_reasons.extend(_check_company_exclusions(job, constraints))
    rejection_reasons.extend(_check_source_site_constraints(job, constraints))
    rejection_reasons.extend(_check_location_constraints(job, constraints))
    rejection_reasons.extend(_check_remote_constraints(job, constraints))
    rejection_reasons.extend(_check_freshness_constraint(job, constraints, now=now))

    return HardFilterResult(
        passed=not rejection_reasons,
        rejection_reasons=rejection_reasons,
    )


def evaluate_job_against_intent(
    job: JobPosting,
    *,
    intent: SearchIntent,
    now: datetime | None = None,
) -> HardFilterResult:
    """Evaluate one job against a parsed search intent using hard constraints only."""
    return evaluate_job_filters(job, constraints=intent.constraints, now=now)


def _check_excluded_keywords(job: JobPosting, constraints: SearchConstraint) -> list[str]:
    haystacks = {
        "title": job.title.casefold(),
        "company": job.company.casefold(),
        "location": job.location.casefold(),
        "description": job.description_text.casefold(),
    }
    reasons: list[str] = []
    for keyword in constraints.exclude_keywords:
        normalized_keyword = keyword.casefold()
        for field_name, field_value in haystacks.items():
            if normalized_keyword in field_value:
                reasons.append(f"Excluded keyword '{keyword}' matched {field_name}")
                break
    return reasons


def _check_company_exclusions(job: JobPosting, constraints: SearchConstraint) -> list[str]:
    company_name = job.company.casefold()
    reasons: list[str] = []
    for excluded_company in constraints.exclude_companies:
        if excluded_company.casefold() == company_name:
            reasons.append(f"Company '{job.company}' matched excluded company hint '{excluded_company}'")
    return reasons


def _check_source_site_constraints(job: JobPosting, constraints: SearchConstraint) -> list[str]:
    if not constraints.source_site_preferences:
        return []
    if job.source_site in constraints.source_site_preferences:
        return []
    allowed = ", ".join(constraints.source_site_preferences)
    return [f"Source site '{job.source_site}' is outside allowed source sites [{allowed}]"]


def _check_location_constraints(job: JobPosting, constraints: SearchConstraint) -> list[str]:
    if not constraints.location_constraints:
        return []
    normalized_location = job.location.casefold()
    if normalized_location.startswith("unknown"):
        return ["Job location is unknown and cannot satisfy explicit location constraints"]
    for location_constraint in constraints.location_constraints:
        if location_constraint.casefold() in normalized_location:
            return []
    requested = ", ".join(constraints.location_constraints)
    return [f"Job location '{job.location}' did not match any required location constraint [{requested}]"]


def _check_remote_constraints(job: JobPosting, constraints: SearchConstraint) -> list[str]:
    if constraints.remote_preference is RemotePreference.UNSPECIFIED:
        return []
    if constraints.remote_preference is RemotePreference.REMOTE_PREFERRED:
        return []
    if constraints.remote_preference is RemotePreference.ONSITE_OK:
        return []

    if job.remote_status.value == "unknown":
        if constraints.remote_preference in {RemotePreference.REMOTE_ONLY, RemotePreference.HYBRID_PREFERRED}:
            return [f"Job remote status is unknown and cannot satisfy explicit requirement '{constraints.remote_preference.value}'"]
        return []

    if constraints.remote_preference is RemotePreference.REMOTE_ONLY and job.remote_status.value != "remote":
        return [f"Job remote status '{job.remote_status.value}' did not satisfy required remote-only constraint"]
    if constraints.remote_preference is RemotePreference.HYBRID_PREFERRED and job.remote_status.value != "hybrid":
        return [f"Job remote status '{job.remote_status.value}' did not satisfy required hybrid constraint"]
    return []


def _check_freshness_constraint(
    job: JobPosting,
    constraints: SearchConstraint,
    *,
    now: datetime | None,
) -> list[str]:
    if constraints.freshness_window_days is None:
        return []
    if job.posted_at is None:
        return []
    reference_now = now or datetime.now(UTC)
    threshold = reference_now - timedelta(days=constraints.freshness_window_days)
    if job.posted_at < threshold:
        return [
            f"Job posted_at '{job.posted_at.isoformat()}' is older than allowed freshness window "
            f"{constraints.freshness_window_days} days"
        ]
    return []
