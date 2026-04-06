"""Macro reviewer: focuses on architecture, design, extensibility, plan alignment.

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
    "Omit empty severity sections. CRITICAL = plan deviation, broken contracts,\n"
    "missing components. MAJOR = poor separation of concerns, missing test\n"
    "coverage, tight coupling. MINOR = naming, minor structure improvements."
)

REVIEW_TOOLS = ["Read", "Glob", "Grep", "Bash"]

_PLAN_CONTEXT_LIMIT = 1500


def _truncate_plan_for_reviewer(plan: str) -> str:
    if len(plan) <= _PLAN_CONTEXT_LIMIT:
        return plan
    return (
        plan[:_PLAN_CONTEXT_LIMIT]
        + f"\n\n... [plan truncated at {_PLAN_CONTEXT_LIMIT} chars — "
        "read the full plan from the workspace if alignment verification requires it]"
    )


@validate_node(
    pre={"current_plan": non_empty, "workspace_path": is_path},
    post={"macro_feedback": contains_verdict},
)
def macro_review(state: BuildReviewState) -> dict:
    """Macro-level architecture review using claude CLI."""
    workspace = state["workspace_path"]

    parts = [
        f"## Approved Plan\n{_truncate_plan_for_reviewer(state['current_plan'])}",
        f"## Code Diff to Review\n```diff\n{state.get('code_diff', '')}\n```",
    ]
    if state.get("agent_architecture"):
        parts.append(
            "## Workspace Architecture (pre-discovered)\n"
            "Use this to orient your structural review. Read only the specific files\n"
            "referenced in the diff — do not re-scan the full workspace.\n\n"
            + state["agent_architecture"]
        )
    parts.append(
        "Review the architecture and design. Read only the files referenced in the "
        "diff above to understand the structure. Then provide your final verdict."
    )
    content = "\n\n".join(parts)

    response = invoke_agent(
        content,
        system_prompt=SYSTEM_PROMPT,
        cwd=workspace,
        allowed_tools=REVIEW_TOOLS,
        model=REVIEWER_MODEL,
        max_budget_usd=REVIEWER_BUDGET_USD,
        timeout=REVIEWER_TIMEOUT,
    )
    return {"macro_feedback": format_verdict_feedback(response)}
