from __future__ import annotations

from job_agent.core.dedupe import (
    build_comparison_inputs,
    canonicalize_url,
    compute_dedupe_key,
    same_canonical_url,
    same_fallback_identity,
    same_source_identity,
)
from job_agent.core.models import JobPosting


def _make_job(
    *,
    source_site: str = "linkedin",
    source_job_id: str | None = "job-123",
    url: str = "https://example.com/jobs/123",
    title: str = "Senior Python Engineer",
    company: str = "Example Co",
    location: str = "Toronto, ON",
) -> JobPosting:
    return JobPosting(
        source_site=source_site,
        source_job_id=source_job_id,
        url=url,
        title=title,
        company=company,
        location=location,
        description_text="Build automation systems.",
    )


def test_canonical_url_removes_trailing_slash_and_fragment() -> None:
    canonical = canonicalize_url("https://Example.com/jobs/123/#section")

    assert canonical == "https://example.com/jobs/123"


def test_canonical_url_sorts_query_and_drops_tracking_params() -> None:
    canonical = canonicalize_url(
        "https://example.com/jobs/123?utm_source=newsletter&b=2&a=1&gclid=test"
    )

    assert canonical == "https://example.com/jobs/123?a=1&b=2"


def test_greenhouse_canonical_url_drops_tracking_noise_and_normalizes_host() -> None:
    canonical = canonicalize_url(
        "https://www.greenhouse.io/job_app?gh_jid=7451366&utm_source=feed&source=linkedin",
        source_site="greenhouse",
    )

    assert canonical == "https://greenhouse.io/job_app?gh_jid=7451366"


def test_greenhouse_canonical_url_normalizes_embed_board_path_without_overmerging() -> None:
    canonical = canonicalize_url(
        "https://boards.greenhouse.io/embed/job_board?for=stripe&utm_campaign=test",
        source_site="greenhouse",
    )

    assert canonical == "https://boards.greenhouse.io/job_board?for=stripe"


def test_lever_canonical_url_normalizes_www_host_and_tracking_query() -> None:
    canonical = canonicalize_url(
        "https://www.jobs.lever.co/shopify/abc123?lever-via=Careers&ref=feed&utm_medium=email",
        source_site="lever",
    )

    assert canonical == "https://jobs.lever.co/shopify/abc123?lever-via=Careers"


def test_lever_canonical_url_keeps_distinct_paths_distinct() -> None:
    listing = canonicalize_url("https://jobs.lever.co/example/abc123", source_site="lever")
    view = canonicalize_url("https://jobs.lever.co/view/abc123", source_site="lever")

    assert listing != view


def test_fixture_site_canonical_url_can_safely_normalize_www_host() -> None:
    canonical = canonicalize_url(
        "https://www.linkedin.com/jobs/view/12345/?utm_source=feed",
        source_site="linkedin",
    )

    assert canonical == "https://linkedin.com/jobs/view/12345"


def test_dedupe_key_prefers_source_identity_when_present() -> None:
    job = _make_job(source_site="LinkedIn", source_job_id="ABC-123")

    assert compute_dedupe_key(job) == "source:linkedin:abc-123"
    assert job.dedupe_key == "source:linkedin:abc-123"


def test_dedupe_key_falls_back_to_canonical_url_when_id_missing() -> None:
    job = _make_job(
        source_job_id=None,
        url="https://example.com/jobs/123/?b=2&a=1&utm_campaign=test",
    )

    assert compute_dedupe_key(job) == "url:https://example.com/jobs/123?a=1&b=2"
    assert job.canonical_url == "https://example.com/jobs/123?a=1&b=2"


def test_same_source_identity_handles_duplicate_ids_with_different_urls() -> None:
    left = _make_job(url="https://example.com/jobs/123", source_job_id="ABC-123")
    right = _make_job(url="https://example.com/jobs/123?ref=feed", source_job_id="abc-123")

    assert same_source_identity(left, right) is True
    assert same_canonical_url(left, right) is True


def test_same_canonical_url_uses_source_specific_rules_for_greenhouse() -> None:
    left = _make_job(
        source_site="greenhouse",
        source_job_id=None,
        url="https://www.greenhouse.io/job_app?gh_jid=7451366&utm_source=feed",
    )
    right = _make_job(
        source_site="greenhouse",
        source_job_id=None,
        url="https://greenhouse.io/job_app?gh_jid=7451366",
    )

    assert same_canonical_url(left, right) is True


def test_greenhouse_canonicalization_does_not_merge_different_job_ids() -> None:
    left = canonicalize_url(
        "https://greenhouse.io/job_app?gh_jid=7451366&utm_source=feed",
        source_site="greenhouse",
    )
    right = canonicalize_url(
        "https://greenhouse.io/job_app?gh_jid=9999999&utm_source=feed",
        source_site="greenhouse",
    )

    assert left != right


def test_comparison_inputs_are_normalized_but_exact() -> None:
    left = _make_job(
        source_job_id=None,
        title=" Senior   Python Engineer ",
        company=" Example Co ",
        location=" Toronto, ON ",
    )
    right = _make_job(
        source_job_id=None,
        url="https://example.com/jobs/999",
        title="senior python engineer",
        company="example co",
        location="toronto, on",
    )

    assert build_comparison_inputs(left) == ("senior python engineer", "example co", "toronto, on")
    assert left.comparison_inputs == right.comparison_inputs
    assert same_fallback_identity(left, right) is True


def test_fallback_identity_does_not_overmerge_distinct_locations() -> None:
    left = _make_job(source_job_id=None, location="Toronto, ON")
    right = _make_job(
        source_job_id=None,
        url="https://example.com/jobs/456",
        location="Vancouver, BC",
    )

    assert same_source_identity(left, right) is False
    assert same_fallback_identity(left, right) is False
