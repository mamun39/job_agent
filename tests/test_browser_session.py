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
        self.calls: list[tuple[str, bool]] = []

    def launch_persistent_context(self, *, user_data_dir: str, headless: bool) -> _FakeContext:
        self.calls.append((user_data_dir, headless))
        return self.context


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
    assert fake_chromium.calls == [(str(tmp_path / "profile"), False)]


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
