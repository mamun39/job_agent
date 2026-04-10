"""Base adapter contract for job-site readers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol

from job_agent.core.models import ParsedJobDetail, ParsedJobListing, SiteCapabilities


class SupportsPageContent(Protocol):
    """Minimal protocol for page-like objects that can expose HTML."""

    def content(self) -> str:
        """Return the current page HTML."""


class JobSiteAdapter(ABC):
    """Read-only adapter contract for job-site discovery and parsing."""

    @property
    @abstractmethod
    def site_name(self) -> str:
        """Return the stable site identifier."""

    @property
    @abstractmethod
    def capabilities(self) -> SiteCapabilities:
        """Describe which read-only workflows the adapter supports."""

    @abstractmethod
    def parse_listings(
        self,
        *,
        html: str | None = None,
        page: SupportsPageContent | None = None,
    ) -> list[ParsedJobListing]:
        """Parse job listings from HTML or a Playwright-like page object."""

    @abstractmethod
    def parse_job_detail(
        self,
        *,
        url: str,
        html: str | None = None,
        page: SupportsPageContent | None = None,
    ) -> ParsedJobDetail:
        """Parse one job detail page from HTML or a Playwright-like page object."""

