"""Optional job-match summarization helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from job_agent.core.models import JobPosting


class JobSummarizer(Protocol):
    """Read-only interface for producing a short match summary."""

    def summarize(self, job: JobPosting, *, rule_explanations: Sequence[str] | None = None) -> str:
        """Return a short explanation of why a job may match."""


class RuleBasedJobSummarizer:
    """Default local summarizer based on deterministic rule explanations."""

    def summarize(self, job: JobPosting, *, rule_explanations: Sequence[str] | None = None) -> str:
        role_summary = f"{job.title} at {job.company} in {job.location}"
        score_summary = _format_score(job)
        explanations = [item.strip() for item in (rule_explanations or []) if item.strip()]

        if not explanations:
            return _join_parts(
                [
                    f"Potential match: {role_summary}.",
                    score_summary,
                    "No rule explanations were provided, so this summary uses the stored job fields only.",
                ]
            )

        positive = [_humanize_explanation(item) for item in explanations if item.startswith("+")]
        negative = [_humanize_explanation(item) for item in explanations if item.startswith("-")]

        reason_parts = []
        if positive:
            reason_parts.append(f"Positive signals: {'; '.join(positive[:2])}.")
        if negative:
            reason_parts.append(f"Possible concerns: {'; '.join(negative[:1])}.")

        return _join_parts(
            [
                f"Potential match: {role_summary}.",
                score_summary,
                *reason_parts,
            ]
        )


def summarize_job_match(
    job: JobPosting,
    *,
    rule_explanations: Sequence[str] | None = None,
    summarizer: JobSummarizer | None = None,
) -> str:
    """Summarize why a job may match without changing stored job data."""
    active_summarizer = summarizer or RuleBasedJobSummarizer()
    return active_summarizer.summarize(job, rule_explanations=rule_explanations)


def _format_score(job: JobPosting) -> str:
    score = job.metadata.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        return "Score: n/a."
    return f"Score: {score}."


def _humanize_explanation(explanation: str) -> str:
    normalized = explanation.lstrip("+-").strip()
    normalized = normalized.split(" ", 1)[1] if normalized and normalized.split(" ", 1)[0].isdigit() else normalized
    if " matched include keyword " in normalized:
        return normalized.replace(" matched include keyword ", " matched preferred keyword ")
    return normalized


def _join_parts(parts: Sequence[str]) -> str:
    return " ".join(part for part in parts if part)
