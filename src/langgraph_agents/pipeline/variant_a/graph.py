"""Variant A graph builder and entry point.

The graph is a fan-out / fan-in pattern. LangGraph's natural superstep model
provides the barrier: when multiple edges converge on a node, the node runs
once in the next superstep with the merged state. Explicit `defer=True`
barrier nodes are unnecessary for a purely topological join.

Budget short-circuit lives in the post-phase routers — if `over_budget`
fires, the flow jumps straight to synthesize so we still emit a final plan
and a truthful `termination_reason`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import partial
from typing import Callable

from langgraph.graph import END, START, StateGraph

from langgraph_agents.pipeline.artifacts import run_dir, write_summary
from langgraph_agents.pipeline.budget import elapsed_seconds, over_budget
from langgraph_agents.pipeline.config import RunConfig, RunResult
from langgraph_agents.pipeline.state import VariantAState
from langgraph_agents.pipeline.variant_a import nodes

logger = logging.getLogger(__name__)

# Node names — referenced by tests and routing decisions.
N_START = "start_run"
N_GEN_L = "generate_left"
N_GEN_R = "generate_right"
N_REVIEW_L = "cross_review_left"
N_REVIEW_R = "cross_review_right"
N_REVISE_L = "revise_left"
N_REVISE_R = "revise_right"
N_SYNTH = "synthesize"


def _bind(fn: Callable, config: RunConfig) -> Callable:
    """Bake RunConfig into a node coroutine so LangGraph's single-arg call works.

    A plain ``functools.partial`` leaves ``config`` visible in the wrapped
    signature, which triggers a (false) LangGraph warning that the parameter
    should be typed as ``RunnableConfig``. Wrapping in a plain coroutine
    hides the parameter entirely.
    """

    async def _wrapped(state):
        return await fn(state, config=config)

    _wrapped.__name__ = fn.__name__
    _wrapped.__qualname__ = fn.__qualname__
    return _wrapped


def _route_post_phase(state: VariantAState, *, next_left: str, next_right: str) -> list[str]:
    """After a parallel phase: either continue to the next phase pair, or
    jump straight to synthesize if the budget is blown.

    Returning a list of destinations implements the fan-out to the next phase.
    """
    hit, _reason = over_budget(state)
    if hit:
        return [N_SYNTH]
    return [next_left, next_right]


def build_variant_a_graph(config: RunConfig) -> StateGraph:
    graph = StateGraph(VariantAState)

    graph.add_node(N_START, _bind(nodes.start_run, config))
    graph.add_node(N_GEN_L, _bind(nodes.generate_left, config))
    graph.add_node(N_GEN_R, _bind(nodes.generate_right, config))
    graph.add_node(N_REVIEW_L, _bind(nodes.cross_review_left, config))
    graph.add_node(N_REVIEW_R, _bind(nodes.cross_review_right, config))
    graph.add_node(N_REVISE_L, _bind(nodes.revise_left, config))
    graph.add_node(N_REVISE_R, _bind(nodes.revise_right, config))
    graph.add_node(N_SYNTH, _bind(nodes.synthesize, config))

    graph.add_edge(START, N_START)

    # Fan out to generation pair from start_run.
    graph.add_conditional_edges(
        N_START,
        partial(_route_post_phase, next_left=N_GEN_L, next_right=N_GEN_R),
        [N_GEN_L, N_GEN_R, N_SYNTH],
    )

    # After generation, fan to cross-review. Both gen_left and gen_right route
    # to the same decision function, but LangGraph batches convergent edges so
    # cross_review_left and cross_review_right each still run once.
    graph.add_conditional_edges(
        N_GEN_L,
        partial(_route_post_phase, next_left=N_REVIEW_L, next_right=N_REVIEW_R),
        [N_REVIEW_L, N_REVIEW_R, N_SYNTH],
    )
    graph.add_conditional_edges(
        N_GEN_R,
        partial(_route_post_phase, next_left=N_REVIEW_L, next_right=N_REVIEW_R),
        [N_REVIEW_L, N_REVIEW_R, N_SYNTH],
    )

    # After cross-review, fan to revision.
    graph.add_conditional_edges(
        N_REVIEW_L,
        partial(_route_post_phase, next_left=N_REVISE_L, next_right=N_REVISE_R),
        [N_REVISE_L, N_REVISE_R, N_SYNTH],
    )
    graph.add_conditional_edges(
        N_REVIEW_R,
        partial(_route_post_phase, next_left=N_REVISE_L, next_right=N_REVISE_R),
        [N_REVISE_L, N_REVISE_R, N_SYNTH],
    )

    # Revisions converge on synthesize.
    graph.add_edge(N_REVISE_L, N_SYNTH)
    graph.add_edge(N_REVISE_R, N_SYNTH)

    graph.add_edge(N_SYNTH, END)

    return graph


def compile_variant_a(config: RunConfig, checkpointer=None):
    """Compile the Variant A graph with an optional checkpointer."""
    from langgraph.checkpoint.memory import InMemorySaver

    cp = checkpointer if checkpointer is not None else InMemorySaver()
    return build_variant_a_graph(config).compile(checkpointer=cp)


def _initial_state(config: RunConfig) -> VariantAState:
    state: VariantAState = {
        "task": config.task,
        "chatroom_dir": config.chatroom_dir,
        "run_id": config.run_id,
        "total_cost_usd": 0.0,
        "max_total_cost_usd": config.max_total_cost_usd,
        "max_wall_clock_seconds": config.max_wall_clock_seconds,
        "run_start_time": datetime.now(timezone.utc).isoformat(),
    }
    return state


async def run_variant_a(config: RunConfig, checkpointer=None) -> RunResult:
    """Execute the full Variant A pipeline and return a `RunResult`.

    The caller is responsible for persisting the return value via
    `write_summary`; this function doesn't write `summary.json` itself so the
    eval matrix runner can choose whether to mark a run complete.
    """
    app = compile_variant_a(config, checkpointer=checkpointer)
    start_ts = datetime.now(timezone.utc)
    state = _initial_state(config)
    final = await app.ainvoke(
        state, config={"configurable": {"thread_id": config.run_id}}
    )
    elapsed = elapsed_seconds(final) or (
        datetime.now(timezone.utc) - start_ts
    ).total_seconds()

    termination = final.get("termination_reason", "")
    if not termination:
        hit, reason = over_budget(final)
        termination = reason if hit else "complete"

    artifacts_dir = str(run_dir(config.chatroom_dir, config.run_id))
    result = RunResult(
        variant="A",
        run_id=config.run_id,
        final_plan=final.get("final_plan", ""),
        total_cost_usd=float(final.get("total_cost_usd", 0.0)),
        wall_clock_seconds=elapsed,
        termination_reason=termination,
        artifacts_dir=artifacts_dir,
        config=config,
    )
    write_summary(result)
    return result
