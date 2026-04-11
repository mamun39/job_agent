from __future__ import annotations

from job_agent.core.intent_parser import parse_search_intent
from job_agent.core.models import RemotePreference, SeniorityLevel


def test_parse_search_intent_extracts_titles_must_haves_and_preferences() -> None:
    intent = parse_search_intent(
        "Looking for senior backend roles, must have python, ideally platform roles or SRE roles."
    )

    assert intent.prompt_text == "Looking for senior backend roles, must have python, ideally platform roles or SRE roles."
    assert intent.constraints.target_titles == ["Backend Engineer"]
    assert intent.constraints.preferred_titles == ["Platform Engineer", "Site Reliability Engineer"]
    assert intent.constraints.include_keywords == ["python", "backend"]
    assert intent.constraints.seniority_preferences == [SeniorityLevel.SENIOR]
    assert "must-have titles: Backend Engineer" in intent.parser_notes
    assert "preferred titles: Platform Engineer, Site Reliability Engineer" in intent.parser_notes


def test_parse_search_intent_extracts_include_exclude_and_company_lists() -> None:
    intent = parse_search_intent(
        "Find backend roles with python, APIs and distributed systems, avoid recruiter roles, exclude companies like Meta and Amazon."
    )

    assert intent.constraints.target_titles == ["Backend Engineer"]
    assert intent.constraints.include_keywords == ["python", "APIs", "distributed systems", "backend"]
    assert intent.constraints.exclude_keywords == ["recruiter roles"]
    assert intent.constraints.excluded_role_categories == ["recruiter roles"]
    assert intent.constraints.exclude_companies == ["Meta", "Amazon"]


def test_parse_search_intent_extracts_location_remote_and_site_preferences() -> None:
    intent = parse_search_intent(
        "Find software engineer jobs in Toronto or Canada, hybrid only, on Greenhouse and Lever."
    )

    assert intent.constraints.location_constraints == ["Toronto", "Canada"]
    assert intent.constraints.remote_preference is RemotePreference.HYBRID_ONLY
    assert intent.constraints.source_site_preferences == ["greenhouse", "lever"]


def test_parse_search_intent_extracts_company_hints_and_common_freshness() -> None:
    intent = parse_search_intent(
        "Looking for product engineer jobs at Stripe or Shopify, exclude companies like Meta and Amazon, past fortnight."
    )

    assert intent.constraints.include_companies == ["Stripe", "Shopify"]
    assert intent.constraints.exclude_companies == ["Meta", "Amazon"]
    assert intent.constraints.freshness_window_days == 14


def test_parse_search_intent_extracts_preferred_locations_and_remote_preference() -> None:
    intent = parse_search_intent(
        "Find backend jobs at Stripe in Canada, prefer Toronto or Vancouver, remote preferred."
    )

    assert intent.constraints.include_companies == ["Stripe"]
    assert intent.constraints.location_constraints == ["Canada"]
    assert intent.constraints.preferred_locations == ["Toronto", "Vancouver"]
    assert intent.constraints.remote_preference is RemotePreference.REMOTE_PREFERRED


def test_parse_search_intent_handles_partial_extraction_conservatively() -> None:
    intent = parse_search_intent(
        "Find backend roles at Stripe in Canada, maybe adjacent to trust tooling."
    )

    assert intent.constraints.target_titles == ["Backend Engineer"]
    assert intent.constraints.include_companies == ["Stripe"]
    assert intent.constraints.location_constraints == ["Canada"]
    assert intent.unresolved_fragments == ["maybe adjacent to trust tooling"]
    assert intent.summary == "titles=Backend Engineer | must=backend | locations=Canada | companies=Stripe | unresolved=1"


def test_parse_search_intent_handles_ambiguous_prompt_conservatively() -> None:
    intent = parse_search_intent("I want something interesting in tech.")

    assert intent.constraints.target_titles == []
    assert intent.constraints.preferred_titles == []
    assert intent.constraints.include_keywords == []
    assert intent.constraints.preferred_keywords == []
    assert intent.constraints.exclude_keywords == []
    assert intent.constraints.location_constraints == []
    assert intent.constraints.remote_preference is RemotePreference.UNSPECIFIED
    assert intent.constraints.seniority_preferences == []
    assert intent.constraints.include_companies == []
    assert intent.constraints.exclude_companies == []
    assert intent.constraints.freshness_window_days is None
    assert intent.parser_notes == []
