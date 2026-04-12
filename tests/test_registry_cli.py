from __future__ import annotations

import json

from job_agent.config import Settings
from job_agent.core.board_registry import load_board_registry_payload
from job_agent.core.models import SearchIntent
from job_agent.core.plan_compiler import compile_search_intent
from job_agent.main import main


def _settings(*, registry_file):
    return Settings(board_registry_file=registry_file, board_registry=[])


def test_registry_add_list_and_remove_round_trip(monkeypatch, tmp_path, capsys) -> None:
    registry_file = tmp_path / "boards.json"
    monkeypatch.setattr("job_agent.main.load_settings", lambda: _settings(registry_file=registry_file))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)

    add_exit = main(
        [
            "registry",
            "add",
            "--company",
            "Stripe",
            "--source-site",
            "greenhouse",
            "--board-url",
            "https://boards.greenhouse.io/stripe",
            "--tag",
            "fintech",
            "--location-hint",
            "Canada",
        ]
    )
    add_output = capsys.readouterr().out

    list_exit = main(["registry", "list"])
    list_output = capsys.readouterr().out

    remove_exit = main(
        [
            "registry",
            "remove",
            "--company",
            "Stripe",
            "--source-site",
            "greenhouse",
        ]
    )
    remove_output = capsys.readouterr().out

    assert add_exit == 0
    assert list_exit == 0
    assert remove_exit == 0
    assert "Added registry entry for Stripe on greenhouse." in add_output
    assert "Stripe | greenhouse | https://boards.greenhouse.io/stripe" in list_output
    assert "Removed registry entry for Stripe on greenhouse." in remove_output
    assert json.loads(registry_file.read_text(encoding="utf-8")) == []


def test_registry_validate_catches_duplicates(monkeypatch, tmp_path, capsys) -> None:
    registry_file = tmp_path / "boards.json"
    registry_file.write_text(
        json.dumps(
            [
                {
                    "company_name": "Stripe",
                    "source_site": "greenhouse",
                    "board_url": "https://boards.greenhouse.io/stripe",
                },
                {
                    "company_name": "stripe",
                    "source_site": "greenhouse",
                    "board_url": "https://boards.greenhouse.io/stripe-two",
                },
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("job_agent.main.load_settings", lambda: _settings(registry_file=registry_file))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)

    exit_code = main(["registry", "validate"])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Registry validation failed:" in output
    assert "duplicate company/source entry" in output


def test_registry_import_and_export_json(monkeypatch, tmp_path, capsys) -> None:
    registry_file = tmp_path / "boards.json"
    import_file = tmp_path / "import.json"
    export_file = tmp_path / "export.json"
    import_file.write_text(
        json.dumps(
            [
                {
                    "company_name": "WHOOP",
                    "source_site": "lever",
                    "board_url": "https://jobs.lever.co/whoop",
                    "tags": ["healthtech"],
                    "location_hints": ["Remote"],
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("job_agent.main.load_settings", lambda: _settings(registry_file=registry_file))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)

    import_exit = main(["registry", "import", "--input", str(import_file)])
    import_output = capsys.readouterr().out
    export_exit = main(["registry", "export", "--output", str(export_file)])
    export_output = capsys.readouterr().out

    exported = json.loads(export_file.read_text(encoding="utf-8"))
    assert import_exit == 0
    assert export_exit == 0
    assert "Imported 1 registry entries into" in import_output
    assert "Exported 1 registry entries to" in export_output
    assert exported[0]["company_name"] == "WHOOP"
    assert exported[0]["source_site"] == "lever"


def test_registry_add_rejects_invalid_source_site(monkeypatch, tmp_path, capsys) -> None:
    registry_file = tmp_path / "boards.json"
    monkeypatch.setattr("job_agent.main.load_settings", lambda: _settings(registry_file=registry_file))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)

    exit_code = main(
        [
            "registry",
            "add",
            "--company",
            "Stripe",
            "--source-site",
            "indeed",
            "--board-url",
            "https://www.indeed.com/jobs",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "source_site must be one of: greenhouse, lever, linkedin" in output


def test_registry_add_enables_planning_with_valid_entries(monkeypatch, tmp_path, capsys) -> None:
    registry_file = tmp_path / "boards.json"
    monkeypatch.setattr("job_agent.main.load_settings", lambda: _settings(registry_file=registry_file))
    monkeypatch.setattr("job_agent.main.configure_logging", lambda level: None)

    exit_code = main(
        [
            "registry",
            "add",
            "--company",
            "Stripe",
            "--source-site",
            "greenhouse",
            "--board-url",
            "https://boards.greenhouse.io/stripe",
            "--tag",
            "backend",
            "--location-hint",
            "Canada",
        ]
    )
    capsys.readouterr()

    registry_entries = load_board_registry_payload(json.loads(registry_file.read_text(encoding="utf-8")))
    plan = compile_search_intent(
        SearchIntent(
            prompt_text="Find backend jobs at Stripe in Canada",
            constraints={
                "include_companies": ["Stripe"],
                "include_keywords": ["backend"],
                "location_constraints": ["Canada"],
                "source_site_preferences": ["greenhouse"],
            },
        ),
        board_registry=registry_entries,
    )

    assert exit_code == 0
    assert len(plan.queries) == 1
    assert str(plan.queries[0].board_url) == "https://boards.greenhouse.io/stripe"
