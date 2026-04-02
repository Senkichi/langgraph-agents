"""Macro reviewer: focuses on architecture, design, extensibility, plan alignment.

Invokes claude CLI with read-only tool access to inspect the workspace.
"""

from langgraph_agents.claude_cli import invoke_agent
from langgraph_agents.state import BuildReviewState

SYSTEM_PROMPT = (
    "You are a senior architect reviewing code at the MACRO level:\n"
    "- Architecture and design patterns\n"
    "- Separation of concerns\n"
    "- Extensibility and maintainability\n"
    "- Alignment with the approved implementation plan\n"
    "- API surface and interface design\n"
    "- Test coverage strategy\n\n"
    "You can read files and run commands to verify your findings.\n"
    "Do NOT modify any files.\n\n"
    "Be antagonistic. Ensure the implementation matches the plan and follows "
    "good architectural practices. Do not rubber-stamp.\n\n"
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


def macro_review(state: BuildReviewState) -> dict:
    """Macro-level architecture review using claude CLI."""
    workspace = state["workspace_path"]
    content = (
        f"## Approved Plan\n{state['current_plan']}\n\n"
        f"## Code Diff to Review\n```diff\n{state.get('code_diff', '')}\n```\n\n"
        "Review the architecture and design. Read the full files to understand "
        "the structure. Then provide your final verdict."
    )

    response = invoke_agent(
        content,
        system_prompt=SYSTEM_PROMPT,
        cwd=workspace,
        allowed_tools=REVIEW_TOOLS,
        model="sonnet",
    )
    return {"macro_feedback": _format_feedback(response)}
