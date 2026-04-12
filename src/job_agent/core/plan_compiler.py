"""Deterministic compilation from search intent to supported-source search plans."""

from __future__ import annotations

from collections.abc import Sequence

from job_agent.core.board_registry import select_board_registry_entries
from job_agent.core.models import BoardRegistryEntry, SUPPORTED_DISCOVERY_SITES, SearchIntent, SearchPlan, SearchPlanQuery


DEFAULT_PLANNING_SITES: tuple[str, ...] = ("greenhouse", "lever")


def compile_search_intent(intent: SearchIntent, *, board_registry: list[BoardRegistryEntry] | None = None) -> SearchPlan:
    """Compile a parsed search intent into a conservative supported-source search plan."""
    constraints = intent.constraints
    requested_sites = list(constraints.source_site_preferences)
    supported_requested = [site for site in requested_sites if site in SUPPORTED_DISCOVERY_SITES]
    unsupported_requested = [site for site in requested_sites if site not in SUPPORTED_DISCOVERY_SITES]

    if requested_sites and not supported_requested:
        supported = ", ".join(sorted(SUPPORTED_DISCOVERY_SITES))
        requested = ", ".join(requested_sites)
        raise ValueError(
            f"Intent requested unsupported source sites: {requested}. Supported live sources: {supported}"
        )

    selected_sites = supported_requested or list(DEFAULT_PLANNING_SITES)
    plan_notes = ["Compiled from parsed search intent using currently supported live discovery sources only."]
    if unsupported_requested:
        ignored = ", ".join(unsupported_requested)
        plan_notes.append(f"Ignored unsupported source-site preferences: {ignored}.")

    if board_registry:
        selected_boards = select_board_registry_entries(
            registry=board_registry,
            constraints=constraints,
            selected_sites=selected_sites,
        )
        plan_notes.append("Board seed URLs were selected from the local registry using explicit intent constraints only.")
        queries = [
            SearchPlanQuery(
                source_site=entry.source_site,
                label=_build_query_label(site=entry.source_site, intent=intent, company_name=entry.company_name),
                company_name=entry.company_name,
                board_url=entry.board_url,
                target_titles=list(constraints.target_titles),
                preferred_titles=list(constraints.preferred_titles),
                include_keywords=list(constraints.include_keywords),
                preferred_keywords=list(constraints.preferred_keywords),
                exclude_keywords=list(constraints.exclude_keywords),
                location_constraints=list(constraints.location_constraints),
                preferred_locations=list(constraints.preferred_locations),
                remote_preference=constraints.remote_preference,
                seniority_preferences=list(constraints.seniority_preferences),
                freshness_window_days=constraints.freshness_window_days,
                include_companies=list(constraints.include_companies),
                exclude_companies=list(constraints.exclude_companies),
                notes=_build_query_notes(
                    site=entry.source_site,
                    requested_sites=requested_sites,
                    company_name=entry.company_name,
                    board_url=entry.board_url.unicode_string(),
                ),
            )
            for entry in selected_boards
        ]
    else:
        plan_notes.append("Generated queries preserve intent constraints but remain non-executable until board seed URLs are provided.")
        if constraints.include_companies or constraints.exclude_companies:
            plan_notes.append("Company hints were preserved, but no board URLs were inferred from company names.")
        queries = [
            SearchPlanQuery(
                source_site=site,
                label=_build_query_label(site=site, intent=intent),
                target_titles=list(constraints.target_titles),
                preferred_titles=list(constraints.preferred_titles),
                include_keywords=list(constraints.include_keywords),
                preferred_keywords=list(constraints.preferred_keywords),
                exclude_keywords=list(constraints.exclude_keywords),
                location_constraints=list(constraints.location_constraints),
                preferred_locations=list(constraints.preferred_locations),
                remote_preference=constraints.remote_preference,
                seniority_preferences=list(constraints.seniority_preferences),
                freshness_window_days=constraints.freshness_window_days,
                include_companies=list(constraints.include_companies),
                exclude_companies=list(constraints.exclude_companies),
                notes=_build_query_notes(site=site, requested_sites=requested_sites),
            )
            for site in selected_sites
        ]
    return SearchPlan(
        intent=intent,
        constraints=constraints.model_copy(deep=True),
        queries=queries,
        notes=plan_notes,
    )


def _build_query_label(*, site: str, intent: SearchIntent, company_name: str | None = None) -> str:
    descriptor = _build_descriptor(intent)
    site_label = site.capitalize()
    if company_name and descriptor:
        return f"{site_label} {company_name} {descriptor}"
    if company_name:
        return f"{site_label} {company_name}"
    if descriptor:
        return f"{site_label} {descriptor}"
    return f"{site_label} General Search"


def _build_descriptor(intent: SearchIntent) -> str:
    constraints = intent.constraints
    if constraints.target_titles:
        return constraints.target_titles[0]
    if constraints.include_keywords:
        return f"{constraints.include_keywords[0]} Roles"
    return ""


def _build_query_notes(
    *,
    site: str,
    requested_sites: Sequence[str],
    company_name: str | None = None,
    board_url: str | None = None,
) -> list[str]:
    notes = [f"Planned for supported source site: {site}."]
    if not requested_sites:
        notes.append("Source selected by default because the intent did not request specific supported sites.")
    else:
        notes.append("Source selected from explicit intent source-site preferences.")
    if company_name is not None and board_url is not None:
        notes.append(f"Resolved board seed for {company_name}: {board_url}")
    else:
        notes.append("No board seed URL was inferred or generated.")
    return notes
