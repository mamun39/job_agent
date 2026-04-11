"""Local board registry loading and deterministic board selection."""

from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from job_agent.core.models import BoardRegistryEntry, SearchConstraint


def load_board_registry_payload(payload: Any) -> list[BoardRegistryEntry]:
    """Validate raw registry payload into board registry entries."""
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise ValueError("Board registry config must be a list of board objects")
    try:
        return [BoardRegistryEntry.model_validate(item) for item in payload]
    except ValidationError as exc:
        raise ValueError(f"Invalid board registry config: {exc}") from exc


def select_board_registry_entries(
    *,
    registry: list[BoardRegistryEntry],
    constraints: SearchConstraint,
    selected_sites: list[str],
) -> list[BoardRegistryEntry]:
    """Select deterministic board entries for executable planning."""
    if not constraints.include_companies:
        raise ValueError("Intent does not name any companies, so no board URLs can be resolved from the local registry.")

    normalized_company_hints = {_normalize_company_key(name) for name in constraints.include_companies}
    allowed_sites = set(selected_sites)
    candidates = [
        entry
        for entry in registry
        if entry.source_site in allowed_sites and _normalize_company_key(entry.company_name) in normalized_company_hints
    ]

    if not candidates:
        requested_companies = ", ".join(constraints.include_companies)
        requested_sites = ", ".join(selected_sites)
        raise ValueError(
            f"No board registry entries matched companies [{requested_companies}] for supported sources [{requested_sites}]."
        )

    filtered = _filter_by_locations(candidates, constraints.location_constraints)
    if filtered:
        candidates = filtered

    filtered = _filter_by_tags(candidates, constraints)
    if filtered:
        candidates = filtered

    return sorted(candidates, key=lambda entry: (entry.company_name.casefold(), entry.source_site, entry.board_url.unicode_string()))


def _filter_by_locations(
    candidates: list[BoardRegistryEntry],
    location_constraints: list[str],
) -> list[BoardRegistryEntry]:
    if not location_constraints:
        return []
    requested_locations = {_normalize_match_key(value) for value in location_constraints}
    return [
        entry
        for entry in candidates
        if any(_normalize_match_key(hint) in requested_locations for hint in entry.location_hints)
    ]


def _filter_by_tags(candidates: list[BoardRegistryEntry], constraints: SearchConstraint) -> list[BoardRegistryEntry]:
    requested_tags = {
        _normalize_match_key(value)
        for value in (
            list(constraints.include_keywords)
            + list(constraints.target_titles)
            + [level.value for level in constraints.seniority_preferences]
        )
    }
    if not requested_tags:
        return []
    return [
        entry
        for entry in candidates
        if any(_normalize_match_key(tag) in requested_tags for tag in entry.tags)
    ]


def _normalize_company_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _normalize_match_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
