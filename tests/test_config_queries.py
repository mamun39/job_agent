from __future__ import annotations

import json

import pytest

from job_agent.config import load_board_registry, load_browser_auth_mode, load_discovery_queries, load_settings


def test_load_discovery_queries_from_env_json(monkeypatch) -> None:
    monkeypatch.setenv(
        "JOB_AGENT_DISCOVERY_QUERIES",
        json.dumps(
            [
                {
                    "source_site": "greenhouse",
                    "label": "Example engineering",
                    "start_url": "https://boards.greenhouse.io/exampleco",
                    "include_keywords": ["python", "backend"],
                    "location_hints": ["Canada"],
                }
            ]
        ),
    )
    monkeypatch.delenv("JOB_AGENT_DISCOVERY_QUERIES_FILE", raising=False)

    queries = load_discovery_queries()

    assert len(queries) == 1
    assert queries[0].source_site == "greenhouse"
    assert queries[0].label == "Example engineering"
    assert str(queries[0].start_url) == "https://boards.greenhouse.io/exampleco"
    assert queries[0].include_keywords == ["python", "backend"]
    assert queries[0].exclude_keywords == []


def test_load_discovery_queries_from_json_file(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "queries.json"
    config_path.write_text(
        json.dumps(
            [
                {
                    "source_site": "lever",
                    "label": "Design roles",
                    "start_url": "https://jobs.lever.co/exampleco",
                    "exclude_keywords": ["senior"],
                    "location_hints": ["Remote"],
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("JOB_AGENT_DISCOVERY_QUERIES_FILE", str(config_path))
    monkeypatch.delenv("JOB_AGENT_DISCOVERY_QUERIES", raising=False)

    settings = load_settings()

    assert settings.discovery_queries is not None
    assert len(settings.discovery_queries) == 1
    assert settings.discovery_queries[0].source_site == "lever"
    assert settings.discovery_queries[0].location_hints == ["Remote"]


def test_invalid_discovery_query_fails_clearly(monkeypatch) -> None:
    monkeypatch.setenv(
        "JOB_AGENT_DISCOVERY_QUERIES",
        json.dumps(
            [
                {
                    "source_site": "bad site!",
                    "label": "Broken config",
                    "start_url": "not-a-url",
                }
            ]
        ),
    )
    monkeypatch.delenv("JOB_AGENT_DISCOVERY_QUERIES_FILE", raising=False)

    with pytest.raises(ValueError) as exc_info:
        load_discovery_queries()

    assert "Invalid discovery query config" in str(exc_info.value)
    assert "source_site" in str(exc_info.value) or "start_url" in str(exc_info.value)


def test_missing_query_file_fails_clearly(monkeypatch, tmp_path) -> None:
    missing_path = tmp_path / "missing.json"
    monkeypatch.setenv("JOB_AGENT_DISCOVERY_QUERIES_FILE", str(missing_path))
    monkeypatch.delenv("JOB_AGENT_DISCOVERY_QUERIES", raising=False)

    with pytest.raises(ValueError) as exc_info:
        load_discovery_queries()

    assert "does not exist" in str(exc_info.value)


def test_load_board_registry_from_json_file(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "boards.json"
    config_path.write_text(
        json.dumps(
            [
                {
                    "company_name": "Example Co",
                    "source_site": "greenhouse",
                    "board_url": "https://boards.greenhouse.io/exampleco",
                    "tags": ["python", "backend"],
                    "location_hints": ["Canada"],
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("JOB_AGENT_BOARD_REGISTRY_FILE", str(config_path))
    monkeypatch.delenv("JOB_AGENT_BOARD_REGISTRY", raising=False)

    registry = load_board_registry()

    assert len(registry) == 1
    assert registry[0].company_name == "Example Co"
    assert registry[0].source_site == "greenhouse"
    assert str(registry[0].board_url) == "https://boards.greenhouse.io/exampleco"


def test_load_board_registry_from_yaml_file(tmp_path, monkeypatch) -> None:
    pytest.importorskip("yaml")
    config_path = tmp_path / "boards.yaml"
    config_path.write_text(
        """
- company_name: Example Co
  source_site: lever
  board_url: https://jobs.lever.co/exampleco
  tags:
    - design
  location_hints:
    - Remote
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("JOB_AGENT_BOARD_REGISTRY_FILE", str(config_path))
    monkeypatch.delenv("JOB_AGENT_BOARD_REGISTRY", raising=False)

    registry = load_board_registry()

    assert len(registry) == 1
    assert registry[0].source_site == "lever"
    assert registry[0].location_hints == ["Remote"]


def test_load_settings_reads_authenticated_browser_config(tmp_path, monkeypatch) -> None:
    profile_dir = tmp_path / "auth-profile"
    registry_path = tmp_path / "boards.json"
    registry_path.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("JOB_AGENT_BROWSER_AUTH_MODE", "profile")
    monkeypatch.setenv("JOB_AGENT_BROWSER_AUTH_PROFILE_DIR", str(profile_dir))
    monkeypatch.setenv("JOB_AGENT_BOARD_REGISTRY_FILE", str(registry_path))
    monkeypatch.delenv("JOB_AGENT_BROWSER_AUTH_CDP_URL", raising=False)

    settings = load_settings()

    assert settings.browser_auth_mode == "profile"
    assert settings.browser_auth_profile_dir == profile_dir
    assert settings.browser_auth_cdp_url is None
    assert settings.board_registry_file == registry_path


def test_invalid_authenticated_browser_mode_fails_clearly(monkeypatch) -> None:
    monkeypatch.setenv("JOB_AGENT_BROWSER_AUTH_MODE", "cookies")

    with pytest.raises(ValueError) as exc_info:
        load_browser_auth_mode()

    assert "must be one of: profile, attach" in str(exc_info.value)
