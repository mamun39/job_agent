# Project Limitations

Last updated: 2026-04-10

## Current limitations

- The CLI is still a minimal bootstrap and does not expose real workflow subcommands yet.
- `.env` parsing is intentionally simple and only supports basic `KEY=VALUE` lines.
- Logging is structured but minimal and does not yet include richer context fields or log sinks.
- SQLite storage uses a single lightweight schema with no migration framework.
- URL deduplication is conservative and generic; it does not include site-specific canonicalization rules.
- Fallback deduplication uses exact normalized `title + company + location` comparison only and does not do fuzzy matching.
- Relevance scoring uses fixed in-code weights and substring matching rather than externalized rules or semantic matching.
- Browser session tests validate wrapper behavior with fakes rather than launching a real browser end to end.
- Playwright browser installation is environment-local and must be installed on each machine separately.
- The site adapter abstraction supports read-only discovery/parsing only.
- Greenhouse support is limited to listing-page parsing and common markup conventions; detail-page parsing is not implemented.
- Lever support is limited to listing-page parsing and common markup conventions; detail-page parsing is not implemented.
- Discovery query configuration can be loaded from JSON directly; YAML is supported only when `PyYAML` is installed locally.
- Discovery query configuration is validated and loaded, but it is not yet connected to a full query-driven crawl runner.
- No login automation, site navigation flows, application submission logic, review dashboard, or resume tailoring logic exists.
- The discovery flow currently supports synchronous adapter runs from provided HTML or pre-parsed postings only; it does not perform live browsing, pagination, or Playwright-driven collection.

## Update rule

- After each completed task, update this file if the task adds a new limitation, removes one, or materially changes an existing limitation.
