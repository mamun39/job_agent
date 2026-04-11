"""Local board registry loading and deterministic board selection."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from pydantic import ValidationError

from job_agent.core.models import BoardRegistryEntry, SearchConstraint


def load_board_registry_payload(payload: Any) -> list[BoardRegistryEntry]:
    """Validate raw registry payload into board registry entries."""
    entries, issues = validate_board_registry_payload(payload)
    if issues:
        raise ValueError(f"Invalid board registry config: {'; '.join(issues)}")
    return entries


def validate_board_registry_payload(payload: Any) -> tuple[list[BoardRegistryEntry], list[str]]:
    """Validate raw registry payload and return both entries and human-readable issues."""
    if payload is None:
        return [], []
    if not isinstance(payload, list):
        return [], ["Board registry config must be a list of board objects"]

    entries: list[BoardRegistryEntry] = []
    issues: list[str] = []
    for index, item in enumerate(payload):
        try:
            entries.append(BoardRegistryEntry.model_validate(item))
        except ValidationError as exc:
            issues.append(f"entry[{index}] invalid: {_summarize_validation_error(exc)}")
    issues.extend(_detect_duplicate_issues(entries))
    return entries, issues


def load_board_registry_json_file(path: Path) -> list[BoardRegistryEntry]:
    """Load a JSON registry file into validated entries."""
    entries, issues = validate_board_registry_json_file(path)
    if issues:
        raise ValueError(f"Invalid board registry file: {'; '.join(issues)}")
    return entries


def validate_board_registry_json_file(path: Path) -> tuple[list[BoardRegistryEntry], list[str]]:
    """Read and validate a JSON registry file into entries and issues."""
    if not path.is_file():
        return [], [f"Board registry file does not exist: {path}"]
    if path.suffix.lower() != ".json":
        return [], [f"Board registry maintenance requires a .json file: {path}"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [], [f"Invalid board registry JSON file: {exc.msg}"]
    return validate_board_registry_payload(payload)


def save_board_registry_json_file(path: Path, entries: list[BoardRegistryEntry]) -> Path:
    """Persist registry entries as sorted JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = [_entry_to_json(entry) for entry in _sort_entries(entries)]
    path.write_text(json.dumps(serialized, indent=2) + "\n", encoding="utf-8")
    return path


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

    filtered = _filter_by_locations(
        candidates,
        list(constraints.location_constraints) + list(constraints.preferred_locations),
    )
    if filtered:
        candidates = filtered

    filtered = _filter_by_tags(candidates, constraints)
    if filtered:
        candidates = filtered

    return sorted(candidates, key=lambda entry: (entry.company_name.casefold(), entry.source_site, entry.board_url.unicode_string()))


def sort_board_registry_entries(entries: list[BoardRegistryEntry]) -> list[BoardRegistryEntry]:
    """Return registry entries in stable deterministic order."""
    return _sort_entries(entries)


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
            + list(constraints.preferred_keywords)
            + list(constraints.target_titles)
            + list(constraints.preferred_titles)
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


def _summarize_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error.get("loc", ()))
        message = error.get("msg", "invalid value")
        if location:
            parts.append(f"{location}: {message}")
        else:
            parts.append(message)
    return "; ".join(parts)


def _detect_duplicate_issues(entries: list[BoardRegistryEntry]) -> list[str]:
    issues: list[str] = []
    seen_company_site: dict[tuple[str, str], BoardRegistryEntry] = {}
    seen_url_site: dict[tuple[str, str], BoardRegistryEntry] = {}
    for entry in entries:
        company_site_key = (_normalize_company_key(entry.company_name), entry.source_site)
        duplicate_company_site = seen_company_site.get(company_site_key)
        if duplicate_company_site is not None:
            issues.append(
                "duplicate company/source entry: "
                f"{entry.company_name} on {entry.source_site} "
                f"already maps to {duplicate_company_site.board_url}"
            )
        else:
            seen_company_site[company_site_key] = entry

        url_site_key = (entry.source_site, entry.board_url.unicode_string())
        duplicate_url_site = seen_url_site.get(url_site_key)
        if duplicate_url_site is not None:
            issues.append(
                "duplicate board_url/source entry: "
                f"{entry.board_url} on {entry.source_site} already exists for {duplicate_url_site.company_name}"
            )
        else:
            seen_url_site[url_site_key] = entry
    return issues


def _sort_entries(entries: list[BoardRegistryEntry]) -> list[BoardRegistryEntry]:
    return sorted(
        entries,
        key=lambda entry: (
            entry.company_name.casefold(),
            entry.source_site,
            entry.board_url.unicode_string(),
        ),
    )


def _entry_to_json(entry: BoardRegistryEntry) -> dict[str, Any]:
    return {
        "company_name": entry.company_name,
        "source_site": entry.source_site,
        "board_url": entry.board_url.unicode_string(),
        "tags": list(entry.tags),
        "location_hints": list(entry.location_hints),
    }
