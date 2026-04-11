from __future__ import annotations

from job_agent.core.models import DiscoveryQuery
from job_agent.flows.discover import run_discovery_query
from job_agent.storage.db import init_db
from job_agent.storage.jobs_repo import JobsRepository


class _FakeSession:
    def close(self) -> None:
        return None


def _lever_page(*, jobs: list[tuple[str, str]], next_href: str | None = None) -> str:
    postings = []
    for job_id, title in jobs:
        postings.append(
            f"""
            <div class="posting">
              <a class="posting-title" href="/exampleco/{job_id}"></a>
              <h5 class="posting-name">{title}</h5>
              <span class="sort-by-location">Remote</span>
            </div>
            """
        )
    next_link = f'<a class="pagination__next" href="{next_href}">Next</a>' if next_href else ""
    return f"""
    <html>
      <body>
        <div class="main-header-text">Example Co</div>
        {''.join(postings)}
        <nav>{next_link}</nav>
      </body>
    </html>
    """


def test_lever_pagination_traverses_multiple_pages(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "lever_pagination.db"
    repo = JobsRepository(init_db(db_path))
    query = DiscoveryQuery(
        source_site="lever",
        label="Example engineering",
        start_url="https://jobs.lever.co/exampleco",
    )
    pages = {
        "https://jobs.lever.co/exampleco": _lever_page(
            jobs=[("backend-engineer", "Backend Engineer"), ("data-engineer", "Data Engineer")],
            next_href="?page=2",
        ),
        "https://jobs.lever.co/exampleco?page=2": _lever_page(
            jobs=[("platform-engineer", "Platform Engineer")],
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
    assert len(repo.list_jobs(source_site="lever")) == 3


def test_lever_pagination_falls_back_to_single_page_when_no_next_exists(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "lever_pagination.db"
    repo = JobsRepository(init_db(db_path))
    query = DiscoveryQuery(
        source_site="lever",
        label="Example engineering",
        start_url="https://jobs.lever.co/exampleco",
    )

    monkeypatch.setattr(
        "job_agent.flows.discover.fetch_listing_page_html",
        lambda **_: _lever_page(jobs=[("backend-engineer", "Backend Engineer")]),
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
    assert len(repo.list_jobs(source_site="lever")) == 1


def test_lever_pagination_stops_on_repeated_page_url(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "lever_pagination.db"
    repo = JobsRepository(init_db(db_path))
    query = DiscoveryQuery(
        source_site="lever",
        label="Example engineering",
        start_url="https://jobs.lever.co/exampleco",
    )
    pages = {
        "https://jobs.lever.co/exampleco": _lever_page(
            jobs=[("backend-engineer", "Backend Engineer")],
            next_href="https://jobs.lever.co/exampleco",
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


def test_lever_pagination_stops_at_page_limit(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "lever_pagination.db"
    repo = JobsRepository(init_db(db_path))
    query = DiscoveryQuery(
        source_site="lever",
        label="Example engineering",
        start_url="https://jobs.lever.co/exampleco",
    )
    pages = {
        "https://jobs.lever.co/exampleco": _lever_page(
            jobs=[("backend-engineer", "Backend Engineer")],
            next_href="?page=2",
        ),
        "https://jobs.lever.co/exampleco?page=2": _lever_page(
            jobs=[("data-engineer", "Data Engineer")],
            next_href="?page=3",
        ),
        "https://jobs.lever.co/exampleco?page=3": _lever_page(
            jobs=[("platform-engineer", "Platform Engineer")],
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
    assert len(repo.list_jobs(source_site="lever")) == 2


def test_lever_pagination_stops_on_empty_page_after_success(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "lever_pagination.db"
    repo = JobsRepository(init_db(db_path))
    query = DiscoveryQuery(
        source_site="lever",
        label="Example engineering",
        start_url="https://jobs.lever.co/exampleco",
    )
    pages = {
        "https://jobs.lever.co/exampleco": _lever_page(
            jobs=[("backend-engineer", "Backend Engineer")],
            next_href="?page=2",
        ),
        "https://jobs.lever.co/exampleco?page=2": _lever_page(
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
    assert len(repo.list_jobs(source_site="lever")) == 1
