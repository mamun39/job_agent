# job-agent

Local-first job discovery tool for collecting and reviewing job postings from supported job boards.

Current scope:
- Config-driven discovery queries
- Playwright-backed listing page fetches
- Greenhouse and Lever listing adapters
- SQLite storage with deterministic deduplication
- Plain CLI review and CSV export workflows

Not included yet:
- Login automation
- Multi-page crawling or pagination
- Detail-page parsing
- Web dashboard
- Application submission logic

## Quick start

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -e .[dev]
python -m playwright install chromium
job-agent --help
```

## Discovery config

Configure discovery queries with `JOB_AGENT_DISCOVERY_QUERIES` or `JOB_AGENT_DISCOVERY_QUERIES_FILE`.

Example JSON:

```json
[
  {
    "source_site": "greenhouse",
    "label": "Example engineering",
    "start_url": "https://boards.greenhouse.io/exampleco"
  },
  {
    "source_site": "lever",
    "label": "Example design",
    "start_url": "https://jobs.lever.co/exampleco"
  }
]
```

## Commands

```bash
job-agent discover
job-agent discover --screenshot
job-agent review list
job-agent review list --source-site greenhouse --min-score 50 --reviewed reviewed
job-agent review show --url https://example.com/jobs/123
job-agent review export --output ./exports/jobs.csv
```

## Notes

Copy `.env.example` to `.env` for local defaults. For current limitations and deferred work, see `docs/codex_tasks/limitations.md`.
