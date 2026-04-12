from __future__ import annotations

import pytest

from job_agent.core.models import RemotePreference, SearchIntent, SeniorityLevel
from job_agent.core.plan_compiler import compile_search_intent


def test_compile_search_intent_defaults_to_supported_live_sources() -> None:
    intent = SearchIntent(
        prompt_text="Find backend engineer jobs in Canada.",
        constraints={
            "target_titles": ["Backend Engineer"],
            "location_constraints": ["Canada"],
        },
    )

    plan = compile_search_intent(intent)

    assert [query.source_site for query in plan.queries] == ["greenhouse", "lever"]
    assert [query.label for query in plan.queries] == ["Greenhouse Backend Engineer", "Lever Backend Engineer"]
    assert "Generated queries preserve intent constraints but remain non-executable until board seed URLs are provided." in plan.notes


def test_compile_search_intent_preserves_supported_source_preferences() -> None:
    intent = SearchIntent(
        prompt_text="Find senior platform roles on Lever and LinkedIn.",
        constraints={
            "target_titles": ["Platform Engineer"],
            "source_site_preferences": ["lever", "linkedin"],
            "seniority_preferences": ["senior"],
        },
    )

    plan = compile_search_intent(intent)

    assert [query.source_site for query in plan.queries] == ["lever", "linkedin"]
    assert plan.queries[0].seniority_preferences == [SeniorityLevel.SENIOR]
    assert all("Ignored unsupported source-site preferences" not in note for note in plan.notes)


def test_compile_search_intent_surfaces_unsupported_source_requests_clearly() -> None:
    intent = SearchIntent(
        prompt_text="Find data roles on Indeed only.",
        constraints={
            "source_site_preferences": ["indeed"],
            "target_titles": ["Data Engineer"],
        },
    )

    with pytest.raises(ValueError) as exc_info:
        compile_search_intent(intent)

    assert "Intent requested unsupported source sites: indeed." in str(exc_info.value)
    assert "Supported live sources: greenhouse, lever, linkedin" in str(exc_info.value)


def test_compile_search_intent_carries_include_exclude_location_and_company_hints() -> None:
    intent = SearchIntent(
        prompt_text="Find remote senior python backend roles in Toronto, avoid crypto, prefer Stripe.",
        constraints={
            "target_titles": ["Backend Engineer"],
            "include_keywords": ["python", "backend"],
            "exclude_keywords": ["crypto"],
            "location_constraints": ["Toronto"],
            "remote_preference": "remote_only",
            "seniority_preferences": ["senior"],
            "freshness_window_days": 7,
            "include_companies": ["Stripe"],
            "exclude_companies": ["Meta"],
        },
    )

    plan = compile_search_intent(intent)
    first_query = plan.queries[0]

    assert first_query.include_keywords == ["python", "backend"]
    assert first_query.exclude_keywords == ["crypto"]
    assert first_query.location_constraints == ["Toronto"]
    assert first_query.remote_preference is RemotePreference.REMOTE_ONLY
    assert first_query.seniority_preferences == [SeniorityLevel.SENIOR]
    assert first_query.freshness_window_days == 7
    assert first_query.include_companies == ["Stripe"]
    assert first_query.exclude_companies == ["Meta"]
    assert "No board seed URL was inferred or generated." in first_query.notes
