"""Build-review loop subgraph.

The coder implements the plan, then two parallel reviewers (micro + macro)
critique the result via Send() fan-out. A pure-Python synthesizer merges
verdicts. Cycles up to 4 times or until both reviewers approve.

Workspace path is carried in state — no factory functions needed since
agents use the claude CLI (which takes cwd as a parameter).
"""

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from langgraph_agents.nodes.coder import code
from langgraph_agents.nodes.macro_reviewer import macro_review
from langgraph_agents.nodes.micro_reviewer import micro_review
from langgraph_agents.nodes.review_synthesizer import synthesize_reviews
from langgraph_agents.state import BuildReviewState

MAX_BUILD_CYCLES = 4


def _fan_out_to_reviewers(state: BuildReviewState) -> list[Send]:
    """Fan out to both reviewers in parallel."""
    return [
        Send("micro_reviewer", state),
        Send("macro_reviewer", state),
    ]


def _route_after_synthesis(state: BuildReviewState) -> str:
    """Route after synthesis: approve → end, revise → coder (up to max cycles)."""
    if state.get("build_verdict") == "APPROVE":
        return END
    if state.get("build_cycle", 0) >= MAX_BUILD_CYCLES:
        return END
    return "coder"


def build_build_review_graph() -> StateGraph:
    """Build the build-review subgraph."""
    graph = StateGraph(BuildReviewState)

    graph.add_node("coder", code)
    graph.add_node("micro_reviewer", micro_review)
    graph.add_node("macro_reviewer", macro_review)
    graph.add_node("synthesizer", synthesize_reviews, defer=True)

    graph.add_edge(START, "coder")
    graph.add_conditional_edges(
        "coder",
        _fan_out_to_reviewers,
        ["micro_reviewer", "macro_reviewer"],
    )
    graph.add_edge("micro_reviewer", "synthesizer")
    graph.add_edge("macro_reviewer", "synthesizer")
    graph.add_conditional_edges(
        "synthesizer",
        _route_after_synthesis,
        {END: END, "coder": "coder"},
    )

    return graph


build_review_app = build_build_review_graph().compile()
