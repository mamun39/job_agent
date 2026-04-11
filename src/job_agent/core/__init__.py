"""Core domain models for job-agent."""

from job_agent.core.hard_filters import evaluate_job_against_intent, evaluate_job_filters
from job_agent.core.intent_parser import parse_search_intent
from job_agent.core.plan_compiler import compile_search_intent
from job_agent.core.models import (
    CrawlResult,
    HardFilterResult,
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
    "HardFilterResult",
    "evaluate_job_filters",
    "evaluate_job_against_intent",
    "parse_search_intent",
    "compile_search_intent",
    "CrawlResult",
    "ReviewDecision",
]
