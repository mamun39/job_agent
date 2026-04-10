# Project Limitations

Last updated: 2026-04-10

## Current limitations

- The CLI exposes discovery and review commands, but it remains a plain command-line interface without richer interactive workflows.
- `.env` parsing is intentionally simple and only supports basic `KEY=VALUE` lines.
- Logging is structured but minimal and does not yet include richer context fields or log sinks.
- SQLite storage uses a single lightweight schema with no migration framework.
- URL deduplication is conservative and generic; it does not include site-specific canonicalization rules.
- Fallback deduplication uses exact normalized `title + company + location` comparison only and does not do fuzzy matching.
- Relevance scoring uses fixed in-code weights and substring matching rather than externalized rules or semantic matching.
- Browser session tests validate wrapper behavior with fakes rather than launching a real browser end to end.
- Playwright browser installation is environment-local and must be installed on each machine separately.
- The Playwright fetch helper is generic and only supports URL navigation, page HTML capture, optional screenshots, and simple wait strategies; it does not include site-specific readiness checks.
- The site adapter abstraction supports read-only discovery/parsing only.
- Greenhouse support is limited to listing-page parsing and common markup conventions; detail-page parsing is not implemented.
- Lever support is limited to listing-page parsing and common markup conventions; detail-page parsing is not implemented.
- Discovery query configuration can be loaded from JSON directly; YAML is supported only when `PyYAML` is installed locally.
- Discovery query configuration can drive live listing-page discovery for supported adapters, but it is still limited to one fetched start URL per query.
- No login automation, site navigation flows, application submission logic, review dashboard, or resume tailoring logic exists.
- The discovery flow supports synchronous live listing-page fetches plus static HTML/pre-parsed input, but it does not yet support pagination, multi-step navigation, or browser-driven detail-page collection.
- The review workflow is CLI-only and non-interactive; there is no dashboard or richer terminal UI.
- Review filtering by score and reviewed state currently depends on values stored in job `metadata` rather than dedicated schema fields.

## Update rule

- After each completed task, update this file if the task adds a new limitation, removes one, or materially changes an existing limitation.
