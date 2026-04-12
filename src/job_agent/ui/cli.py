"""Plain-text CLI rendering helpers."""

from __future__ import annotations

import csv
from pathlib import Path
import sqlite3
import webbrowser

from job_agent.core.models import (
    CrawlResult,
    JobPosting,
    JobStatus,
    MatchedJobMatch,
    PromptSearchResult,
    RejectedJobMatch,
    ReviewDecision,
    ReviewDecisionHistoryEntry,
    ReviewStatus,
    ScoreResult,
)
from job_agent.llm.summarizer import JobSummarizer, summarize_job_match


def render_jobs_list(jobs: list[JobPosting], *, decisions: dict[str, ReviewDecision] | None = None) -> str:
    """Render a compact plain-text job listing view."""
    if not jobs:
        return "No jobs found."

    decisions = decisions or {}
    lines = []
    for index, job in enumerate(jobs, start=1):
        score = _job_score(job)
        decision = decisions.get(job.url.unicode_string())
        reviewed = decision.decision.value if decision else "unreviewed"
        lines.append(
            f"{index}. id={job.metadata.get('db_id', 'n/a')} [{job.source_site}] "
            f"{job.title} | {job.company} | {job.location} | "
            f"score={score if score is not None else 'n/a'} | status={job.job_status.value} | {reviewed}"
        )
        lines.append(f"   {job.url}")
    return "\n".join(lines)


def render_job_detail(
    job: JobPosting,
    *,
    decision: ReviewDecision | None = None,
    decision_history: list[ReviewDecisionHistoryEntry] | None = None,
) -> str:
    """Render a single job posting in a readable detail view."""
    metadata_lines = []
    for key in sorted(job.metadata):
        metadata_lines.append(f"{key}: {job.metadata[key]}")

    lines = [
        f"Job ID: {job.metadata.get('db_id', 'n/a')}",
        f"Title: {job.title}",
        f"Company: {job.company}",
        f"Location: {job.location}",
        f"Source: {job.source_site}",
        f"Source Job ID: {job.source_job_id or 'n/a'}",
        f"URL: {job.url}",
        f"Remote Status: {job.remote_status.value}",
        f"Employment Type: {job.employment_type.value}",
        f"Seniority: {job.seniority.value}",
        f"Job Status: {job.job_status.value}",
        f"Score: {_job_score(job) if _job_score(job) is not None else 'n/a'}",
        f"Reviewed: {'yes' if decision is not None else 'no'}",
        f"Decision: {decision.decision.value if decision is not None else 'n/a'}",
        f"Decision Note: {decision.note or 'n/a' if decision is not None else 'n/a'}",
        "Description:",
        job.description_text,
    ]
    if decision is not None:
        lines.extend(
            [
                f"Decision Time: {decision.decided_at.isoformat()}",
            ]
        )
    if decision_history:
        lines.append("Decision History:")
        for entry in decision_history:
            lines.append(
                f"- {entry.decided_at.isoformat()} | {entry.decision.value} | {entry.note or 'n/a'}"
            )
    if metadata_lines:
        lines.append("Metadata:")
        lines.extend(metadata_lines)
    return "\n".join(lines)


def render_job_match_summary(
    job: JobPosting,
    *,
    rule_explanations: list[str] | None = None,
    summarizer: JobSummarizer | None = None,
) -> str:
    """Render a short optional match summary for CLI output."""
    summary = summarize_job_match(
        job,
        rule_explanations=rule_explanations,
        summarizer=summarizer,
    )
    return f"Match Summary: {summary}"


def render_discovery_summary(result: CrawlResult) -> str:
    """Render a concise discovery summary from crawl metadata."""
    metadata = result.metadata
    return (
        f"queries={metadata.get('queries_attempted', 0)} "
        f"pages={metadata.get('pages_fetched', 0)} failed_pages={metadata.get('pages_failed', 0)} "
        f"jobs={metadata.get('jobs_parsed', metadata.get('parsed_count', 0))} "
        f"inserted={metadata.get('jobs_inserted', metadata.get('inserted_count', 0))} "
        f"updated={metadata.get('jobs_updated', metadata.get('updated_count', 0))} "
        f"duplicates={metadata.get('jobs_skipped_duplicates', metadata.get('duplicate_count', 0))} "
        f"detail_selected={metadata.get('detail_enrichment_selected', 0)} "
        f"detail_attempts={metadata.get('detail_fetch_attempts', 0)} "
        f"detail_successes={metadata.get('detail_enrichment_successes', 0)} "
        f"detail_failures={metadata.get('detail_parse_failures', 0)}"
    )


def export_jobs_csv(
    jobs: list[JobPosting],
    output_path: str | Path,
    *,
    decisions: dict[str, ReviewDecision] | None = None,
) -> Path:
    """Export jobs to a CSV file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    decisions = decisions or {}
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "source_site",
                "source_job_id",
                "title",
                "company",
                "location",
                "url",
                "remote_status",
                "employment_type",
                "seniority",
                "score",
                "reviewed",
                "decision",
            ],
        )
        writer.writeheader()
        for job in jobs:
            decision = decisions.get(job.url.unicode_string())
            writer.writerow(
                {
                    "source_site": job.source_site,
                    "source_job_id": job.source_job_id or "",
                    "title": job.title,
                    "company": job.company,
                    "location": job.location,
                    "url": str(job.url),
                    "remote_status": job.remote_status.value,
                    "employment_type": job.employment_type.value,
                    "seniority": job.seniority.value,
                    "score": _job_score(job) if _job_score(job) is not None else "",
                    "reviewed": "true" if decision is not None else "false",
                    "decision": decision.decision.value if decision is not None else "",
                }
            )
    return path


def render_review_decision(decision: ReviewDecision | None) -> str:
    """Render a persisted review decision for plain CLI output."""
    if decision is None:
        return "No review decision recorded."
    return "\n".join(
        [
            f"URL: {decision.posting_url}",
            f"Decision: {decision.decision.value}",
            f"Decision Time: {decision.decided_at.isoformat()}",
            f"Note: {decision.note or 'n/a'}",
        ]
    )


def format_review_update_result(decision: ReviewDecision) -> str:
    """Render a one-line confirmation for a persisted review update."""
    note = f" note={decision.note}" if decision.note else ""
    return f"Updated decision for {decision.posting_url}: {decision.decision.value}{note}"


def format_rescore_summary(*, rescored_count: int) -> str:
    """Render a concise CLI summary for score refreshes."""
    return f"Rescored {rescored_count} jobs."


def format_mark_stale_summary(*, stale_count: int, stale_threshold_days: int) -> str:
    """Render a concise CLI summary for stale-job maintenance."""
    return f"Marked {stale_count} jobs stale using threshold={stale_threshold_days} days."


def format_cleanup_summary(*, removed_review_decisions: int, removed_review_history: int) -> str:
    """Render a concise CLI summary for orphaned review-decision cleanup."""
    return (
        f"Removed {removed_review_decisions} orphaned review decisions "
        f"and {removed_review_history} orphaned review history entries."
    )


def render_prompt_search_summary(result: PromptSearchResult) -> str:
    """Render a concise plain-text summary for prompt-driven search."""
    constraints = result.intent.constraints
    highlights: list[str] = []
    if constraints.target_titles:
        highlights.append(f"titles={', '.join(constraints.target_titles)}")
    if constraints.preferred_titles:
        highlights.append(f"preferred_titles={', '.join(constraints.preferred_titles)}")
    if constraints.include_keywords:
        highlights.append(f"include={', '.join(constraints.include_keywords)}")
    if constraints.preferred_keywords:
        highlights.append(f"prefer={', '.join(constraints.preferred_keywords)}")
    if constraints.exclude_keywords:
        highlights.append(f"exclude={', '.join(constraints.exclude_keywords)}")
    if constraints.excluded_role_categories:
        highlights.append(f"exclude_roles={', '.join(constraints.excluded_role_categories)}")
    if constraints.location_constraints:
        highlights.append(f"locations={', '.join(constraints.location_constraints)}")
    if constraints.preferred_locations:
        highlights.append(f"preferred_locations={', '.join(constraints.preferred_locations)}")
    if constraints.include_companies:
        highlights.append(f"companies={', '.join(constraints.include_companies)}")
    if constraints.exclude_companies:
        highlights.append(f"exclude_companies={', '.join(constraints.exclude_companies)}")
    if constraints.remote_preference.value != "unspecified":
        highlights.append(f"remote={constraints.remote_preference.value}")
    if constraints.freshness_window_days is not None:
        highlights.append(f"freshness={constraints.freshness_window_days}d")
    if not highlights:
        highlights.append("no explicit constraints parsed")
    lines = [
        f"Intent: {' | '.join(highlights)}",
        (
            f"Summary: boards={len(result.plan.queries)} discovered={result.discovered_jobs_count} "
            f"matched={len(result.matched_jobs)} rejected={len(result.rejected_jobs)}"
        ),
    ]
    if result.intent.parser_notes:
        lines.append(f"Parser Notes: {' | '.join(result.intent.parser_notes)}")
    if result.intent.unresolved_fragments:
        lines.append(f"Unresolved: {' | '.join(result.intent.unresolved_fragments)}")
    return "\n".join(lines)


def render_matched_jobs(matched_jobs: list[MatchedJobMatch]) -> str:
    """Render matched prompt-search jobs with concise deterministic explanations."""
    if not matched_jobs:
        return "No matched jobs."
    lines: list[str] = []
    for index, matched in enumerate(matched_jobs, start=1):
        job = matched.job
        lines.append(
            f"{index}. [{job.source_site}] {job.title} | {job.company} | {job.location} | score={matched.score}"
        )
        lines.append(f"   {job.url}")
        lines.append(f"   pass={matched.hard_filter_explanation}")
        if matched.score_reasons:
            lines.append(f"   reasons={'; '.join(matched.score_reasons)}")
        else:
            lines.append("   reasons=No positive scoring signals from current deterministic rules.")
    return "\n".join(lines)


def render_rejected_jobs(rejected_jobs: list[RejectedJobMatch]) -> str:
    """Render rejected prompt-search jobs and their rejection reasons."""
    if not rejected_jobs:
        return "No rejected jobs."
    lines: list[str] = []
    for index, rejected in enumerate(rejected_jobs, start=1):
        job = rejected.job
        lines.append(
            f"{index}. [{job.source_site}] {job.title} | {job.company} | {job.location}"
        )
        lines.append(f"   {job.url}")
        lines.append(f"   reasons={rejected.explanation or '; '.join(rejected.rejection_reasons)}")
    return "\n".join(lines)


def format_store_matches_summary(*, inserted_count: int, total_matches: int) -> str:
    """Render a concise summary for prompt-search match persistence."""
    return f"Stored {inserted_count} new matched jobs out of {total_matches} matched."


def format_saved_search_summary(*, name: str) -> str:
    """Render a concise summary for saving a reusable prompt."""
    return f"Saved prompt as '{name}'."


def export_prompt_search_matches_csv(matched_jobs: list[MatchedJobMatch], output_path: str | Path) -> Path:
    """Export matched prompt-search results to CSV."""
    return export_jobs_csv([matched.job for matched in matched_jobs], output_path)


def apply_score_result(job: JobPosting, score_result: ScoreResult) -> JobPosting:
    """Return a job copy with refreshed score metadata applied."""
    metadata = dict(job.metadata)
    metadata["score"] = score_result.score
    metadata["score_explanations"] = list(score_result.explanations)
    return job.model_copy(update={"metadata": metadata})


def parse_review_decision(value: str) -> ReviewStatus:
    """Parse a CLI review decision value."""
    normalized = value.strip().lower()
    try:
        return ReviewStatus(normalized)
    except ValueError as exc:
        supported = ", ".join(ReviewStatus.choices())
        raise ValueError(f"Invalid review decision '{value}'. Supported decisions: {supported}") from exc


def parse_job_status(value: str) -> JobStatus:
    """Parse a CLI job lifecycle status value."""
    normalized = value.strip().lower()
    try:
        return JobStatus(normalized)
    except ValueError as exc:
        supported = ", ".join(JobStatus.choices())
        raise ValueError(f"Invalid job status '{value}'. Supported statuses: {supported}") from exc


def resolve_open_job_url(
    connection: sqlite3.Connection,
    *,
    job_id: int | None = None,
    url: str | None = None,
) -> str:
    """Resolve a stored job URL by database id or exact URL."""
    if job_id is None and url is None:
        raise ValueError("Provide either --id or --url.")
    if job_id is not None and url is not None:
        raise ValueError("Provide only one of --id or --url.")

    if job_id is not None:
        row = connection.execute("SELECT url FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise ValueError(f"Job not found for id: {job_id}")
        return str(row["url"])

    row = connection.execute("SELECT url FROM jobs WHERE url = ?", (url,)).fetchone()
    if row is None:
        raise ValueError(f"Job not found for url: {url}")
    return str(row["url"])


def open_job_in_browser(connection: sqlite3.Connection, *, job_id: int | None = None, url: str | None = None) -> str:
    """Resolve and open a stored job URL in the user's default browser."""
    resolved_url = resolve_open_job_url(connection, job_id=job_id, url=url)
    opened = webbrowser.open(resolved_url)
    if not opened:
        raise RuntimeError(f"Failed to open browser for url: {resolved_url}")
    return resolved_url


def _job_score(job: JobPosting) -> float | int | None:
    value = job.metadata.get("score")
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None
