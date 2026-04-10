from __future__ import annotations

import subprocess
import sys


def test_package_importable() -> None:
    import job_agent

    assert job_agent is not None


def test_cli_starts() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "job_agent.main", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Local job-search automation tool bootstrap." in result.stdout
