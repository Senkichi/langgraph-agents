"""Variant B graph builder and entry point.

Variant B is Variant A's first three phases plus an init -> turn -> compact
loop before synthesis. The pre-debate nodes are imported verbatim from
Variant A so the two variants cannot drift out of sync.
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
from langgraph_agents.pipeline.state import VariantBState
from langgraph_agents.pipeline.variant_a import nodes as a_nodes
from langgraph_agents.pipeline.variant_b import nodes as b_nodes
from langgraph_agents.pipeline.variant_b import registry
from langgraph_agents.pipeline.variant_b.parsing import stable_disagreement

logger = logging.getLogger(__name__)

# Pre-debate nodes (mirror Variant A)
N_START = "start_run"
N_GEN_L = "generate_left"
N_GEN_R = "generate_right"
N_REVIEW_L = "cross_review_left"
N_REVIEW_R = "cross_review_right"
N_REVISE_L = "revise_left"
N_REVISE_R = "revise_right"

# Debate phase
N_INIT_DEBATE = "init_debate"
N_DEBATE_TURN = "debate_turn"
N_COMPACT = "compact"
N_RECORD_TERM = "record_termination"
N_SYNTH = "synthesize_with_debate"


def _bind(fn: Callable, config: RunConfig) -> Callable:
    """Wrap ``fn(state, *, config=...)`` so LangGraph sees a single-arg coroutine."""

    async def _async_wrapped(state):
        return await fn(state, config=config)

    def _sync_wrapped(state):
        return fn(state, config=config)

    import asyncio as _asyncio

    if _asyncio.iscoroutinefunction(fn):
        _async_wrapped.__name__ = fn.__name__
        _async_wrapped.__qualname__ = fn.__qualname__
        return _async_wrapped
    _sync_wrapped.__name__ = fn.__name__
    _sync_wrapped.__qualname__ = fn.__qualname__
    return _sync_wrapped


def _route_to_pair(state, *, next_left: str, next_right: str, synth: str) -> list[str]:
    hit, _ = over_budget(state)
    if hit:
        return [synth]
    return [next_left, next_right]


def _route_to_single(state, *, nxt: str, synth: str) -> str:
    hit, _ = over_budget(state)
    if hit:
        return synth
    return nxt


def _route_after_turn(state, *, config: RunConfig) -> str:
    """After a turn: budget > mutual agreement > max rounds > stable dis. > compact > turn."""
    hit, _ = over_budget(state)
    if hit:
        return N_RECORD_TERM
    if state.get("left_signaled_agreement") and state.get("right_signaled_agreement"):
        return N_RECORD_TERM
    if state.get("round_count", 0) >= config.max_debate_rounds:
        return N_RECORD_TERM
    if stable_disagreement(state.get("transcript") or []):
        return N_RECORD_TERM
    # Compaction check: threshold exceeded AND under hard-cap.
    if (
        state.get("transcript_token_estimate", 0)
        >= config.soft_compact_threshold_tokens
        and state.get("compaction_count", 0) < b_nodes.MAX_COMPACTIONS
    ):
        return N_COMPACT
    return N_DEBATE_TURN


def build_variant_b_graph(config: RunConfig) -> StateGraph:
    graph = StateGraph(VariantBState)

    # Pre-debate phases — reuse Variant A nodes.
    graph.add_node(N_START, _bind(a_nodes.start_run, config))
    graph.add_node(N_GEN_L, _bind(a_nodes.generate_left, config))
    graph.add_node(N_GEN_R, _bind(a_nodes.generate_right, config))
    graph.add_node(N_REVIEW_L, _bind(a_nodes.cross_review_left, config))
    graph.add_node(N_REVIEW_R, _bind(a_nodes.cross_review_right, config))
    graph.add_node(N_REVISE_L, _bind(a_nodes.revise_left, config))
    graph.add_node(N_REVISE_R, _bind(a_nodes.revise_right, config))

    # Debate nodes.
    graph.add_node(N_INIT_DEBATE, _bind(b_nodes.init_debate, config))
    graph.add_node(N_DEBATE_TURN, _bind(b_nodes.debate_turn, config))
    graph.add_node(N_COMPACT, _bind(b_nodes.compact, config))
    graph.add_node(N_RECORD_TERM, _bind(b_nodes.record_termination, config))
    graph.add_node(N_SYNTH, _bind(b_nodes.synthesize_with_debate, config))

    graph.add_edge(START, N_START)

    graph.add_conditional_edges(
        N_START,
        partial(_route_to_pair, next_left=N_GEN_L, next_right=N_GEN_R, synth=N_SYNTH),
        [N_GEN_L, N_GEN_R, N_SYNTH],
    )

    for gen in (N_GEN_L, N_GEN_R):
        graph.add_conditional_edges(
            gen,
            partial(_route_to_pair, next_left=N_REVIEW_L, next_right=N_REVIEW_R, synth=N_SYNTH),
            [N_REVIEW_L, N_REVIEW_R, N_SYNTH],
        )

    for review in (N_REVIEW_L, N_REVIEW_R):
        graph.add_conditional_edges(
            review,
            partial(_route_to_pair, next_left=N_REVISE_L, next_right=N_REVISE_R, synth=N_SYNTH),
            [N_REVISE_L, N_REVISE_R, N_SYNTH],
        )

    # Revisions converge on init_debate.
    for revise in (N_REVISE_L, N_REVISE_R):
        graph.add_conditional_edges(
            revise,
            partial(_route_to_single, nxt=N_INIT_DEBATE, synth=N_SYNTH),
            [N_INIT_DEBATE, N_SYNTH],
        )

    # Init -> first turn (or straight to termination if budget already blown).
    graph.add_conditional_edges(
        N_INIT_DEBATE,
        partial(_route_to_single, nxt=N_DEBATE_TURN, synth=N_RECORD_TERM),
        [N_DEBATE_TURN, N_RECORD_TERM],
    )

    # After a turn: route per termination/compaction logic. Use a closure
    # rather than functools.partial so LangGraph doesn't see `config` as an
    # unknown second parameter.
    def _after_turn(state):
        return _route_after_turn(state, config=config)

    graph.add_conditional_edges(
        N_DEBATE_TURN,
        _after_turn,
        [N_DEBATE_TURN, N_COMPACT, N_RECORD_TERM],
    )

    # Compaction always returns to a debate turn (or termination if now over budget).
    graph.add_conditional_edges(
        N_COMPACT,
        partial(_route_to_single, nxt=N_DEBATE_TURN, synth=N_RECORD_TERM),
        [N_DEBATE_TURN, N_RECORD_TERM],
    )

    graph.add_edge(N_RECORD_TERM, N_SYNTH)
    graph.add_edge(N_SYNTH, END)

    return graph


def compile_variant_b(config: RunConfig, checkpointer=None):
    """Compile the Variant B graph with an optional checkpointer.

    The recursion limit needs headroom for the debate turn loop: every turn
    is a superstep and we may run several turns with compactions interleaved.
    """
    from langgraph.checkpoint.memory import InMemorySaver

    cp = checkpointer if checkpointer is not None else InMemorySaver()
    return build_variant_b_graph(config).compile(checkpointer=cp)


def _initial_state(config: RunConfig) -> VariantBState:
    state: VariantBState = {
        "task": config.task,
        "chatroom_dir": config.chatroom_dir,
        "run_id": config.run_id,
        "total_cost_usd": 0.0,
        "max_total_cost_usd": config.max_total_cost_usd,
        "max_wall_clock_seconds": config.max_wall_clock_seconds,
        "run_start_time": datetime.now(timezone.utc).isoformat(),
        "anonymize_in_debate": config.anonymize_in_debate,
        "transcript": [],
        "transcript_token_estimate": 0,
        "turn_count": 0,
        "round_count": 0,
        "compaction_count": 0,
        "left_signaled_agreement": False,
        "right_signaled_agreement": False,
        "debate_sessions_initialized": False,
    }
    return state


async def run_variant_b(config: RunConfig, checkpointer=None) -> RunResult:
    """Execute the Variant B pipeline end-to-end with guaranteed cleanup."""
    app = compile_variant_b(config, checkpointer=checkpointer)
    start_ts = datetime.now(timezone.utc)
    state = _initial_state(config)

    # Turns + compactions can exceed LangGraph's default recursion limit; lift it.
    turn_budget = 2 + config.max_debate_rounds * 2 + 3  # init + turns + compactions
    recursion_limit = max(50, 20 + turn_budget * 4)

    try:
        final = await app.ainvoke(
            state,
            config={
                "configurable": {"thread_id": config.run_id},
                "recursion_limit": recursion_limit,
            },
        )
    finally:
        await registry.close_all(config.run_id)

    elapsed = elapsed_seconds(final) or (
        datetime.now(timezone.utc) - start_ts
    ).total_seconds()

    termination = final.get("termination_reason") or ""
    if not termination:
        hit, reason = over_budget(final)
        termination = reason if hit else "complete"

    artifacts_dir = str(run_dir(config.chatroom_dir, config.run_id))
    result = RunResult(
        variant="B",
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
