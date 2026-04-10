from __future__ import annotations

from job_agent.core.models import JobPosting
from job_agent.llm.summarizer import RuleBasedJobSummarizer, summarize_job_match
from job_agent.ui.cli import render_job_match_summary


def _make_job(*, score: int | None = 88) -> JobPosting:
    metadata = {}
    if score is not None:
        metadata["score"] = score
    return JobPosting(
        source_site="greenhouse",
        source_job_id="job-1",
        url="https://example.com/jobs/1",
        title="Senior Python Engineer",
        company="Example Co",
        location="Remote - Canada",
        description_text="Build internal platforms.",
        metadata=metadata,
    )


def test_rule_based_summarizer_uses_rule_explanations() -> None:
    job = _make_job()

    summary = summarize_job_match(
        job,
        rule_explanations=[
            "+15 title matched include keyword 'python'",
            "+12 remote_status matched preferred value 'remote'",
            "-6 employment_type did not match preferred values",
        ],
    )

    assert "Potential match: Senior Python Engineer at Example Co in Remote - Canada." in summary
    assert "Score: 88." in summary
    assert "Positive signals: title matched preferred keyword 'python'; remote_status matched preferred value 'remote'." in summary
    assert "Possible concerns: employment_type did not match preferred values." in summary


def test_rule_based_summarizer_falls_back_without_explanations() -> None:
    job = _make_job(score=None)

    summary = RuleBasedJobSummarizer().summarize(job)

    assert "Potential match: Senior Python Engineer at Example Co in Remote - Canada." in summary
    assert "Score: n/a." in summary
    assert "No rule explanations were provided" in summary


def test_render_job_match_summary_uses_custom_summarizer() -> None:
    job = _make_job()

    class CustomSummarizer:
        def summarize(self, job: JobPosting, *, rule_explanations: list[str] | None = None) -> str:
            return f"Custom summary for {job.title}"

    rendered = render_job_match_summary(job, summarizer=CustomSummarizer())

    assert rendered == "Match Summary: Custom summary for Senior Python Engineer"
