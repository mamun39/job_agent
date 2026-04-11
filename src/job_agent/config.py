"""Configuration loading for job-agent."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import os
from typing import Any

from pydantic import ValidationError

from job_agent.core.board_registry import load_board_registry_payload
from job_agent.core.models import BoardRegistryEntry, DiscoveryOptions, DiscoveryQuery

@dataclass(slots=True)
class Settings:
    """Application settings loaded from the environment."""

    env: str = "development"
    log_level: str = "INFO"
    data_dir: Path = Path("./data")
    db_path: Path = Path("./data/job_agent.db")
    browser_user_data_dir: Path = Path("./data/browser")
    browser_screenshot_dir: Path = Path("./data/screenshots")
    debug_artifacts_dir: Path = Path("./data/debug_artifacts")
    browser_headless: bool = False
    browser_auth_mode: str | None = None
    browser_auth_profile_dir: Path | None = None
    browser_auth_cdp_url: str | None = None
    max_pages_per_query: int = 1
    debug_artifacts_on_failure: bool = False
    discovery_options: DiscoveryOptions = field(default_factory=DiscoveryOptions)
    board_registry_file: Path | None = None
    board_registry: list[BoardRegistryEntry] = field(default_factory=list)
    discovery_queries: list[DiscoveryQuery] | None = None


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
    debug_artifacts_dir = Path(
        os.getenv("JOB_AGENT_DEBUG_ARTIFACTS_DIR", data_dir / "debug_artifacts")
    )
    browser_auth_mode = load_browser_auth_mode()
    browser_auth_profile_dir = _load_optional_path("JOB_AGENT_BROWSER_AUTH_PROFILE_DIR")
    browser_auth_cdp_url = _load_optional_text("JOB_AGENT_BROWSER_AUTH_CDP_URL")
    return Settings(
        env=os.getenv("JOB_AGENT_ENV", "development"),
        log_level=os.getenv("JOB_AGENT_LOG_LEVEL", "INFO").upper(),
        data_dir=data_dir,
        db_path=db_path,
        browser_user_data_dir=browser_user_data_dir,
        browser_screenshot_dir=browser_screenshot_dir,
        debug_artifacts_dir=debug_artifacts_dir,
        browser_headless=_parse_bool(os.getenv("JOB_AGENT_BROWSER_HEADLESS", "false")),
        browser_auth_mode=browser_auth_mode,
        browser_auth_profile_dir=browser_auth_profile_dir,
        browser_auth_cdp_url=browser_auth_cdp_url,
        max_pages_per_query=load_max_pages_per_query(),
        debug_artifacts_on_failure=_parse_bool(os.getenv("JOB_AGENT_DEBUG_ARTIFACTS_ON_FAILURE", "false")),
        discovery_options=load_discovery_options(),
        board_registry_file=_load_optional_path("JOB_AGENT_BOARD_REGISTRY_FILE"),
        board_registry=load_board_registry(),
        discovery_queries=load_discovery_queries(),
    )


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _load_optional_text(env_var: str) -> str | None:
    value = os.getenv(env_var)
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _load_optional_path(env_var: str) -> Path | None:
    value = _load_optional_text(env_var)
    if value is None:
        return None
    return Path(value)


def load_browser_auth_mode() -> str | None:
    """Load the optional authenticated local-browser reuse mode."""
    load_dotenv()
    value = _load_optional_text("JOB_AGENT_BROWSER_AUTH_MODE")
    if value is None:
        return None
    normalized = value.lower()
    if normalized not in {"profile", "attach"}:
        raise ValueError("JOB_AGENT_BROWSER_AUTH_MODE must be one of: profile, attach")
    return normalized


def load_max_pages_per_query() -> int:
    """Load the conservative per-query page limit for live discovery."""
    load_dotenv()
    return _parse_positive_int(
        os.getenv("JOB_AGENT_MAX_PAGES_PER_QUERY", "1"),
        env_var="JOB_AGENT_MAX_PAGES_PER_QUERY",
    )


def load_discovery_options() -> DiscoveryOptions:
    """Load optional deterministic discovery behaviors from environment variables."""
    load_dotenv()
    return DiscoveryOptions(
        enrich_greenhouse_details=_parse_bool(os.getenv("JOB_AGENT_ENRICH_GREENHOUSE_DETAILS", "false")),
        enrich_lever_details=_parse_bool(os.getenv("JOB_AGENT_ENRICH_LEVER_DETAILS", "false")),
    )


def _parse_positive_int(value: str, *, env_var: str) -> int:
    normalized = value.strip()
    try:
        parsed = int(normalized)
    except ValueError as exc:
        raise ValueError(f"{env_var} must be a positive integer") from exc
    if parsed < 1:
        raise ValueError(f"{env_var} must be a positive integer")
    return parsed


def load_discovery_queries() -> list[DiscoveryQuery]:
    """Load discovery query config from a file path or JSON environment variable."""
    file_path = os.getenv("JOB_AGENT_DISCOVERY_QUERIES_FILE")
    raw_json = os.getenv("JOB_AGENT_DISCOVERY_QUERIES")

    if file_path:
        payload = _load_payload_from_file(Path(file_path), config_kind="Discovery query")
    elif raw_json:
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JOB_AGENT_DISCOVERY_QUERIES JSON: {exc.msg}") from exc
    else:
        return []

    if not isinstance(payload, list):
        raise ValueError("Discovery query config must be a list of query objects")

    try:
        return [DiscoveryQuery.model_validate(item) for item in payload]
    except ValidationError as exc:
        raise ValueError(f"Invalid discovery query config: {exc}") from exc
def load_board_registry() -> list[BoardRegistryEntry]:
    """Load local board registry config from a file path or JSON environment variable."""
    file_path = os.getenv("JOB_AGENT_BOARD_REGISTRY_FILE")
    raw_json = os.getenv("JOB_AGENT_BOARD_REGISTRY")

    if file_path:
        payload = _load_payload_from_file(Path(file_path), config_kind="Board registry")
    elif raw_json:
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JOB_AGENT_BOARD_REGISTRY JSON: {exc.msg}") from exc
    else:
        return []

    return load_board_registry_payload(payload)


def _load_payload_from_file(path: Path, *, config_kind: str) -> Any:
    if not path.is_file():
        raise ValueError(f"{config_kind} config file does not exist: {path}")

    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")

    if suffix == ".json":
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid {config_kind.lower()} JSON file: {exc.msg}") from exc

    if suffix in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:
            raise ValueError(
                f"YAML {config_kind.lower()} config requires PyYAML to be installed, or use JSON instead"
            ) from exc

        try:
            payload = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid {config_kind.lower()} YAML file: {exc}") from exc
        return [] if payload is None else payload

    raise ValueError(f"{config_kind} config file must use .json, .yaml, or .yml")
