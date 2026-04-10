# job-agent

`job-agent` is a local-first CLI for discovering job listings, storing normalized postings in SQLite, and reviewing them from the terminal.

## What it does

- Loads discovery queries from env or a local config file
- Fetches listing pages with Playwright Chromium
- Parses and stores normalized job postings
- Deduplicates by source identity, canonical URL, and exact fallback fields
- Lists stored jobs, shows job details, exports CSV, and opens stored URLs in your default browser
- Persists review decisions in storage
- Runs a minimal local dashboard for browser-based job review
- Provides an optional read-only summarizer interface for short job-match explanations, with a local fallback summarizer and no required external model service

## Current support

Live configured discovery:
- `greenhouse`
- `lever`

Parser support from saved HTML fixtures:
- `indeed`
- `linkedin`

Still not implemented:
- Login automation
- Pagination or multi-page crawling
- Detail-page parsing
- Application submission
- Authentication or hardened multi-user web dashboard
- Remote LLM provider integration for summaries

## Quick start

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -e .[dev]
python -m playwright install chromium
job-agent --help
```

On Windows PowerShell, activate the venv with:

```powershell
. .venv\Scripts\Activate.ps1
```

## Configuration

`job-agent` reads a local `.env` file if present.

Important environment variables:
- `JOB_AGENT_ENV`
- `JOB_AGENT_LOG_LEVEL`
- `JOB_AGENT_DATA_DIR`
- `JOB_AGENT_DB_PATH`
- `JOB_AGENT_BROWSER_USER_DATA_DIR`
- `JOB_AGENT_BROWSER_SCREENSHOT_DIR`
- `JOB_AGENT_BROWSER_HEADLESS`
- `JOB_AGENT_DISCOVERY_QUERIES`
- `JOB_AGENT_DISCOVERY_QUERIES_FILE`

Copy `.env.example` to `.env` and add the values you need.

## Discovery query config

Configure discovery queries with `JOB_AGENT_DISCOVERY_QUERIES` or `JOB_AGENT_DISCOVERY_QUERIES_FILE`.

Example JSON:

```json
[
  {
    "source_site": "greenhouse",
    "label": "Example engineering",
    "start_url": "https://boards.greenhouse.io/exampleco",
    "include_keywords": ["python", "backend"],
    "exclude_keywords": ["staff"],
    "location_hints": ["Canada", "Remote"]
  },
  {
    "source_site": "lever",
    "label": "Example design",
    "start_url": "https://jobs.lever.co/exampleco"
  }
]
```

You can point at a file instead:

```powershell
$env:JOB_AGENT_DISCOVERY_QUERIES_FILE="C:\path\to\queries.json"
```

## Main commands

```bash
job-agent discover
job-agent discover --screenshot

job-agent review list
job-agent review list --source-site greenhouse --min-score 50 --reviewed reviewed
job-agent review show --url https://example.com/jobs/123
job-agent review export --output ./exports/jobs.csv

job-agent open --id 1
job-agent open --url https://example.com/jobs/123

job-agent dashboard
job-agent dashboard --host 127.0.0.1 --port 8001
```

## Typical workflow

1. Configure one or more discovery queries.
2. Run `job-agent discover` to fetch and store listings.
3. Run `job-agent review list` to inspect stored jobs.
4. Run `job-agent review show --url ...` for full details.
5. Run `job-agent open --id ...` to open a posting in your browser for manual review.
6. Run `job-agent dashboard` to review jobs in a minimal local browser UI.
7. Run `job-agent review export --output ...` to export filtered jobs to CSV.

## Storage

The local database defaults to:

```text
./data/job_agent.db
```

Browser profile and screenshots default under:

```text
./data/browser
./data/screenshots
```

These paths are created automatically when needed.

## Notes

- Discovery currently supports live runs only for `greenhouse` and `lever`.
- Indeed and LinkedIn adapters currently exist for saved fixture parsing, not for configured live discovery.
- YAML query files require `PyYAML`; JSON works out of the box.
- Review decision persistence exists in storage, but dedicated CLI commands for updating/viewing those decisions are not fully wired yet.
- The dashboard is a simple local FastAPI app with server-rendered pages for list, detail, and review-decision updates.
- The dashboard is intended for localhost use and does not implement authentication, CSRF protection, pagination, or richer multi-user web features.
- The optional summarizer layer is presentation-only today: it returns short explanatory text from job data plus rule explanations and does not modify stored job records.
- Model-backed summarizers are not implemented; the default behavior is a local fallback summarizer with no remote dependency.

For current project limitations and deferred work, see [docs/codex_tasks/limitations.md](C:/Users/MRAka/PycharmProjects/job_agent/docs/codex_tasks/limitations.md).
