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
            return pages[0]
        return context.new_page()

    def take_screenshot(self, *, name: str, page: Page | None = None) -> Path:
        """Capture a page screenshot into the configured directory."""
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        target_page = page or self.open_page()
        output_path = self.screenshot_dir / _normalize_screenshot_name(name)
        target_page.screenshot(path=str(output_path))
        return output_path

    def close(self) -> None:
        """Close browser resources safely and idempotently."""
        context = self._context
        playwright = self._playwright
        self._context = None
        self._playwright = None

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
