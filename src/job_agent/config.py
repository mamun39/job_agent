"""Configuration loading for job-agent."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(slots=True)
class Settings:
    """Application settings loaded from the environment."""

    env: str = "development"
    log_level: str = "INFO"
    data_dir: Path = Path("./data")
    db_path: Path = Path("./data/job_agent.db")
    browser_user_data_dir: Path = Path("./data/browser")
    browser_screenshot_dir: Path = Path("./data/screenshots")
    browser_headless: bool = False


def load_dotenv(dotenv_path: str | Path = ".env") -> None:
    """Load simple KEY=VALUE pairs from a local .env file if present."""
    path = Path(dotenv_path)
    if not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def load_settings() -> Settings:
    """Build settings from environment variables."""
    load_dotenv()
    data_dir = Path(os.getenv("JOB_AGENT_DATA_DIR", "./data"))
    db_path = Path(os.getenv("JOB_AGENT_DB_PATH", data_dir / "job_agent.db"))
    browser_user_data_dir = Path(
        os.getenv("JOB_AGENT_BROWSER_USER_DATA_DIR", data_dir / "browser")
    )
    browser_screenshot_dir = Path(
        os.getenv("JOB_AGENT_BROWSER_SCREENSHOT_DIR", data_dir / "screenshots")
    )
    return Settings(
        env=os.getenv("JOB_AGENT_ENV", "development"),
        log_level=os.getenv("JOB_AGENT_LOG_LEVEL", "INFO").upper(),
        data_dir=data_dir,
        db_path=db_path,
        browser_user_data_dir=browser_user_data_dir,
        browser_screenshot_dir=browser_screenshot_dir,
        browser_headless=_parse_bool(os.getenv("JOB_AGENT_BROWSER_HEADLESS", "false")),
    )


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}
