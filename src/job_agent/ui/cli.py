"""Plain-text CLI rendering helpers."""

from __future__ import annotations

import csv
from pathlib import Path

from job_agent.core.models import JobPosting


def render_jobs_list(jobs: list[JobPosting]) -> str:
    """Render a compact plain-text job listing view."""
    if not jobs:
        return "No jobs found."

    lines = []
    for index, job in enumerate(jobs, start=1):
        score = _job_score(job)
        reviewed = "reviewed" if _job_reviewed(job) else "unreviewed"
        lines.append(
            f"{index}. [{job.source_site}] {job.title} | {job.company} | {job.location} | "
            f"score={score if score is not None else 'n/a'} | {reviewed}"
        )
        lines.append(f"   {job.url}")
    return "\n".join(lines)


def render_job_detail(job: JobPosting) -> str:
    """Render a single job posting in a readable detail view."""
    metadata_lines = []
    for key in sorted(job.metadata):
        metadata_lines.append(f"{key}: {job.metadata[key]}")

    lines = [
        f"Title: {job.title}",
        f"Company: {job.company}",
        f"Location: {job.location}",
        f"Source: {job.source_site}",
        f"Source Job ID: {job.source_job_id or 'n/a'}",
        f"URL: {job.url}",
        f"Remote Status: {job.remote_status.value}",
        f"Employment Type: {job.employment_type.value}",
        f"Seniority: {job.seniority.value}",
        f"Score: {_job_score(job) if _job_score(job) is not None else 'n/a'}",
        f"Reviewed: {'yes' if _job_reviewed(job) else 'no'}",
        "Description:",
        job.description_text,
    ]
    if metadata_lines:
        lines.append("Metadata:")
        lines.extend(metadata_lines)
    return "\n".join(lines)


def export_jobs_csv(jobs: list[JobPosting], output_path: str | Path) -> Path:
    """Export jobs to a CSV file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
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
            ],
        )
        writer.writeheader()
        for job in jobs:
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
                    "reviewed": "true" if _job_reviewed(job) else "false",
                }
            )
    return path


def _job_score(job: JobPosting) -> float | int | None:
    value = job.metadata.get("score")
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _job_reviewed(job: JobPosting) -> bool:
    reviewed = job.metadata.get("reviewed")
    return reviewed is True
