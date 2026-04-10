from __future__ import annotations

import json

import pytest

from job_agent.config import load_discovery_queries, load_settings


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
