"""Behavioral reviewer: evaluates prompt changes for instruction quality.

Focuses on whether the changes will actually produce the intended behavior
from the LLM agents.
"""

from langgraph_agents.claude_cli import invoke_agent
from langgraph_agents.config import REVIEWER_MODEL, REVIEWER_TIMEOUT
from langgraph_agents.node_contract import (
    contains_verdict,
    format_verdict_feedback,
    is_path,
    non_empty,
    validate_node,
)
from langgraph_agents.state import PromptBuildState

SYSTEM_PROMPT = (
    "You are an expert prompt reviewer focused on BEHAVIORAL quality.\n\n"
    "You review changes to agent prompts and knowledge files in Claude Code "
    "multi-agent systems. Your focus:\n\n"
    "- **Instruction clarity**: Are the new/modified instructions unambiguous? "
    "Will an LLM interpret them as intended?\n"
    "- **Contradiction detection**: Do the changes contradict existing instructions "
    "in the same file or in other agent files?\n"
    "- **Intent-instruction gap**: Will the changes actually produce the intended "
    "behavioral shift? Or is there a gap between what was intended and what was written?\n"
    "- **Edge case coverage**: What happens when the input doesn't match the "
    "expected pattern? (e.g., a JD without the signals the prompt checks for)\n"
    "- **Instruction completeness**: Are there scenarios where the agent won't "
    "know what to do because the instructions don't cover it?\n\n"
    "You can read files to verify your findings. Do NOT modify any files.\n\n"
    "Be antagonistic. Find real problems. Do not rubber-stamp.\n\n"
    "End your response with your final verdict using EXACTLY this format:\n"
    "VERDICT:<APPROVE or REVISE>\n"
    "REASONING:<your reasoning>\n"
    "ISSUES:<comma-separated list of issues, or NONE>\n"
    "SUGGESTIONS:<comma-separated list of suggestions, or NONE>"
)

REVIEW_TOOLS = ["Read", "Glob", "Grep", "Bash"]


@validate_node(
    pre={
        "current_plan": non_empty,
        "agent_architecture": non_empty,
        "workspace_path": is_path,
    },
    post={"behavioral_feedback": contains_verdict},
)
def behavioral_review(state: PromptBuildState) -> dict:
    """Behavioral review of prompt/knowledge file changes."""
    workspace = state["workspace_path"]
    content = (
        f"## Approved Plan\n{state['current_plan']}\n\n"
        f"## Agent Architecture\n{state['agent_architecture']}\n\n"
        f"## Changes to Review\n```diff\n{state.get('prompt_diff', '')}\n```\n\n"
        "Review these prompt/knowledge file changes. Read the affected files "
        "in full to understand context. Then provide your verdict."
    )

    response = invoke_agent(
        content,
        system_prompt=SYSTEM_PROMPT,
        cwd=workspace,
        allowed_tools=REVIEW_TOOLS,
        model=REVIEWER_MODEL,
        timeout=REVIEWER_TIMEOUT,
    )
    return {"behavioral_feedback": format_verdict_feedback(response)}
