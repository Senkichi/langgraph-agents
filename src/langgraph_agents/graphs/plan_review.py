"""Plan-review loop subgraph.

Supports dual input:
- If current_plan is populated → goes straight to reviewer
- If current_plan is empty → planner drafts first

Cycles up to 4 times or until the reviewer approves.
"""

from langgraph.graph import END, START, StateGraph

from langgraph_agents.nodes.plan_reviewer import review_plan
from langgraph_agents.nodes.planner import plan
from langgraph_agents.state import PlanReviewState

MAX_PLAN_CYCLES = 4


def _route_entry(state: PlanReviewState) -> str:
    """Route on entry: skip planner if a plan was already provided."""
    if state.get("current_plan"):
        return "plan_reviewer"
    return "planner"


def _route_after_review(state: PlanReviewState) -> str:
    """Route after review: approve → end, revise → planner (up to max cycles)."""
    if state.get("plan_verdict") == "APPROVE":
        return END
    if state.get("plan_cycle", 0) >= MAX_PLAN_CYCLES:
        return END
    return "planner"


def build_plan_review_graph() -> StateGraph:
    graph = StateGraph(PlanReviewState)

    graph.add_node("planner", plan)
    graph.add_node("plan_reviewer", review_plan)

    graph.add_conditional_edges(
        START,
        _route_entry,
        {"planner": "planner", "plan_reviewer": "plan_reviewer"},
    )
    graph.add_edge("planner", "plan_reviewer")
    graph.add_conditional_edges(
        "plan_reviewer",
        _route_after_review,
        {END: END, "planner": "planner"},
    )

    return graph


plan_review_app = build_plan_review_graph().compile()
