"""Deterministic deduplication helpers for job postings."""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import re

from job_agent.core.models import JobPosting


TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "source",
    "trk",
    "trkinfo",
}


def canonicalize_url(url: str, *, source_site: str | None = None) -> str:
    """Normalize a job URL conservatively for dedupe comparisons."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower() or "https"
    hostname = _normalize_hostname((parts.hostname or "").lower(), source_site=source_site)
    port = parts.port

    netloc = hostname
    if port is not None and not _is_default_port(scheme, port):
        netloc = f"{hostname}:{port}"

    path = _normalize_path(parts.path or "/", hostname=hostname, source_site=source_site)

    query = _normalize_query(parts.query)
    return urlunsplit((scheme, netloc, path, query, ""))


def compute_dedupe_key(job: JobPosting) -> str:
    """Compute a stable dedupe key with conservative precedence."""
    if job.source_job_id:
        return f"source:{job.source_site}:{job.source_job_id.casefold()}"
    return f"url:{canonicalize_url(str(job.url), source_site=job.source_site)}"


def build_comparison_inputs(job: JobPosting) -> tuple[str, str, str]:
    """Build normalized fallback fields for exact deterministic comparison."""
    return (
        _normalize_free_text(job.title),
        _normalize_free_text(job.company),
        _normalize_free_text(job.location),
    )


def same_source_identity(left: JobPosting, right: JobPosting) -> bool:
    """Return true when both postings expose the same source identity."""
    return bool(
        left.source_job_id
        and right.source_job_id
        and left.source_site == right.source_site
        and left.source_job_id.casefold() == right.source_job_id.casefold()
    )


def same_canonical_url(left: JobPosting, right: JobPosting) -> bool:
    """Return true when both postings share the same canonical URL."""
    return canonicalize_url(str(left.url), source_site=left.source_site) == canonicalize_url(
        str(right.url),
        source_site=right.source_site,
    )


def same_fallback_identity(left: JobPosting, right: JobPosting) -> bool:
    """Return true for exact normalized fallback fields only."""
    return build_comparison_inputs(left) == build_comparison_inputs(right)


def normalize_job_posting(job: JobPosting) -> JobPosting:
    """Return a copy of the posting with a canonicalized URL."""
    payload = job.model_dump()
    payload["url"] = canonicalize_url(str(job.url), source_site=job.source_site)
    return JobPosting.model_validate(payload)


def deduplicate_job_postings(jobs: Iterable[JobPosting]) -> list[JobPosting]:
    """Deduplicate jobs deterministically using source id, canonical URL, then exact fallback fields."""
    deduplicated: list[JobPosting] = []
    seen_source_keys: set[str] = set()
    seen_url_keys: set[str] = set()
    seen_fallback_keys: set[tuple[str, str, str]] = set()

    for job in jobs:
        normalized = normalize_job_posting(job)
        source_key = _source_identity_key(normalized)
        url_key = normalized.canonical_url
        fallback_key = build_comparison_inputs(normalized)

        if source_key and source_key in seen_source_keys:
            continue
        if url_key in seen_url_keys:
            continue
        if fallback_key in seen_fallback_keys:
            continue

        deduplicated.append(normalized)
        seen_url_keys.add(url_key)
        seen_fallback_keys.add(fallback_key)
        if source_key:
            seen_source_keys.add(source_key)

    return deduplicated


def _normalize_query(query: str) -> str:
    items = parse_qsl(query, keep_blank_values=False)
    filtered = [
        (key, value)
        for key, value in items
        if not _is_tracking_query_key(key)
    ]
    filtered.sort(key=lambda item: (item[0], item[1]))
    return urlencode(filtered, doseq=True)


def _normalize_hostname(hostname: str, *, source_site: str | None) -> str:
    normalized = hostname
    if source_site == "greenhouse" or hostname.endswith("greenhouse.io"):
        if normalized.startswith("www."):
            normalized = normalized[4:]
    elif source_site == "lever" or hostname.endswith("lever.co"):
        if normalized == "www.jobs.lever.co":
            normalized = "jobs.lever.co"
        elif normalized.startswith("www.") and normalized.endswith(".lever.co"):
            normalized = normalized[4:]
    elif source_site in {"indeed", "linkedin"}:
        if normalized.startswith("www."):
            normalized = normalized[4:]
    return normalized


def _normalize_path(path: str, *, hostname: str, source_site: str | None) -> str:
    normalized = path or "/"
    if normalized != "/":
        normalized = normalized.rstrip("/")
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"

    if source_site == "greenhouse" or hostname.endswith("greenhouse.io"):
        normalized = _normalize_greenhouse_path(normalized)
    elif source_site == "lever" or hostname.endswith("lever.co"):
        normalized = _normalize_lever_path(normalized)
    elif source_site == "linkedin" or hostname.endswith("linkedin.com"):
        normalized = _collapse_repeated_slashes(normalized)
    elif source_site == "indeed" or hostname.endswith("indeed.com"):
        normalized = _collapse_repeated_slashes(normalized)
    return normalized


def _normalize_greenhouse_path(path: str) -> str:
    normalized = _collapse_repeated_slashes(path)
    normalized = re.sub(r"^/embed/job_app\b", "/job_app", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"^/embed/job_board\b", "/job_board", normalized, flags=re.IGNORECASE)
    return normalized


def _normalize_lever_path(path: str) -> str:
    normalized = _collapse_repeated_slashes(path)
    normalized = re.sub(r"^/jobs/\s*", "/jobs/", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"^/view/\s*", "/view/", normalized, flags=re.IGNORECASE)
    return normalized


def _collapse_repeated_slashes(path: str) -> str:
    collapsed = re.sub(r"/{2,}", "/", path)
    return collapsed or "/"


def _is_tracking_query_key(key: str) -> bool:
    lowered = key.casefold()
    return lowered.startswith(TRACKING_QUERY_PREFIXES) or lowered in TRACKING_QUERY_KEYS


def _is_default_port(scheme: str, port: int) -> bool:
    return (scheme == "http" and port == 80) or (scheme == "https" and port == 443)


def _normalize_free_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _source_identity_key(job: JobPosting) -> str | None:
    if not job.source_job_id:
        return None
    return f"{job.source_site}:{job.source_job_id.casefold()}"
