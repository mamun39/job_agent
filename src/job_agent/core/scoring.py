"""Deterministic rule-based relevance scoring for job postings."""

from __future__ import annotations

from job_agent.core.models import (
    JobPosting,
    RemotePreference,
    RemoteStatus,
    ScoreResult,
    ScoringCriteria,
    ScoringRuleSet,
    SearchConstraint,
)

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
    return build_scoring_criteria_from_rules(ScoringRuleSet.default_rules())


def build_scoring_criteria_from_rules(rules: ScoringRuleSet) -> ScoringCriteria:
    """Convert local configurable scoring rules into deterministic scoring criteria."""
    keyword_rules = _dedupe_casefolded(list(rules.include_keywords))
    exclude_keyword_rules = _dedupe_casefolded(list(rules.exclude_keywords))
    return ScoringCriteria(
        include_title_keywords=keyword_rules,
        exclude_title_keywords=exclude_keyword_rules,
        include_company_keywords=_dedupe_casefolded(list(rules.preferred_companies)),
        exclude_company_keywords=_dedupe_casefolded(list(rules.discouraged_companies)),
        include_location_keywords=_dedupe_casefolded(list(rules.preferred_locations)),
        exclude_location_keywords=_dedupe_casefolded(list(rules.discouraged_locations)),
        include_description_keywords=keyword_rules,
        exclude_description_keywords=exclude_keyword_rules,
        preferred_remote_statuses=list(rules.preferred_remote_statuses),
        preferred_employment_types=list(rules.preferred_employment_types),
        preferred_seniority_levels=list(rules.preferred_seniority_levels),
    )


def rescore_job_posting(job: JobPosting, criteria: ScoringCriteria | None = None) -> ScoreResult:
    """Score a stored job using the current default rules unless criteria are provided."""
    active_criteria = criteria or build_default_scoring_criteria()
    return score_job_posting(job, active_criteria)


def build_scoring_criteria_from_constraints(constraints: SearchConstraint) -> ScoringCriteria:
    """Build deterministic scoring criteria from parsed search constraints."""
    preferred_remote_statuses: list[RemoteStatus] = []
    if constraints.remote_preference in {RemotePreference.REMOTE_ONLY, RemotePreference.REMOTE_PREFERRED}:
        preferred_remote_statuses = [RemoteStatus.REMOTE]
    elif constraints.remote_preference is RemotePreference.HYBRID_PREFERRED:
        preferred_remote_statuses = [RemoteStatus.HYBRID]

    return ScoringCriteria(
        include_title_keywords=_dedupe_casefolded(
            list(constraints.include_keywords) + list(constraints.target_titles)
        ),
        include_description_keywords=_dedupe_casefolded(list(constraints.include_keywords)),
        include_company_keywords=_dedupe_casefolded(list(constraints.include_companies)),
        exclude_company_keywords=_dedupe_casefolded(list(constraints.exclude_companies)),
        include_location_keywords=_dedupe_casefolded(list(constraints.location_constraints)),
        preferred_remote_statuses=preferred_remote_statuses,
        preferred_seniority_levels=list(constraints.seniority_preferences),
    )


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
    score += _apply_keyword_rules(
        field_name="description",
        field_value=job.description_text,
        include_keywords=criteria.include_description_keywords,
        exclude_keywords=criteria.exclude_description_keywords,
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


def _dedupe_casefolded(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = value.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered
