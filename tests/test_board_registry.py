from __future__ import annotations

import pytest

from job_agent.core.board_registry import select_board_registry_entries
from job_agent.core.models import BoardRegistryEntry, SearchConstraint, SearchIntent
from job_agent.core.plan_compiler import compile_search_intent


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
            company_name="Stripe",
            source_site="lever",
            board_url="https://jobs.lever.co/stripe",
            tags=["backend"],
            location_hints=["United States"],
        ),
        BoardRegistryEntry(
            company_name="Shopify",
            source_site="lever",
            board_url="https://jobs.lever.co/shopify",
            tags=["ruby", "platform"],
            location_hints=["Canada"],
        ),
    ]


def test_select_board_registry_entries_matches_exact_company_name() -> None:
    selected = select_board_registry_entries(
        registry=_registry(),
        constraints=SearchConstraint(include_companies=["Stripe"]),
        selected_sites=["greenhouse", "lever"],
    )

    assert [entry.source_site for entry in selected] == ["greenhouse", "lever"]
    assert all(entry.company_name == "Stripe" for entry in selected)


def test_select_board_registry_entries_matches_simple_normalized_company_name() -> None:
    selected = select_board_registry_entries(
        registry=_registry(),
        constraints=SearchConstraint(include_companies=["stripe!!"]),
        selected_sites=["greenhouse"],
    )

    assert len(selected) == 1
    assert selected[0].company_name == "Stripe"
    assert selected[0].source_site == "greenhouse"


def test_select_board_registry_entries_can_refine_by_location_hints() -> None:
    selected = select_board_registry_entries(
        registry=_registry(),
        constraints=SearchConstraint(include_companies=["Stripe"], location_constraints=["Canada"]),
        selected_sites=["greenhouse", "lever"],
    )

    assert len(selected) == 1
    assert selected[0].source_site == "greenhouse"


def test_compile_search_intent_with_board_registry_resolves_board_urls() -> None:
    intent = SearchIntent(
        prompt_text="Find backend jobs at Stripe in Canada on Greenhouse.",
        constraints={
            "include_companies": ["Stripe"],
            "include_keywords": ["backend"],
            "location_constraints": ["Canada"],
            "source_site_preferences": ["greenhouse"],
        },
    )

    plan = compile_search_intent(intent, board_registry=_registry())

    assert len(plan.queries) == 1
    assert plan.queries[0].company_name == "Stripe"
    assert str(plan.queries[0].board_url) == "https://boards.greenhouse.io/stripe"
    assert plan.queries[0].source_site == "greenhouse"
    assert "Board seed URLs were selected from the local registry using explicit intent constraints only." in plan.notes


def test_compile_search_intent_with_registry_fails_honestly_when_no_board_matches() -> None:
    intent = SearchIntent(
        prompt_text="Find backend jobs at Unknown Co.",
        constraints={"include_companies": ["Unknown Co"]},
    )

    with pytest.raises(ValueError) as exc_info:
        compile_search_intent(intent, board_registry=_registry())

    assert "No board registry entries matched companies [Unknown Co]" in str(exc_info.value)


def test_compile_search_intent_with_registry_requires_company_hints() -> None:
    intent = SearchIntent(
        prompt_text="Find backend jobs in Canada.",
        constraints={"include_keywords": ["backend"], "location_constraints": ["Canada"]},
    )

    with pytest.raises(ValueError) as exc_info:
        compile_search_intent(intent, board_registry=_registry())

    assert "Intent does not name any companies" in str(exc_info.value)
