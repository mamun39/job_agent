"""Application flows for job-agent."""

from job_agent.flows.discover import run_discovery
from job_agent.flows.prompt_search import run_prompt_search

__all__ = ["run_discovery", "run_prompt_search"]
