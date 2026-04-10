from __future__ import annotations

from job_agent.core.models import DiscoveryQuery
from job_agent.flows.discover import run_discovery_query
from job_agent.storage.db import init_db
from job_agent.storage.jobs_repo import JobsRepository


class _FakeSession:
    def close(self) -> None:
        return None


def _greenhouse_page(*, jobs: list[tuple[str, str]], next_href: str | None = None) -> str:
    openings = []
    for job_id, title in jobs:
        openings.append(
            f"""
            <div class="opening">
              <a class="opening" href="/exampleco/jobs/{job_id}">{title}</a>
              <span class="location">Remote</span>
            </div>
            """
        )
    next_link = f'<a class="pagination__next" href="{next_href}">Next</a>' if next_href else ""
    return f"""
    <html>
      <body>
        <section class="level-0">Example Co</section>
        {''.join(openings)}
        <nav>{next_link}</nav>
      </body>
    </html>
    """


def test_greenhouse_pagination_traverses_multiple_pages(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "greenhouse_pagination.db"
    repo = JobsRepository(init_db(db_path))
    query = DiscoveryQuery(
        source_site="greenhouse",
        label="Example engineering",
        start_url="https://boards.greenhouse.io/exampleco",
    )
    pages = {
        "https://boards.greenhouse.io/exampleco": _greenhouse_page(
            jobs=[("1", "Backend Engineer"), ("2", "Data Engineer")],
            next_href="?page=2",
        ),
        "https://boards.greenhouse.io/exampleco?page=2": _greenhouse_page(
            jobs=[("3", "Platform Engineer")],
        ),
    }

    def fake_fetch(*, session, url, screenshot_name=None, wait_until="networkidle", wait_delay_ms=0):  # noqa: ARG001
        return pages[url]

    monkeypatch.setattr("job_agent.flows.discover.fetch_listing_page_html", fake_fetch)

    result = run_discovery_query(
        query=query,
        session=_FakeSession(),
        jobs_repo=repo,
        max_pages_per_query=3,
    )

    assert result.metadata["pages_fetched"] == 2
    assert result.metadata["pages_parsed"] == 2
    assert result.metadata["parsed_count"] == 3
    assert len(repo.list_jobs(source_site="greenhouse")) == 3


def test_greenhouse_pagination_falls_back_to_single_page_when_no_next_exists(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "greenhouse_pagination.db"
    repo = JobsRepository(init_db(db_path))
    query = DiscoveryQuery(
        source_site="greenhouse",
        label="Example engineering",
        start_url="https://boards.greenhouse.io/exampleco",
    )

    monkeypatch.setattr(
        "job_agent.flows.discover.fetch_listing_page_html",
        lambda **_: _greenhouse_page(jobs=[("1", "Backend Engineer")]),
    )

    result = run_discovery_query(
        query=query,
        session=_FakeSession(),
        jobs_repo=repo,
        max_pages_per_query=5,
    )

    assert result.metadata["pages_fetched"] == 1
    assert result.metadata["pages_parsed"] == 1
    assert result.metadata["parsed_count"] == 1
    assert len(repo.list_jobs(source_site="greenhouse")) == 1


def test_greenhouse_pagination_stops_on_repeated_page_url(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "greenhouse_pagination.db"
    repo = JobsRepository(init_db(db_path))
    query = DiscoveryQuery(
        source_site="greenhouse",
        label="Example engineering",
        start_url="https://boards.greenhouse.io/exampleco",
    )
    pages = {
        "https://boards.greenhouse.io/exampleco": _greenhouse_page(
            jobs=[("1", "Backend Engineer")],
            next_href="https://boards.greenhouse.io/exampleco",
        ),
    }

    def fake_fetch(*, session, url, screenshot_name=None, wait_until="networkidle", wait_delay_ms=0):  # noqa: ARG001
        return pages[url]

    monkeypatch.setattr("job_agent.flows.discover.fetch_listing_page_html", fake_fetch)

    result = run_discovery_query(
        query=query,
        session=_FakeSession(),
        jobs_repo=repo,
        max_pages_per_query=5,
    )

    assert result.metadata["pages_fetched"] == 1
    assert result.metadata["pages_parsed"] == 1
    assert result.metadata["parsed_count"] == 1


def test_greenhouse_pagination_stops_at_page_limit(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "greenhouse_pagination.db"
    repo = JobsRepository(init_db(db_path))
    query = DiscoveryQuery(
        source_site="greenhouse",
        label="Example engineering",
        start_url="https://boards.greenhouse.io/exampleco",
    )
    pages = {
        "https://boards.greenhouse.io/exampleco": _greenhouse_page(
            jobs=[("1", "Backend Engineer")],
            next_href="?page=2",
        ),
        "https://boards.greenhouse.io/exampleco?page=2": _greenhouse_page(
            jobs=[("2", "Data Engineer")],
            next_href="?page=3",
        ),
        "https://boards.greenhouse.io/exampleco?page=3": _greenhouse_page(
            jobs=[("3", "Platform Engineer")],
        ),
    }

    def fake_fetch(*, session, url, screenshot_name=None, wait_until="networkidle", wait_delay_ms=0):  # noqa: ARG001
        return pages[url]

    monkeypatch.setattr("job_agent.flows.discover.fetch_listing_page_html", fake_fetch)

    result = run_discovery_query(
        query=query,
        session=_FakeSession(),
        jobs_repo=repo,
        max_pages_per_query=2,
    )

    assert result.metadata["pages_fetched"] == 2
    assert result.metadata["pages_parsed"] == 2
    assert result.metadata["parsed_count"] == 2
    assert len(repo.list_jobs(source_site="greenhouse")) == 2


def test_greenhouse_pagination_stops_on_empty_page_after_success(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "greenhouse_pagination.db"
    repo = JobsRepository(init_db(db_path))
    query = DiscoveryQuery(
        source_site="greenhouse",
        label="Example engineering",
        start_url="https://boards.greenhouse.io/exampleco",
    )
    pages = {
        "https://boards.greenhouse.io/exampleco": _greenhouse_page(
            jobs=[("1", "Backend Engineer")],
            next_href="?page=2",
        ),
        "https://boards.greenhouse.io/exampleco?page=2": _greenhouse_page(
            jobs=[],
            next_href="?page=3",
        ),
    }

    def fake_fetch(*, session, url, screenshot_name=None, wait_until="networkidle", wait_delay_ms=0):  # noqa: ARG001
        return pages[url]

    monkeypatch.setattr("job_agent.flows.discover.fetch_listing_page_html", fake_fetch)

    result = run_discovery_query(
        query=query,
        session=_FakeSession(),
        jobs_repo=repo,
        max_pages_per_query=3,
    )

    assert result.metadata["pages_fetched"] == 2
    assert result.metadata["pages_parsed"] == 1
    assert result.metadata["parsed_count"] == 1
    assert len(repo.list_jobs(source_site="greenhouse")) == 1
