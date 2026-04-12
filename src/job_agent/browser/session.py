"""Playwright browser session management."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from job_agent.config import Settings

try:
    from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright
except ImportError:  # pragma: no cover - exercised indirectly by guard behavior
    Browser = Any  # type: ignore[assignment]
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
        auth_mode: str | None = None,
        auth_profile_dir: Path | None = None,
        auth_cdp_url: str | None = None,
    ) -> None:
        self.user_data_dir = user_data_dir
        self.screenshot_dir = screenshot_dir
        self.headless = headless
        self.auth_mode = auth_mode
        self.auth_profile_dir = auth_profile_dir
        self.auth_cdp_url = auth_cdp_url
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._last_page: Page | None = None
        self._owns_context = True

    @classmethod
    def from_settings(cls, settings: Settings) -> BrowserSessionManager:
        """Build a session manager from application settings."""
        return cls(
            user_data_dir=settings.browser_user_data_dir,
            screenshot_dir=settings.browser_screenshot_dir,
            headless=settings.browser_headless,
            auth_mode=settings.browser_auth_mode,
            auth_profile_dir=settings.browser_auth_profile_dir,
            auth_cdp_url=settings.browser_auth_cdp_url,
        )

    def launch(self) -> BrowserContext:
        """Start Playwright and launch a persistent Chromium context."""
        self._ensure_playwright_available()
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        if self._context is not None:
            return self._context

        self._playwright = sync_playwright().start()
        self._context = self._launch_context()
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
        browser = self._browser
        playwright = self._playwright
        self._context = None
        self._browser = None
        self._playwright = None
        self._last_page = None
        owns_context = self._owns_context
        self._owns_context = True

        if context is not None and owns_context:
            context.close()
        if browser is not None and owns_context:
            browser.close()
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

    def _launch_context(self) -> BrowserContext:
        mode = self.auth_mode
        if mode is None:
            self._owns_context = True
            self.user_data_dir.mkdir(parents=True, exist_ok=True)
            return self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.user_data_dir),
                headless=self.headless,
            )
        if mode == "profile":
            return self._launch_authenticated_profile_context()
        if mode == "attach":
            return self._attach_to_existing_browser_context()
        raise RuntimeError(f"Unsupported browser auth mode: {mode}")

    def _launch_authenticated_profile_context(self) -> BrowserContext:
        profile_dir = self.auth_profile_dir
        if profile_dir is None:
            raise RuntimeError(
                "Authenticated browser mode 'profile' requires a profile directory. "
                "Set JOB_AGENT_BROWSER_AUTH_PROFILE_DIR or pass --auth-browser-profile-dir."
            )
        if not profile_dir.is_dir():
            raise RuntimeError(
                f"Authenticated browser profile directory does not exist: {profile_dir}"
            )
        launch_kwargs = _resolve_authenticated_profile_launch_kwargs(profile_dir)
        self._owns_context = True
        return self._playwright.chromium.launch_persistent_context(**launch_kwargs, headless=self.headless)

    def _attach_to_existing_browser_context(self) -> BrowserContext:
        cdp_url = self.auth_cdp_url
        if cdp_url is None:
            raise RuntimeError(
                "Authenticated browser mode 'attach' requires a Chromium CDP URL. "
                "Set JOB_AGENT_BROWSER_AUTH_CDP_URL or pass --auth-browser-cdp-url."
            )
        _validate_cdp_url(cdp_url)
        browser = self._playwright.chromium.connect_over_cdp(cdp_url)
        contexts = list(browser.contexts)
        if not contexts:
            raise RuntimeError(
                "Attached Chromium browser did not expose any browser contexts to reuse. "
                "Open the target browser with remote debugging enabled and an existing profile."
            )
        self._browser = browser
        self._owns_context = False
        return contexts[0]


def _normalize_screenshot_name(name: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in name.strip())
    cleaned = cleaned.strip("._") or "screenshot"
    if not cleaned.endswith(".png"):
        cleaned = f"{cleaned}.png"
    return cleaned


def _normalize_artifact_name(name: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in name.strip())
    return cleaned.strip("._") or "artifact"


def _validate_cdp_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"ws", "wss", "http", "https"} or not parsed.netloc:
        raise RuntimeError(
            "Authenticated browser CDP URL must be a valid http(s) or ws(s) URL."
        )


def _resolve_authenticated_profile_launch_kwargs(profile_dir: Path) -> dict[str, Any]:
    profile_name = profile_dir.name
    parent_dir = profile_dir.parent
    if profile_name == "Default" or profile_name.startswith("Profile "):
        launch_kwargs: dict[str, Any] = {
            "user_data_dir": str(parent_dir),
            "args": [f"--profile-directory={profile_name}"],
        }
        channel = _infer_chromium_channel(profile_dir)
        if channel is not None:
            launch_kwargs["channel"] = channel
        return launch_kwargs
    return {"user_data_dir": str(profile_dir)}


def _infer_chromium_channel(profile_dir: Path) -> str | None:
    normalized_parts = {part.casefold() for part in profile_dir.parts}
    if "chrome" in normalized_parts and "google" in normalized_parts:
        return "chrome"
    if "edge" in normalized_parts and "microsoft" in normalized_parts:
        return "msedge"
    return None
