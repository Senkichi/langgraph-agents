"""Micro reviewer: focuses on code quality, bugs, edge cases, correctness.

Invokes claude CLI with read-only tool access to inspect the workspace.
"""

from langgraph_agents.claude_cli import invoke_agent
from langgraph_agents.config import REVIEWER_BUDGET_USD, REVIEWER_MODEL, REVIEWER_TIMEOUT
from langgraph_agents.node_contract import (
    contains_verdict,
    format_verdict_feedback,
    is_path,
    non_empty,
    validate_node,
)
from langgraph_agents.state import BuildReviewState

SYSTEM_PROMPT = (
    "You are a meticulous code reviewer focused on MICRO-LEVEL quality:\n"
    "- Bugs and logic errors\n"
    "- Edge cases and error handling\n"
    "- Code style and readability\n"
    "- Performance issues\n"
    "- Security vulnerabilities\n\n"
    "You can read files and run commands (tests, linters) to verify your findings.\n"
    "Do NOT modify any files.\n\n"
    "Be antagonistic. Find real problems. Do not rubber-stamp.\n\n"
    "End your response with your final verdict using EXACTLY this format:\n\n"
    "VERDICT:<APPROVE or REVISE>\n"
    "REASONING:<1-3 sentences>\n\n"
    "If REVISE, categorize every issue by severity. Each issue MUST include\n"
    "the file path, approximate line number, and a concrete ACTION the coder\n"
    "should take. Use EXACTLY this structure:\n\n"
    "CRITICAL:\n"
    "- <file>:<line> — <what is wrong> — ACTION: <specific fix>\n\n"
    "MAJOR:\n"
    "- <file>:<line> — <what is wrong> — ACTION: <specific fix>\n\n"
    "MINOR:\n"
    "- <suggestion, not a blocker>\n\n"
    "Omit empty severity sections. CRITICAL = bugs, security, data loss.\n"
    "MAJOR = correctness, missing tests, bad error handling.\n"
    "MINOR = style, naming, minor readability."
)

REVIEW_TOOLS = ["Read", "Glob", "Grep", "Bash"]


@validate_node(
    pre={"current_plan": non_empty, "workspace_path": is_path},
    post={"micro_feedback": contains_verdict},
)
def micro_review(state: BuildReviewState) -> dict:
    """Micro-level code review using claude CLI."""
    workspace = state["workspace_path"]
    content = (
        f"## Plan\n{state['current_plan']}\n\n"
        f"## Code Diff to Review\n```diff\n{state.get('code_diff', '')}\n```\n\n"
        "Review the code. Read files and run tests/linters to verify findings. "
        "Then provide your final verdict."
    )

    response = invoke_agent(
        content,
        system_prompt=SYSTEM_PROMPT,
        cwd=workspace,
        allowed_tools=REVIEW_TOOLS,
        model=REVIEWER_MODEL,
        max_budget_usd=REVIEWER_BUDGET_USD,
        timeout=REVIEWER_TIMEOUT,
    )
    return {"micro_feedback": format_verdict_feedback(response)}
