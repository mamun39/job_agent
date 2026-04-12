# job-agent

Local-first, prompt-driven job search and review for supported company job boards.

`job-agent` is a Python CLI with a small local dashboard. It combines deterministic prompt parsing, registry-backed planning, Playwright-based discovery, SQLite storage, hard filtering, configurable scoring, and local review workflows. It is designed to stay honest about what is executable now and what still depends on future work.

## Why I built this

Two gaps motivated this project:

1. Hosted assistants generally do not operate through a user's local authenticated browser session, which makes them a poor fit for some job-search workflows that depend on local browser state or local login context.
2. Many open-source alternatives stop at extraction. They scrape listings, but do not combine prompt-driven search, browser-assisted discovery, deterministic filtering, persistent storage, and review workflows in one local tool.

`job-agent` is an attempt to cover that middle ground without pretending to be a general autonomous web agent. The implementation is local-first, conservative, and intentionally narrower than the broader design target.

## Core features

- Local CLI for discovery, prompt-driven search, registry maintenance, review, export, cleanup, rescoring, and stale-job maintenance
- Minimal localhost dashboard for browsing stored jobs, sorting/paginating results, and updating review decisions
- Prompt-driven search pipeline built around explicit `SearchIntent` and `SearchPlan` models
- Local board registry for resolving prompt-driven company searches into known executable Greenhouse, Lever, and explicit LinkedIn Jobs query URLs
- Live listing discovery for Greenhouse, Lever, and authenticated LinkedIn Jobs queries
- Parser-only support for Indeed from saved HTML fixtures
- Playwright-based page fetching with optional authenticated local Chromium reuse
- Optional Greenhouse and Lever detail-page enrichment, including selective two-stage enrichment
- Deterministic deduplication with source-specific URL canonicalization for supported live sources
- Hard-filter pass/reject decisions with explicit rejection reasons
- Rule-based scoring with configurable local rule sets and deterministic explanations
- Review decisions with notes plus lightweight local review-history auditability
- CSV export for stored jobs and prompt-search matches
- Local saved searches by name
- Optional debug artifacts on discovery failures: screenshot plus raw HTML
- Optional summarizer interface with a local fallback summarizer

## How it works

The prompt-driven path is:

1. Parse a raw prompt into a structured `SearchIntent`.
2. Compile that intent into a supported `SearchPlan`.
3. Resolve executable board URLs from a local board registry.
4. Fetch listing pages with Playwright.
5. Parse, normalize, deduplicate, and store jobs.
6. Apply deterministic hard filters.
7. Score surviving matches with the current rule-based scoring logic.
8. Review, export, or persist the results.

For non-prompt discovery, the system can also run directly from configured `DiscoveryQuery` start URLs.

## Current capabilities

### Implemented now

- Live configured discovery for:
  - `greenhouse`
  - `lever`
  - `linkedin` via an authenticated local Chromium browser session and an explicit LinkedIn Jobs search/query URL
- Conservative listing-page pagination for Greenhouse and Lever
- Optional Greenhouse and Lever detail enrichment, including selective second-stage detail fetches for promising listings
- Prompt-driven search from:
  - inline prompt text
  - prompt file
  - saved prompt name
- Local board registry loading and maintenance from JSON, plus YAML loading when `PyYAML` is installed
- Authenticated local Chromium reuse for read-only discovery/search via:
  - persistent profile reuse
  - CDP attach to an already-running Chromium browser
- Hard filters for explicit constraints such as:
  - excluded keywords
  - company exclusions
  - source-site restrictions
  - location constraints
  - explicit remote, hybrid, or onsite requirements
  - freshness windows when job age is known
- Persistent review workflow:
  - list jobs
  - inspect details
  - set decision and note
  - filter by decision and lifecycle status
  - rescore stored jobs with active scoring rules
  - mark stale jobs
  - clean orphaned review records
- Local review audit trail via append-only review decision history
- Prompt-search match and review export to CSV
- Local debug artifact capture on fetch or parse failures when enabled
- Local real-browser smoke tests for core browser launch/fetch/screenshot behavior

### Partial or limited

- Indeed parsing exists only for saved HTML fixtures, not live configured discovery
- LinkedIn live support is intentionally narrow: authenticated read-only jobs search and detail reads only
- Prompt-driven search is read-only by default; matched jobs only appear in the main database and dashboard when `--store-matches` is used
- Prompt parsing is still conservative and rule-based
- The dashboard is intentionally minimal and localhost-oriented
- The summarizer layer exists as an interface plus local fallback, not as a required external model integration

## Current limitations

- Live source coverage is narrow. Greenhouse, Lever, and authenticated LinkedIn Jobs are the only supported live discovery sources.
- Prompt parsing remains rule-based and phrasing-sensitive rather than semantic.
- Prompt-driven execution depends on local board registry coverage. If a company board is not registered, the planner will not invent a board URL.
- The project does not implement login automation, application submission, Easy Apply automation, or generic authenticated-board support.
- The dashboard is a lightweight local review surface, not a hardened web application.
- Storage is intentionally lightweight and SQLite-based, with ad hoc schema upgrades instead of a full migration framework.
- Scoring is deterministic and rule-based. It is not semantic matching.
- Saved searches are local records only. There is no scheduler, background execution, remote sync, or multi-user management.

For the maintained limitation list, see [docs/codex_tasks/limitations.md](docs/codex_tasks/limitations.md).

## Installation

Requirements:

- Python 3.11+
- Playwright Chromium installed locally

Install in a virtual environment:

```bash
python -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
. .venv\Scripts\Activate.ps1
```

Install the project and dev dependencies:

```bash
pip install -e .[dev]
python -m playwright install chromium
```

Check the CLI:

```bash
job-agent --help
```

## Quick start

1. Copy `.env.example` to `.env`.
2. Add either:
   - configured discovery queries, or
   - a local board registry for prompt-driven search.
3. Run a discovery pass or a prompt-driven search.
4. Review stored jobs from the CLI or the local dashboard.

Example direct discovery run:

```bash
job-agent discover
```

Example prompt-driven run:

```bash
job-agent search "Find backend security roles at Stripe in Canada"
```

Example local dashboard:

```bash
job-agent dashboard
```

## Configuration

`job-agent` loads a simple local `.env` file when present. It only supports basic `KEY=VALUE` lines.

Common settings:

- `JOB_AGENT_ENV`
- `JOB_AGENT_LOG_LEVEL`
- `JOB_AGENT_DATA_DIR`
- `JOB_AGENT_DB_PATH`
- `JOB_AGENT_BROWSER_USER_DATA_DIR`
- `JOB_AGENT_BROWSER_SCREENSHOT_DIR`
- `JOB_AGENT_BROWSER_HEADLESS`
- `JOB_AGENT_BROWSER_AUTH_MODE`
- `JOB_AGENT_BROWSER_AUTH_PROFILE_DIR`
- `JOB_AGENT_BROWSER_AUTH_CDP_URL`
- `JOB_AGENT_MAX_PAGES_PER_QUERY`
- `JOB_AGENT_DEBUG_ARTIFACTS_ON_FAILURE`
- `JOB_AGENT_DEBUG_ARTIFACTS_DIR`
- `JOB_AGENT_ENRICH_GREENHOUSE_DETAILS`
- `JOB_AGENT_ENRICH_LEVER_DETAILS`
- `JOB_AGENT_SELECTIVE_DETAIL_ENRICHMENT`
- `JOB_AGENT_MIN_LISTING_SCORE_FOR_DETAIL_ENRICHMENT`
- `JOB_AGENT_DISCOVERY_QUERIES`
- `JOB_AGENT_DISCOVERY_QUERIES_FILE`
- `JOB_AGENT_BOARD_REGISTRY`
- `JOB_AGENT_BOARD_REGISTRY_FILE`
- `JOB_AGENT_SCORING_RULES`
- `JOB_AGENT_SCORING_RULES_FILE`

Notes:

- Discovery queries, board registries, and scoring rules can be loaded from JSON directly.
- YAML files are also supported for file-backed config when `PyYAML` is installed.
- The local browser profile, screenshots, database, and debug artifacts default under `./data`.

## Authenticated local browser mode

Read-only browser reuse is optional and explicit.

Supported modes:

- `profile`: launch Chromium with an existing local profile directory or named subprofile such as `Profile 1` or `Default`
- `attach`: connect to an already-running Chromium browser over CDP

Operational guidance:

- For LinkedIn, `attach` mode is currently the more reliable path.
- `profile` mode can work for local Chromium profile reuse, but real default Chrome user-data directories and copied encrypted profiles can still be fragile on Windows.
- If you use `attach`, start a separate debug-enabled Chrome or Edge instance and log into LinkedIn manually in that browser before running `job-agent`.

Examples:

```bash
job-agent discover --auth-browser profile --auth-browser-profile-dir /path/to/profile
job-agent discover --auth-browser profile --auth-browser-profile-dir "/path/to/Chrome/User Data/Profile 1"
job-agent discover --auth-browser attach --auth-browser-cdp-url http://127.0.0.1:9222
job-agent search "Find security roles at LinkedIn in Canada on LinkedIn" --auth-browser attach --auth-browser-cdp-url http://127.0.0.1:9222
```

Typical LinkedIn attach flow:

```bash
chrome --remote-debugging-port=9222 --user-data-dir="/path/to/Chrome/User Data"
job-agent search "Find security roles at LinkedIn in Canada on LinkedIn" --auth-browser attach --auth-browser-cdp-url http://127.0.0.1:9222
```

This mode is intended for local authenticated browsing context reuse only. It does not store credentials, automate login, or submit forms.

## Board registry

Prompt-driven search can only run against boards the project can resolve honestly. The board registry is the local configuration that maps companies to supported board URLs.

Each entry can include:

- company name
- source site
- board URL
- optional tags or sectors
- optional location hints

Example JSON:

```json
[
  {
    "company_name": "Stripe",
    "source_site": "greenhouse",
    "board_url": "https://boards.greenhouse.io/stripe",
    "tags": ["fintech", "payments"],
    "location_hints": ["Canada", "Remote"]
  },
  {
    "company_name": "WHOOP",
    "source_site": "lever",
    "board_url": "https://jobs.lever.co/whoop",
    "tags": ["healthtech"]
  },
  {
    "company_name": "LinkedIn",
    "source_site": "linkedin",
    "board_url": "https://www.linkedin.com/jobs/search/?keywords=security&f_C=1337",
    "tags": ["security"],
    "location_hints": ["Canada", "Remote"]
  }
]
```

Set it via environment:

```bash
export JOB_AGENT_BOARD_REGISTRY_FILE=./board_registry.json
```

Or on Windows PowerShell:

```powershell
$env:JOB_AGENT_BOARD_REGISTRY_FILE = ".\board_registry.json"
```

Registry maintenance is available from the CLI:

```bash
job-agent registry list --registry-file ./board_registry.json
job-agent registry validate --registry-file ./board_registry.json
job-agent registry add --registry-file ./board_registry.json --company Stripe --source-site greenhouse --board-url https://boards.greenhouse.io/stripe
job-agent registry remove --registry-file ./board_registry.json --company Stripe --source-site greenhouse
job-agent registry export --registry-file ./board_registry.json --output ./registry_export.json
```

Registry selection is deterministic. The compiler prefers explicit company mentions from the prompt, then narrows by supported source-site preferences and simple tag/location hints when available. It does not invent missing company boards.

## Prompt-driven search

The prompt-search flow is synchronous and local:

1. Parse the raw prompt into `SearchIntent`.
2. Compile the intent into a supported `SearchPlan`.
3. Resolve matching boards from the local registry.
4. Run discovery against those board URLs.
5. Apply hard filters.
6. Return matched and rejected jobs with concise explanations.

Examples:

```bash
job-agent search "Find AI security roles in Canada"
job-agent search "Find backend jobs at Stripe in Canada" --show-rejected
job-agent search --prompt-file ./prompt.txt
job-agent search --saved-search stripe-canada
job-agent search "Find backend jobs at Stripe in Canada" --save-search stripe-canada
job-agent search "Find backend jobs at Stripe in Canada" --export ./exports/matches.csv
job-agent search "Find backend jobs at Stripe in Canada" --store-matches
```

What the search summary reports:

- parsed intent highlights
- boards queried
- jobs discovered
- jobs matched after hard filters
- jobs rejected

`--show-rejected` prints rejected jobs plus stable rejection reasons. `--store-matches` persists newly matched jobs into the main database if they are not already stored.

Important:

- `job-agent search` is read-only by default.
- If you want matched jobs to appear in `review` commands or the dashboard, run the search with `--store-matches`.

## Scoring rules

Scoring is configurable through local rule sets instead of Python edits.

Supported rule categories include:

- include keywords
- exclude keywords
- preferred companies
- discouraged companies
- preferred locations
- preferred seniority levels
- preferred remote statuses
- preferred employment types

Example JSON:

```json
{
  "include_keywords": ["backend", "platform", "python", "security"],
  "exclude_keywords": ["sales", "recruiter"],
  "preferred_companies": ["Stripe", "Grafana Labs"],
  "preferred_locations": ["Canada", "Remote"],
  "preferred_remote_statuses": ["remote", "hybrid"],
  "preferred_seniority_levels": ["senior", "staff", "principal"]
}
```

Apply via config:

```bash
export JOB_AGENT_SCORING_RULES_FILE=./scoring_rules.json
job-agent review rescore
```

## Main commands

### Discovery

```bash
job-agent discover
job-agent discover --screenshot
job-agent discover --greenhouse-details
job-agent discover --lever-details
job-agent discover --selective-details --min-detail-candidate-score 2
```

### Prompt-driven search

```bash
job-agent search "Find AI security roles in Canada"
job-agent search --prompt-file ./prompt.txt
job-agent search --saved-search my-search
job-agent search "Find backend jobs at Stripe" --show-rejected --export ./matches.csv
```

### Registry maintenance

```bash
job-agent registry list
job-agent registry validate
job-agent registry import --registry-file ./board_registry.json --input ./seed_registry.json
job-agent registry export --registry-file ./board_registry.json --output ./registry_export.json
```

### Review and maintenance

```bash
job-agent review list
job-agent review list --source-site greenhouse --reviewed unreviewed --decision saved --job-status active
job-agent review show --id 1
job-agent review decision --url https://example.com/jobs/123
job-agent review set-decision --id 1 --decision saved --note "Strong fit"
job-agent review export --output ./exports/jobs.csv
job-agent review rescore
job-agent review mark-stale --days 14
job-agent review cleanup
```

### Open and dashboard

```bash
job-agent open --id 1
job-agent dashboard
job-agent dashboard --host 127.0.0.1 --port 8001
```

## Typical workflows

### 1. Direct board discovery

1. Configure `JOB_AGENT_DISCOVERY_QUERIES` or `JOB_AGENT_DISCOVERY_QUERIES_FILE`.
2. Run `job-agent discover`.
3. Review the summary lines for fetched pages, failures, inserts, updates, duplicates, and detail-enrichment outcomes.
4. Inspect stored jobs with `job-agent review list` and `job-agent review show`.

### 2. Prompt-driven search

1. Configure a local board registry.
2. Run `job-agent search "..."`.
3. Inspect matches and optional rejected jobs.
4. Export matches to CSV or persist them with `--store-matches`.
5. Open the dashboard or `review list` only after persisting matches if you want them in the main database.

### 3. Ongoing local review

1. Run `job-agent review list` with filters.
2. Set review decisions and notes.
3. Run `job-agent review rescore` after scoring-rule changes.
4. Run `job-agent review mark-stale --days N` periodically.
5. Run `job-agent review cleanup` if you have removed jobs and want orphaned review state cleaned up.

## Architecture

At a high level:

- `src/job_agent/main.py`: CLI entrypoint
- `src/job_agent/config.py`: `.env`, discovery query, registry, and scoring-rule loading
- `src/job_agent/core/`: shared models, parser, plan compiler, board registry selection, hard filters, scoring, dedupe
- `src/job_agent/browser/`: Playwright session and fetch helpers
- `src/job_agent/sites/`: site-local parsers for supported boards
- `src/job_agent/flows/discover.py`: configured discovery pipeline
- `src/job_agent/flows/prompt_search.py`: prompt-driven orchestration pipeline
- `src/job_agent/storage/`: SQLite schema and repository logic
- `src/job_agent/ui/`: CLI renderers and minimal local dashboard

Design choices:

- local-first over hosted orchestration
- deterministic rules over hidden heuristics
- site-local adapter behavior over generic scraping frameworks
- explicit stored state over transient CLI-only results

## Storage and matching model

Storage is SQLite-backed and local by default.

The main persisted records are:

- `jobs`: normalized job postings plus metadata
- `review_decisions`: latest explicit review decision per posting URL
- `review_decision_history`: append-only local audit trail for review writes
- `saved_searches`: named raw prompt records

Job records can carry:

- source identity and canonicalized URL
- normalized title, company, location, and description fields
- score and score explanations
- lifecycle status: `active`, `stale`, `archived`
- discovery and last-seen timestamps

Matching model:

- discovery deduplication is deterministic
- prompt-driven search applies hard filters first
- surviving matches are scored second
- review decisions are separate from scoring

## Troubleshooting

### `job-agent discover` finds nothing

- Check that discovery queries or board registry entries are configured correctly.
- Confirm the board URL is a supported Greenhouse or Lever listing page, or an explicit LinkedIn Jobs search/query URL.
- If pagination or detail enrichment was expected, verify the source actually exposes those pages in standard markup.

### Prompt-driven search says it cannot resolve executable boards

- Add the company board to the local registry.
- Confirm the prompt names a company that exists in the registry.
- Confirm the registry source site is one of the supported live sources.

### LinkedIn live discovery does not show authenticated results

- Use `--auth-browser profile` or `--auth-browser attach`; LinkedIn live reads do not run unauthenticated.
- Prefer `--auth-browser attach` for LinkedIn.
- In `attach` mode, start Chrome or Edge with remote debugging enabled before running `job-agent`, then log into LinkedIn manually in that browser window.
- In `profile` mode, prefer a real Chromium subprofile path such as `.../User Data/Profile 1` or `.../User Data/Default`, but avoid assuming a copied or default production Chrome profile will always launch cleanly.
- If LinkedIn still fails to render readable results, enable `JOB_AGENT_DEBUG_ARTIFACTS_ON_FAILURE=true` and inspect the captured HTML/screenshot.

### Prompt-search matches do not appear in the dashboard

- `job-agent search` uses an in-memory temporary store by default.
- Run the same command with `--store-matches` if you want matched jobs inserted into the main SQLite database.
- After that, the jobs will appear in `job-agent review list` and `job-agent dashboard`.

### LinkedIn search works but some detail fetches still fail

- The current LinkedIn MVP can fall back to listing-only data when direct detail reads fail for some jobs.
- This is non-fatal by design; discovery can still succeed and matched jobs can still be returned or stored.
- If you need to inspect those failures, enable `JOB_AGENT_DEBUG_ARTIFACTS_ON_FAILURE=true` and review the saved page HTML/screenshot.

### Dashboard shows `n/a` for score

- Stored jobs only show scores that have already been written to metadata.
- Run `job-agent review rescore` to refresh stored scores using the current deterministic scoring rules.

### Browser fetches fail intermittently

- Make sure Playwright Chromium is installed locally.
- Try with a visible browser by setting `JOB_AGENT_BROWSER_HEADLESS=false`.
- Enable `JOB_AGENT_DEBUG_ARTIFACTS_ON_FAILURE=true` to capture screenshot and HTML artifacts for failed pages.

## Security / trust model

- Treat all fetched page content as untrusted input.
- The project is local-first and intended to run on a machine the user controls.
- The dashboard is for localhost use. It is not designed as an internet-exposed or multi-user service.
- Authenticated browser reuse is local-only and read-only.
- The tool does not automate login flows, application submission, or remote account actions.
- Debug artifacts can contain page content. Store and handle them as local sensitive data.

## Roadmap

Likely next steps, not current claims:

- broader supported-source coverage
- stronger deterministic parser coverage without leaving rule-based behavior
- richer prompt-plan execution ergonomics
- more selective and source-aware enrichment behavior
- more formal schema migration support
- optional model-backed summarization as a clearly separate read-only layer

## Development / testing

Run the default test suite:

```bash
pytest
```

Useful notes:

- Default `pytest` excludes the slower real-browser smoke layer.
- Run the real-browser smoke layer explicitly with:

```bash
pytest -m smoke
```

- The smoke tests use a tiny local HTTP fixture server and skip cleanly when Playwright Chromium is not available.
- YAML-based config tests require `PyYAML` when that path is exercised.
- The project aims for small, reviewable, deterministic changes.

## License

MIT. See [LICENSE](LICENSE).
