from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from job_agent.browser.fetch import build_debug_artifact_dir, capture_debug_artifacts
from job_agent.config import load_settings
from job_agent.core.models import DiscoveryQuery
from job_agent.flows.discover import run_discovery_query
from job_agent.storage.db import init_db
from job_agent.storage.jobs_repo import JobsRepository


class _FakePage:
    def __init__(self, html: str = "<html></html>") -> None:
        self._html = html
        self.screenshots: list[str] = []

    def content(self) -> str:
        return self._html

    def screenshot(self, *, path: str) -> None:
        Path(path).write_text("png", encoding="utf-8")
        self.screenshots.append(path)


class _FakeSession:
    def __init__(self, *, html: str = "<html></html>", fail_save: bool = False) -> None:
        self.page = _FakePage(html)
        self.fail_save = fail_save

    def save_debug_artifacts(self, *, directory: Path, name: str, html: str | None = None) -> dict[str, Path]:
        if self.fail_save:
            raise RuntimeError("artifact save failed")
        directory.mkdir(parents=True, exist_ok=True)
        html_path = directory / f"{name}.html"
        html_path.write_text(html or self.page.content(), encoding="utf-8")
        png_path = directory / f"{name}.png"
        png_path.write_text("png", encoding="utf-8")
        return {"html": html_path, "screenshot": png_path}

    def close(self) -> None:
        return None


def test_build_debug_artifact_dir_uses_site_query_and_timestamp(tmp_path) -> None:
    target = build_debug_artifact_dir(
        base_dir=tmp_path,
        site_name="greenhouse",
        query_label="Example Engineering",
        timestamp=datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc),
    )

    assert target == tmp_path / "greenhouse" / "Example_Engineering" / "20260410T120000Z"


def test_capture_debug_artifacts_saves_html_and_screenshot(tmp_path) -> None:
    session = _FakeSession(html="<html>captured</html>")

    artifacts = capture_debug_artifacts(
        session=session,
        base_dir=tmp_path,
        site_name="greenhouse",
        query_label="Example Engineering",
        artifact_name="listing_parse_failure_page_1",
        timestamp=datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc),
    )

    assert artifacts["html"].read_text(encoding="utf-8") == "<html>captured</html>"
    assert artifacts["screenshot"].read_text(encoding="utf-8") == "png"


def test_capture_debug_artifacts_ignores_save_failures(tmp_path) -> None:
    session = _FakeSession(fail_save=True)

    artifacts = capture_debug_artifacts(
        session=session,
        base_dir=tmp_path,
        site_name="greenhouse",
        query_label="Example Engineering",
        artifact_name="listing_parse_failure_page_1",
    )

    assert artifacts == {}


def test_discovery_debug_artifacts_only_capture_when_enabled(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "artifacts.db"
    repo = JobsRepository(init_db(db_path))
    query = DiscoveryQuery(
        source_site="greenhouse",
        label="Example engineering",
        start_url="https://boards.greenhouse.io/exampleco",
    )
    listing_html = """
    <html><body>
      <section class="level-0">Example Co</section>
      <div class="opening">
        <a class="opening" href="/exampleco/jobs/12345">Backend Engineer</a>
        <span class="location">Remote</span>
      </div>
    </body></html>
    """

    def fake_fetch(**kwargs):
        if kwargs["url"] == "https://boards.greenhouse.io/exampleco":
            return listing_html
        raise RuntimeError("detail failed")

    monkeypatch.setattr("job_agent.flows.discover.fetch_listing_page_html", fake_fetch)
    monkeypatch.setattr(
        "job_agent.flows.discover.capture_debug_artifacts",
        lambda **kwargs: {"html": Path(kwargs["base_dir"]) / "saved.html"},
    )

    run_discovery_query(
        query=query,
        session=_FakeSession(),
        jobs_repo=repo,
        options=None,
        debug_artifacts_on_failure=True,
        debug_artifacts_dir=tmp_path / "enabled",
    )

    enabled_dir = tmp_path / "enabled"
    assert enabled_dir.exists() is False

    run_discovery_query(
        query=query,
        session=_FakeSession(),
        jobs_repo=JobsRepository(init_db(tmp_path / "disabled.db")),
        options=None,
        debug_artifacts_on_failure=False,
        debug_artifacts_dir=tmp_path / "disabled",
    )

    assert (tmp_path / "disabled").exists() is False


def test_load_settings_reads_debug_artifact_config(monkeypatch) -> None:
    monkeypatch.setenv("JOB_AGENT_DEBUG_ARTIFACTS_ON_FAILURE", "true")
    monkeypatch.setenv("JOB_AGENT_DEBUG_ARTIFACTS_DIR", "C:\\debug-artifacts")

    settings = load_settings()

    assert settings.debug_artifacts_on_failure is True
    assert settings.debug_artifacts_dir == Path("C:/debug-artifacts")
