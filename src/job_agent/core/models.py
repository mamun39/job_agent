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


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _normalize_text(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError("value must not be empty")
    return normalized


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
    posted_at: datetime | None = Field(default=None, description="When the job was originally posted.")
    discovered_at: datetime = Field(
        default_factory=_utc_now,
        description="When job-agent discovered this posting.",
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
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("value must be a list of strings")
        return [_normalize_text(item) for item in value]

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
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("value must be a list of strings")
        return [_normalize_text(item) for item in value]


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
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("value must be a list of strings")
        return [_normalize_text(item).casefold() for item in value]


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
