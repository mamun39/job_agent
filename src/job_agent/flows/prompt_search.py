"""Synchronous prompt-driven search orchestration."""

from __future__ import annotations

from datetime import UTC, datetime

from job_agent.browser.session import BrowserSessionManager
from job_agent.config import load_settings
from job_agent.core.hard_filters import evaluate_job_against_intent
from job_agent.core.intent_parser import parse_search_intent
from job_agent.core.models import (
    BoardRegistryEntry,
    DiscoveryOptions,
    DiscoveryQuery,
    MatchedJobMatch,
    PromptSearchResult,
    RejectedJobMatch,
    SearchPlanQuery,
)
from job_agent.core.scoring import build_scoring_criteria_from_constraints, score_job_posting
from job_agent.core.plan_compiler import compile_search_intent
from job_agent.flows.discover import run_discovery_query
from job_agent.storage.jobs_repo import JobsRepository


def run_prompt_search(
    *,
    prompt_text: str,
    session: BrowserSessionManager,
    jobs_repo: JobsRepository,
    board_registry: list[BoardRegistryEntry] | None = None,
    options: DiscoveryOptions | None = None,
    now: datetime | None = None,
) -> PromptSearchResult:
    """Run the deterministic prompt-driven search flow end to end."""
    settings = None
    if board_registry is None or options is None:
        settings = load_settings()

    intent = parse_search_intent(prompt_text)
    plan = compile_search_intent(
        intent,
        board_registry=board_registry if board_registry is not None else list(settings.board_registry),
    )

    executable_queries = [_plan_query_to_discovery_query(query) for query in plan.queries if query.board_url is not None]
    if not executable_queries:
        raise ValueError("Compiled search plan did not resolve to any executable board URLs.")

    matched_jobs: list[MatchedJobMatch] = []
    rejected_jobs: list[RejectedJobMatch] = []
    discovered_jobs_count = 0
    evaluation_now = now or datetime.now(UTC)
    scoring_criteria = build_scoring_criteria_from_constraints(intent.constraints)

    for query in executable_queries:
        result = run_discovery_query(
            query=query,
            session=session,
            jobs_repo=jobs_repo,
            options=options if options is not None else settings.discovery_options,
        )
        discovered_jobs_count += len(result.postings)
        for job in result.postings:
            filter_result = evaluate_job_against_intent(job, intent=intent, now=evaluation_now)
            if filter_result.passed:
                score_result = score_job_posting(job, scoring_criteria)
                matched_jobs.append(
                    MatchedJobMatch(
                        job=job,
                        hard_filter_explanation="Passed explicit hard filters.",
                        score=score_result.score,
                        score_reasons=_top_score_reasons(score_result.explanations),
                    )
                )
            else:
                rejected_jobs.append(
                    RejectedJobMatch(
                        job=job,
                        rejection_reasons=list(filter_result.rejection_reasons),
                        explanation="; ".join(filter_result.rejection_reasons),
                    )
                )

    return PromptSearchResult(
        intent=intent,
        plan=plan,
        discovered_jobs_count=discovered_jobs_count,
        matched_jobs=matched_jobs,
        rejected_jobs=rejected_jobs,
    )


def _plan_query_to_discovery_query(plan_query: SearchPlanQuery) -> DiscoveryQuery:
    return DiscoveryQuery(
        source_site=plan_query.source_site,
        label=plan_query.label,
        start_url=plan_query.board_url,
        include_keywords=list(plan_query.include_keywords),
        exclude_keywords=list(plan_query.exclude_keywords),
        location_hints=list(plan_query.location_constraints),
    )


def _top_score_reasons(explanations: list[str], *, limit: int = 3) -> list[str]:
    positive = [item for item in explanations if item.startswith("+")]
    return positive[:limit]
