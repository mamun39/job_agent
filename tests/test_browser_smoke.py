from __future__ import annotations

from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import threading

import pytest

from job_agent.browser.fetch import fetch_page_html, fetch_page_html_with_screenshot
from job_agent.browser.session import BrowserSessionManager, sync_playwright


pytestmark = pytest.mark.smoke


@contextmanager
def _local_fixture_server(root: Path):
    class _Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, format: str, *args) -> None:  # pragma: no cover - suppress noisy server logs
            return None

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        host, port = probe.getsockname()

    server = ThreadingHTTPServer((host, port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _require_real_playwright_browser() -> None:
    if sync_playwright is None:
        pytest.skip("Playwright is not installed in this environment.")
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser.close()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"Playwright Chromium is unavailable for smoke tests: {exc}")


def test_real_browser_fetch_and_screenshot_smoke(tmp_path: Path) -> None:
    _require_real_playwright_browser()

    fixture_dir = tmp_path / "site"
    fixture_dir.mkdir()
    (fixture_dir / "index.html").write_text(
        """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>job-agent smoke</title>
  </head>
  <body>
    <main id="content">
      <h1>Local Smoke Fixture</h1>
      <p data-test="message">Browser smoke path exercised.</p>
    </main>
  </body>
</html>
""",
        encoding="utf-8",
    )

    session = BrowserSessionManager(
        user_data_dir=tmp_path / "profile",
        screenshot_dir=tmp_path / "screenshots",
        headless=True,
    )
    with _local_fixture_server(fixture_dir) as base_url:
        try:
            html = fetch_page_html(
                session=session,
                url=f"{base_url}/index.html",
                wait_until="load",
            )
            html_with_shot, screenshot_path = fetch_page_html_with_screenshot(
                session=session,
                url=f"{base_url}/index.html",
                screenshot_name="smoke-index",
                wait_until="load",
            )
        finally:
            session.close()

    assert "<h1>Local Smoke Fixture</h1>" in html
    assert 'data-test="message"' in html_with_shot
    assert screenshot_path.is_file()
    assert screenshot_path.suffix == ".png"
