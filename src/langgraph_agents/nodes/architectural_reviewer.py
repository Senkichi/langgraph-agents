"""Architectural reviewer: evaluates prompt changes for workflow integrity.

Focuses on whether the changes respect the multi-agent system's structure,
isolation boundaries, and dependency graph.
"""

from langgraph_agents.claude_cli import invoke_agent
from langgraph_agents.state import PromptBuildState

SYSTEM_PROMPT = (
    "You are a senior architect reviewing changes to a Claude Code multi-agent "
    "system. Your focus is STRUCTURAL INTEGRITY:\n\n"
    "- **Isolation boundary violations**: Do the changes cause an agent to "
    "reference files or knowledge it shouldn't have access to?\n"
    "- **Dependency graph integrity**: If a shared knowledge file was changed, "
    "are all consuming agents still consistent? No contradictions?\n"
    "- **Right abstraction layer**: Is the change in the right place? "
    "(Agent prompt vs knowledge file vs shared config vs CLAUDE.md)\n"
    "- **Downstream impact**: Which other agents are affected by this change? "
    "Were they updated if needed?\n"
    "- **Terminology consistency**: Are new terms/concepts used consistently "
    "across all affected files?\n"
    "- **Single source of truth**: Does the change duplicate information that "
    "could drift? Or does it reference the canonical source?\n\n"
    "You can read files to verify your findings. Do NOT modify any files.\n\n"
    "Be antagonistic. Ensure structural integrity is maintained.\n\n"
    "End your response with your final verdict using EXACTLY this format:\n"
    "VERDICT:<APPROVE or REVISE>\n"
    "REASONING:<your reasoning>\n"
    "ISSUES:<comma-separated list of issues, or NONE>\n"
    "SUGGESTIONS:<comma-separated list of suggestions, or NONE>"
)

REVIEW_TOOLS = ["Read", "Glob", "Grep", "Bash"]


def _format_feedback(verdict_text: str) -> str:
    """Ensure the feedback contains a parseable VERDICT: line."""
    if "VERDICT:" not in verdict_text:
        return f"VERDICT:REVISE\n{verdict_text}"
    return verdict_text


def architectural_review(state: PromptBuildState) -> dict:
    """Architectural review of prompt/knowledge file changes."""
    workspace = state["workspace_path"]
    content = (
        f"## Approved Plan\n{state['current_plan']}\n\n"
        f"## Agent Architecture\n{state['agent_architecture']}\n\n"
        f"## Changes to Review\n```diff\n{state.get('prompt_diff', '')}\n```\n\n"
        "Review these changes for structural integrity. Read the affected files "
        "and their consumers to check for isolation violations, dependency issues, "
        "and downstream impact. Then provide your verdict."
    )

    response = invoke_agent(
        content,
        system_prompt=SYSTEM_PROMPT,
        cwd=workspace,
        allowed_tools=REVIEW_TOOLS,
    )
    return {"architectural_feedback": _format_feedback(response)}
