"""Generic Playwright-backed page fetch helpers."""

from __future__ import annotations

from pathlib import Path

from job_agent.browser.session import BrowserSessionManager


def fetch_page_html(
    *,
    session: BrowserSessionManager,
    url: str,
    wait_until: str = "networkidle",
    wait_delay_ms: int = 0,
    screenshot_name: str | None = None,
) -> str:
    """Open a URL, optionally wait longer, and return the page HTML."""
    page = session.open_url(url, wait_until=wait_until)

    if wait_delay_ms > 0:
        page.wait_for_timeout(wait_delay_ms)

    if screenshot_name is not None:
        session.take_screenshot(name=screenshot_name, page=page)

    return page.content()


def fetch_page_html_with_screenshot(
    *,
    session: BrowserSessionManager,
    url: str,
    screenshot_name: str,
    wait_until: str = "networkidle",
    wait_delay_ms: int = 0,
) -> tuple[str, Path]:
    """Open a URL, return HTML, and persist a screenshot."""
    page = session.open_url(url, wait_until=wait_until)

    if wait_delay_ms > 0:
        page.wait_for_timeout(wait_delay_ms)

    screenshot_path = session.take_screenshot(name=screenshot_name, page=page)
    return page.content(), screenshot_path
