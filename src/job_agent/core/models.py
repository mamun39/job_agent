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
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"
    SKIPPED = "skipped"


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
    reviewer: str | None = None
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reviewer", "notes", mode="before")
    @classmethod
    def _normalize_review_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_text(value)
