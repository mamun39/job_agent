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
from job_agent.ui.cli import export_jobs_csv, render_job_detail, render_jobs_list


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

    review_parser = subparsers.add_parser(
        "review",
        help="List, inspect, and export stored jobs.",
    )
    review_subparsers = review_parser.add_subparsers(dest="review_command")

    review_list_parser = review_subparsers.add_parser("list", help="List stored jobs.")
    _add_review_filters(review_list_parser)
    review_list_parser.add_argument("--limit", type=int, default=100)

    review_show_parser = review_subparsers.add_parser("show", help="Show one stored job.")
    review_show_parser.add_argument("--url", required=True, help="Job URL to display.")

    review_export_parser = review_subparsers.add_parser("export", help="Export filtered jobs to CSV.")
    _add_review_filters(review_export_parser)
    review_export_parser.add_argument("--limit", type=int, default=100)
    review_export_parser.add_argument("--output", required=True, help="CSV output path.")
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

    if args.command == "review":
        repo = JobsRepository(init_db(settings.db_path))

        if args.review_command == "list":
            jobs = repo.list_jobs(
                source_site=args.source_site,
                min_score=args.min_score,
                reviewed=_parse_review_filter(args.reviewed),
                limit=args.limit,
            )
            print(render_jobs_list(jobs))
            return 0

        if args.review_command == "show":
            job = repo.fetch_for_review(url=args.url)
            if job is None:
                print(f"Job not found: {args.url}")
                return 1
            print(render_job_detail(job))
            return 0

        if args.review_command == "export":
            jobs = repo.list_jobs(
                source_site=args.source_site,
                min_score=args.min_score,
                reviewed=_parse_review_filter(args.reviewed),
                limit=args.limit,
            )
            output_path = export_jobs_csv(jobs, args.output)
            print(f"Exported {len(jobs)} jobs to {output_path}")
            return 0

        parser.error("review requires a subcommand")

    return 0


def _add_review_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source-site", help="Filter by source site.")
    parser.add_argument("--min-score", type=float, help="Filter by minimum numeric score.")
    parser.add_argument(
        "--reviewed",
        choices=["reviewed", "unreviewed", "all"],
        default="all",
        help="Filter by review status.",
    )


def _parse_review_filter(value: str) -> bool | None:
    if value == "reviewed":
        return True
    if value == "unreviewed":
        return False
    return None


if __name__ == "__main__":
    raise SystemExit(main())
