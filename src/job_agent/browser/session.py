"""Playwright browser session management."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from job_agent.config import Settings

try:
    from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright
except ImportError:  # pragma: no cover - exercised indirectly by guard behavior
    BrowserContext = Any  # type: ignore[assignment]
    Page = Any  # type: ignore[assignment]
    Playwright = Any  # type: ignore[assignment]
    sync_playwright = None


class BrowserSessionManager:
    """Thin wrapper around a persistent Chromium session."""

    def __init__(
        self,
        *,
        user_data_dir: Path,
        screenshot_dir: Path,
        headless: bool = False,
    ) -> None:
        self.user_data_dir = user_data_dir
        self.screenshot_dir = screenshot_dir
        self.headless = headless
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._last_page: Page | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> BrowserSessionManager:
        """Build a session manager from application settings."""
        return cls(
            user_data_dir=settings.browser_user_data_dir,
            screenshot_dir=settings.browser_screenshot_dir,
            headless=settings.browser_headless,
        )

    def launch(self) -> BrowserContext:
        """Start Playwright and launch a persistent Chromium context."""
        self._ensure_playwright_available()
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        if self._context is not None:
            return self._context

        self._playwright = sync_playwright().start()
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.user_data_dir),
            headless=self.headless,
        )
        return self._context

    def open_page(self) -> Page:
        """Return an existing page or create a new one."""
        context = self.launch()
        pages = list(context.pages)
        if pages:
            self._last_page = pages[0]
            return pages[0]
        self._last_page = context.new_page()
        return self._last_page

    def open_url(self, url: str, *, wait_until: str = "networkidle") -> Page:
        """Open a URL in a managed page and wait for the requested load state."""
        page = self.open_page()
        page.goto(url, wait_until=wait_until)
        self._last_page = page
        return page

    def take_screenshot(self, *, name: str, page: Page | None = None) -> Path:
        """Capture a page screenshot into the configured directory."""
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        target_page = page or self._last_page or self.open_page()
        output_path = self.screenshot_dir / _normalize_screenshot_name(name)
        target_page.screenshot(path=str(output_path))
        return output_path

    def save_debug_artifacts(
        self,
        *,
        directory: Path,
        name: str,
        html: str | None = None,
        page: Page | None = None,
    ) -> dict[str, Path]:
        """Persist best-effort local debug artifacts from the current page state."""
        directory.mkdir(parents=True, exist_ok=True)
        target_page = page or self._last_page
        artifacts: dict[str, Path] = {}
        base_name = _normalize_artifact_name(name)

        html_content = html
        if html_content is None and target_page is not None:
            html_content = target_page.content()
        if html_content is not None:
            html_path = directory / f"{base_name}.html"
            html_path.write_text(html_content, encoding="utf-8")
            artifacts["html"] = html_path

        if target_page is not None:
            screenshot_path = directory / f"{base_name}.png"
            target_page.screenshot(path=str(screenshot_path))
            artifacts["screenshot"] = screenshot_path

        return artifacts

    def close(self) -> None:
        """Close browser resources safely and idempotently."""
        context = self._context
        playwright = self._playwright
        self._context = None
        self._playwright = None
        self._last_page = None

        if context is not None:
            context.close()
        if playwright is not None:
            playwright.stop()

    def __enter__(self) -> BrowserSessionManager:
        self.launch()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def _ensure_playwright_available(self) -> None:
        if sync_playwright is None:
            raise RuntimeError(
                "Playwright is not installed. Add 'playwright' to project dependencies before launching a browser session."
            )


def _normalize_screenshot_name(name: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in name.strip())
    cleaned = cleaned.strip("._") or "screenshot"
    if not cleaned.endswith(".png"):
        cleaned = f"{cleaned}.png"
    return cleaned


def _normalize_artifact_name(name: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in name.strip())
    return cleaned.strip("._") or "artifact"
