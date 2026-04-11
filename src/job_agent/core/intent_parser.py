"""Deterministic rule-based parsing for natural-language job search prompts."""

from __future__ import annotations

from collections.abc import Iterable
import re

from job_agent.core.models import RemotePreference, SearchConstraint, SearchIntent, SeniorityLevel


_TITLE_PATTERN = re.compile(
    r"\b("
    r"(?:senior|sr\.?|junior|jr\.?|staff|lead|principal|mid(?:-level)?|backend|front(?:-| )end|full(?:-| )stack|"
    r"software|platform|data|product|devops|site reliability|sre|machine learning|ml|security|cloud|infrastructure|"
    r"mobile|android|ios|qa|applied|research|analytics|python|ai)"
    r"(?:\s+"
    r"(?:senior|sr\.?|junior|jr\.?|staff|lead|principal|mid(?:-level)?|backend|front(?:-| )end|full(?:-| )stack|"
    r"software|platform|data|product|devops|site reliability|sre|machine learning|ml|security|cloud|infrastructure|"
    r"mobile|android|ios|qa|applied|research|analytics|python|ai)){0,3}\s+"
    r"(?:engineer|developer|scientist|analyst|designer|manager|architect|administrator|specialist|recruiter)"
    r"|"
    r"(?:engineer|developer|scientist|analyst|designer|manager|architect|administrator|specialist|recruiter)"
    r")\b",
    re.IGNORECASE,
)

_SENIORITY_PATTERNS: tuple[tuple[re.Pattern[str], SeniorityLevel], ...] = (
    (re.compile(r"\bintern(ship)?\b", re.IGNORECASE), SeniorityLevel.INTERN),
    (re.compile(r"\b(junior|jr\.?|entry(?:-level)?)\b", re.IGNORECASE), SeniorityLevel.ENTRY),
    (re.compile(r"\bmid(?:-level)?\b", re.IGNORECASE), SeniorityLevel.MID),
    (re.compile(r"\bsenior\b|\bsr\.?\b", re.IGNORECASE), SeniorityLevel.SENIOR),
    (re.compile(r"\bstaff\b", re.IGNORECASE), SeniorityLevel.STAFF),
    (re.compile(r"\bprincipal\b", re.IGNORECASE), SeniorityLevel.PRINCIPAL),
    (re.compile(r"\blead\b", re.IGNORECASE), SeniorityLevel.LEAD),
    (re.compile(r"\bmanager\b", re.IGNORECASE), SeniorityLevel.MANAGER),
    (re.compile(r"\bdirector\b", re.IGNORECASE), SeniorityLevel.DIRECTOR),
    (re.compile(r"\bexecutive\b|\bvp\b|\bchief\b", re.IGNORECASE), SeniorityLevel.EXECUTIVE),
)

_REMOTE_ONLY_PATTERNS = (
    re.compile(r"\bremote[- ]only\b", re.IGNORECASE),
    re.compile(r"\bfully remote\b", re.IGNORECASE),
    re.compile(r"\bremote roles? only\b", re.IGNORECASE),
)
_REMOTE_PREFERRED_PATTERNS = (
    re.compile(r"\bprefer(?:ably)? remote\b", re.IGNORECASE),
    re.compile(r"\bremote preferred\b", re.IGNORECASE),
)
_HYBRID_PREFERRED_PATTERNS = (
    re.compile(r"\bprefer(?:ably)? hybrid\b", re.IGNORECASE),
    re.compile(r"\bhybrid preferred\b", re.IGNORECASE),
    re.compile(r"\bhybrid roles?\b", re.IGNORECASE),
)
_ONSITE_OK_PATTERNS = (
    re.compile(r"\bonsite (?:is )?(?:ok|okay|fine)\b", re.IGNORECASE),
    re.compile(r"\bon-site (?:is )?(?:ok|okay|fine)\b", re.IGNORECASE),
)

_FRESHNESS_PATTERNS: tuple[tuple[re.Pattern[str], int | None], ...] = (
    (re.compile(r"\b(?:last|past)\s+(\d+)\s+days?\b", re.IGNORECASE), None),
    (re.compile(r"\b(?:last|past)\s+(\d+)\s+weeks?\b", re.IGNORECASE), 7),
    (re.compile(r"\b(?:last|past)\s+(\d+)\s+months?\b", re.IGNORECASE), 30),
    (re.compile(r"\b(?:last|past)\s+week\b", re.IGNORECASE), 7),
    (re.compile(r"\b(?:last|past)\s+month\b", re.IGNORECASE), 30),
)

_SITE_PATTERNS = (
    ("greenhouse", re.compile(r"\bgreenhouse\b", re.IGNORECASE)),
    ("lever", re.compile(r"\blever\b", re.IGNORECASE)),
)

_CLAUSE_STOP_PATTERN = re.compile(
    r"\b(?:in|from|at|on|within|over|during|posted|last|past|avoid|exclude|excluding|without|greenhouse|lever)\b",
    re.IGNORECASE,
)

_KEYWORD_MARKERS = (
    "with",
    "using",
    "experience with",
    "skills in",
    "skill in",
    "focused on",
    "focus on",
)
_EXCLUDE_MARKERS = (
    "avoid",
    "excluding",
    "exclude",
    "without",
)


def parse_search_intent(prompt_text: str) -> SearchIntent:
    """Convert a natural-language prompt into a conservative structured search intent."""
    constraints = SearchConstraint(
        target_titles=_extract_target_titles(prompt_text),
        include_keywords=_extract_include_keywords(prompt_text),
        exclude_keywords=_extract_exclude_keywords(prompt_text),
        location_constraints=_extract_locations(prompt_text),
        remote_preference=_extract_remote_preference(prompt_text),
        seniority_preferences=_extract_seniority_preferences(prompt_text),
        source_site_preferences=_extract_source_site_preferences(prompt_text),
        freshness_window_days=_extract_freshness_window_days(prompt_text),
        include_companies=_extract_company_hints(prompt_text, include=True),
        exclude_companies=_extract_company_hints(prompt_text, include=False),
    )
    return SearchIntent(prompt_text=prompt_text, constraints=constraints)


def _extract_target_titles(prompt_text: str) -> list[str]:
    return _dedupe_strings(_normalize_title(match.group(1)) for match in _TITLE_PATTERN.finditer(prompt_text))


def _extract_include_keywords(prompt_text: str) -> list[str]:
    keywords: list[str] = []
    for marker in _KEYWORD_MARKERS:
        keywords.extend(_extract_clause_items(prompt_text, marker))
    return _dedupe_strings(keyword for keyword in keywords if _is_keyword_like(keyword))


def _extract_exclude_keywords(prompt_text: str) -> list[str]:
    keywords: list[str] = []
    company_items = _extract_company_hints(prompt_text, include=False)
    for marker in _EXCLUDE_MARKERS:
        keywords.extend(
            item
            for item in _extract_clause_items(prompt_text, marker)
            if item not in company_items and "company" not in item.casefold() and _is_keyword_like(item)
        )
    return _dedupe_strings(keyword for keyword in keywords if _is_keyword_like(keyword))


def _extract_locations(prompt_text: str) -> list[str]:
    clauses: list[str] = []
    patterns = (
        re.compile(r"\b(?:roles?|jobs?|positions?|openings?)\s+in\s+([^.;]+)", re.IGNORECASE),
        re.compile(r"\b(?:based in|located in|remote in)\s+([^.;]+)", re.IGNORECASE),
        re.compile(r"\b(?:anywhere in)\s+([^.;]+)", re.IGNORECASE),
    )
    for pattern in patterns:
        for match in pattern.finditer(prompt_text):
            clauses.extend(_split_clause_items(_truncate_clause(match.group(1))))
    filtered = [
        clause
        for clause in clauses
        if clause
        and not _looks_like_keyword_fragment(clause)
        and "company" not in clause.casefold()
        and clause.casefold() not in {"remote", "preferably remote", "hybrid", "onsite", "on-site", "tech"}
    ]
    return _dedupe_strings(filtered)


def _extract_remote_preference(prompt_text: str) -> RemotePreference:
    for pattern in _REMOTE_ONLY_PATTERNS:
        if pattern.search(prompt_text):
            return RemotePreference.REMOTE_ONLY
    for pattern in _REMOTE_PREFERRED_PATTERNS:
        if pattern.search(prompt_text):
            return RemotePreference.REMOTE_PREFERRED
    for pattern in _HYBRID_PREFERRED_PATTERNS:
        if pattern.search(prompt_text):
            return RemotePreference.HYBRID_PREFERRED
    for pattern in _ONSITE_OK_PATTERNS:
        if pattern.search(prompt_text):
            return RemotePreference.ONSITE_OK
    return RemotePreference.UNSPECIFIED


def _extract_seniority_preferences(prompt_text: str) -> list[SeniorityLevel]:
    return [
        level
        for pattern, level in _SENIORITY_PATTERNS
        if pattern.search(prompt_text)
    ]


def _extract_source_site_preferences(prompt_text: str) -> list[str]:
    return [site_name for site_name, pattern in _SITE_PATTERNS if pattern.search(prompt_text)]


def _extract_freshness_window_days(prompt_text: str) -> int | None:
    for pattern, multiplier in _FRESHNESS_PATTERNS:
        match = pattern.search(prompt_text)
        if not match:
            continue
        if multiplier is None:
            return int(match.group(1))
        if match.groups():
            return int(match.group(1)) * multiplier
        return multiplier
    return None


def _extract_company_hints(prompt_text: str, *, include: bool) -> list[str]:
    clauses: list[str] = []
    if include:
        patterns = (
            re.compile(r"\b(?:at|from)\s+([^.;]+)", re.IGNORECASE),
            re.compile(r"\b(?:include|prefer|target)\s+companies?\s+(?:like\s+)?([^.;]+)", re.IGNORECASE),
        )
    else:
        patterns = (
            re.compile(r"\b(?:avoid|exclude|excluding)\s+companies?\s+(?:like\s+)?([^.;]+)", re.IGNORECASE),
            re.compile(r"\b(?:avoid|exclude|excluding)\s+([^.;]+?)\s+companies?\b", re.IGNORECASE),
        )
    for pattern in patterns:
        for match in pattern.finditer(prompt_text):
            clauses.extend(_split_clause_items(_truncate_clause(match.group(1))))
    return _dedupe_strings(item for item in clauses if _looks_like_company_hint(item))


def _extract_clause_items(prompt_text: str, marker: str) -> list[str]:
    pattern = re.compile(rf"\b{re.escape(marker)}\s+([^.;]+)", re.IGNORECASE)
    items: list[str] = []
    for match in pattern.finditer(prompt_text):
        truncated = _truncate_clause(match.group(1))
        items.extend(_split_clause_items(truncated))
    return items


def _truncate_clause(value: str) -> str:
    match = _CLAUSE_STOP_PATTERN.search(value)
    if match is None:
        return value.strip()
    return value[: match.start()].strip()


def _split_clause_items(value: str) -> list[str]:
    if not value:
        return []
    parts = re.split(r",|/|\bor\b|\band\b", value, flags=re.IGNORECASE)
    return [_clean_phrase(part) for part in parts if _clean_phrase(part)]


def _clean_phrase(value: str) -> str:
    cleaned = value.strip(" ,.;:()[]{}\"'")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _normalize_title(value: str) -> str:
    normalized = value.replace("Sr.", "Senior").replace("sr.", "Senior").replace("Jr.", "Junior").replace("jr.", "Junior")
    words = [word.capitalize() if word.lower() not in {"qa", "ml", "ai", "ios"} else word.upper() for word in normalized.split()]
    result = " ".join(words)
    return result.replace("Devops", "DevOps")


def _is_keyword_like(value: str) -> bool:
    normalized = value.casefold()
    if normalized in {"remote", "hybrid", "onsite", "on-site"}:
        return False
    if "company" in normalized:
        return False
    return bool(normalized)


def _looks_like_keyword_fragment(value: str) -> bool:
    normalized = value.casefold()
    return normalized.startswith(("python", "backend", "frontend", "api", "data", "platform"))


def _looks_like_company_hint(value: str) -> bool:
    normalized = value.casefold()
    if normalized in {"startups", "startup", "companies", "company", "the", "last", "past"}:
        return False
    return len(normalized) >= 2


def _dedupe_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = value.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(value)
    return ordered
