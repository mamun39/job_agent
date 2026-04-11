from __future__ import annotations

from job_agent.core.intent_parser import parse_search_intent
from job_agent.core.models import RemotePreference, SeniorityLevel


def test_parse_search_intent_extracts_titles_and_seniority() -> None:
    intent = parse_search_intent(
        "Looking for senior backend engineer or platform engineer roles."
    )

    assert intent.prompt_text == "Looking for senior backend engineer or platform engineer roles."
    assert intent.constraints.target_titles == ["Senior Backend Engineer", "Platform Engineer"]
    assert intent.constraints.seniority_preferences == [SeniorityLevel.SENIOR]


def test_parse_search_intent_extracts_include_and_exclude_keywords() -> None:
    intent = parse_search_intent(
        "Find backend roles with python, APIs and distributed systems, avoid crypto and adtech."
    )

    assert intent.constraints.include_keywords == ["python", "APIs", "distributed systems"]
    assert intent.constraints.exclude_keywords == ["crypto", "adtech"]


def test_parse_search_intent_extracts_location_remote_and_site_preferences() -> None:
    intent = parse_search_intent(
        "Find software engineer jobs in Toronto or Canada, preferably remote, on Greenhouse and Lever."
    )

    assert intent.constraints.location_constraints == ["Toronto", "Canada"]
    assert intent.constraints.remote_preference is RemotePreference.REMOTE_PREFERRED
    assert intent.constraints.source_site_preferences == ["greenhouse", "lever"]


def test_parse_search_intent_extracts_company_hints_and_freshness() -> None:
    intent = parse_search_intent(
        "Looking for product engineer jobs at Stripe or Shopify, exclude companies like Meta and Amazon, past month."
    )

    assert intent.constraints.include_companies == ["Stripe", "Shopify"]
    assert intent.constraints.exclude_companies == ["Meta", "Amazon"]
    assert intent.constraints.freshness_window_days == 30


def test_parse_search_intent_extracts_simple_numeric_freshness_window() -> None:
    intent = parse_search_intent("Backend developer roles in Canada from the last 7 days.")

    assert intent.constraints.freshness_window_days == 7


def test_parse_search_intent_handles_ambiguous_prompt_conservatively() -> None:
    intent = parse_search_intent("I want something interesting in tech.")

    assert intent.constraints.target_titles == []
    assert intent.constraints.include_keywords == []
    assert intent.constraints.exclude_keywords == []
    assert intent.constraints.location_constraints == []
    assert intent.constraints.remote_preference is RemotePreference.UNSPECIFIED
    assert intent.constraints.seniority_preferences == []
    assert intent.constraints.include_companies == []
    assert intent.constraints.exclude_companies == []
    assert intent.constraints.freshness_window_days is None
