from __future__ import annotations

from datetime import UTC, datetime

from job_agent.storage.db import init_db
from job_agent.storage.jobs_repo import JobsRepository


def test_save_search_prompt_persists_and_updates_timestamps(tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "saved_searches.db"))
    created_at = datetime(2026, 4, 11, 10, 0, tzinfo=UTC)
    updated_at = datetime(2026, 4, 11, 11, 0, tzinfo=UTC)

    first = repo.save_search_prompt(
        name="backend-canada",
        raw_prompt_text="Find backend jobs in Canada",
        now=created_at,
    )
    second = repo.save_search_prompt(
        name="backend-canada",
        raw_prompt_text="Find senior backend jobs in Canada",
        now=updated_at,
    )

    assert first.name == "backend-canada"
    assert first.raw_prompt_text == "Find backend jobs in Canada"
    assert first.created_at == created_at
    assert first.updated_at == created_at
    assert second.raw_prompt_text == "Find senior backend jobs in Canada"
    assert second.created_at == created_at
    assert second.updated_at == updated_at


def test_get_saved_search_returns_none_for_missing_name(tmp_path) -> None:
    repo = JobsRepository(init_db(tmp_path / "saved_searches.db"))

    assert repo.get_saved_search(name="missing") is None
