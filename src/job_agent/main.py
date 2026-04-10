"""CLI entrypoint for job-agent."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from job_agent.browser.session import BrowserSessionManager
from job_agent.config import load_settings
from job_agent.flows.discover import run_discovery_query
from job_agent.logging import configure_logging
from job_agent.storage.db import init_db
from job_agent.storage.jobs_repo import JobsRepository


def build_parser() -> argparse.ArgumentParser:
    """Create the top-level CLI parser."""
    parser = argparse.ArgumentParser(
        prog="job-agent",
        description="Local job-search automation tool bootstrap.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="job-agent 0.1.0",
    )
    subparsers = parser.add_subparsers(dest="command")

    discover_parser = subparsers.add_parser(
        "discover",
        help="Run configured read-only discovery queries.",
    )
    discover_parser.add_argument(
        "--screenshot",
        action="store_true",
        help="Save one screenshot per query.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    settings = load_settings()
    configure_logging(settings.log_level)
    logging.getLogger(__name__).info(
        "cli_started",
        extra={"env": settings.env, "data_dir": str(settings.data_dir)},
    )

    if args.command == "discover":
        if not settings.discovery_queries:
            print("No discovery queries configured.")
            return 1

        repo = JobsRepository(init_db(settings.db_path))
        failures = 0
        session = BrowserSessionManager.from_settings(settings)
        try:
            for query in settings.discovery_queries:
                try:
                    screenshot_name = f"{query.source_site}_{query.label}" if args.screenshot else None
                    result = run_discovery_query(
                        query=query,
                        session=session,
                        jobs_repo=repo,
                        screenshot_name=screenshot_name,
                    )
                    print(
                        f"[ok] {query.label} ({query.source_site}) stored={result.metadata['stored_count']} "
                        f"inserted={result.metadata['inserted_count']} updated={result.metadata['updated_count']} "
                        f"duplicates={result.metadata['duplicate_count']}"
                    )
                except Exception as exc:  # pragma: no cover - exercised by CLI integration tests
                    failures += 1
                    print(f"[error] {query.label} ({query.source_site}) {exc}")
        finally:
            session.close()

        return 1 if failures else 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
