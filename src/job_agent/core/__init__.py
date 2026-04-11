"""Core domain models for job-agent."""

from job_agent.core.models import (
    CrawlResult,
    JobPosting,
    MatchExplanation,
    ReviewDecision,
    SearchConstraint,
    SearchIntent,
    SearchPlan,
    SearchPlanQuery,
    SearchQuery,
)

__all__ = [
    "JobPosting",
    "SearchQuery",
    "SearchIntent",
    "SearchConstraint",
    "SearchPlan",
    "SearchPlanQuery",
    "MatchExplanation",
    "CrawlResult",
    "ReviewDecision",
]
