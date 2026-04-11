"""Core data models for job-agent."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class RemoteStatus(StrEnum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    TEMPORARY = "temporary"
    INTERNSHIP = "internship"
    FREELANCE = "freelance"
    UNKNOWN = "unknown"


class SeniorityLevel(StrEnum):
    INTERN = "intern"
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    PRINCIPAL = "principal"
    LEAD = "lead"
    MANAGER = "manager"
    DIRECTOR = "director"
    EXECUTIVE = "executive"
    UNKNOWN = "unknown"


class ReviewStatus(StrEnum):
    SAVED = "saved"
    SKIPPED = "skipped"
    APPLIED_ELSEWHERE = "applied_elsewhere"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"

    @classmethod
    def choices(cls) -> tuple[str, ...]:
        """Return supported persisted review decision values."""
        return tuple(status.value for status in cls)


class JobStatus(StrEnum):
    ACTIVE = "active"
    STALE = "stale"
    ARCHIVED = "archived"

    @classmethod
    def choices(cls) -> tuple[str, ...]:
        """Return supported persisted job status values."""
        return tuple(status.value for status in cls)


class RemotePreference(StrEnum):
    UNSPECIFIED = "unspecified"
    REMOTE_ONLY = "remote_only"
    REMOTE_PREFERRED = "remote_preferred"
    HYBRID_PREFERRED = "hybrid_preferred"
    ONSITE_OK = "onsite_ok"


SUPPORTED_DISCOVERY_SITES: frozenset[str] = frozenset({"greenhouse", "lever"})


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _normalize_text(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError("value must not be empty")
    return normalized


def _normalize_string_list(value: Any, *, casefold: bool = False) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError("value must be a list of strings")
    normalized_items = [_normalize_text(item) for item in value]
    if casefold:
        return [item.casefold() for item in normalized_items]
    return normalized_items


class JobPosting(BaseModel):
    """Normalized representation of a discovered job posting."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source_site: str = Field(..., description="Short source identifier, for example linkedin.")
    source_job_id: str | None = Field(default=None, description="Source-native job id if available.")
    url: HttpUrl
    title: str
    company: str
    location: str
    remote_status: RemoteStatus = RemoteStatus.UNKNOWN
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    seniority: SeniorityLevel = SeniorityLevel.UNKNOWN
    job_status: JobStatus = JobStatus.ACTIVE
    posted_at: datetime | None = Field(default=None, description="When the job was originally posted.")
    discovered_at: datetime = Field(
        default_factory=_utc_now,
        description="When job-agent discovered this posting.",
    )
    last_seen_at: datetime = Field(
        default_factory=_utc_now,
        description="When job-agent most recently observed this posting in discovery.",
    )
    description_text: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "source_site",
        "source_job_id",
        "title",
        "company",
        "location",
        "description_text",
        mode="before",
    )
    @classmethod
    def _normalize_string_fields(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _normalize_text(value)

    @field_validator("source_site")
    @classmethod
    def _validate_source_site(cls, value: str) -> str:
        normalized = value.lower().replace(" ", "_").replace("-", "_")
        if not normalized.replace("_", "").isalnum():
            raise ValueError("source_site must contain letters, numbers, spaces, hyphens, or underscores")
        return normalized

    @field_validator("metadata")
    @classmethod
    def _validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("metadata must be a dictionary")
        return value

    @model_validator(mode="after")
    def _validate_dates(self) -> JobPosting:
        if self.posted_at and self.posted_at > self.discovered_at:
            raise ValueError("posted_at cannot be later than discovered_at")
        if self.last_seen_at < self.discovered_at:
            raise ValueError("last_seen_at cannot be earlier than discovered_at")
        return self

    @property
    def canonical_url(self) -> str:
        from job_agent.core.dedupe import canonicalize_url

        return canonicalize_url(str(self.url))

    @property
    def dedupe_key(self) -> str:
        from job_agent.core.dedupe import compute_dedupe_key

        return compute_dedupe_key(self)

    @property
    def comparison_inputs(self) -> tuple[str, str, str]:
        from job_agent.core.dedupe import build_comparison_inputs

        return build_comparison_inputs(self)


class SearchQuery(BaseModel):
    """Search input definition for finding jobs."""

    model_config = ConfigDict(str_strip_whitespace=True)

    keywords: list[str] = Field(default_factory=list)
    location: str | None = None
    remote_only: bool = False
    companies: list[str] = Field(default_factory=list)
    employment_types: list[EmploymentType] = Field(default_factory=list)
    seniority_levels: list[SeniorityLevel] = Field(default_factory=list)
    posted_within_days: int | None = Field(default=None, ge=1, le=365)
    page_limit: int = Field(default=1, ge=1, le=100)

    @field_validator("keywords", "companies", mode="before")
    @classmethod
    def _normalize_string_list(cls, value: Any) -> Any:
        return _normalize_string_list(value)

    @field_validator("location", mode="before")
    @classmethod
    def _normalize_location(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_text(value)


class DiscoveryQuery(BaseModel):
    """Configured discovery entrypoint for one site run."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source_site: str
    label: str
    start_url: HttpUrl
    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    location_hints: list[str] = Field(default_factory=list)

    @field_validator("source_site", "label", mode="before")
    @classmethod
    def _normalize_required_text(cls, value: str) -> str:
        return _normalize_text(value)

    @field_validator("source_site")
    @classmethod
    def _normalize_query_source_site(cls, value: str) -> str:
        normalized = value.lower().replace(" ", "_").replace("-", "_")
        if not normalized.replace("_", "").isalnum():
            raise ValueError("source_site must contain letters, numbers, spaces, hyphens, or underscores")
        return normalized

    @field_validator("include_keywords", "exclude_keywords", "location_hints", mode="before")
    @classmethod
    def _normalize_string_list(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class SearchConstraint(BaseModel):
    """Normalized user or plan constraints for job discovery."""

    model_config = ConfigDict(str_strip_whitespace=True)

    target_titles: list[str] = Field(default_factory=list)
    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    location_constraints: list[str] = Field(default_factory=list)
    remote_preference: RemotePreference = RemotePreference.UNSPECIFIED
    seniority_preferences: list[SeniorityLevel] = Field(default_factory=list)
    source_site_preferences: list[str] = Field(default_factory=list)
    freshness_window_days: int | None = Field(default=None, ge=1, le=365)
    include_companies: list[str] = Field(default_factory=list)
    exclude_companies: list[str] = Field(default_factory=list)

    @field_validator(
        "target_titles",
        "include_keywords",
        "exclude_keywords",
        "location_constraints",
        "include_companies",
        "exclude_companies",
        mode="before",
    )
    @classmethod
    def _normalize_constraint_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("source_site_preferences", mode="before")
    @classmethod
    def _normalize_source_site_preferences(cls, value: Any) -> list[str]:
        return [item.lower().replace(" ", "_").replace("-", "_") for item in _normalize_string_list(value)]


class SearchIntent(BaseModel):
    """Structured user-facing search intent extracted from a natural-language prompt."""

    model_config = ConfigDict(str_strip_whitespace=True)

    prompt_text: str
    constraints: SearchConstraint = Field(default_factory=SearchConstraint)
    summary: str | None = None

    @field_validator("prompt_text", "summary", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_text(value)


class SearchPlanQuery(BaseModel):
    """One executable site-specific search query derived from a search intent."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source_site: str
    label: str
    company_name: str | None = None
    board_url: HttpUrl | None = None
    target_titles: list[str] = Field(default_factory=list)
    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    location_constraints: list[str] = Field(default_factory=list)
    remote_preference: RemotePreference = RemotePreference.UNSPECIFIED
    seniority_preferences: list[SeniorityLevel] = Field(default_factory=list)
    freshness_window_days: int | None = Field(default=None, ge=1, le=365)
    include_companies: list[str] = Field(default_factory=list)
    exclude_companies: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("label", mode="before")
    @classmethod
    def _normalize_plan_label(cls, value: str) -> str:
        return _normalize_text(value)

    @field_validator("company_name", mode="before")
    @classmethod
    def _normalize_plan_company_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_text(value)

    @field_validator(
        "target_titles",
        "include_keywords",
        "exclude_keywords",
        "location_constraints",
        "include_companies",
        "exclude_companies",
        "notes",
        mode="before",
    )
    @classmethod
    def _normalize_plan_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("source_site", mode="before")
    @classmethod
    def _normalize_plan_source_site(cls, value: str) -> str:
        return _normalize_text(value)

    @field_validator("source_site")
    @classmethod
    def _validate_plan_source_site(cls, value: str) -> str:
        normalized = value.lower().replace(" ", "_").replace("-", "_")
        if normalized not in SUPPORTED_DISCOVERY_SITES:
            supported = ", ".join(sorted(SUPPORTED_DISCOVERY_SITES))
            raise ValueError(f"source_site must be one of: {supported}")
        return normalized


class SearchPlan(BaseModel):
    """Executable search plan derived from a search intent for supported discovery sites."""

    model_config = ConfigDict(str_strip_whitespace=True)

    intent: SearchIntent
    queries: list[SearchPlanQuery] = Field(default_factory=list)
    constraints: SearchConstraint | None = None
    notes: list[str] = Field(default_factory=list)

    @field_validator("notes", mode="before")
    @classmethod
    def _normalize_plan_notes(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @model_validator(mode="after")
    def _validate_queries(self) -> SearchPlan:
        if not self.queries:
            raise ValueError("queries must contain at least one executable query")
        return self


class BoardRegistryEntry(BaseModel):
    """Local registry entry for a supported company job board."""

    model_config = ConfigDict(str_strip_whitespace=True)

    company_name: str
    source_site: str
    board_url: HttpUrl
    tags: list[str] = Field(default_factory=list)
    location_hints: list[str] = Field(default_factory=list)

    @field_validator("company_name", mode="before")
    @classmethod
    def _normalize_company_name(cls, value: str) -> str:
        return _normalize_text(value)

    @field_validator("source_site", mode="before")
    @classmethod
    def _normalize_board_source_site(cls, value: str) -> str:
        return _normalize_text(value)

    @field_validator("source_site")
    @classmethod
    def _validate_board_source_site(cls, value: str) -> str:
        normalized = value.lower().replace(" ", "_").replace("-", "_")
        if normalized not in SUPPORTED_DISCOVERY_SITES:
            supported = ", ".join(sorted(SUPPORTED_DISCOVERY_SITES))
            raise ValueError(f"source_site must be one of: {supported}")
        return normalized

    @field_validator("tags", "location_hints", mode="before")
    @classmethod
    def _normalize_registry_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class MatchExplanation(BaseModel):
    """Structured deterministic explanation for why a job matched an intent or plan."""

    model_config = ConfigDict(str_strip_whitespace=True)

    summary: str
    matched_titles: list[str] = Field(default_factory=list)
    matched_keywords: list[str] = Field(default_factory=list)
    excluded_keywords_triggered: list[str] = Field(default_factory=list)
    location_match: str | None = None
    remote_alignment: str | None = None
    seniority_alignment: str | None = None
    company_alignment: str | None = None
    notes: list[str] = Field(default_factory=list)

    @field_validator(
        "summary",
        "location_match",
        "remote_alignment",
        "seniority_alignment",
        "company_alignment",
        mode="before",
    )
    @classmethod
    def _normalize_explanation_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_text(value)

    @field_validator(
        "matched_titles",
        "matched_keywords",
        "excluded_keywords_triggered",
        "notes",
        mode="before",
    )
    @classmethod
    def _normalize_explanation_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class HardFilterResult(BaseModel):
    """Deterministic hard-filter evaluation result for one job against one intent."""

    passed: bool
    rejection_reasons: list[str] = Field(default_factory=list)

    @field_validator("rejection_reasons", mode="before")
    @classmethod
    def _normalize_rejection_reasons(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @model_validator(mode="after")
    def _validate_rejection_consistency(self) -> HardFilterResult:
        if self.passed and self.rejection_reasons:
            raise ValueError("rejection_reasons must be empty when passed is true")
        if not self.passed and not self.rejection_reasons:
            raise ValueError("rejection_reasons are required when passed is false")
        return self


class RejectedJobMatch(BaseModel):
    """One discovered job rejected by hard filters with explicit reasons."""

    job: JobPosting
    rejection_reasons: list[str] = Field(default_factory=list)
    explanation: str | None = None

    @field_validator("rejection_reasons", mode="before")
    @classmethod
    def _normalize_match_rejection_reasons(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)

    @field_validator("explanation", mode="before")
    @classmethod
    def _normalize_rejection_explanation(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_text(value)


class MatchedJobMatch(BaseModel):
    """One discovered job accepted by hard filters with deterministic match explanations."""

    job: JobPosting
    hard_filter_explanation: str
    score: int
    score_reasons: list[str] = Field(default_factory=list)

    @field_validator("hard_filter_explanation", mode="before")
    @classmethod
    def _normalize_hard_filter_explanation(cls, value: str) -> str:
        return _normalize_text(value)

    @field_validator("score_reasons", mode="before")
    @classmethod
    def _normalize_score_reasons(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class PromptSearchResult(BaseModel):
    """End-to-end prompt-driven search result."""

    intent: SearchIntent
    plan: SearchPlan
    discovered_jobs_count: int = 0
    matched_jobs: list[MatchedJobMatch] = Field(default_factory=list)
    rejected_jobs: list[RejectedJobMatch] = Field(default_factory=list)


class SavedSearch(BaseModel):
    """Locally persisted reusable raw prompt."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    raw_prompt_text: str
    created_at: datetime
    updated_at: datetime

    @field_validator("name", "raw_prompt_text", mode="before")
    @classmethod
    def _normalize_saved_search_text(cls, value: str) -> str:
        return _normalize_text(value)


class CrawlResult(BaseModel):
    """Result of a crawl or fetch attempt."""

    model_config = ConfigDict(str_strip_whitespace=True)

    query: SearchQuery
    postings: list[JobPosting] = Field(default_factory=list)
    fetched_at: datetime = Field(default_factory=_utc_now)
    source_site: str
    success: bool = True
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_site", "error_message", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_text(value)

    @field_validator("source_site")
    @classmethod
    def _normalize_source_site(cls, value: str) -> str:
        return value.lower().replace(" ", "_").replace("-", "_")

    @model_validator(mode="after")
    def _validate_error_message(self) -> CrawlResult:
        if not self.success and not self.error_message:
            raise ValueError("error_message is required when success is false")
        return self


class ReviewDecision(BaseModel):
    """Manual review decision for a job posting."""

    model_config = ConfigDict(str_strip_whitespace=True)

    posting_url: HttpUrl
    decision: ReviewStatus
    decided_at: datetime = Field(default_factory=_utc_now)
    note: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("note", mode="before")
    @classmethod
    def _normalize_review_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_text(value)


class ScoringCriteria(BaseModel):
    """Deterministic rule inputs for job relevance scoring."""

    model_config = ConfigDict(str_strip_whitespace=True)

    include_title_keywords: list[str] = Field(default_factory=list)
    exclude_title_keywords: list[str] = Field(default_factory=list)
    include_company_keywords: list[str] = Field(default_factory=list)
    exclude_company_keywords: list[str] = Field(default_factory=list)
    include_location_keywords: list[str] = Field(default_factory=list)
    exclude_location_keywords: list[str] = Field(default_factory=list)
    preferred_remote_statuses: list[RemoteStatus] = Field(default_factory=list)
    preferred_employment_types: list[EmploymentType] = Field(default_factory=list)
    preferred_seniority_levels: list[SeniorityLevel] = Field(default_factory=list)

    @field_validator(
        "include_title_keywords",
        "exclude_title_keywords",
        "include_company_keywords",
        "exclude_company_keywords",
        "include_location_keywords",
        "exclude_location_keywords",
        mode="before",
    )
    @classmethod
    def _normalize_keyword_list(cls, value: Any) -> list[str]:
        return _normalize_string_list(value, casefold=True)


class ScoreResult(BaseModel):
    """Deterministic score and explanation output."""

    score: int
    explanations: list[str] = Field(default_factory=list)


class SiteCapabilities(BaseModel):
    """Capability flags for a site adapter."""

    supports_listing_html_parse: bool = True
    supports_listing_page_parse: bool = False
    supports_detail_html_parse: bool = True
    supports_detail_page_parse: bool = False


class ParsedJobListing(BaseModel):
    """Lightweight listing discovery result before full detail parsing."""

    source_site: str
    url: HttpUrl
    source_job_id: str | None = None
    title_hint: str | None = None
    company_hint: str | None = None
    location_hint: str | None = None
    department_hint: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator(
        "source_site",
        "source_job_id",
        "title_hint",
        "company_hint",
        "location_hint",
        "department_hint",
        mode="before",
    )
    @classmethod
    def _normalize_listing_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_text(value)

    @field_validator("source_site")
    @classmethod
    def _normalize_listing_source_site(cls, value: str) -> str:
        normalized = value.lower().replace(" ", "_").replace("-", "_")
        if not normalized.replace("_", "").isalnum():
            raise ValueError("source_site must contain letters, numbers, spaces, hyphens, or underscores")
        return normalized


class ParsedJobDetail(BaseModel):
    """Read-only parse result for one job detail document."""

    listing: ParsedJobListing
    posting: JobPosting
    raw_html: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DiscoveryOptions(BaseModel):
    """Optional deterministic discovery behavior toggles."""

    enrich_greenhouse_details: bool = False
    enrich_lever_details: bool = False


class DiscoveryTelemetry(BaseModel):
    """Local structured counters for one discovery run."""

    queries_attempted: int = 0
    pages_fetched: int = 0
    pages_failed: int = 0
    jobs_parsed: int = 0
    jobs_inserted: int = 0
    jobs_updated: int = 0
    jobs_skipped_duplicates: int = 0
    detail_pages_fetched: int = 0
    detail_parse_failures: int = 0

    def as_metadata(self) -> dict[str, int]:
        """Return telemetry fields using the metadata keys exposed in crawl results."""
        return self.model_dump()
