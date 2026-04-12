from __future__ import annotations

from pathlib import Path

from job_agent.browser.session import BrowserSessionManager
from job_agent.config import Settings


class _FakePage:
    def __init__(self) -> None:
        self.screenshot_paths: list[str] = []

    def screenshot(self, *, path: str) -> None:
        Path(path).write_bytes(b"fake-image")
        self.screenshot_paths.append(path)

    def content(self) -> str:
        return "<html></html>"


class _FakeContext:
    def __init__(self, pages: list[_FakePage] | None = None) -> None:
        self.pages = pages or []
        self.created_pages = 0
        self.closed = False

    def new_page(self) -> _FakePage:
        self.created_pages += 1
        page = _FakePage()
        self.pages.append(page)
        return page

    def close(self) -> None:
        self.closed = True


class _FakeChromium:
    def __init__(self, context: _FakeContext) -> None:
        self.context = context
        self.calls: list[dict[str, object]] = []
        self.cdp_calls: list[str] = []
        self.browser: _FakeBrowser | None = None

    def launch_persistent_context(self, **kwargs) -> _FakeContext:
        self.calls.append(kwargs)
        return self.context

    def connect_over_cdp(self, url: str) -> "_FakeBrowser":
        self.cdp_calls.append(url)
        assert self.browser is not None
        return self.browser


class _FakeBrowser:
    def __init__(self, contexts: list[_FakeContext]) -> None:
        self.contexts = contexts
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakePlaywright:
    def __init__(self, chromium: _FakeChromium) -> None:
        self.chromium = chromium
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class _FakeSyncPlaywrightFactory:
    def __init__(self, playwright: _FakePlaywright) -> None:
        self.playwright = playwright
        self.started = False

    def start(self) -> _FakePlaywright:
        self.started = True
        return self.playwright


def test_browser_session_from_settings_uses_config_paths(tmp_path) -> None:
    settings = Settings(
        browser_user_data_dir=tmp_path / "profile",
        browser_screenshot_dir=tmp_path / "shots",
        browser_headless=True,
    )

    session = BrowserSessionManager.from_settings(settings)

    assert session.user_data_dir == tmp_path / "profile"
    assert session.screenshot_dir == tmp_path / "shots"
    assert session.headless is True


def test_launch_creates_missing_paths_and_uses_persistent_context(tmp_path, monkeypatch) -> None:
    fake_context = _FakeContext()
    fake_chromium = _FakeChromium(fake_context)
    fake_playwright = _FakePlaywright(fake_chromium)
    fake_factory = _FakeSyncPlaywrightFactory(fake_playwright)
    monkeypatch.setattr("job_agent.browser.session.sync_playwright", lambda: fake_factory)

    session = BrowserSessionManager(
        user_data_dir=tmp_path / "profile",
        screenshot_dir=tmp_path / "shots",
        headless=False,
    )

    context = session.launch()

    assert context is fake_context
    assert session.user_data_dir.is_dir()
    assert session.screenshot_dir.is_dir()
    assert fake_factory.started is True
    assert fake_chromium.calls == [{"user_data_dir": str(tmp_path / "profile"), "headless": False}]


def test_open_page_reuses_existing_page_or_creates_one(tmp_path, monkeypatch) -> None:
    existing_page = _FakePage()
    fake_context = _FakeContext(pages=[existing_page])
    fake_chromium = _FakeChromium(fake_context)
    fake_playwright = _FakePlaywright(fake_chromium)
    fake_factory = _FakeSyncPlaywrightFactory(fake_playwright)
    monkeypatch.setattr("job_agent.browser.session.sync_playwright", lambda: fake_factory)

    session = BrowserSessionManager(
        user_data_dir=tmp_path / "profile",
        screenshot_dir=tmp_path / "shots",
    )

    page = session.open_page()
    assert page is existing_page

    fake_context.pages.clear()
    page = session.open_page()
    assert page in fake_context.pages
    assert fake_context.created_pages == 1


def test_take_screenshot_creates_png_file(tmp_path) -> None:
    session = BrowserSessionManager(
        user_data_dir=tmp_path / "profile",
        screenshot_dir=tmp_path / "shots",
    )
    page = _FakePage()

    output = session.take_screenshot(name="home page", page=page)

    assert output.name == "home_page.png"
    assert output.is_file()
    assert page.screenshot_paths == [str(output)]


def test_close_is_safe_and_idempotent(tmp_path, monkeypatch) -> None:
    fake_context = _FakeContext()
    fake_chromium = _FakeChromium(fake_context)
    fake_playwright = _FakePlaywright(fake_chromium)
    fake_factory = _FakeSyncPlaywrightFactory(fake_playwright)
    monkeypatch.setattr("job_agent.browser.session.sync_playwright", lambda: fake_factory)

    session = BrowserSessionManager(
        user_data_dir=tmp_path / "profile",
        screenshot_dir=tmp_path / "shots",
    )
    session.launch()

    session.close()
    session.close()

    assert fake_context.closed is True
    assert fake_playwright.stopped is True


def test_authenticated_profile_mode_requires_existing_profile_dir(tmp_path, monkeypatch) -> None:
    fake_context = _FakeContext()
    fake_chromium = _FakeChromium(fake_context)
    fake_playwright = _FakePlaywright(fake_chromium)
    fake_factory = _FakeSyncPlaywrightFactory(fake_playwright)
    monkeypatch.setattr("job_agent.browser.session.sync_playwright", lambda: fake_factory)

    session = BrowserSessionManager(
        user_data_dir=tmp_path / "profile",
        screenshot_dir=tmp_path / "shots",
        auth_mode="profile",
        auth_profile_dir=tmp_path / "missing-profile",
    )

    try:
        session.launch()
    except RuntimeError as exc:
        assert "does not exist" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected RuntimeError for missing authenticated profile directory")


def test_authenticated_attach_mode_requires_cdp_url(tmp_path, monkeypatch) -> None:
    fake_context = _FakeContext()
    fake_chromium = _FakeChromium(fake_context)
    fake_playwright = _FakePlaywright(fake_chromium)
    fake_factory = _FakeSyncPlaywrightFactory(fake_playwright)
    monkeypatch.setattr("job_agent.browser.session.sync_playwright", lambda: fake_factory)

    session = BrowserSessionManager(
        user_data_dir=tmp_path / "profile",
        screenshot_dir=tmp_path / "shots",
        auth_mode="attach",
    )

    try:
        session.launch()
    except RuntimeError as exc:
        assert "requires a Chromium CDP URL" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected RuntimeError for missing CDP URL")


def test_authenticated_attach_mode_reuses_existing_browser_context(tmp_path, monkeypatch) -> None:
    attached_context = _FakeContext(pages=[_FakePage()])
    fake_browser = _FakeBrowser([attached_context])
    fake_context = _FakeContext()
    fake_chromium = _FakeChromium(fake_context)
    fake_chromium.browser = fake_browser
    fake_playwright = _FakePlaywright(fake_chromium)
    fake_factory = _FakeSyncPlaywrightFactory(fake_playwright)
    monkeypatch.setattr("job_agent.browser.session.sync_playwright", lambda: fake_factory)

    session = BrowserSessionManager(
        user_data_dir=tmp_path / "profile",
        screenshot_dir=tmp_path / "shots",
        auth_mode="attach",
        auth_cdp_url="http://127.0.0.1:9222",
    )

    context = session.launch()
    session.close()

    assert context is attached_context
    assert fake_chromium.calls == []
    assert fake_chromium.cdp_calls == ["http://127.0.0.1:9222"]
    assert fake_browser.closed is False
    assert fake_playwright.stopped is True


def test_authenticated_profile_mode_can_reuse_named_chromium_subprofile(tmp_path, monkeypatch) -> None:
    profile_root = tmp_path / "Google" / "Chrome" / "User Data"
    profile_dir = profile_root / "Profile 1"
    profile_dir.mkdir(parents=True)
    fake_context = _FakeContext()
    fake_chromium = _FakeChromium(fake_context)
    fake_playwright = _FakePlaywright(fake_chromium)
    fake_factory = _FakeSyncPlaywrightFactory(fake_playwright)
    monkeypatch.setattr("job_agent.browser.session.sync_playwright", lambda: fake_factory)

    session = BrowserSessionManager(
        user_data_dir=tmp_path / "profile",
        screenshot_dir=tmp_path / "shots",
        auth_mode="profile",
        auth_profile_dir=profile_dir,
    )

    session.launch()

    assert fake_chromium.calls == [
        {
            "user_data_dir": str(profile_root),
            "args": ["--profile-directory=Profile 1"],
            "channel": "chrome",
            "headless": False,
        }
    ]
