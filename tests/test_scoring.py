from __future__ import annotations

from job_agent.core.models import EmploymentType, JobPosting, RemoteStatus, ScoringCriteria, ScoringRuleSet, SeniorityLevel
from job_agent.core.scoring import build_default_scoring_criteria, build_scoring_criteria_from_rules, score_job_posting


def _make_job(
    *,
    title: str = "Senior Python Engineer",
    company: str = "Example Co",
    location: str = "Remote - Canada",
    remote_status: str = "remote",
    employment_type: str = "full_time",
    seniority: str = "senior",
) -> JobPosting:
    return JobPosting(
        source_site="linkedin",
        source_job_id="job-1",
        url="https://example.com/jobs/1",
        title=title,
        company=company,
        location=location,
        remote_status=remote_status,
        employment_type=employment_type,
        seniority=seniority,
        description_text="Build internal platforms.",
    )


def test_scoring_positive_match_is_predictable() -> None:
    job = _make_job()
    criteria = ScoringCriteria(
        include_title_keywords=["python", "engineer"],
        include_company_keywords=["example"],
        include_location_keywords=["canada"],
        preferred_remote_statuses=[RemoteStatus.REMOTE],
        preferred_employment_types=[EmploymentType.FULL_TIME],
        preferred_seniority_levels=[SeniorityLevel.SENIOR],
    )

    result = score_job_posting(job, criteria)

    assert result.score == 88
    assert "+15 title matched include keyword 'python'" in result.explanations
    assert "+12 remote_status matched preferred value 'remote'" in result.explanations


def test_scoring_negative_match_strongly_penalizes_excluded_roles() -> None:
    job = _make_job(
        title="Junior Sales Associate",
        company="Example Co",
        location="Onsite - Toronto",
        remote_status="onsite",
        employment_type="part_time",
        seniority="entry",
    )
    criteria = ScoringCriteria(
        exclude_title_keywords=["sales", "associate"],
        preferred_remote_statuses=[RemoteStatus.REMOTE],
        preferred_employment_types=[EmploymentType.FULL_TIME],
        preferred_seniority_levels=[SeniorityLevel.SENIOR],
    )

    result = score_job_posting(job, criteria)

    assert result.score == -102
    assert "-40 title matched exclude keyword 'sales'" in result.explanations
    assert "-10 remote_status did not match preferred values" in result.explanations


def test_scoring_mixed_case_combines_positive_and_negative_reasons() -> None:
    job = _make_job(
        title="Senior Python Support Engineer",
        company="Legacy Example Co",
        location="Hybrid - Toronto",
        remote_status="hybrid",
        employment_type="contract",
        seniority="senior",
    )
    criteria = ScoringCriteria(
        include_title_keywords=["python"],
        exclude_title_keywords=["support"],
        include_company_keywords=["example"],
        include_location_keywords=["toronto"],
        preferred_remote_statuses=[RemoteStatus.HYBRID],
        preferred_employment_types=[EmploymentType.FULL_TIME],
        preferred_seniority_levels=[SeniorityLevel.SENIOR],
    )

    result = score_job_posting(job, criteria)

    assert result.score == 19
    assert any("matched include keyword 'python'" in item for item in result.explanations)
    assert any("matched exclude keyword 'support'" in item for item in result.explanations)
    assert any("employment_type did not match preferred values" in item for item in result.explanations)


def test_scoring_explanations_track_each_score_change() -> None:
    job = _make_job()
    criteria = ScoringCriteria(
        include_title_keywords=["python"],
        exclude_company_keywords=["other"],
        preferred_remote_statuses=[RemoteStatus.REMOTE],
    )

    result = score_job_posting(job, criteria)

    assert result.score == 27
    assert result.explanations == [
        "+15 title matched include keyword 'python'",
        "+12 remote_status matched preferred value 'remote'",
    ]


def test_build_scoring_criteria_from_rules_maps_configured_categories_predictably() -> None:
    rules = ScoringRuleSet(
        include_keywords=["Python", "platform"],
        exclude_keywords=["sales"],
        preferred_companies=["Example Co"],
        discouraged_companies=["Bad Co"],
        preferred_locations=["Canada"],
        discouraged_locations=["Onsite"],
        preferred_remote_statuses=[RemoteStatus.REMOTE],
        preferred_seniority_levels=[SeniorityLevel.SENIOR],
    )

    criteria = build_scoring_criteria_from_rules(rules)

    assert criteria.include_title_keywords == ["python", "platform"]
    assert criteria.include_description_keywords == ["python", "platform"]
    assert criteria.exclude_description_keywords == ["sales"]
    assert criteria.include_company_keywords == ["example co"]
    assert criteria.exclude_company_keywords == ["bad co"]
    assert criteria.include_location_keywords == ["canada"]
    assert criteria.exclude_location_keywords == ["onsite"]


def test_default_scoring_criteria_is_safe_and_non_empty() -> None:
    criteria = build_default_scoring_criteria()

    assert "engineer" in criteria.include_title_keywords
    assert "engineer" in criteria.include_description_keywords
    assert criteria.preferred_remote_statuses == [RemoteStatus.REMOTE, RemoteStatus.HYBRID]


def test_configured_rule_set_changes_score_and_explanations_predictably() -> None:
    job = _make_job(
        title="Staff Platform Engineer",
        company="Example Co",
        location="Hybrid - Canada",
        remote_status="hybrid",
        seniority="staff",
    )
    rules = ScoringRuleSet(
        include_keywords=["platform"],
        preferred_companies=["Example Co"],
        preferred_locations=["Canada"],
        preferred_remote_statuses=[RemoteStatus.HYBRID],
        preferred_seniority_levels=[SeniorityLevel.STAFF],
    )

    result = score_job_posting(job, build_scoring_criteria_from_rules(rules))

    assert result.score == 80
    assert "+15 title matched include keyword 'platform'" in result.explanations
    assert "+15 description matched include keyword 'platform'" in result.explanations
    assert "+15 company matched include keyword 'example co'" in result.explanations
    assert "+15 location matched include keyword 'canada'" in result.explanations
    assert "+12 remote_status matched preferred value 'hybrid'" in result.explanations
    assert "+8 seniority matched preferred value 'staff'" in result.explanations
