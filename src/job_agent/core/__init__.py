"""Core domain models for job-agent."""

from job_agent.core.intent_parser import parse_search_intent
from job_agent.core.plan_compiler import compile_search_intent
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
    "parse_search_intent",
    "compile_search_intent",
    "CrawlResult",
    "ReviewDecision",
]
