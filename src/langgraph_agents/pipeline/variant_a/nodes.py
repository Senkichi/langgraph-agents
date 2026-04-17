"""Variant A phase nodes.

Each node is a thin async function: call `single_query` with the right prompt,
write the artifact to disk, return a state update with the cost delta.

The router-level budget check is handled in the graph builder; nodes do not
short-circuit on their own. The one exception is the barrier-less "start_run"
initializer which only stamps metadata and writes inputs to disk.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from langgraph_agents.pipeline.artifacts import (
    run_dir_from_state,
    write_artifact,
    write_config,
    write_task,
)
from langgraph_agents.pipeline.config import RunConfig
from langgraph_agents.pipeline.prompts import (
    CRITIC_BUILDER,
    CRITIC_CHALLENGER,
    GENERATOR_BASE,
    REVISER_BASE,
    SYNTHESIS_JUDGE_PROMPT,
)
from langgraph_agents.pipeline.session import single_query
from langgraph_agents.pipeline.state import VariantAState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase 0 — stamp run metadata and persist inputs
# ---------------------------------------------------------------------------


async def start_run(state: VariantAState, *, config: RunConfig) -> dict:
    """Persist the run inputs and stamp `run_start_time`.

    Running before the parallel fan-out guarantees the run directory and
    `config.json` / `task.md` exist before any node tries to write a draft
    into it.
    """
    write_config(config)
    write_task(config)
    # Materialize the run dir so subsequent nodes can write into it concurrently.
    run_dir_from_state(state)
    return {
        "run_start_time": datetime.now(timezone.utc).isoformat(),
        "max_total_cost_usd": config.max_total_cost_usd,
        "max_wall_clock_seconds": config.max_wall_clock_seconds,
    }


# ---------------------------------------------------------------------------
# Phase 1 — generation
# ---------------------------------------------------------------------------


async def _generate(side: str, model: str, state: VariantAState) -> dict:
    task = state["task"]
    prompt = (
        f"## Task\n{task}\n\n"
        "Produce your draft response now. Be concrete and claim-dense."
    )
    response, cost = await single_query(
        GENERATOR_BASE,
        prompt,
        cwd=state["chatroom_dir"],
        model=model,
    )
    write_artifact(state, f"{side}_draft_v1.md", response)
    return {f"{side}_draft_v1": response, "total_cost_usd": cost}


async def generate_left(state: VariantAState, *, config: RunConfig) -> dict:
    return await _generate("left", config.models.generator_left, state)


async def generate_right(state: VariantAState, *, config: RunConfig) -> dict:
    return await _generate("right", config.models.generator_right, state)


# ---------------------------------------------------------------------------
# Phase 2 — cross-review (asymmetric critics)
#
# `left` side reviews right's draft with the CHALLENGER persona.
# `right` side reviews left's draft with the BUILDER persona.
#
# The artifact field `<who>_critique_of_<whom>` names the author first, target
# second. So `left_critique_of_right` is produced by cross_review_left.
# ---------------------------------------------------------------------------


async def _cross_review(
    author: str,
    target_draft_field: str,
    output_field: str,
    artifact_filename: str,
    system_prompt: str,
    model: str,
    state: VariantAState,
) -> dict:
    target_draft = state[target_draft_field]
    task = state["task"]
    prompt = (
        f"## Task\n{task}\n\n"
        f"## Draft to review\n{target_draft}\n\n"
        "Produce your structured critique now using the CRITICAL/MAJOR/MINOR format."
    )
    response, cost = await single_query(
        system_prompt,
        prompt,
        cwd=state["chatroom_dir"],
        model=model,
    )
    write_artifact(state, artifact_filename, response)
    return {output_field: response, "total_cost_usd": cost}


async def cross_review_left(state: VariantAState, *, config: RunConfig) -> dict:
    return await _cross_review(
        author="left",
        target_draft_field="right_draft_v1",
        output_field="left_critique_of_right",
        artifact_filename="left_critique_of_right.md",
        system_prompt=CRITIC_CHALLENGER,
        model=config.models.critic_left,
        state=state,
    )


async def cross_review_right(state: VariantAState, *, config: RunConfig) -> dict:
    return await _cross_review(
        author="right",
        target_draft_field="left_draft_v1",
        output_field="right_critique_of_left",
        artifact_filename="right_critique_of_left.md",
        system_prompt=CRITIC_BUILDER,
        model=config.models.critic_right,
        state=state,
    )


# ---------------------------------------------------------------------------
# Phase 3 — revise
#
# Each side reads its OWN v1 draft plus the critique OF its draft (produced
# by the other side), and revises.
# ---------------------------------------------------------------------------


async def _revise(
    side: str,
    own_draft_field: str,
    critique_field: str,
    model: str,
    state: VariantAState,
) -> dict:
    own_draft = state[own_draft_field]
    critique = state[critique_field]
    task = state["task"]
    prompt = (
        f"## Task\n{task}\n\n"
        f"## Your prior draft\n{own_draft}\n\n"
        f"## Critique from the other reviewer\n{critique}\n\n"
        "Produce your revised draft now. Name which points you accepted and "
        "which you rejected at the top of your revision."
    )
    response, cost = await single_query(
        REVISER_BASE,
        prompt,
        cwd=state["chatroom_dir"],
        model=model,
    )
    write_artifact(state, f"{side}_draft_v2.md", response)
    return {f"{side}_draft_v2": response, "total_cost_usd": cost}


async def revise_left(state: VariantAState, *, config: RunConfig) -> dict:
    return await _revise(
        side="left",
        own_draft_field="left_draft_v1",
        critique_field="right_critique_of_left",
        model=config.models.reviser_left,
        state=state,
    )


async def revise_right(state: VariantAState, *, config: RunConfig) -> dict:
    return await _revise(
        side="right",
        own_draft_field="right_draft_v1",
        critique_field="left_critique_of_right",
        model=config.models.reviser_right,
        state=state,
    )


# ---------------------------------------------------------------------------
# Phase 4 — synthesize
# ---------------------------------------------------------------------------


async def synthesize(state: VariantAState, *, config: RunConfig) -> dict:
    """Produce the final response.

    Falls back gracefully if upstream phases were short-circuited by the
    budget guard — it prefers v2 drafts but will use v1 or empty strings if
    those are all that reached it. The ``termination_reason`` reflects
    whichever of (cost, timeout, complete) actually applies.
    """
    from langgraph_agents.pipeline.budget import over_budget

    task = state["task"]
    left = state.get("left_draft_v2") or state.get("left_draft_v1") or ""
    right = state.get("right_draft_v2") or state.get("right_draft_v1") or ""

    user_message = (
        f"## Task\n{task}\n\n"
        f"## Reviewer 1 final draft\n{left}\n\n"
        f"## Reviewer 2 final draft\n{right}\n\n"
        "Produce the final response now."
    )
    system_prompt = SYNTHESIS_JUDGE_PROMPT.format(debate_section_or_empty="")
    response, cost = await single_query(
        system_prompt,
        user_message,
        cwd=state["chatroom_dir"],
        model=config.models.synthesizer,
    )
    write_artifact(state, "final_plan.md", response)

    hit, reason = over_budget(state)
    termination = reason if hit else "complete"

    return {
        "final_plan": response,
        "total_cost_usd": cost,
        "termination_reason": termination,
    }
