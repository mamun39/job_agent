"""Optional summarization interfaces for job explanations."""

from job_agent.llm.summarizer import JobSummarizer, RuleBasedJobSummarizer, summarize_job_match

__all__ = ["JobSummarizer", "RuleBasedJobSummarizer", "summarize_job_match"]
