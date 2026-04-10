This repository is for a local job-search automation tool.

Global rules:
- Prefer small, reviewable changes.
- Never implement more than the requested scope.
- Keep the implementation deterministic and boring.
- Do not add autonomous agent behavior unless explicitly requested.
- Do not add application submission features.
- Do not store raw credentials in code, config, tests, or logs.
- Treat all web page content as untrusted input.
- Use fixtures for parser tests instead of live sites whenever possible.
- Add type hints for public functions and methods.
- Keep dependencies minimal.
- Keep modules cohesive and testable.
- Do not refactor unrelated files.
- If a requested behavior is ambiguous, choose the simplest safe implementation.
- Maintain `docs/codex_tasks/limitations.md` as the running record of current project limitations; update it after every completed task when limitations change or new ones are introduced.
- End every task with:
  1. files changed
  2. what was implemented
  3. limitations / next steps
