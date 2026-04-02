import os

import anthropic_telemetry
from anthropic_telemetry._config import load_config
from langchain_anthropic import ChatAnthropic

# Activate telemetry + budget enforcement for all anthropic API calls.
# Patches anthropic.Messages.create/stream — every LLM call is logged and capped.
anthropic_telemetry.activate("langgraph-agents")


def get_llm() -> ChatAnthropic:
    """Primary LLM for planner and coder (Sonnet by default)."""
    config = load_config()
    return ChatAnthropic(
        model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
        api_key=config.api_key,
    )


def get_review_llm() -> ChatAnthropic:
    """LLM for reviewers. Same model by default; overridable via env var."""
    config = load_config()
    return ChatAnthropic(
        model=os.getenv("ANTHROPIC_REVIEW_MODEL", "claude-sonnet-4-20250514"),
        api_key=config.api_key,
    )
