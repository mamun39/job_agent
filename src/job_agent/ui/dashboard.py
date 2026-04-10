"""Minimal local dashboard for reviewing stored jobs."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from job_agent.core.models import ReviewStatus
from job_agent.storage.db import init_db
from job_agent.storage.jobs_repo import JobsRepository


TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates"
STATIC_DIR = Path(__file__).resolve().parents[3] / "static"


def create_dashboard_app(*, db_path: str | Path) -> FastAPI:
    """Create a minimal local-only dashboard application."""
    app = FastAPI(title="job-agent dashboard")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    def get_repo() -> JobsRepository:
        return JobsRepository(init_db(db_path))

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    @app.get("/jobs", response_class=HTMLResponse)
    def list_jobs(
        request: Request,
        source_site: str | None = None,
        company: str | None = None,
        location_contains: str | None = None,
        reviewed: str = "all",
        decision: str | None = None,
        min_score: str | None = None,
        limit: int = 100,
    ) -> HTMLResponse:
        parsed_min_score = _parse_optional_float(min_score)
        jobs_repo = get_repo()
        jobs = jobs_repo.list_jobs(
            source_site=source_site or None,
            company=company or None,
            location_contains=location_contains or None,
            reviewed=_parse_reviewed_filter(reviewed),
            decision=decision or None,
            min_score=parsed_min_score,
            limit=limit,
        )
        decision_map = jobs_repo.get_review_decisions_by_url(job.url.unicode_string() for job in jobs)
        job_rows = [
            {
                "id": int(job.metadata["db_id"]),
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "source_site": job.source_site,
                "score": job.metadata.get("score", "n/a"),
                "decision": (
                    decision_map[job.url.unicode_string()].decision.value
                    if job.url.unicode_string() in decision_map
                    else ("reviewed" if job.metadata.get("reviewed") else "unreviewed")
                ),
            }
            for job in jobs
        ]
        return templates.TemplateResponse(
            request,
            "jobs.html",
            {
                "jobs": job_rows,
                "filters": {
                    "source_site": source_site or "",
                    "company": company or "",
                    "location_contains": location_contains or "",
                    "reviewed": reviewed,
                    "decision": decision or "",
                    "min_score": "" if parsed_min_score is None else parsed_min_score,
                    "limit": limit,
                },
            },
        )

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def show_job_detail(request: Request, job_id: int) -> HTMLResponse:
        jobs_repo = get_repo()
        job = jobs_repo.fetch_by_id(job_id)
        if job is None:
            return HTMLResponse("Job not found.", status_code=404)
        decision = jobs_repo.get_review_decision(posting_url=job.url.unicode_string())
        return templates.TemplateResponse(
            request,
            "job_detail.html",
            {
                "job": job,
                "decision": decision,
                "review_statuses": [status.value for status in ReviewStatus],
            },
        )

    @app.post("/jobs/{job_id}/decision")
    async def update_review_decision(request: Request, job_id: int) -> RedirectResponse:
        jobs_repo = get_repo()
        job = jobs_repo.fetch_by_id(job_id)
        if job is None:
            return RedirectResponse(url="/jobs", status_code=303)
        form = parse_qs((await request.body()).decode("utf-8"))
        decision = (form.get("decision") or [""])[0].strip()
        note = (form.get("note") or [""])[0].strip()
        jobs_repo.set_review_decision(
            posting_url=job.url.unicode_string(),
            decision=ReviewStatus(decision),
            note=note or None,
        )
        return RedirectResponse(url=f"/jobs/{job_id}?updated=1", status_code=303)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _parse_reviewed_filter(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized == "reviewed":
        return True
    if normalized == "unreviewed":
        return False
    return None


def _parse_optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return float(normalized)
