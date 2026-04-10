# Architecture

## Goal

`job-agent` is a local-first Python tool for job-search automation. This bootstrap intentionally limits scope to package structure, configuration, logging, and CLI startup.

## Current components

- `job_agent.main`: CLI entrypoint and startup wiring
- `job_agent.config`: environment variable loading and typed settings
- `job_agent.logging`: structured logging configuration

## Deliberate exclusions

- No browser automation
- No web framework
- No database logic
- No job-board specific integrations
- No autonomous workflows

## Design notes

- `src/` layout keeps imports aligned with installed package behavior.
- Configuration is loaded from process environment, with optional `.env` support for local development.
- Logging uses the standard library and emits JSON-formatted records for predictable local inspection.
- The CLI is intentionally minimal and currently provides startup/help behavior only.

## Expected next steps

1. Add application commands for local workflows.
2. Introduce domain models for search inputs and results.
3. Add explicit adapters only when automation scope is defined.

