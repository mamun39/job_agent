"""Generic Playwright-backed page fetch helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path

from job_agent.browser.session import BrowserSessionManager

LOGGER = logging.getLogger(__name__)


def fetch_page_html(
    *,
    session: BrowserSessionManager,
    url: str,
    wait_until: str = "networkidle",
    wait_delay_ms: int = 0,
    screenshot_name: str | None = None,
) -> str:
    """Open a URL, optionally wait longer, and return the page HTML."""
    try:
        page = session.open_url(url, wait_until=wait_until)
    except Exception:
        LOGGER.exception(
            "fetch_failed",
            extra={
                "event": "fetch_failed",
                "url": url,
                "wait_until": wait_until,
                "wait_delay_ms": wait_delay_ms,
            },
        )
        raise

    if wait_delay_ms > 0:
        page.wait_for_timeout(wait_delay_ms)

    if screenshot_name is not None:
        session.take_screenshot(name=screenshot_name, page=page)

    return page.content()


def build_debug_artifact_dir(
    *,
    base_dir: str | Path,
    site_name: str,
    query_label: str,
    timestamp: datetime | None = None,
) -> Path:
    """Build a structured local directory path for debug artifacts."""
    instant = timestamp or datetime.now(timezone.utc)
    stamp = instant.strftime("%Y%m%dT%H%M%SZ")
    return Path(base_dir) / _normalize_path_part(site_name) / _normalize_path_part(query_label) / stamp


def capture_debug_artifacts(
    *,
    session: BrowserSessionManager,
    base_dir: str | Path,
    site_name: str,
    query_label: str,
    artifact_name: str,
    html: str | None = None,
    timestamp: datetime | None = None,
) -> dict[str, Path]:
    """Best-effort local artifact capture that never masks the triggering failure."""
    target_dir = build_debug_artifact_dir(
        base_dir=base_dir,
        site_name=site_name,
        query_label=query_label,
        timestamp=timestamp,
    )
    try:
        return session.save_debug_artifacts(directory=target_dir, name=artifact_name, html=html)
    except Exception:
        LOGGER.exception(
            "debug_artifact_failed",
            extra={
                "event": "debug_artifact_failed",
                "site_name": site_name,
                "query_label": query_label,
                "artifact_name": artifact_name,
                "target_dir": str(target_dir),
            },
        )
        return {}


def fetch_listing_page_html(
    *,
    session: BrowserSessionManager,
    url: str,
    screenshot_name: str | None = None,
    wait_until: str = "networkidle",
    wait_delay_ms: int = 0,
) -> str:
    """Fetch listing page HTML with safe generic defaults for discovery."""
    return fetch_page_html(
        session=session,
        url=url,
        wait_until=wait_until,
        wait_delay_ms=wait_delay_ms,
        screenshot_name=screenshot_name,
    )


def fetch_page_html_with_screenshot(
    *,
    session: BrowserSessionManager,
    url: str,
    screenshot_name: str,
    wait_until: str = "networkidle",
    wait_delay_ms: int = 0,
) -> tuple[str, Path]:
    """Open a URL, return HTML, and persist a screenshot."""
    try:
        page = session.open_url(url, wait_until=wait_until)
    except Exception:
        LOGGER.exception(
            "fetch_failed",
            extra={
                "event": "fetch_failed",
                "url": url,
                "wait_until": wait_until,
                "wait_delay_ms": wait_delay_ms,
            },
        )
        raise

    if wait_delay_ms > 0:
        page.wait_for_timeout(wait_delay_ms)

    screenshot_path = session.take_screenshot(name=screenshot_name, page=page)
    return page.content(), screenshot_path


def _normalize_path_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value.strip())
    return cleaned.strip("._") or "unknown"
