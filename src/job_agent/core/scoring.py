"""Deterministic rule-based relevance scoring for job postings."""

from __future__ import annotations

from job_agent.core.models import JobPosting, ScoreResult, ScoringCriteria

INCLUDE_KEYWORD_POINTS = 15
EXCLUDE_KEYWORD_PENALTY = -40
PREFERRED_REMOTE_POINTS = 12
NON_PREFERRED_REMOTE_PENALTY = -10
PREFERRED_EMPLOYMENT_POINTS = 8
NON_PREFERRED_EMPLOYMENT_PENALTY = -6
PREFERRED_SENIORITY_POINTS = 8
NON_PREFERRED_SENIORITY_PENALTY = -6


def build_default_scoring_criteria() -> ScoringCriteria:
    """Return the current default deterministic scoring rules."""
    return ScoringCriteria()


def rescore_job_posting(job: JobPosting, criteria: ScoringCriteria | None = None) -> ScoreResult:
    """Score a stored job using the current default rules unless criteria are provided."""
    active_criteria = criteria or build_default_scoring_criteria()
    return score_job_posting(job, active_criteria)


def score_job_posting(job: JobPosting, criteria: ScoringCriteria) -> ScoreResult:
    """Score a job posting using conservative deterministic rules."""
    score = 0
    explanations: list[str] = []

    score += _apply_keyword_rules(
        field_name="title",
        field_value=job.title,
        include_keywords=criteria.include_title_keywords,
        exclude_keywords=criteria.exclude_title_keywords,
        explanations=explanations,
    )
    score += _apply_keyword_rules(
        field_name="company",
        field_value=job.company,
        include_keywords=criteria.include_company_keywords,
        exclude_keywords=criteria.exclude_company_keywords,
        explanations=explanations,
    )
    score += _apply_keyword_rules(
        field_name="location",
        field_value=job.location,
        include_keywords=criteria.include_location_keywords,
        exclude_keywords=criteria.exclude_location_keywords,
        explanations=explanations,
    )
    score += _apply_preference_rule(
        label="remote_status",
        actual_value=job.remote_status.value,
        preferred_values=[item.value for item in criteria.preferred_remote_statuses],
        preferred_points=PREFERRED_REMOTE_POINTS,
        penalty_points=NON_PREFERRED_REMOTE_PENALTY,
        explanations=explanations,
    )
    score += _apply_preference_rule(
        label="employment_type",
        actual_value=job.employment_type.value,
        preferred_values=[item.value for item in criteria.preferred_employment_types],
        preferred_points=PREFERRED_EMPLOYMENT_POINTS,
        penalty_points=NON_PREFERRED_EMPLOYMENT_PENALTY,
        explanations=explanations,
    )
    score += _apply_preference_rule(
        label="seniority",
        actual_value=job.seniority.value,
        preferred_values=[item.value for item in criteria.preferred_seniority_levels],
        preferred_points=PREFERRED_SENIORITY_POINTS,
        penalty_points=NON_PREFERRED_SENIORITY_PENALTY,
        explanations=explanations,
    )

    return ScoreResult(score=score, explanations=explanations)


def _apply_keyword_rules(
    *,
    field_name: str,
    field_value: str,
    include_keywords: list[str],
    exclude_keywords: list[str],
    explanations: list[str],
) -> int:
    score_delta = 0
    normalized = field_value.casefold()

    for keyword in include_keywords:
        if keyword in normalized:
            score_delta += INCLUDE_KEYWORD_POINTS
            explanations.append(f"+{INCLUDE_KEYWORD_POINTS} {field_name} matched include keyword '{keyword}'")

    for keyword in exclude_keywords:
        if keyword in normalized:
            score_delta += EXCLUDE_KEYWORD_PENALTY
            explanations.append(f"{EXCLUDE_KEYWORD_PENALTY} {field_name} matched exclude keyword '{keyword}'")

    return score_delta


def _apply_preference_rule(
    *,
    label: str,
    actual_value: str,
    preferred_values: list[str],
    preferred_points: int,
    penalty_points: int,
    explanations: list[str],
) -> int:
    if not preferred_values:
        return 0

    if actual_value in preferred_values:
        explanations.append(f"+{preferred_points} {label} matched preferred value '{actual_value}'")
        return preferred_points

    explanations.append(f"{penalty_points} {label} did not match preferred values")
    return penalty_points
