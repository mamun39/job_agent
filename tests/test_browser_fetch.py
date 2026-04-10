from __future__ import annotations

from pathlib import Path

from job_agent.browser.fetch import fetch_page_html, fetch_page_html_with_screenshot
from job_agent.browser.session import BrowserSessionManager


class _FakePage:
    def __init__(self) -> None:
        self.goto_calls: list[tuple[str, str]] = []
        self.timeout_calls: list[int] = []
        self.screenshot_paths: list[str] = []

    def goto(self, url: str, *, wait_until: str) -> None:
        self.goto_calls.append((url, wait_until))

    def wait_for_timeout(self, timeout_ms: int) -> None:
        self.timeout_calls.append(timeout_ms)

    def content(self) -> str:
        return "<html><body>fixture</body></html>"

    def screenshot(self, *, path: str) -> None:
        Path(path).write_bytes(b"fake-image")
        self.screenshot_paths.append(path)


def test_fetch_page_html_returns_content_and_waits(tmp_path, monkeypatch) -> None:
    page = _FakePage()
    session = BrowserSessionManager(
        user_data_dir=tmp_path / "profile",
        screenshot_dir=tmp_path / "shots",
    )
    monkeypatch.setattr(session, "open_url", lambda url, wait_until="networkidle": page)

    html = fetch_page_html(
        session=session,
        url="https://example.com/jobs",
        wait_until="networkidle",
        wait_delay_ms=250,
    )

    assert html == "<html><body>fixture</body></html>"
    assert page.timeout_calls == [250]


def test_fetch_page_html_optionally_saves_screenshot(tmp_path, monkeypatch) -> None:
    page = _FakePage()
    session = BrowserSessionManager(
        user_data_dir=tmp_path / "profile",
        screenshot_dir=tmp_path / "shots",
    )
    monkeypatch.setattr(session, "open_url", lambda url, wait_until="networkidle": page)

    html = fetch_page_html(
        session=session,
        url="https://example.com/jobs",
        screenshot_name="listing page",
    )

    assert html == "<html><body>fixture</body></html>"
    assert len(page.screenshot_paths) == 1
    assert page.screenshot_paths[0].endswith("listing_page.png")


def test_fetch_page_html_with_screenshot_returns_path(tmp_path, monkeypatch) -> None:
    page = _FakePage()
    session = BrowserSessionManager(
        user_data_dir=tmp_path / "profile",
        screenshot_dir=tmp_path / "shots",
    )
    monkeypatch.setattr(session, "open_url", lambda url, wait_until="networkidle": page)

    html, screenshot_path = fetch_page_html_with_screenshot(
        session=session,
        url="https://example.com/jobs",
        screenshot_name="detail",
        wait_delay_ms=100,
    )

    assert html == "<html><body>fixture</body></html>"
    assert screenshot_path.name == "detail.png"
    assert screenshot_path.is_file()
    assert page.timeout_calls == [100]
