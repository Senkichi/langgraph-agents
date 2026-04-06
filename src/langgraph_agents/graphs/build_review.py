"""Build-review loop subgraph.

The coder implements the plan, then two parallel reviewers (micro + macro)
critique the result via Send() fan-out. A pure-Python synthesizer merges
verdicts. Cycles up to 4 times or until both reviewers approve.

Workspace path is carried in state — no factory functions needed since
agents use the claude CLI (which takes cwd as a parameter).
"""

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send

from langgraph_agents.nodes.coder import code
from langgraph_agents.nodes.macro_reviewer import macro_review
from langgraph_agents.nodes.micro_reviewer import micro_review
from langgraph_agents.nodes.review_synthesizer import synthesize_reviews
from langgraph_agents.state import BuildReviewState
from langgraph_agents.tracer import traced_route

MAX_BUILD_CYCLES = 4

_SUBPROCESS_RETRY = RetryPolicy(
    max_attempts=3,
    initial_interval=2.0,
    retry_on=RuntimeError,
)


@traced_route("coder", ["micro_reviewer", "macro_reviewer"])
def _fan_out_to_reviewers(state: BuildReviewState) -> list[Send]:
    """Fan out to both reviewers in parallel."""
    return [
        Send("micro_reviewer", state),
        Send("macro_reviewer", state),
    ]


@traced_route("synthesizer", ["__end__", "coder"])
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

    graph.add_node("coder", code, retry_policy=_SUBPROCESS_RETRY)
    graph.add_node("micro_reviewer", micro_review, retry_policy=_SUBPROCESS_RETRY)
    graph.add_node("macro_reviewer", macro_review, retry_policy=_SUBPROCESS_RETRY)
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


def compile_build_review(checkpointer=None):
    """Compile the build-review graph with an optional checkpointer."""
    from langgraph.checkpoint.memory import InMemorySaver

    cp = checkpointer if checkpointer is not None else InMemorySaver()
    return build_build_review_graph().compile(checkpointer=cp)


build_review_app = compile_build_review()
