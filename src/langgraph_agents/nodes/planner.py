from langgraph_agents.claude_cli import invoke
from langgraph_agents.node_contract import non_empty, validate_node
from langgraph_agents.state import PlanReviewState

SYSTEM_PROMPT = (
    "You are an expert implementation planner. You receive a task description "
    "and optionally feedback from a prior review cycle.\n\n"
    "If feedback is provided, revise the plan to address every issue raised.\n"
    "If no feedback is provided, create an initial detailed implementation plan.\n\n"
    "Output ONLY the plan text. Do not include meta-commentary."
)


@validate_node(
    pre={"task": non_empty},
    post={"current_plan": non_empty},
)
def plan(state: PlanReviewState) -> dict:
    """Create or revise an implementation plan based on task and feedback."""
    parts = [f"## Task\n{state['task']}"]
    if state.get("current_plan"):
        parts.append(f"## Current Plan\n{state['current_plan']}")
    if state.get("plan_feedback"):
        parts.append(
            "## Reviewer Feedback (you MUST address every point)\n"
            f"{state['plan_feedback']}"
        )

    response = invoke(
        "\n\n".join(parts),
        system_prompt=SYSTEM_PROMPT,
        model="opus",
    )
    return {
        "current_plan": response,
        "plan_cycle": state.get("plan_cycle", 0) + 1,
    }
