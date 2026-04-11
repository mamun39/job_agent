"""CLI entrypoint for job-agent."""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime
from collections.abc import Sequence
from typing import Any

from job_agent.browser.session import BrowserSessionManager
from job_agent.config import load_settings
from job_agent.core.models import CrawlResult, DiscoveryOptions
from job_agent.flows.discover import run_discovery_query
from job_agent.logging import configure_logging
from job_agent.core.scoring import rescore_job_posting
from job_agent.storage.db import init_db
from job_agent.storage.jobs_repo import JobsRepository
from job_agent.ui.cli import (
    apply_score_result,
    export_jobs_csv,
    format_mark_stale_summary,
    format_review_update_result,
    format_rescore_summary,
    open_job_in_browser,
    parse_job_status,
    parse_review_decision,
    render_discovery_summary,
    render_job_detail,
    render_jobs_list,
    render_review_decision,
)


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
    discover_parser.add_argument(
        "--greenhouse-details",
        action="store_true",
        help="Enable optional Greenhouse detail-page enrichment for this run.",
    )
    discover_parser.add_argument(
        "--lever-details",
        action="store_true",
        help="Enable optional Lever detail-page enrichment for this run.",
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
    _add_review_target(review_show_parser)

    review_export_parser = review_subparsers.add_parser("export", help="Export filtered jobs to CSV.")
    _add_review_filters(review_export_parser)
    review_export_parser.add_argument("--limit", type=int, default=100)
    review_export_parser.add_argument("--output", required=True, help="CSV output path.")

    review_rescore_parser = review_subparsers.add_parser(
        "rescore",
        help="Recalculate stored scores using current deterministic rules.",
    )
    _add_review_filters(review_rescore_parser)
    review_rescore_parser.add_argument("--limit", type=int, default=100000)

    review_mark_stale_parser = review_subparsers.add_parser(
        "mark-stale",
        help="Mark stored jobs stale using last-seen timestamps.",
    )
    _add_review_filters(review_mark_stale_parser)
    review_mark_stale_parser.add_argument("--days", type=int, required=True, help="Stale threshold in days.")
    review_mark_stale_parser.add_argument("--limit", type=int, default=100000)

    review_decision_parser = review_subparsers.add_parser(
        "decision",
        help="Show the stored review decision for one job.",
    )
    _add_review_target(review_decision_parser)

    review_set_decision_parser = review_subparsers.add_parser(
        "set-decision",
        help="Persist an explicit review decision for one job.",
    )
    _add_review_target(review_set_decision_parser)
    review_set_decision_parser.add_argument("--decision", required=True, help="Decision to store.")
    review_set_decision_parser.add_argument("--note", help="Optional note stored with the decision.")

    open_parser = subparsers.add_parser(
        "open",
        help="Open a stored job URL in the default browser.",
    )
    open_target = open_parser.add_mutually_exclusive_group(required=True)
    open_target.add_argument("--id", type=int, help="Stored job database id.")
    open_target.add_argument("--url", help="Exact stored job URL.")

    dashboard_parser = subparsers.add_parser(
        "dashboard",
        help="Run a minimal local review dashboard.",
    )
    dashboard_parser.add_argument("--host", default="127.0.0.1", help="Bind host. Defaults to localhost only.")
    dashboard_parser.add_argument("--port", type=int, default=8000, help="Bind port.")
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

        discovery_options = DiscoveryOptions(
            enrich_greenhouse_details=(
                settings.discovery_options.enrich_greenhouse_details or bool(args.greenhouse_details)
            ),
            enrich_lever_details=(
                settings.discovery_options.enrich_lever_details or bool(args.lever_details)
            ),
        )
        repo = JobsRepository(init_db(settings.db_path))
        failures = 0
        successful_results: list[CrawlResult] = []
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
                        options=discovery_options,
                    )
                    successful_results.append(result)
                    status = "warn" if result.metadata["parsed_count"] == 0 else "ok"
                    artifact_hint = _format_debug_artifact_hint(result.metadata.get("debug_artifact_dirs"))
                    print(f"[{status}] {query.label} ({query.source_site}) {render_discovery_summary(result)}{artifact_hint}")
                except Exception as exc:  # pragma: no cover - exercised by CLI integration tests
                    failures += 1
                    artifact_hint = _format_debug_artifact_hint(getattr(exc, "debug_artifact_dir", None))
                    print(f"[error] {query.label} ({query.source_site}) {exc}{artifact_hint}")
        finally:
            session.close()

        if successful_results:
            aggregate = _aggregate_discovery_results(successful_results)
            print(f"[summary] {_render_aggregate_discovery_summary(aggregate)}")

        return 1 if failures else 0

    if args.command == "review":
        repo = JobsRepository(init_db(settings.db_path))

        if args.review_command == "list":
            try:
                decision_filter = _parse_review_decision_filter(args.decision)
            except ValueError as exc:
                print(str(exc))
                return 1
            jobs = repo.list_jobs(
                source_site=args.source_site,
                min_score=args.min_score,
                reviewed=_parse_review_filter(args.reviewed),
                decision=decision_filter,
                job_status=_parse_job_status_filter(args.job_status),
                limit=args.limit,
            )
            decisions = repo.get_review_decisions_by_url(job.url.unicode_string() for job in jobs)
            print(render_jobs_list(jobs, decisions=decisions))
            return 0

        if args.review_command == "show":
            job = repo.fetch_for_review(job_id=args.id, url=args.url)
            if job is None:
                print(_format_missing_job_message(job_id=args.id, url=args.url))
                return 1
            decision = repo.get_review_decision(posting_url=job.url.unicode_string())
            print(render_job_detail(job, decision=decision))
            return 0

        if args.review_command == "decision":
            job = repo.fetch_for_review(job_id=args.id, url=args.url)
            if job is None:
                print(_format_missing_job_message(job_id=args.id, url=args.url))
                return 1
            decision = repo.get_review_decision(posting_url=job.url.unicode_string())
            print(render_review_decision(decision))
            return 0

        if args.review_command == "set-decision":
            job = repo.fetch_for_review(job_id=args.id, url=args.url)
            if job is None:
                print(_format_missing_job_message(job_id=args.id, url=args.url))
                return 1
            try:
                parsed_decision = parse_review_decision(args.decision)
            except ValueError as exc:
                print(str(exc))
                return 1
            decision = repo.set_review_decision(
                posting_url=job.url.unicode_string(),
                decision=parsed_decision,
                note=args.note,
            )
            print(format_review_update_result(decision))
            return 0

        if args.review_command == "export":
            try:
                decision_filter = _parse_review_decision_filter(args.decision)
            except ValueError as exc:
                print(str(exc))
                return 1
            jobs = repo.list_jobs(
                source_site=args.source_site,
                min_score=args.min_score,
                reviewed=_parse_review_filter(args.reviewed),
                decision=decision_filter,
                job_status=_parse_job_status_filter(args.job_status),
                limit=args.limit,
            )
            output_path = export_jobs_csv(jobs, args.output)
            print(f"Exported {len(jobs)} jobs to {output_path}")
            return 0

        if args.review_command == "rescore":
            try:
                decision_filter = _parse_review_decision_filter(args.decision)
                job_status_filter = _parse_job_status_filter(args.job_status)
            except ValueError as exc:
                print(str(exc))
                return 1
            jobs = repo.list_jobs(
                source_site=args.source_site,
                reviewed=_parse_review_filter(args.reviewed),
                decision=decision_filter,
                job_status=job_status_filter,
                limit=args.limit,
            )
            rescored_count = 0
            for job in jobs:
                refreshed = apply_score_result(job, rescore_job_posting(job))
                repo.update_job_score(
                    posting_url=job.url.unicode_string(),
                    score=int(refreshed.metadata["score"]),
                    explanations=list(refreshed.metadata["score_explanations"]),
                )
                rescored_count += 1
            print(format_rescore_summary(rescored_count=rescored_count))
            return 0

        if args.review_command == "mark-stale":
            try:
                decision_filter = _parse_review_decision_filter(args.decision)
                job_status_filter = _parse_job_status_filter(args.job_status)
            except ValueError as exc:
                print(str(exc))
                return 1
            try:
                stale_count = repo.mark_stale_jobs(
                    stale_threshold_days=args.days,
                    source_site=args.source_site,
                    reviewed=_parse_review_filter(args.reviewed),
                    decision=decision_filter,
                    job_status=job_status_filter,
                    limit=args.limit,
                    now=datetime.now(UTC),
                )
            except ValueError as exc:
                print(str(exc))
                return 1
            print(format_mark_stale_summary(stale_count=stale_count, stale_threshold_days=args.days))
            return 0

        parser.error("review requires a subcommand")

    if args.command == "open":
        repo = JobsRepository(init_db(settings.db_path))
        try:
            opened_url = open_job_in_browser(repo._connection, job_id=args.id, url=args.url)
        except (ValueError, RuntimeError) as exc:
            print(str(exc))
            return 1
        print(f"Opened {opened_url}")
        return 0

    if args.command == "dashboard":
        import uvicorn
        from job_agent.ui.dashboard import create_dashboard_app

        app = create_dashboard_app(db_path=settings.db_path)
        uvicorn.run(app, host=args.host, port=args.port)
        return 0

    return 0


def _add_review_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source-site", help="Filter by source site.")
    parser.add_argument("--min-score", type=float, help="Filter by minimum numeric score.")
    parser.add_argument("--decision", help="Filter by explicit persisted review decision.")
    parser.add_argument("--job-status", help="Filter by persisted job lifecycle status.")
    parser.add_argument(
        "--reviewed",
        choices=["reviewed", "unreviewed", "all"],
        default="all",
        help="Filter by review status.",
    )


def _add_review_target(parser: argparse.ArgumentParser) -> None:
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--id", type=int, help="Stored job database id.")
    target.add_argument("--url", help="Exact stored job URL.")


def _parse_review_filter(value: str) -> bool | None:
    if value == "reviewed":
        return True
    if value == "unreviewed":
        return False
    return None


def _parse_review_decision_filter(value: str | None):
    if value is None:
        return None
    return parse_review_decision(value)


def _parse_job_status_filter(value: str | None):
    if value is None:
        return None
    return parse_job_status(value)


def _format_missing_job_message(*, job_id: int | None, url: str | None) -> str:
    if job_id is not None:
        return f"Job not found for id: {job_id}"
    return f"Job not found for url: {url}"


def _aggregate_discovery_results(results: Sequence[CrawlResult]) -> dict[str, int]:
    aggregate = {
        "queries_attempted": 0,
        "pages_fetched": 0,
        "pages_failed": 0,
        "jobs_parsed": 0,
        "jobs_inserted": 0,
        "jobs_updated": 0,
        "jobs_skipped_duplicates": 0,
        "detail_pages_fetched": 0,
        "detail_parse_failures": 0,
    }
    for result in results:
        metadata = result.metadata
        for key in aggregate:
            value = metadata.get(key, 0)
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                aggregate[key] += int(value)
    return aggregate


def _render_aggregate_discovery_summary(aggregate: dict[str, Any]) -> str:
    result = CrawlResult(query={}, source_site="aggregate", metadata=aggregate)
    return render_discovery_summary(result)


def _format_debug_artifact_hint(value: object) -> str:
    if isinstance(value, str) and value:
        return f" artifacts={value}"
    if isinstance(value, list) and value:
        return f" artifacts={value[0]}"
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
