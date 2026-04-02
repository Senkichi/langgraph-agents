"""Coder node: invokes claude CLI as a full development agent.

Claude Code natively reads files, writes code, runs tests, and commits.
After the agent finishes, captures `git diff` into state.
"""

from langgraph_agents.claude_cli import invoke_agent
from langgraph_agents.state import BuildReviewState
from langgraph_agents.tools.dev_tools import run_git_diff

CODER_SYSTEM_PROMPT = (
    "You are an expert software engineer. Implement the approved plan precisely.\n\n"
    "Write files, run tests, install dependencies as needed.\n"
    "If reviewer feedback is provided, address every issue raised.\n"
    "Write clean, well-tested code. Run tests before finishing.\n"
    "Do NOT explain what you did — just do the work."
)


def _build_coder_context(state: BuildReviewState) -> str:
    """Build the prompt for the coder agent."""
    parts = [f"## Task\n{state['task']}", f"## Approved Plan\n{state['current_plan']}"]
    if state.get("e2e_feedback"):
        parts.append(
            "## End-to-End Test Findings (address these FIRST — they represent "
            "gaps between what the code does and what it was supposed to achieve)\n"
            f"{state['e2e_feedback']}"
        )
    if state.get("build_feedback"):
        parts.append(
            "## Reviewer Feedback (address every point)\n"
            f"{state['build_feedback']}"
        )
        if state.get("code_diff"):
            parts.append(f"## Current Code Diff\n```diff\n{state['code_diff']}\n```")
    return "\n\n".join(parts)


def code(state: BuildReviewState) -> dict:
    """Implement the plan using claude CLI as a full agent."""
    workspace = state["workspace_path"]
    context = _build_coder_context(state)

    invoke_agent(
        context,
        system_prompt=CODER_SYSTEM_PROMPT,
        cwd=workspace,
        model="sonnet",
    )

    diff = run_git_diff(workspace)
    return {
        "code_diff": diff,
        "build_cycle": state.get("build_cycle", 0) + 1,
    }
