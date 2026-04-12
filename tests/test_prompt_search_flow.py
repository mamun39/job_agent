from __future__ import annotations

from datetime import UTC, datetime

import pytest

from job_agent.core.models import BoardRegistryEntry, CrawlResult, DiscoveryOptions, JobPosting, SearchIntent, SearchQuery
from job_agent.flows.prompt_search import run_prompt_search
from job_agent.storage.db import init_db
from job_agent.storage.jobs_repo import JobsRepository


def _registry() -> list[BoardRegistryEntry]:
    return [
        BoardRegistryEntry(
            company_name="Stripe",
            source_site="greenhouse",
            board_url="https://boards.greenhouse.io/stripe",
            tags=["backend", "python"],
            location_hints=["Canada", "Remote"],
        ),
        BoardRegistryEntry(
            company_name="Shopify",
            source_site="lever",
            board_url="https://jobs.lever.co/shopify",
            tags=["platform"],
            location_hints=["Canada"],
        ),
        BoardRegistryEntry(
            company_name="LinkedIn",
            source_site="linkedin",
            board_url="https://www.linkedin.com/jobs/search/?keywords=security&f_C=1337",
            tags=["security"],
            location_hints=["Canada", "Remote"],
        ),
    ]


def _job(
    *,
    url: str,
    title: str,
    company: str,
    location: str,
    source_site: str,
    remote_status: str = "remote",
    posted_at: datetime | None = None,
    description_text: str = "Build backend systems.",
) -> JobPosting:
    source_job_id = url.rstrip("/").rsplit("/", 1)[-1]
    return JobPosting(
        source_site=source_site,
        source_job_id=source_job_id,
        url=url,
        title=title,
        company=company,
        location=location,
        remote_status=remote_status,
        posted_at=posted_at,
        discovered_at=datetime(2026, 4, 11, tzinfo=UTC),
        last_seen_at=datetime(2026, 4, 11, tzinfo=UTC),
        description_text=description_text,
    )


def _result_for(*jobs: JobPosting, source_site: str) -> CrawlResult:
    return CrawlResult(
        query=SearchQuery(),
        postings=list(jobs),
        source_site=source_site,
        metadata={"parsed_count": len(jobs)},
    )


def test_prompt_search_runs_end_to_end_with_seeded_board(monkeypatch, tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "prompt.db"))
    captured_queries: list[tuple[str, str]] = []

    def fake_run_discovery_query(*, query, session, jobs_repo, options=None, **kwargs):
        captured_queries.append((query.source_site, str(query.start_url)))
        return _result_for(
            _job(
                url="https://boards.greenhouse.io/stripe/jobs/1",
                title="Backend Engineer",
                company="Stripe",
                location="Remote - Canada",
                source_site="greenhouse",
                posted_at=datetime(2026, 4, 10, tzinfo=UTC),
            ),
            source_site="greenhouse",
        )

    monkeypatch.setattr("job_agent.flows.prompt_search.run_discovery_query", fake_run_discovery_query)

    result = run_prompt_search(
        prompt_text="Find remote backend jobs at Stripe in Canada on Greenhouse from the last 7 days.",
        session=object(),
        jobs_repo=repo,
        board_registry=_registry(),
        options=DiscoveryOptions(),
        now=datetime(2026, 4, 11, tzinfo=UTC),
    )

    assert captured_queries == [("greenhouse", "https://boards.greenhouse.io/stripe")]
    assert result.discovered_jobs_count == 1
    assert len(result.matched_jobs) == 1
    assert result.rejected_jobs == []
    assert result.matched_jobs[0].job.title == "Backend Engineer"
    assert result.matched_jobs[0].hard_filter_explanation == "Passed explicit hard filters."
    assert result.matched_jobs[0].score >= 0
    assert result.matched_jobs[0].score_reasons
    assert any("matched include keyword" in item or "matched preferred value" in item for item in result.matched_jobs[0].score_reasons)
    assert result.plan.queries[0].board_url is not None
    assert str(result.plan.queries[0].board_url) == "https://boards.greenhouse.io/stripe"


def test_prompt_search_handles_partially_parsed_prompt(monkeypatch, tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "prompt.db"))

    def fake_run_discovery_query(*, query, session, jobs_repo, options=None, **kwargs):
        return _result_for(
            _job(
                url="https://boards.greenhouse.io/stripe/jobs/2",
                title="Software Engineer",
                company="Stripe",
                location="Remote - Canada",
                source_site="greenhouse",
            ),
            source_site="greenhouse",
        )

    monkeypatch.setattr("job_agent.flows.prompt_search.run_discovery_query", fake_run_discovery_query)

    result = run_prompt_search(
        prompt_text="Find something interesting at Stripe.",
        session=object(),
        jobs_repo=repo,
        board_registry=_registry(),
        options=DiscoveryOptions(),
        now=datetime(2026, 4, 11, tzinfo=UTC),
    )

    assert result.intent.constraints.target_titles == []
    assert result.intent.constraints.include_companies == ["Stripe"]
    assert result.discovered_jobs_count == 1
    assert len(result.matched_jobs) == 1
    assert result.matched_jobs[0].hard_filter_explanation == "Passed explicit hard filters."


def test_prompt_search_fails_honestly_when_no_executable_board_resolves(tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "prompt.db"))

    with pytest.raises(ValueError) as exc_info:
        run_prompt_search(
            prompt_text="Find backend jobs at Unknown Co.",
            session=object(),
            jobs_repo=repo,
            board_registry=_registry(),
            options=DiscoveryOptions(),
        )

    assert "No board registry entries matched companies [Unknown Co]" in str(exc_info.value)


def test_prompt_search_returns_rejected_jobs_with_reasons(monkeypatch, tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "prompt.db"))

    def fake_run_discovery_query(*, query, session, jobs_repo, options=None, **kwargs):
        return _result_for(
            _job(
                url="https://boards.greenhouse.io/stripe/jobs/3",
                title="Backend Engineer",
                company="Stripe",
                location="Remote - Canada",
                source_site="greenhouse",
                description_text="Build crypto payment systems.",
            ),
            _job(
                url="https://boards.greenhouse.io/stripe/jobs/4",
                title="Backend Engineer",
                company="Stripe",
                location="Remote - Canada",
                source_site="greenhouse",
                description_text="Build compliant backend systems.",
            ),
            source_site="greenhouse",
        )

    monkeypatch.setattr("job_agent.flows.prompt_search.run_discovery_query", fake_run_discovery_query)

    result = run_prompt_search(
        prompt_text="Find backend jobs at Stripe in Canada, avoid crypto.",
        session=object(),
        jobs_repo=repo,
        board_registry=_registry(),
        options=DiscoveryOptions(),
        now=datetime(2026, 4, 11, tzinfo=UTC),
    )

    assert result.discovered_jobs_count == 2
    assert len(result.matched_jobs) == 1
    assert len(result.rejected_jobs) == 1
    assert result.rejected_jobs[0].job.url.unicode_string() == "https://boards.greenhouse.io/stripe/jobs/3"
    assert result.rejected_jobs[0].rejection_reasons == ["Excluded keyword 'crypto' matched description"]
    assert result.rejected_jobs[0].explanation == "Excluded keyword 'crypto' matched description"


def test_prompt_search_can_target_linkedin_when_explicitly_requested(monkeypatch, tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "prompt.db"))
    captured_queries: list[tuple[str, str]] = []

    def fake_run_discovery_query(*, query, session, jobs_repo, options=None, **kwargs):
        captured_queries.append((query.source_site, str(query.start_url)))
        return _result_for(
            _job(
                url="https://www.linkedin.com/jobs/view/1234567890/",
                title="Security Engineer",
                company="LinkedIn",
                location="Remote - Canada",
                source_site="linkedin",
                posted_at=datetime(2026, 4, 10, tzinfo=UTC),
            ),
            source_site="linkedin",
        )

    monkeypatch.setattr("job_agent.flows.prompt_search.run_discovery_query", fake_run_discovery_query)
    monkeypatch.setattr(
        "job_agent.flows.prompt_search.parse_search_intent",
        lambda prompt_text: SearchIntent(
            prompt_text=prompt_text,
            constraints={
                "target_titles": ["Security Engineer"],
                "include_companies": ["LinkedIn"],
                "location_constraints": ["Canada"],
                "source_site_preferences": ["linkedin"],
            },
        ),
    )

    result = run_prompt_search(
        prompt_text="Find security roles at LinkedIn in Canada on LinkedIn.",
        session=object(),
        jobs_repo=repo,
        board_registry=_registry(),
        options=DiscoveryOptions(),
        now=datetime(2026, 4, 11, tzinfo=UTC),
    )

    assert captured_queries == [("linkedin", "https://www.linkedin.com/jobs/search/?keywords=security&f_C=1337")]
    assert result.discovered_jobs_count == 1
    assert len(result.matched_jobs) == 1
    assert result.plan.queries[0].source_site == "linkedin"
