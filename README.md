# job-agent

`job-agent` is a local-first CLI for discovering job listings, storing normalized postings in SQLite, and reviewing them from the terminal.

## What it does

- Loads discovery queries from env or a local config file
- Fetches listing pages with Playwright Chromium
- Parses and stores normalized job postings
- Supports conservative listing-page pagination for Greenhouse and Lever
- Optionally enriches Greenhouse and Lever jobs from detail pages
- Deduplicates by source identity, canonical URL, and exact fallback fields
- Lists stored jobs, shows job details, exports CSV, and opens stored URLs in your default browser
- Persists review decisions and notes in storage
- Recalculates stored scores from current scoring rules
- Tracks local job lifecycle state as `active`, `stale`, or `archived`
- Runs a minimal local dashboard for browser-based job review
- Emits local discovery telemetry and can optionally capture debug artifacts on failures
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
- Application submission
- Authentication or hardened multi-user web dashboard
- Remote LLM provider integration for summaries
- Generic cross-site pagination or site navigation flows beyond the current Greenhouse and Lever support

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
- `JOB_AGENT_MAX_PAGES_PER_QUERY`
- `JOB_AGENT_DEBUG_ARTIFACTS_ON_FAILURE`
- `JOB_AGENT_DEBUG_ARTIFACTS_DIR`
- `JOB_AGENT_ENRICH_GREENHOUSE_DETAILS`
- `JOB_AGENT_ENRICH_LEVER_DETAILS`
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
job-agent discover --greenhouse-details
job-agent discover --lever-details

job-agent review list
job-agent review list --source-site greenhouse --min-score 50 --reviewed reviewed --decision saved --job-status active
job-agent review show --id 1
job-agent review show --url https://example.com/jobs/123
job-agent review decision --id 1
job-agent review set-decision --id 1 --decision saved --note "Strong fit"
job-agent review rescore --source-site lever --reviewed unreviewed
job-agent review mark-stale --days 14
job-agent review cleanup
job-agent review export --output ./exports/jobs.csv

job-agent open --id 1
job-agent open --url https://example.com/jobs/123

job-agent dashboard
job-agent dashboard --host 127.0.0.1 --port 8001
```

## Typical workflow

1. Configure one or more discovery queries.
2. Run `job-agent discover` to fetch and store listings.
3. Review the per-query summary line for pages fetched, failures, parsed jobs, inserts, updates, duplicates, and detail-enrichment outcomes.
4. Run `job-agent review list` to inspect stored jobs, including review decision and lifecycle status.
5. Run `job-agent review show --id ...` or `--url ...` for full details.
6. Run `job-agent review set-decision --id ... --decision ...` to triage a job.
7. Run `job-agent review rescore` after changing deterministic scoring rules.
8. Run `job-agent review mark-stale --days ...` as local maintenance to age old jobs into `stale`.
9. Run `job-agent review cleanup` to remove orphaned stored review decisions after manual database cleanup or imports.
10. Run `job-agent open --id ...` to open a posting in your browser for manual review.
11. Run `job-agent dashboard` to review jobs in a minimal local browser UI.
12. Run `job-agent review export --output ...` to export filtered jobs to CSV.

## Discovery behavior

- Each configured query starts from one listing-page URL.
- Greenhouse and Lever can walk multiple listing pages when a standard next-page link is exposed.
- Pagination is capped by `JOB_AGENT_MAX_PAGES_PER_QUERY`.
- Greenhouse and Lever detail enrichment is optional and runs only after listing-page discovery.
- Discovery summaries are intentionally concise and include query/page/job counters.
- When `JOB_AGENT_DEBUG_ARTIFACTS_ON_FAILURE=true`, fetch or parse failures can save local screenshot and HTML artifacts under `JOB_AGENT_DEBUG_ARTIFACTS_DIR`.

Example:

```bash
job-agent discover --greenhouse-details --lever-details
```

Typical output:

```text
[ok] Example engineering (greenhouse) queries=1 pages=2 failed_pages=0 jobs=14 inserted=8 updated=4 duplicates=2 detail_pages=8 detail_failures=1
[summary] queries=1 pages=2 failed_pages=0 jobs=14 inserted=8 updated=4 duplicates=2 detail_pages=8 detail_failures=1
```

## Review workflow

- `job-agent review list` supports filtering by `--source-site`, `--min-score`, `--reviewed`, `--decision`, and `--job-status`.
- `job-agent review show` and `job-agent review decision` can target a stored job by `--id` or exact `--url`.
- `job-agent review cleanup` removes orphaned `review_decisions` rows whose URLs no longer exist in `jobs`.
- Supported explicit review decisions are:
  - `saved`
  - `skipped`
  - `applied_elsewhere`
  - `needs_manual_review`
- Stored jobs also carry a local lifecycle status:
  - `active`
  - `stale`
  - `archived`

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
- The dashboard is a simple local FastAPI app with server-rendered pages for list, detail, and review-decision updates.
- The dashboard is intended for localhost use and does not implement authentication, CSRF protection, pagination, or richer multi-user web features.
- Stale detection is local and timestamp-based. It does not confirm whether a posting was actually removed from the source site.
- Review decisions store only the latest explicit state for a posting URL, and orphan cleanup is manual via `job-agent review cleanup`.
- The optional summarizer layer is presentation-only today: it returns short explanatory text from job data plus rule explanations and does not modify stored job records.
- Model-backed summarizers are not implemented; the default behavior is a local fallback summarizer with no remote dependency.

For current project limitations and deferred work, see [docs/codex_tasks/limitations.md](docs/codex_tasks/limitations.md).
