"""Parent graph: composes plan-review, build-review, and e2e-test.

Usage:
    from langgraph_agents.graphs.plan_build_review import plan_build_review_app

    # With a task description (planner drafts the plan):
    result = plan_build_review_app.invoke({
        "task": "Build a REST API for ...",
        "current_plan": "",
        "current_code": "",
        "workspace_path": "/path/to/workspace",
        "e2e_verdict": "",
        "e2e_report": "",
        "e2e_cycle": 0,
    })

    # With a pre-written plan (skips straight to reviewer):
    result = plan_build_review_app.invoke({
        "task": "Build a REST API for ...",
        "current_plan": "1. Create models...",
        "current_code": "",
        "workspace_path": "/path/to/workspace",
        "e2e_verdict": "",
        "e2e_report": "",
        "e2e_cycle": 0,
    })
"""

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from langgraph_agents.graphs.build_review import MAX_BUILD_CYCLES, build_review_app
from langgraph_agents.graphs.plan_review import plan_review_app
from langgraph_agents.nodes.discover_architecture import discover_architecture
from langgraph_agents.nodes.e2e_tester import e2e_test
from langgraph_agents.state import (
    BuildReviewState,
    ParentState,
)
from langgraph_agents.tracer import get_tracer, traced_route

MAX_E2E_CYCLES = 2

_SUBPROCESS_RETRY = RetryPolicy(
    max_attempts=3,
    initial_interval=2.0,
    retry_on=RuntimeError,
)


def _call_build_review(state: ParentState) -> dict:
    """Wrapper: transforms parent state → subgraph input → subgraph output.

    When re-entering after an e2e failure, injects the e2e report as
    e2e_feedback so the coder sees intent-gap diagnostics on its first cycle.
    """
    tracer = get_tracer()
    if tracer is not None:
        tracer.push_graph("build_review")

    is_e2e_reentry = state.get("e2e_verdict") == "REVISE"
    e2e_feedback = state.get("e2e_report", "") if is_e2e_reentry else ""

    # On e2e re-entry, start build_cycle at MAX-1 so only one coder+review
    # pass runs before returning to e2e. On initial entry, start at 0 for
    # the full budget.
    build_cycle = MAX_BUILD_CYCLES - 1 if is_e2e_reentry else 0

    subgraph_input: BuildReviewState = {
        "task": state.get("task", ""),
        "current_plan": state["current_plan"],
        "agent_architecture": state.get("agent_architecture", ""),
        "code_diff": "",
        "workspace_path": state.get("workspace_path", ""),
        "micro_feedback": "",
        "macro_feedback": "",
        "build_verdict": "",
        "build_feedback": "",
        "build_cycle": build_cycle,
        "e2e_feedback": e2e_feedback,
        "resolved_issues": [],
        "persistent_rules": "",
    }
    try:
        result = build_review_app.invoke(subgraph_input)
        return {"current_code": result.get("code_diff", "")}
    finally:
        if tracer is not None:
            tracer.pop_graph()


@traced_route("e2e_test", ["__end__", "build_review"])
def _route_after_e2e(state: ParentState) -> str:
    """Route after e2e test: approve/skip → end, revise → build_review (up to max cycles)."""
    verdict = state.get("e2e_verdict", "")
    if verdict in ("APPROVE", "SKIP"):
        return END
    if state.get("e2e_cycle", 0) >= MAX_E2E_CYCLES:
        return END
    return "build_review"


@traced_route("__start__", ["discover_architecture", "build_review"])
def _route_entry(state: ParentState) -> str:
    """Skip plan review when caller has a pre-validated plan."""
    if state.get("skip_plan_review"):
        return "build_review"
    return "discover_architecture"


def build_plan_build_review_graph() -> StateGraph:
    """Build the parent graph composing discover, plan-review, build-review, and e2e-test."""
    graph = StateGraph(ParentState)

    graph.add_node("discover_architecture", discover_architecture, retry_policy=_SUBPROCESS_RETRY)
    graph.add_node("plan_review", plan_review_app)  # native subgraph
    graph.add_node("build_review", _call_build_review)
    graph.add_node("e2e_test", e2e_test, retry_policy=_SUBPROCESS_RETRY)

    graph.add_conditional_edges(
        START,
        _route_entry,
        {"discover_architecture": "discover_architecture", "build_review": "build_review"},
    )
    graph.add_edge("discover_architecture", "plan_review")
    graph.add_edge("plan_review", "build_review")
    graph.add_edge("build_review", "e2e_test")
    graph.add_conditional_edges(
        "e2e_test",
        _route_after_e2e,
        {END: END, "build_review": "build_review"},
    )

    return graph


def compile_plan_build_review(checkpointer=None):
    """Compile the parent graph with an optional checkpointer."""
    from langgraph.checkpoint.memory import InMemorySaver

    cp = checkpointer if checkpointer is not None else InMemorySaver()
    return build_plan_build_review_graph().compile(checkpointer=cp)


plan_build_review_app = compile_plan_build_review()
