"""job-agent package."""

from job_agent.config import Settings, load_settings
from job_agent.core import (
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
    "Settings",
    "load_settings",
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
