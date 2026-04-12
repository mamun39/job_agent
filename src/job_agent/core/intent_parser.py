"""Deterministic rule-based parsing for natural-language job search prompts."""

from __future__ import annotations

from collections.abc import Iterable
import re

from job_agent.core.models import RemotePreference, SearchConstraint, SearchIntent, SeniorityLevel


_ROLE_FAMILY_TITLE_MAP = {
    "ai": "AI Engineer",
    "ai security": "AI Security Engineer",
    "analytics": "Analytics Engineer",
    "android": "Android Engineer",
    "applied ai": "Applied AI Engineer",
    "backend": "Backend Engineer",
    "cloud": "Cloud Engineer",
    "data": "Data Engineer",
    "data platform": "Data Platform Engineer",
    "devops": "DevOps Engineer",
    "frontend": "Frontend Engineer",
    "front end": "Frontend Engineer",
    "full stack": "Full Stack Engineer",
    "full-stack": "Full Stack Engineer",
    "infrastructure": "Infrastructure Engineer",
    "ios": "iOS Engineer",
    "machine learning": "Machine Learning Engineer",
    "ml": "Machine Learning Engineer",
    "platform": "Platform Engineer",
    "product": "Product Engineer",
    "python": "Python Engineer",
    "qa": "QA Engineer",
    "research": "Research Engineer",
    "security": "Security Engineer",
    "site reliability": "Site Reliability Engineer",
    "sre": "Site Reliability Engineer",
}

_ROLE_FAMILY_TERMS = tuple(sorted(_ROLE_FAMILY_TITLE_MAP, key=len, reverse=True))
_GENERIC_ROLE_NOUNS = ("roles", "role", "jobs", "job", "positions", "position", "openings", "opening")
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

_ROLE_PHRASE_PATTERN = re.compile(
    r"\b((?:senior|sr\.?|junior|jr\.?|staff|lead|principal|mid(?:-level)?|"
    r"backend|front(?:-| )end|full(?:-| )stack|platform|data|product|devops|site reliability|sre|"
    r"machine learning|ml|security|cloud|infrastructure|android|ios|qa|analytics|python|ai"
    r")(?:[\s/-]+(?:backend|front(?:-| )end|full(?:-| )stack|platform|data|product|devops|site reliability|sre|"
    r"machine learning|ml|security|cloud|infrastructure|android|ios|qa|analytics|python|ai|trust|safety)){0,3})\s+"
    r"(roles?|jobs?|positions?|openings?)\b",
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
    re.compile(r"\bonly remote\b", re.IGNORECASE),
    re.compile(r"\bmust be remote\b", re.IGNORECASE),
)
_REMOTE_PREFERRED_PATTERNS = (
    re.compile(r"\bprefer(?:ably)? remote\b", re.IGNORECASE),
    re.compile(r"\bremote preferred\b", re.IGNORECASE),
    re.compile(r"\bideally remote\b", re.IGNORECASE),
    re.compile(r"\bremote\s+(?:[a-z]+(?:\s+[a-z]+){0,2}\s+)?(?:roles?|jobs?|positions?|openings?)\b", re.IGNORECASE),
)
_HYBRID_ONLY_PATTERNS = (
    re.compile(r"\bhybrid[- ]only\b", re.IGNORECASE),
    re.compile(r"\bonly hybrid\b", re.IGNORECASE),
    re.compile(r"\bmust be hybrid\b", re.IGNORECASE),
)
_HYBRID_PREFERRED_PATTERNS = (
    re.compile(r"\bprefer(?:ably)? hybrid\b", re.IGNORECASE),
    re.compile(r"\bhybrid preferred\b", re.IGNORECASE),
    re.compile(r"\bideally hybrid\b", re.IGNORECASE),
)
_ONSITE_ONLY_PATTERNS = (
    re.compile(r"\bonsite[- ]only\b", re.IGNORECASE),
    re.compile(r"\bon-site[- ]only\b", re.IGNORECASE),
    re.compile(r"\bonly onsite\b", re.IGNORECASE),
    re.compile(r"\bonly on-site\b", re.IGNORECASE),
    re.compile(r"\bmust be onsite\b", re.IGNORECASE),
    re.compile(r"\bmust be on-site\b", re.IGNORECASE),
)
_ONSITE_PREFERRED_PATTERNS = (
    re.compile(r"\bprefer(?:ably)? onsite\b", re.IGNORECASE),
    re.compile(r"\bprefer(?:ably)? on-site\b", re.IGNORECASE),
    re.compile(r"\bonsite preferred\b", re.IGNORECASE),
    re.compile(r"\bon-site preferred\b", re.IGNORECASE),
    re.compile(r"\bideally onsite\b", re.IGNORECASE),
    re.compile(r"\bideally on-site\b", re.IGNORECASE),
)
_ONSITE_OK_PATTERNS = (
    re.compile(r"\bonsite (?:is )?(?:ok|okay|fine)\b", re.IGNORECASE),
    re.compile(r"\bon-site (?:is )?(?:ok|okay|fine)\b", re.IGNORECASE),
)

_FRESHNESS_PATTERNS: tuple[tuple[re.Pattern[str], int | None], ...] = (
    (re.compile(r"\b(?:last|past)\s+(\d+)\s+days?\b", re.IGNORECASE), None),
    (re.compile(r"\b(?:last|past)\s+(\d+)\s+weeks?\b", re.IGNORECASE), 7),
    (re.compile(r"\b(?:last|past)\s+(\d+)\s+months?\b", re.IGNORECASE), 30),
    (re.compile(r"\b(?:last|past)\s+24\s+hours?\b", re.IGNORECASE), 1),
    (re.compile(r"\b(?:last|past)\s+fortnight\b", re.IGNORECASE), 14),
    (re.compile(r"\b(?:last|past)\s+week\b", re.IGNORECASE), 7),
    (re.compile(r"\b(?:last|past)\s+month\b", re.IGNORECASE), 30),
    (re.compile(r"\bthis\s+week\b", re.IGNORECASE), 7),
    (re.compile(r"\btoday\b", re.IGNORECASE), 1),
    (re.compile(r"\byesterday\b", re.IGNORECASE), 1),
)

_SITE_PATTERNS = (
    ("greenhouse", re.compile(r"\bgreenhouse\b", re.IGNORECASE)),
    ("lever", re.compile(r"\blever\b", re.IGNORECASE)),
)
_EXPLICIT_SOURCE_SITE_PATTERNS: tuple[tuple[str, tuple[re.Pattern[str], ...]], ...] = (
    (
        "linkedin",
        (
            re.compile(r"\bon\s+linkedin\b", re.IGNORECASE),
            re.compile(r"\busing\s+linkedin\b", re.IGNORECASE),
            re.compile(r"\bvia\s+linkedin\b", re.IGNORECASE),
            re.compile(r"\bsearch\s+linkedin\s+jobs\b", re.IGNORECASE),
            re.compile(r"\blinkedin\s+jobs\b", re.IGNORECASE),
            re.compile(r"\blinkedin\s+source\b", re.IGNORECASE),
            re.compile(r"\blinkedin\s+site\b", re.IGNORECASE),
        ),
    ),
)

_CLAUSE_STOP_PATTERN = re.compile(
    r"\b(?:in|from|at|on|within|over|during|posted|last|past|today|yesterday|"
    r"avoid|exclude|excluding|without|greenhouse|lever|prefer|preferred|ideally)\b",
    re.IGNORECASE,
)
_MUST_HAVE_MARKERS = (
    "must have",
    "must include",
    "required",
    "require",
    "requires",
    "need",
    "needs",
)
_PREFERENCE_MARKERS = (
    "prefer",
    "preferred",
    "ideally",
    "nice to have",
    "bonus if",
    "bonus points for",
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
    "not",
    "no",
)
_PREFERENCE_LOCATION_MARKERS = (
    "prefer in",
    "prefer based in",
    "prefer located in",
    "ideally in",
    "ideally based in",
    "ideally located in",
)
_EXCLUDED_CATEGORY_MARKERS = (
    "avoid",
    "exclude",
    "excluding",
    "not",
    "no",
)
_FILLER_WORDS = {
    "a",
    "an",
    "and",
    "at",
    "based",
    "be",
    "can",
    "company",
    "companies",
    "find",
    "for",
    "from",
    "hire",
    "hiring",
    "i",
    "ideally",
    "in",
    "is",
    "job",
    "jobs",
    "like",
    "located",
    "looking",
    "me",
    "of",
    "on",
    "only",
    "or",
    "position",
    "positions",
    "prefer",
    "preferred",
    "role",
    "roles",
    "search",
    "show",
    "something",
    "that",
    "the",
    "to",
    "want",
    "with",
}


def parse_search_intent(prompt_text: str) -> SearchIntent:
    """Convert a natural-language prompt into a conservative structured search intent."""
    target_titles = _extract_target_titles(prompt_text)
    preferred_titles = _extract_preferred_titles(prompt_text)
    include_keywords = _extract_include_keywords(prompt_text)
    preferred_keywords = _extract_preferred_keywords(prompt_text)
    exclude_keywords = _extract_exclude_keywords(prompt_text)
    excluded_role_categories = _extract_excluded_role_categories(prompt_text)
    location_constraints = _extract_locations(prompt_text)
    preferred_locations = _extract_preferred_locations(prompt_text)

    constraints = SearchConstraint(
        target_titles=target_titles,
        preferred_titles=preferred_titles,
        include_keywords=include_keywords,
        preferred_keywords=preferred_keywords,
        exclude_keywords=exclude_keywords,
        excluded_role_categories=excluded_role_categories,
        location_constraints=location_constraints,
        preferred_locations=preferred_locations,
        remote_preference=_extract_remote_preference(prompt_text),
        seniority_preferences=_extract_seniority_preferences(prompt_text),
        source_site_preferences=_extract_source_site_preferences(prompt_text),
        freshness_window_days=_extract_freshness_window_days(prompt_text),
        include_companies=_extract_company_hints(prompt_text, include=True),
        exclude_companies=_extract_company_hints(prompt_text, include=False),
    )
    parser_notes = _build_parser_notes(constraints)
    unresolved_fragments = _extract_unresolved_fragments(prompt_text, constraints)
    summary = _build_summary(constraints, unresolved_fragments=unresolved_fragments)
    return SearchIntent(
        prompt_text=prompt_text,
        constraints=constraints,
        summary=summary,
        parser_notes=parser_notes,
        unresolved_fragments=unresolved_fragments,
    )


def _extract_target_titles(prompt_text: str) -> list[str]:
    explicit_titles = (
        _normalize_title(match.group(1))
        for match in _TITLE_PATTERN.finditer(prompt_text)
        if not _is_exclusion_context(prompt_text, match.start())
    )
    role_phrase_titles = _extract_role_phrase_titles(prompt_text, preferred=False)
    return _dedupe_strings(list(explicit_titles) + role_phrase_titles)


def _extract_preferred_titles(prompt_text: str) -> list[str]:
    return _extract_role_phrase_titles(prompt_text, preferred=True)


def _extract_include_keywords(prompt_text: str) -> list[str]:
    keywords: list[str] = []
    for marker in _KEYWORD_MARKERS + _MUST_HAVE_MARKERS:
        keywords.extend(_extract_clause_items(prompt_text, marker))
    keywords.extend(_extract_role_phrase_keywords(prompt_text, preferred=False))
    return _dedupe_strings(keyword for keyword in keywords if _is_keyword_like(keyword))


def _extract_preferred_keywords(prompt_text: str) -> list[str]:
    keywords: list[str] = []
    for marker in _PREFERENCE_MARKERS:
        keywords.extend(_extract_clause_items(prompt_text, marker))
    keywords.extend(_extract_role_phrase_keywords(prompt_text, preferred=True))
    location_preferences = {item.casefold() for item in _extract_preferred_locations(prompt_text)}
    return _dedupe_strings(
        keyword
        for keyword in keywords
        if _is_keyword_like(keyword)
        and keyword.casefold() not in {item.casefold() for item in _extract_include_keywords(prompt_text)}
        and keyword.casefold() not in location_preferences
        and keyword.casefold() not in {"remote", "remote only", "hybrid", "hybrid only", "onsite", "onsite only", "on-site"}
    )


def _extract_exclude_keywords(prompt_text: str) -> list[str]:
    keywords: list[str] = []
    company_items = _extract_company_hints(prompt_text, include=False)
    normalized_company_items = {_strip_company_prefix(item).casefold() for item in company_items}
    for marker in _EXCLUDE_MARKERS:
        keywords.extend(
            item
            for item in _extract_clause_items(prompt_text, marker)
            if _strip_company_prefix(item).casefold() not in normalized_company_items
            and "company" not in item.casefold()
            and _is_keyword_like(item)
        )
    return _dedupe_strings(keyword for keyword in keywords if _is_keyword_like(keyword))


def _extract_excluded_role_categories(prompt_text: str) -> list[str]:
    categories: list[str] = []
    for marker in _EXCLUDED_CATEGORY_MARKERS:
        for item in _extract_clause_items(prompt_text, marker):
            if _looks_like_role_or_category(item):
                categories.append(item)
    return _dedupe_strings(categories)


def _extract_locations(prompt_text: str) -> list[str]:
    clauses: list[str] = []
    patterns = (
        re.compile(r"\b(?:roles?|jobs?|positions?|openings?)\s+in\s+([^.;]+)", re.IGNORECASE),
        re.compile(r"\b(?:based in|located in|remote in|must be in|only in)\s+([^.;]+)", re.IGNORECASE),
        re.compile(r"\b(?:anywhere in)\s+([^.;]+)", re.IGNORECASE),
        re.compile(r"\b(?:at|from)\s+[A-Za-z0-9 .&-]+\s+in\s+([^.;]+)", re.IGNORECASE),
    )
    for pattern in patterns:
        for match in pattern.finditer(prompt_text):
            clauses.extend(_split_clause_items(_truncate_clause(match.group(1))))
    return _dedupe_strings(_filter_locations(clauses))


def _extract_preferred_locations(prompt_text: str) -> list[str]:
    clauses: list[str] = []
    for marker in _PREFERENCE_LOCATION_MARKERS + ("prefer", "ideally", "preferred"):
        clauses.extend(_extract_clause_items(prompt_text, marker))
    return _dedupe_strings(_filter_locations(clauses))


def _extract_remote_preference(prompt_text: str) -> RemotePreference:
    for pattern in _REMOTE_ONLY_PATTERNS:
        if pattern.search(prompt_text):
            return RemotePreference.REMOTE_ONLY
    for pattern in _HYBRID_ONLY_PATTERNS:
        if pattern.search(prompt_text):
            return RemotePreference.HYBRID_ONLY
    for pattern in _ONSITE_ONLY_PATTERNS:
        if pattern.search(prompt_text):
            return RemotePreference.ONSITE_ONLY
    for pattern in _REMOTE_PREFERRED_PATTERNS:
        if pattern.search(prompt_text):
            return RemotePreference.REMOTE_PREFERRED
    for pattern in _HYBRID_PREFERRED_PATTERNS:
        if pattern.search(prompt_text):
            return RemotePreference.HYBRID_PREFERRED
    for pattern in _ONSITE_PREFERRED_PATTERNS:
        if pattern.search(prompt_text):
            return RemotePreference.ONSITE_PREFERRED
    for pattern in _ONSITE_OK_PATTERNS:
        if pattern.search(prompt_text):
            return RemotePreference.ONSITE_OK
    return RemotePreference.UNSPECIFIED


def _extract_seniority_preferences(prompt_text: str) -> list[SeniorityLevel]:
    return [level for pattern, level in _SENIORITY_PATTERNS if pattern.search(prompt_text)]


def _extract_source_site_preferences(prompt_text: str) -> list[str]:
    preferences = [
        site_name
        for site_name, patterns in _EXPLICIT_SOURCE_SITE_PATTERNS
        if any(pattern.search(prompt_text) for pattern in patterns)
    ]
    preferences.extend(
        site_name
        for site_name, pattern in _SITE_PATTERNS
        if site_name not in preferences and pattern.search(prompt_text)
    )
    return preferences


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
            re.compile(r"\b(?:avoid|exclude|excluding)\s+([A-Z][^.;]+)"),
        )
    for pattern in patterns:
        for match in pattern.finditer(prompt_text):
            clauses.extend(_split_clause_items(_truncate_clause(match.group(1))))
    cleaned_clauses = [_strip_company_prefix(item) for item in clauses]
    return _dedupe_strings(item for item in cleaned_clauses if _looks_like_company_hint(item))


def _extract_role_phrase_titles(prompt_text: str, *, preferred: bool) -> list[str]:
    titles: list[str] = []
    for match in _ROLE_PHRASE_PATTERN.finditer(prompt_text):
        phrase = _clean_phrase(match.group(1))
        if _is_exclusion_context(prompt_text, match.start()):
            continue
        if preferred != _is_preference_context(prompt_text, match.start()):
            continue
        for item in _split_clause_items(phrase):
            normalized = _normalize_role_family(item)
            title = _ROLE_FAMILY_TITLE_MAP.get(normalized)
            if title is not None:
                titles.append(title)
    return _dedupe_strings(titles)


def _extract_role_phrase_keywords(prompt_text: str, *, preferred: bool) -> list[str]:
    keywords: list[str] = []
    for match in _ROLE_PHRASE_PATTERN.finditer(prompt_text):
        phrase = _clean_phrase(match.group(1))
        if _is_exclusion_context(prompt_text, match.start()):
            continue
        if preferred != _is_preference_context(prompt_text, match.start()):
            continue
        normalized_phrase = _normalize_role_family(phrase)
        if normalized_phrase in _ROLE_FAMILY_TITLE_MAP:
            keywords.extend(_keywords_for_role_family(normalized_phrase))
            continue
        for item in _split_clause_items(phrase):
            normalized_item = _normalize_role_family(item)
            if normalized_item in _ROLE_FAMILY_TITLE_MAP:
                keywords.extend(_keywords_for_role_family(normalized_item))
    return _dedupe_strings(keyword for keyword in keywords if _is_keyword_like(keyword))


def _keywords_for_role_family(value: str) -> list[str]:
    if value in {"ml", "machine learning"}:
        return ["machine learning"]
    if value == "front end":
        return ["frontend"]
    if value == "site reliability":
        return ["site reliability"]
    return [part.upper() if part in {"ai", "qa", "ios"} else part for part in value.split()]


def _is_preference_context(prompt_text: str, position: int) -> bool:
    window = prompt_text[max(0, position - 30):position].casefold()
    return any(marker in window for marker in ("prefer", "preferred", "ideally", "nice to have", "bonus"))


def _is_exclusion_context(prompt_text: str, position: int) -> bool:
    window = prompt_text[max(0, position - 60):position].casefold()
    return any(marker in window for marker in ("avoid", "exclude", "excluding", "without", "not", "no "))


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


def _normalize_role_family(value: str) -> str:
    normalized = _clean_phrase(value).casefold().replace("-", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"^(?:senior|sr|junior|jr|staff|lead|principal|mid|mid level)\s+", "", normalized)
    return normalized


def _is_keyword_like(value: str) -> bool:
    normalized = value.casefold()
    if normalized in {"remote", "hybrid", "onsite", "on-site"}:
        return False
    if "company" in normalized:
        return False
    return bool(normalized)


def _looks_like_role_or_category(value: str) -> bool:
    normalized = value.casefold()
    return any(term in normalized for term in _ROLE_FAMILY_TERMS + ("sales", "recruit", "manager", "management", "crypto", "adtech"))


def _filter_locations(values: list[str]) -> list[str]:
    filtered = [
        clause
        for clause in values
        if clause
        and not _looks_like_keyword_fragment(clause)
        and "company" not in clause.casefold()
        and clause.casefold() not in {"remote", "preferably remote", "hybrid", "onsite", "on-site", "tech"}
        and not clause.casefold().startswith(("maybe ", "around ", "about "))
        and "hybrid" not in clause.casefold()
        and "remote" not in clause.casefold()
        and "onsite" not in clause.casefold()
        and "on-site" not in clause.casefold()
        and not _looks_like_role_or_category(clause)
    ]
    return filtered


def _looks_like_keyword_fragment(value: str) -> bool:
    normalized = value.casefold()
    return normalized.startswith(("python", "backend", "frontend", "api", "data", "platform"))


def _looks_like_company_hint(value: str) -> bool:
    normalized = value.casefold()
    if normalized in {"startups", "startup", "companies", "company", "the", "last", "past"}:
        return False
    return len(normalized) >= 2 and not _looks_like_role_or_category(value)


def _strip_company_prefix(value: str) -> str:
    return re.sub(r"^(?:companies?|company)\s+like\s+", "", value, flags=re.IGNORECASE)


def _build_parser_notes(constraints: SearchConstraint) -> list[str]:
    notes: list[str] = []
    if constraints.target_titles:
        notes.append(f"must-have titles: {', '.join(constraints.target_titles)}")
    if constraints.preferred_titles:
        notes.append(f"preferred titles: {', '.join(constraints.preferred_titles)}")
    if constraints.include_keywords:
        notes.append(f"must-have keywords: {', '.join(constraints.include_keywords)}")
    if constraints.preferred_keywords:
        notes.append(f"preferred keywords: {', '.join(constraints.preferred_keywords)}")
    if constraints.excluded_role_categories:
        notes.append(f"excluded roles/categories: {', '.join(constraints.excluded_role_categories)}")
    if constraints.location_constraints:
        notes.append(f"required locations: {', '.join(constraints.location_constraints)}")
    if constraints.preferred_locations:
        notes.append(f"preferred locations: {', '.join(constraints.preferred_locations)}")
    if constraints.include_companies:
        notes.append(f"target companies: {', '.join(constraints.include_companies)}")
    if constraints.exclude_companies:
        notes.append(f"excluded companies: {', '.join(constraints.exclude_companies)}")
    if constraints.remote_preference is not RemotePreference.UNSPECIFIED:
        notes.append(f"workplace preference: {constraints.remote_preference.value}")
    if constraints.freshness_window_days is not None:
        notes.append(f"freshness window: {constraints.freshness_window_days} days")
    return notes


def _extract_unresolved_fragments(prompt_text: str, constraints: SearchConstraint) -> list[str]:
    resolved_tokens = {
        token.casefold()
        for token in (
            list(constraints.target_titles)
            + list(constraints.preferred_titles)
            + list(constraints.include_keywords)
            + list(constraints.preferred_keywords)
            + list(constraints.exclude_keywords)
            + list(constraints.excluded_role_categories)
            + list(constraints.location_constraints)
            + list(constraints.preferred_locations)
            + list(constraints.include_companies)
            + list(constraints.exclude_companies)
            + [level.value for level in constraints.seniority_preferences]
            + list(constraints.source_site_preferences)
        )
    }
    fragments: list[str] = []
    for raw_clause in re.split(r"[.;,]", prompt_text):
        clause = _clean_phrase(raw_clause)
        if not clause:
            continue
        normalized_clause = clause.casefold()
        if any(token and token in normalized_clause for token in resolved_tokens):
            continue
        if constraints.remote_preference is not RemotePreference.UNSPECIFIED and any(
            marker in normalized_clause for marker in ("remote", "hybrid", "onsite", "on-site")
        ):
            continue
        if constraints.freshness_window_days is not None and any(
            marker in normalized_clause for marker in ("last", "past", "today", "yesterday", "week", "month", "day", "days")
        ):
            continue
        if constraints.source_site_preferences and any(site in normalized_clause for site in constraints.source_site_preferences):
            continue
        words = [word for word in re.findall(r"[A-Za-z0-9][A-Za-z0-9+/-]*", normalized_clause) if word not in _FILLER_WORDS]
        if len(words) < 2:
            continue
        fragments.append(clause)
    return _dedupe_strings(fragments)


def _build_summary(constraints: SearchConstraint, *, unresolved_fragments: list[str]) -> str | None:
    parts: list[str] = []
    if constraints.target_titles:
        parts.append(f"titles={', '.join(constraints.target_titles)}")
    if constraints.include_keywords:
        parts.append(f"must={', '.join(constraints.include_keywords)}")
    if constraints.preferred_keywords:
        parts.append(f"prefer={', '.join(constraints.preferred_keywords)}")
    if constraints.exclude_keywords:
        parts.append(f"exclude={', '.join(constraints.exclude_keywords)}")
    if constraints.location_constraints:
        parts.append(f"locations={', '.join(constraints.location_constraints)}")
    if constraints.include_companies:
        parts.append(f"companies={', '.join(constraints.include_companies)}")
    if constraints.remote_preference is not RemotePreference.UNSPECIFIED:
        parts.append(f"remote={constraints.remote_preference.value}")
    if constraints.freshness_window_days is not None:
        parts.append(f"freshness={constraints.freshness_window_days}d")
    if unresolved_fragments:
        parts.append(f"unresolved={len(unresolved_fragments)}")
    if not parts:
        return None
    return " | ".join(parts)


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
