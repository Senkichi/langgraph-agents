"""Coder node: invokes claude CLI as a full development agent.

Claude Code natively reads files, writes code, runs tests, and commits.
After the agent finishes, captures `git diff` into state.
"""

from langgraph_agents.claude_cli import invoke_agent
from langgraph_agents.config import CODER_BUDGET_USD, CODER_MODEL, CODER_TIMEOUT
from langgraph_agents.node_contract import is_path, non_empty, validate_node
from langgraph_agents.state import BuildReviewState
from langgraph_agents.tools.dev_tools import run_git_diff, truncate_diff

CODER_SYSTEM_PROMPT = (
    "You are an expert software engineer. Implement the approved plan precisely.\n\n"
    "Write files, run tests, install dependencies as needed.\n"
    "Write clean, well-tested code. Run tests before finishing.\n"
    "Do NOT explain what you did — just do the work.\n\n"
    "## Handling Reviewer Feedback\n"
    "If reviewer feedback is provided, process it by severity:\n"
    "- CRITICAL: you MUST fix before proceeding.\n"
    "- MAJOR: fix unless there is a strong architectural reason not to.\n"
    "- MINOR: address at your discretion — do not let these block progress."
)


def _build_coder_context(state: BuildReviewState) -> str:
    """Build the prompt for the coder agent."""
    parts = [f"## Task\n{state['task']}", f"## Approved Plan\n{state['current_plan']}"]

    if state.get("persistent_rules"):
        parts.append(
            "## Engineering Constraints (learned from prior cycles — treat as hard rules)\n"
            + state["persistent_rules"]
        )

    resolved = state.get("resolved_issues") or []
    if resolved:
        issue_list = "\n".join(f"- {issue}" for issue in resolved)
        parts.append(
            "## Do Not Reintroduce (confirmed fixed in a prior cycle — keep these passing)\n"
            + issue_list
        )

    if state.get("e2e_feedback"):
        parts.append(
            "## End-to-End Test Findings (address these FIRST)\n"
            f"{state['e2e_feedback']}"
        )
    if state.get("build_feedback"):
        parts.append(f"## Reviewer Feedback\n{state['build_feedback']}")
        if state.get("code_diff"):
            diff = truncate_diff(state["code_diff"])
            parts.append(f"## Current Code Diff\n```diff\n{diff}\n```")
    return "\n\n".join(parts)


@validate_node(
    pre={"task": non_empty, "current_plan": non_empty, "workspace_path": is_path},
    post={"code_diff": non_empty},
)
def code(state: BuildReviewState) -> dict:
    """Implement the plan using claude CLI as a full agent."""
    workspace = state["workspace_path"]
    context = _build_coder_context(state)

    invoke_agent(
        context,
        system_prompt=CODER_SYSTEM_PROMPT,
        cwd=workspace,
        model=CODER_MODEL,
        max_budget_usd=CODER_BUDGET_USD,
        timeout=CODER_TIMEOUT,
    )

    diff = run_git_diff(workspace)
    return {
        "code_diff": diff,
        "build_cycle": state.get("build_cycle", 0) + 1,
    }
