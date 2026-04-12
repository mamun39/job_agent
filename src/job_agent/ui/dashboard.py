"""Minimal local dashboard for reviewing stored jobs."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs
from urllib.parse import urlencode
from urllib.parse import quote_plus

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from job_agent.core.models import ReviewStatus
from job_agent.storage.db import init_db
from job_agent.storage.jobs_repo import JobsRepository


TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates"
STATIC_DIR = Path(__file__).resolve().parents[3] / "static"
DEFAULT_PER_PAGE = 25
MAX_PER_PAGE = 100
ALLOWED_SORT_FIELDS = {"discovered_at", "posted_at", "title", "company", "location", "source_site", "score"}
ALLOWED_SORT_DIRECTIONS = {"asc", "desc"}


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
        page: str = "1",
        per_page: str = str(DEFAULT_PER_PAGE),
        sort_by: str = "discovered_at",
        sort_dir: str = "desc",
    ) -> HTMLResponse:
        errors: list[str] = []
        parsed_min_score = _parse_optional_float(min_score, label="Min Score", errors=errors)
        parsed_page = _parse_positive_int(page, label="Page", default=1, maximum=None, errors=errors)
        parsed_per_page = _parse_positive_int(per_page, label="Per Page", default=DEFAULT_PER_PAGE, maximum=MAX_PER_PAGE, errors=errors)
        normalized_sort_by = _parse_sort_by(sort_by, errors=errors)
        normalized_sort_dir = _parse_sort_dir(sort_dir, errors=errors)
        jobs_repo = get_repo()
        filtered_jobs = jobs_repo.list_jobs(
            source_site=source_site or None,
            company=company or None,
            location_contains=location_contains or None,
            reviewed=_parse_reviewed_filter(reviewed),
            decision=decision or None,
            min_score=parsed_min_score,
            limit=None,
            sort_by=normalized_sort_by,
            sort_desc=normalized_sort_dir == "desc",
        )
        total_jobs = len(filtered_jobs)
        total_pages = max(1, (total_jobs + parsed_per_page - 1) // parsed_per_page)
        if parsed_page > total_pages:
            parsed_page = total_pages
        start = (parsed_page - 1) * parsed_per_page
        jobs = filtered_jobs[start:start + parsed_per_page]
        decision_map = jobs_repo.get_review_decisions_by_url(job.url.unicode_string() for job in jobs)
        current_query = {
            "source_site": source_site or "",
            "company": company or "",
            "location_contains": location_contains or "",
            "reviewed": reviewed,
            "decision": decision or "",
            "min_score": min_score or "",
            "page": parsed_page,
            "per_page": parsed_per_page,
            "sort_by": normalized_sort_by,
            "sort_dir": normalized_sort_dir,
        }
        current_path = f"/jobs?{urlencode({key: value for key, value in current_query.items() if value not in {'', None}})}"
        job_rows = [
            {
                "id": int(job.metadata["db_id"]),
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "source_site": job.source_site,
                "score": _format_score(job),
                "score_explanations": _score_explanations(job),
                "decision": (
                    decision_map[job.url.unicode_string()].decision.value
                    if job.url.unicode_string() in decision_map
                    else ("reviewed" if job.metadata.get("reviewed") else "unreviewed")
                ),
                "decision_note": (
                    decision_map[job.url.unicode_string()].note
                    if job.url.unicode_string() in decision_map and decision_map[job.url.unicode_string()].note
                    else ""
                ),
                "return_to": current_path,
                "detail_url": f"/jobs/{int(job.metadata['db_id'])}?return_to={quote_plus(current_path)}",
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
                    "min_score": min_score or ("" if parsed_min_score is None else parsed_min_score),
                    "page": parsed_page,
                    "per_page": parsed_per_page,
                    "sort_by": normalized_sort_by,
                    "sort_dir": normalized_sort_dir,
                },
                "errors": errors,
                "pagination": {
                    "page": parsed_page,
                    "per_page": parsed_per_page,
                    "total_jobs": total_jobs,
                    "total_pages": total_pages,
                    "has_previous": parsed_page > 1,
                    "has_next": parsed_page < total_pages,
                    "previous_page": parsed_page - 1,
                    "next_page": parsed_page + 1,
                },
                "current_query": current_query,
                "sort_fields": sorted(ALLOWED_SORT_FIELDS),
            },
        )

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def show_job_detail(request: Request, job_id: int, return_to: str | None = None) -> HTMLResponse:
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
                "return_to": return_to or "/jobs",
                "score_display": _format_score(job),
                "score_explanations": _score_explanations(job),
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
        redirect_to = (form.get("redirect_to") or [f"/jobs/{job_id}"])[0].strip() or f"/jobs/{job_id}"
        jobs_repo.set_review_decision(
            posting_url=job.url.unicode_string(),
            decision=ReviewStatus(decision),
            note=note or None,
        )
        separator = "&" if "?" in redirect_to else "?"
        return RedirectResponse(url=f"{redirect_to}{separator}updated=1", status_code=303)

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

def _parse_positive_int(
    value: str | None,
    *,
    label: str,
    default: int,
    maximum: int | None,
    errors: list[str],
) -> int:
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError:
        errors.append(f"{label} must be a whole number.")
        return default
    if parsed < 1:
        errors.append(f"{label} must be at least 1.")
        return default
    if maximum is not None and parsed > maximum:
        errors.append(f"{label} must be at most {maximum}.")
        return maximum
    return parsed


def _parse_optional_float(value: str | None, *, label: str, errors: list[str]) -> float | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    try:
        return float(normalized)
    except ValueError:
        errors.append(f"{label} must be a valid number.")
        return None


def _parse_sort_by(value: str | None, *, errors: list[str]) -> str:
    normalized = (value or "discovered_at").strip().lower()
    if normalized not in ALLOWED_SORT_FIELDS:
        errors.append("Sort field is not supported; using discovered_at.")
        return "discovered_at"
    return normalized


def _parse_sort_dir(value: str | None, *, errors: list[str]) -> str:
    normalized = (value or "desc").strip().lower()
    if normalized not in ALLOWED_SORT_DIRECTIONS:
        errors.append("Sort direction is not supported; using desc.")
        return "desc"
    return normalized


def _format_score(job) -> str:
    score = job.metadata.get("score")
    if isinstance(score, bool):
        return "n/a"
    if isinstance(score, int):
        return str(score)
    if isinstance(score, float):
        return f"{score:.1f}"
    return "n/a"


def _score_explanations(job) -> list[str]:
    value = job.metadata.get("score_explanations")
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []
