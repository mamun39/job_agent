"""CLI entrypoint for job-agent."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence

from job_agent.config import load_settings
from job_agent.logging import configure_logging


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

    # Keep args referenced so parser usage remains explicit as commands are added later.
    _ = args
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

