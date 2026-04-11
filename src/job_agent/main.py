"""CLI entrypoint for job-agent."""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from job_agent.browser.session import BrowserSessionManager
from job_agent.config import load_settings
from job_agent.core.board_registry import (
    load_board_registry_json_file,
    load_board_registry_payload,
    save_board_registry_json_file,
    sort_board_registry_entries,
    validate_board_registry_json_file,
    validate_board_registry_payload,
)
from job_agent.core.models import CrawlResult, DiscoveryOptions, MatchedJobMatch
from job_agent.flows.discover import run_discovery_query
from job_agent.flows.prompt_search import run_prompt_search
from job_agent.logging import configure_logging
from job_agent.core.scoring import rescore_job_posting
from job_agent.storage.db import init_db
from job_agent.storage.jobs_repo import JobsRepository
from job_agent.ui.cli import (
    apply_score_result,
    export_prompt_search_matches_csv,
    export_jobs_csv,
    format_cleanup_summary,
    format_mark_stale_summary,
    format_review_update_result,
    format_rescore_summary,
    format_saved_search_summary,
    format_store_matches_summary,
    open_job_in_browser,
    parse_job_status,
    parse_review_decision,
    render_discovery_summary,
    render_job_detail,
    render_jobs_list,
    render_matched_jobs,
    render_prompt_search_summary,
    render_rejected_jobs,
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
    _add_authenticated_browser_options(discover_parser)

    search_parser = subparsers.add_parser(
        "search",
        help="Run prompt-driven search from a raw natural-language prompt using the local board registry.",
    )
    search_parser.add_argument("prompt", nargs="?", help="Inline natural-language search prompt.")
    search_parser.add_argument("--prompt-file", help="Path to a text file containing the prompt.")
    search_parser.add_argument("--saved-search", help="Run a previously saved prompt by name.")
    search_parser.add_argument("--save-search", help="Save the resolved raw prompt under this name for reuse.")
    search_parser.add_argument("--export", help="Export matched prompt-search results to CSV.")
    search_parser.add_argument(
        "--show-rejected",
        action="store_true",
        help="Show rejected jobs and hard-filter reasons.",
    )
    search_parser.add_argument(
        "--store-matches",
        action="store_true",
        help="Persist newly matched jobs into the configured database.",
    )
    _add_authenticated_browser_options(search_parser)

    registry_parser = subparsers.add_parser(
        "registry",
        help="Manage the local board registry used to resolve prompt-driven plans into executable boards.",
    )
    registry_subparsers = registry_parser.add_subparsers(dest="registry_command")

    registry_list_parser = registry_subparsers.add_parser("list", help="List board registry entries.")
    registry_list_parser.add_argument("--registry-file", help="Path to the local board registry JSON file.")

    registry_add_parser = registry_subparsers.add_parser("add", help="Add one board registry entry.")
    registry_add_parser.add_argument("--registry-file", help="Path to the local board registry JSON file.")
    registry_add_parser.add_argument("--company", required=True, help="Company name.")
    registry_add_parser.add_argument("--source-site", required=True, help="Supported source site.")
    registry_add_parser.add_argument("--board-url", required=True, help="Board listing URL.")
    registry_add_parser.add_argument("--tag", action="append", default=[], help="Optional tag. Repeat for multiple values.")
    registry_add_parser.add_argument(
        "--location-hint",
        action="append",
        default=[],
        help="Optional location hint. Repeat for multiple values.",
    )

    registry_remove_parser = registry_subparsers.add_parser("remove", help="Remove one board registry entry.")
    registry_remove_parser.add_argument("--registry-file", help="Path to the local board registry JSON file.")
    registry_remove_parser.add_argument("--company", required=True, help="Company name.")
    registry_remove_parser.add_argument("--source-site", required=True, help="Supported source site.")
    registry_remove_parser.add_argument("--board-url", help="Optional exact board URL to disambiguate removal.")

    registry_validate_parser = registry_subparsers.add_parser("validate", help="Validate board registry entries.")
    registry_validate_parser.add_argument("--registry-file", help="Path to the local board registry JSON file.")

    registry_import_parser = registry_subparsers.add_parser("import", help="Import board registry entries from JSON.")
    registry_import_parser.add_argument("--registry-file", help="Path to the destination local board registry JSON file.")
    registry_import_parser.add_argument("--input", required=True, help="Source JSON file containing registry entries.")
    registry_import_parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace destination entries instead of merging.",
    )

    registry_export_parser = registry_subparsers.add_parser("export", help="Export board registry entries to JSON.")
    registry_export_parser.add_argument("--registry-file", help="Path to the source local board registry JSON file.")
    registry_export_parser.add_argument("--output", required=True, help="Destination JSON file.")

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

    review_subparsers.add_parser(
        "cleanup",
        help="Delete orphaned review decisions that no longer match stored jobs.",
    )

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
        try:
            session = _build_browser_session_manager(settings, args=args)
        except ValueError as exc:
            print(str(exc))
            return 1
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

    if args.command == "search":
        saved_search_repo = JobsRepository(init_db(settings.db_path))
        try:
            prompt_text = _resolve_search_prompt(
                prompt=args.prompt,
                prompt_file=args.prompt_file,
                saved_search_name=args.saved_search,
                saved_search_repo=saved_search_repo,
            )
        except ValueError as exc:
            print(str(exc))
            return 1

        if args.save_search:
            saved_search_repo.save_search_prompt(name=args.save_search, raw_prompt_text=prompt_text, now=datetime.now(UTC))
            print(format_saved_search_summary(name=args.save_search))

        try:
            session = _build_browser_session_manager(settings, args=args)
        except ValueError as exc:
            print(str(exc))
            return 1
        ephemeral_repo = JobsRepository(init_db(":memory:"))
        try:
            try:
                result = run_prompt_search(
                    prompt_text=prompt_text,
                    session=session,
                    jobs_repo=ephemeral_repo,
                    board_registry=settings.board_registry,
                    options=settings.discovery_options,
                    now=datetime.now(UTC),
                )
            except ValueError as exc:
                print(str(exc))
                return 1
        finally:
            session.close()

        print(render_prompt_search_summary(result))
        print(render_matched_jobs(result.matched_jobs))
        if args.show_rejected:
            print("Rejected Jobs:")
            print(render_rejected_jobs(result.rejected_jobs))
        if args.store_matches:
            repo = JobsRepository(init_db(settings.db_path))
            inserted_count = _store_new_matched_jobs(repo, result.matched_jobs)
            print(format_store_matches_summary(inserted_count=inserted_count, total_matches=len(result.matched_jobs)))
        if args.export:
            output_path = export_prompt_search_matches_csv(result.matched_jobs, args.export)
            print(f"Exported {len(result.matched_jobs)} matched jobs to {output_path}")
        return 0

    if args.command == "registry":
        if args.registry_command == "list":
            try:
                entries = _load_registry_entries_for_read(settings, registry_file=args.registry_file)
            except ValueError as exc:
                print(str(exc))
                return 1
            if not entries:
                print("No board registry entries configured.")
                return 0
            for entry in sort_board_registry_entries(entries):
                tags = ",".join(entry.tags) if entry.tags else "-"
                locations = ",".join(entry.location_hints) if entry.location_hints else "-"
                print(
                    f"{entry.company_name} | {entry.source_site} | {entry.board_url} | "
                    f"tags={tags} | locations={locations}"
                )
            return 0

        if args.registry_command == "validate":
            issues: list[str] = []
            if args.registry_file or settings.board_registry_file is not None:
                registry_file = _resolve_registry_file(settings, registry_file=args.registry_file, require_writable=False)
                _, issues = validate_board_registry_json_file(registry_file)
            else:
                _, issues = validate_board_registry_payload(_registry_entries_to_payload(settings.board_registry))
            if issues:
                print("Registry validation failed:")
                for issue in issues:
                    print(f"- {issue}")
                return 1
            print("Registry validation passed.")
            return 0

        if args.registry_command == "add":
            try:
                registry_file = _resolve_registry_file(settings, registry_file=args.registry_file, require_writable=True)
                entry = load_board_registry_payload(
                    [
                        {
                            "company_name": args.company,
                            "source_site": args.source_site,
                            "board_url": args.board_url,
                            "tags": list(args.tag),
                            "location_hints": list(args.location_hint),
                        }
                    ]
                )[0]
                entries = _load_registry_entries_for_write(registry_file)
                entries.append(entry)
                _write_registry_entries_with_validation(registry_file, entries)
            except ValueError as exc:
                print(str(exc))
                return 1
            print(f"Added registry entry for {entry.company_name} on {entry.source_site}.")
            return 0

        if args.registry_command == "remove":
            try:
                registry_file = _resolve_registry_file(settings, registry_file=args.registry_file, require_writable=True)
                entries = _load_registry_entries_for_write(registry_file)
                remaining_entries, removed_entry = _remove_registry_entry(
                    entries,
                    company_name=args.company,
                    source_site=args.source_site,
                    board_url=args.board_url,
                )
                _write_registry_entries_with_validation(registry_file, remaining_entries)
            except ValueError as exc:
                print(str(exc))
                return 1
            print(f"Removed registry entry for {removed_entry.company_name} on {removed_entry.source_site}.")
            return 0

        if args.registry_command == "import":
            try:
                registry_file = _resolve_registry_file(settings, registry_file=args.registry_file, require_writable=True)
                imported_entries = load_board_registry_json_file(Path(args.input))
                if args.replace:
                    merged_entries = imported_entries
                else:
                    merged_entries = _load_registry_entries_for_write(registry_file) + imported_entries
                _write_registry_entries_with_validation(registry_file, merged_entries)
            except ValueError as exc:
                print(str(exc))
                return 1
            print(f"Imported {len(imported_entries)} registry entries into {registry_file}.")
            return 0

        if args.registry_command == "export":
            try:
                entries = _load_registry_entries_for_read(settings, registry_file=args.registry_file)
                output_path = save_board_registry_json_file(Path(args.output), entries)
            except ValueError as exc:
                print(str(exc))
                return 1
            print(f"Exported {len(entries)} registry entries to {output_path}.")
            return 0

        parser.error("registry requires a subcommand")

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

        if args.review_command == "cleanup":
            removed_review_decisions = repo.cleanup_orphaned_review_decisions()
            print(format_cleanup_summary(removed_review_decisions=removed_review_decisions))
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


def _add_authenticated_browser_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--auth-browser",
        choices=["profile", "attach"],
        help="Opt in to authenticated local Chromium session reuse via a persistent profile or CDP attach.",
    )
    parser.add_argument(
        "--auth-browser-profile-dir",
        help="Existing Chromium profile directory to reuse in authenticated profile mode.",
    )
    parser.add_argument(
        "--auth-browser-cdp-url",
        help="Existing Chromium remote-debugging CDP URL to attach to in authenticated attach mode.",
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


def _build_browser_session_manager(settings: Any, *, args: Any) -> BrowserSessionManager:
    auth_mode = args.auth_browser or settings.browser_auth_mode
    auth_profile_dir = Path(args.auth_browser_profile_dir) if args.auth_browser_profile_dir else settings.browser_auth_profile_dir
    auth_cdp_url = args.auth_browser_cdp_url or settings.browser_auth_cdp_url
    if auth_mode == "profile" and auth_profile_dir is None:
        raise ValueError(
            "Authenticated browser mode 'profile' requires --auth-browser-profile-dir "
            "or JOB_AGENT_BROWSER_AUTH_PROFILE_DIR."
        )
    if auth_mode == "attach" and auth_cdp_url is None:
        raise ValueError(
            "Authenticated browser mode 'attach' requires --auth-browser-cdp-url "
            "or JOB_AGENT_BROWSER_AUTH_CDP_URL."
        )
    if auth_mode is None and (args.auth_browser_profile_dir or args.auth_browser_cdp_url):
        raise ValueError(
            "Provide --auth-browser profile or --auth-browser attach when passing "
            "authenticated browser reuse options."
        )
    return BrowserSessionManager(
        user_data_dir=settings.browser_user_data_dir,
        screenshot_dir=settings.browser_screenshot_dir,
        headless=settings.browser_headless,
        auth_mode=auth_mode,
        auth_profile_dir=auth_profile_dir,
        auth_cdp_url=auth_cdp_url,
    )


def _resolve_search_prompt(
    *,
    prompt: str | None,
    prompt_file: str | None,
    saved_search_name: str | None,
    saved_search_repo: JobsRepository,
) -> str:
    provided = sum(
        1
        for value in (prompt if prompt and prompt.strip() else None, prompt_file, saved_search_name)
        if value
    )
    if provided > 1:
        raise ValueError("Provide exactly one of: inline prompt, --prompt-file, or --saved-search.")
    if prompt_file:
        path = Path(prompt_file)
        if not path.is_file():
            raise ValueError(f"Prompt file does not exist: {path}")
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            raise ValueError("Prompt file is empty.")
        return text
    if saved_search_name:
        saved = saved_search_repo.get_saved_search(name=saved_search_name)
        if saved is None:
            raise ValueError(f"Saved search not found: {saved_search_name}")
        return saved.raw_prompt_text
    if prompt and prompt.strip():
        return prompt
    raise ValueError("Provide a prompt, --prompt-file, or --saved-search.")


def _store_new_matched_jobs(repo: JobsRepository, jobs: Sequence[MatchedJobMatch]) -> int:
    inserted_count = 0
    for matched in jobs:
        job = matched.job
        existing = repo.fetch_by_url(job.url.unicode_string())
        if existing is None and job.source_job_id:
            existing = repo.fetch_by_source_identity(job.source_site, job.source_job_id)
        if existing is not None:
            continue
        repo.insert_job(job)
        inserted_count += 1
    return inserted_count


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


def _resolve_registry_file(settings: Any, *, registry_file: str | None, require_writable: bool) -> Path:
    target = Path(registry_file) if registry_file else settings.board_registry_file
    if target is None:
        raise ValueError(
            "Board registry maintenance requires --registry-file or JOB_AGENT_BOARD_REGISTRY_FILE."
        )
    if target.suffix.lower() != ".json":
        raise ValueError("Board registry maintenance requires a .json registry file.")
    if target.exists() and not target.is_file():
        raise ValueError(f"Board registry path is not a file: {target}")
    if require_writable and target.exists() and not target.is_file():
        raise ValueError(f"Board registry path is not a writable file: {target}")
    return target


def _load_registry_entries_for_read(settings: Any, *, registry_file: str | None) -> list[Any]:
    if registry_file or settings.board_registry_file is not None:
        target = _resolve_registry_file(settings, registry_file=registry_file, require_writable=False)
        if not target.exists():
            return []
        return load_board_registry_json_file(target)
    return list(settings.board_registry)


def _load_registry_entries_for_write(registry_file: Path) -> list[Any]:
    if not registry_file.exists():
        return []
    return load_board_registry_json_file(registry_file)


def _write_registry_entries_with_validation(registry_file: Path, entries: list[Any]) -> Path:
    _, issues = validate_board_registry_payload(_registry_entries_to_payload(entries))
    if issues:
        raise ValueError(f"Registry validation failed: {'; '.join(issues)}")
    return save_board_registry_json_file(registry_file, sort_board_registry_entries(entries))


def _registry_entries_to_payload(entries: Sequence[Any]) -> list[dict[str, Any]]:
    return [
        {
            "company_name": entry.company_name,
            "source_site": entry.source_site,
            "board_url": entry.board_url.unicode_string(),
            "tags": list(entry.tags),
            "location_hints": list(entry.location_hints),
        }
        for entry in entries
    ]


def _remove_registry_entry(entries: list[Any], *, company_name: str, source_site: str, board_url: str | None) -> tuple[list[Any], Any]:
    normalized_company = "".join(char for char in company_name.casefold() if char.isalnum())
    normalized_source = source_site.lower().replace(" ", "_").replace("-", "_")
    matches = [
        entry
        for entry in entries
        if "".join(char for char in entry.company_name.casefold() if char.isalnum()) == normalized_company
        and entry.source_site == normalized_source
        and (board_url is None or entry.board_url.unicode_string() == board_url)
    ]
    if not matches:
        raise ValueError("No registry entry matched the requested company/source combination.")
    if len(matches) > 1:
        raise ValueError("Multiple registry entries matched. Re-run with --board-url to remove exactly one entry.")
    removed = matches[0]
    remaining = [entry for entry in entries if entry is not removed]
    return remaining, removed


if __name__ == "__main__":
    raise SystemExit(main())
