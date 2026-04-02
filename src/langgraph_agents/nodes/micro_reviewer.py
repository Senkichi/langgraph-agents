"""Micro reviewer: focuses on code quality, bugs, edge cases, correctness.

Invokes claude CLI with read-only tool access to inspect the workspace.
"""

from langgraph_agents.claude_cli import invoke_agent
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
        model="sonnet",
    )
    return {"micro_feedback": _format_feedback(response)}
