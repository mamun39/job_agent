# Project Limitations

Last updated: 2026-04-10

## Current limitations

- The CLI exposes discovery and review commands, but it remains a plain command-line interface without richer interactive workflows.
- A minimal local dashboard now exists for review workflows, but it is intentionally server-rendered and limited to simple list/detail/review actions.
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
- Greenhouse support is limited to listing-page parsing and common markup conventions, with conservative next-page traversal only when standard listing pagination links are exposed; detail-page parsing is not implemented.
- Lever support is limited to listing-page parsing and common markup conventions, with conservative next-page traversal only when standard listing pagination links are exposed; detail-page parsing is not implemented.
- Indeed support is limited to listing-page parsing from saved HTML fixtures and common markup conventions; detail-page parsing and live-site hardening are not implemented.
- LinkedIn support is limited to listing-page parsing from saved HTML fixtures and common public markup conventions; detail-page parsing and live-site hardening are not implemented.
- Discovery query configuration can be loaded from JSON directly; YAML is supported only when `PyYAML` is installed locally.
- Discovery query configuration can drive live listing-page discovery for supported adapters from one configured start URL per query, but multi-page traversal is implemented only for Greenhouse and Lever and remains limited by a conservative per-query page cap.
- No login automation, site navigation flows, application submission logic, review dashboard, or resume tailoring logic exists.
- No login automation, site navigation flows, application submission logic, or resume tailoring logic exists.
- The discovery flow supports synchronous live listing-page fetches plus static HTML/pre-parsed input, but pagination is limited to conservative Greenhouse and Lever next-page traversal and it still does not support multi-step navigation or browser-driven detail-page collection.
- The review workflow now supports both CLI and a minimal local dashboard, but there is still no richer terminal UI, authentication layer, or collaborative multi-user workflow.
- Review decisions are now persisted separately, but some review-related filtering still falls back to older job `metadata` fields for backward compatibility.
- Review decisions store only the latest explicit state per posting URL; there is no decision history or audit trail.
- The CLI can open stored job URLs in the system browser for manual review, but it does not track browser-open events or review completion.
- The local dashboard is intended for localhost use only and does not implement authentication, authorization, CSRF protection, or hardened deployment concerns.
- The local dashboard uses simple server-rendered pages and basic form/query filters; it does not include pagination, sorting controls, live updates, or richer search ergonomics.
- The local dashboard tolerates blank filter fields from its forms, but invalid non-numeric values for numeric filters such as `min_score` are not yet rendered as friendly validation errors in the UI.
- The optional summarizer layer is currently presentation-only: it provides a local rule-based fallback and an interface for future injected model-backed summarizers, but it is not yet wired into the main CLI command surface.
- No remote LLM provider integration, prompt configuration, or model-specific runtime settings are implemented; any future model-backed summarizer must remain explicitly optional and read-only.

## Update rule

- After each completed task, update this file if the task adds a new limitation, removes one, or materially changes an existing limitation.
