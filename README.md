# job-agent

Minimal bootstrap for a local job-search automation tool.

Current scope:
- Python package with `src/` layout
- CLI entrypoint
- Environment-based config loading
- Structured logging setup
- Basic pytest smoke tests

Not included yet:
- Browser automation
- Web framework
- Database/storage
- Site-specific adapters

## Quick start

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -e .[dev]
job-agent --help
pytest
```

## Environment

Copy `.env.example` to `.env` if you want local defaults, then adjust values as needed.

