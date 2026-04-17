"""Parent graph: composes plan-review, plan-chunking, build-review, and e2e-test.

After plan_review approves a plan, the plan_chunker decomposes it into ordered
implementation steps. Each step runs through build_review sequentially, with
state (resolved_issues, persistent_rules) carrying forward across steps. A
single e2e_test runs after all steps complete.

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
        "chunks": [],
        "chunk_index": 0,
        "full_plan": "",
        "resolved_issues": [],
        "persistent_rules": "",
    })

    # With a pre-written plan (skips plan_review, still chunked):
    result = plan_build_review_app.invoke({
        "task": "Build a REST API for ...",
        "current_plan": "1. Create models...",
        "current_code": "",
        "workspace_path": "/path/to/workspace",
        "e2e_verdict": "",
        "e2e_report": "",
        "e2e_cycle": 0,
        "skip_plan_review": True,
        "chunks": [],
        "chunk_index": 0,
        "full_plan": "",
        "resolved_issues": [],
        "persistent_rules": "",
    })
"""

import logging

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from langgraph_agents.graphs.build_review import MAX_BUILD_CYCLES, build_review_app
from langgraph_agents.graphs.plan_review import plan_review_app
from langgraph_agents.nodes.discover_architecture import discover_architecture
from langgraph_agents.nodes.e2e_tester import e2e_test
from langgraph_agents.nodes.plan_chunker import chunk_plan
from langgraph_agents.state import (
    BuildReviewState,
    ParentState,
)
from langgraph_agents.tracer import get_tracer, traced_route

logger = logging.getLogger(__name__)

MAX_E2E_CYCLES = 2

_SUBPROCESS_RETRY = RetryPolicy(
    max_attempts=3,
    initial_interval=2.0,
    retry_on=RuntimeError,
)


def _call_build_review(state: ParentState) -> dict:
    """Run build_review for the current chunk or whole-plan remediation.

    Normal execution scopes the coder to the current chunk while carrying
    forward resolved_issues and persistent_rules from prior chunks. On e2e
    re-entry, widen the scope back to the full plan so cross-cutting intent
    gaps can be fixed in one final remediation pass.
    """
    tracer = get_tracer()
    if tracer is not None:
        tracer.push_graph("build_review")

    chunks = state.get("chunks", [])
    chunk_index = state.get("chunk_index", 0)
    full_plan = state.get("full_plan", "")

    is_e2e_reentry = state.get("e2e_verdict") == "REVISE"
    e2e_feedback = state.get("e2e_report", "") if is_e2e_reentry else ""

    # On e2e re-entry, start build_cycle at MAX-1 so only one coder+review
    # pass runs before returning to e2e. On initial entry, start at 0.
    build_cycle = MAX_BUILD_CYCLES - 1 if is_e2e_reentry else 0

    # E2E failures can span multiple chunks. Re-enter with full-plan scope.
    if is_e2e_reentry and full_plan:
        total_chunks = len(chunks)
        logger.info(
            "build_review: e2e re-entry after chunk %d/%d — widening scope to full plan",
            min(chunk_index + 1, total_chunks) if total_chunks else 0,
            total_chunks,
        )
        coder_plan = (
            "You are revising the implementation after an end-to-end validation "
            "failure. The defect may span multiple prior steps, so you may edit "
            "any affected files.\n\n"
            f"## Full Plan\n{full_plan}"
        )
    elif chunks and 0 <= chunk_index < len(chunks):
        chunk = chunks[chunk_index]
        chunk_title = chunk.get("title", f"Step {chunk_index + 1}")
        chunk_plan = chunk.get("plan_section", "")
        total_chunks = len(chunks)

        coder_plan = (
            f"You are implementing step {chunk_index + 1} of {total_chunks}: "
            f'"{chunk_title}"\n'
            f"Prior steps have already been implemented in this workspace.\n\n"
            f"## Full Plan (reference only)\n{full_plan}\n\n"
            f"## YOUR FOCUS — implement this step only:\n{chunk_plan}"
        )
        logger.info(
            "build_review: chunk %d/%d — %s", chunk_index + 1, total_chunks, chunk_title
        )
    elif chunks:
        logger.warning(
            "build_review: chunk_index %d out of bounds for %d chunk(s); falling back to full plan",
            chunk_index,
            len(chunks),
        )
        coder_plan = full_plan or state["current_plan"]
    else:
        # Fallback: no chunks (single-pass legacy invocation)
        coder_plan = state["current_plan"]

    subgraph_input: BuildReviewState = {
        "task": state.get("task", ""),
        "current_plan": coder_plan,
        "agent_architecture": state.get("agent_architecture", ""),
        "code_diff": "",
        "workspace_path": state.get("workspace_path", ""),
        "micro_feedback": "",
        "macro_feedback": "",
        "build_verdict": "",
        "build_feedback": "",
        "build_cycle": build_cycle,
        "e2e_feedback": e2e_feedback,
        "resolved_issues": list(state.get("resolved_issues", [])),
        "persistent_rules": state.get("persistent_rules", ""),
    }
    try:
        result = build_review_app.invoke(subgraph_input)
        return {
            "current_code": result.get("code_diff", ""),
            "resolved_issues": result.get("resolved_issues", []),
            "persistent_rules": result.get("persistent_rules", ""),
        }
    finally:
        if tracer is not None:
            tracer.pop_graph()


def _advance_chunk(state: ParentState) -> dict:
    """Advance to the next chunk — increment index."""
    next_index = state.get("chunk_index", 0) + 1
    chunks = state.get("chunks", [])
    chunk = chunks[next_index] if next_index < len(chunks) else {}
    logger.info(
        "Advancing to chunk %d/%d: %s",
        next_index + 1,
        len(chunks),
        chunk.get("title", "?"),
    )
    return {"chunk_index": next_index}


@traced_route("build_review", ["advance_chunk", "e2e_test"])
def _route_after_build_review(state: ParentState) -> str:
    """After build_review: more chunks → advance, else → e2e_test."""
    chunks = state.get("chunks", [])
    chunk_index = state.get("chunk_index", 0)
    if chunk_index < len(chunks) - 1:
        return "advance_chunk"
    return "e2e_test"


@traced_route("e2e_test", ["__end__", "build_review"])
def _route_after_e2e(state: ParentState) -> str:
    """Route after e2e test: approve/skip → end, revise → build_review (up to max cycles)."""
    verdict = state.get("e2e_verdict", "")
    if verdict in ("APPROVE", "SKIP"):
        return END
    if state.get("e2e_cycle", 0) >= MAX_E2E_CYCLES:
        return END
    return "build_review"


@traced_route("discover_architecture", ["plan_review", "plan_chunker"])
def _route_after_discovery(state: ParentState) -> str:
    """After discovery: skip plan review only, never architecture discovery."""
    if state.get("skip_plan_review"):
        return "plan_chunker"
    return "plan_review"


@traced_route("__start__", ["discover_architecture"])
def _route_entry(state: ParentState) -> str:
    """Always discover architecture before any plan/build work."""
    return "discover_architecture"


def build_plan_build_review_graph() -> StateGraph:
    """Build the parent graph: discover, plan-review, plan-chunker, build-review loop, e2e-test."""
    graph = StateGraph(ParentState)

    graph.add_node("discover_architecture", discover_architecture, retry_policy=_SUBPROCESS_RETRY)
    graph.add_node("plan_review", plan_review_app)  # native subgraph
    graph.add_node("plan_chunker", chunk_plan, retry_policy=_SUBPROCESS_RETRY)
    graph.add_node("build_review", _call_build_review)
    graph.add_node("advance_chunk", _advance_chunk)
    graph.add_node("e2e_test", e2e_test, retry_policy=_SUBPROCESS_RETRY)

    # Entry routing
    graph.add_conditional_edges(
        START,
        _route_entry,
        {"discover_architecture": "discover_architecture"},
    )

    # Normal flow: discover → (plan_review | plan_chunker) → build_review
    graph.add_conditional_edges(
        "discover_architecture",
        _route_after_discovery,
        {"plan_review": "plan_review", "plan_chunker": "plan_chunker"},
    )
    graph.add_edge("plan_review", "plan_chunker")
    graph.add_edge("plan_chunker", "build_review")

    # Chunk loop: build_review → advance_chunk → build_review | e2e_test
    graph.add_conditional_edges(
        "build_review",
        _route_after_build_review,
        {"advance_chunk": "advance_chunk", "e2e_test": "e2e_test"},
    )
    graph.add_edge("advance_chunk", "build_review")

    # E2E routing: approve/skip → end, revise → build_review (last chunk re-entry)
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
