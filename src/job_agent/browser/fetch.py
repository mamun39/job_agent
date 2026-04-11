"""Generic Playwright-backed page fetch helpers."""

from __future__ import annotations

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
