from __future__ import annotations

from datetime import UTC, datetime

from job_agent.core.models import JobPosting, MatchedJobMatch, RejectedJobMatch
from job_agent.ui.cli import render_matched_jobs, render_rejected_jobs


def _job(*, url: str = "https://example.com/jobs/1") -> JobPosting:
    return JobPosting(
        source_site="greenhouse",
        source_job_id=url.rsplit("/", 1)[-1],
        url=url,
        title="Backend Engineer",
        company="Stripe",
        location="Remote - Canada",
        remote_status="remote",
        discovered_at=datetime(2026, 4, 11, tzinfo=UTC),
        last_seen_at=datetime(2026, 4, 11, tzinfo=UTC),
        description_text="Build backend systems.",
    )


def test_render_matched_jobs_includes_hard_filter_and_top_score_reasons() -> None:
    rendered = render_matched_jobs(
        [
            MatchedJobMatch(
                job=_job(),
                hard_filter_explanation="Passed explicit hard filters.",
                score=27,
                score_reasons=[
                    "+15 title matched include keyword 'backend'",
                    "+12 remote_status matched preferred value 'remote'",
                ],
            )
        ]
    )

    assert "score=27" in rendered
    assert "pass=Passed explicit hard filters." in rendered
    assert "reasons=+15 title matched include keyword 'backend'; +12 remote_status matched preferred value 'remote'" in rendered


def test_render_rejected_jobs_prefers_compact_rejection_explanation() -> None:
    rendered = render_rejected_jobs(
        [
            RejectedJobMatch(
                job=_job(url="https://example.com/jobs/2"),
                rejection_reasons=["Excluded keyword 'crypto' matched description"],
                explanation="Excluded keyword 'crypto' matched description",
            )
        ]
    )

    assert "Excluded keyword 'crypto' matched description" in rendered
