"""Variant B debate-phase nodes and the debate-aware synthesis node.

The pre-debate phases (generate, cross-review, revise) reuse Variant A's
node functions verbatim — they're imported and wired into the graph as-is.

The debate loop is:

    init_debate  →  debate_turn  ↺  (route: budget | agreement | rounds |
                                     stable_disagreement | compact | turn)
                       ↓
                record_termination  →  synthesize_with_debate

State mutation contract:
    - ``init_debate`` returns both opening messages as transcript entries.
    - ``debate_turn`` appends exactly one entry (the current speaker) and
      flips ``current_speaker``.
    - ``compact`` appends compaction summaries to the transcript as special
      entries with ``speaker == "compaction"`` so the synthesizer can still
      read a coherent log.
    - ``record_termination`` sets ``termination_reason`` and is a pure-Python
      barrier before synthesis; it never calls the LLM.
"""

from __future__ import annotations

import asyncio
import logging
import random

from langgraph_agents.pipeline.anonymize import anonymize_pair
from langgraph_agents.pipeline.artifacts import write_artifact
from langgraph_agents.pipeline.budget import over_budget
from langgraph_agents.pipeline.config import RunConfig
from langgraph_agents.pipeline.prompts import (
    DEBATE_OPENING_USER_MESSAGE,
    DEBATE_SYSTEM_PROMPT,
    SYNTHESIS_JUDGE_PROMPT,
)
from langgraph_agents.pipeline.session import AgentSession, single_query
from langgraph_agents.pipeline.state import VariantBState
from langgraph_agents.pipeline.variant_b import registry
from langgraph_agents.pipeline.variant_b.parsing import (
    parse_key_point,
    parse_stance,
    stable_disagreement,
    transcript_token_estimate,
)

logger = logging.getLogger(__name__)

MAX_COMPACTIONS = 3

_COMPACTION_PROMPT = (
    "The debate has grown long. In 300 words or less, summarise your current "
    "position: what you have argued, what you have conceded, and what you "
    "still disagree with. Do NOT advance a new argument — compaction only."
)


def _render_proposals(
    own_draft: str,
    other_draft: str,
    anonymize: bool,
    rng: random.Random,
) -> str:
    """Format the ``{proposals_section}`` of the debate primer."""
    if anonymize:
        a, b, _mapping = anonymize_pair(own_draft, other_draft, rng=rng)
        return f"## Proposal A\n{a}\n\n## Proposal B\n{b}"
    return (
        f"## Your draft\n{own_draft}\n\n"
        f"## Other reviewer's draft\n{other_draft}"
    )


# ---------------------------------------------------------------------------
# init_debate — open both sessions in parallel and capture opening statements
# ---------------------------------------------------------------------------


async def init_debate(state: VariantBState, *, config: RunConfig) -> dict:
    """Open both debater sessions and record their opening statements.

    The system prompt is kept short (role + rules + format) so the bundled
    Claude Code CLI can receive it as a command-line argument even on
    Windows, where CreateProcess caps at ~32KB. The drafts and task body
    travel in the opening USER message, which goes through the API payload
    path and is uncapped.

    Opening statements are produced in parallel (``asyncio.gather``) so
    neither side sees the other's statement before writing its own.
    """
    run_id = state["run_id"]
    anonymize = bool(
        state.get("anonymize_in_debate", config.anonymize_in_debate)
    )
    rng = random.Random(config.random_seed) if config.random_seed is not None else random.Random()

    left_draft = state.get("left_draft_v2") or state.get("left_draft_v1") or ""
    right_draft = state.get("right_draft_v2") or state.get("right_draft_v1") or ""

    left_model = config.models.debater_left or config.models.reviser_left
    right_model = config.models.debater_right or config.models.reviser_right

    # Short system prompts — role + rules only.
    left_system = DEBATE_SYSTEM_PROMPT.format(role="Reviewer 1")
    right_system = DEBATE_SYSTEM_PROMPT.format(role="Reviewer 2")

    # Long opening user messages — task + proposals + opening directive.
    left_opening = DEBATE_OPENING_USER_MESSAGE.format(
        task=state["task"],
        proposals_section=_render_proposals(left_draft, right_draft, anonymize, rng),
    )
    right_opening = DEBATE_OPENING_USER_MESSAGE.format(
        task=state["task"],
        proposals_section=_render_proposals(right_draft, left_draft, anonymize, rng),
    )

    left_session = AgentSession(
        name="left",
        system_prompt=left_system,
        cwd=state["chatroom_dir"],
        model=left_model,
    )
    right_session = AgentSession(
        name="right",
        system_prompt=right_system,
        cwd=state["chatroom_dir"],
        model=right_model,
    )
    registry.register(run_id, "left", left_session)
    registry.register(run_id, "right", right_session)

    (left_resp, left_cost), (right_resp, right_cost) = await asyncio.gather(
        left_session.start(left_opening),
        right_session.start(right_opening),
    )

    left_entry = _make_transcript_entry(
        "left", left_resp, turn=1, round_=1
    )
    right_entry = _make_transcript_entry(
        "right", right_resp, turn=2, round_=1
    )

    return {
        "debate_sessions_initialized": True,
        "anonymize_in_debate": anonymize,
        "transcript": [left_entry, right_entry],
        "transcript_token_estimate": transcript_token_estimate(
            [left_entry, right_entry]
        ),
        "current_speaker": "left",  # left opens the sequential loop
        "turn_count": 2,
        "round_count": 1,
        "left_signaled_agreement": left_entry["stance"] == "AGREE",
        "right_signaled_agreement": right_entry["stance"] == "AGREE",
        "compaction_count": 0,
        "total_cost_usd": left_cost + right_cost,
    }


def _make_transcript_entry(
    speaker: str, content: str, *, turn: int, round_: int
) -> dict:
    return {
        "speaker": speaker,
        "content": content,
        "stance": parse_stance(content),
        "key_point": parse_key_point(content),
        "turn": turn,
        "round": round_,
    }


# ---------------------------------------------------------------------------
# debate_turn — one speaker replies to the other's latest message
# ---------------------------------------------------------------------------


async def debate_turn(state: VariantBState, *, config: RunConfig) -> dict:
    """Advance the debate by one turn.

    The current speaker's session receives the other speaker's most recent
    message (anonymised if configured) plus the required-format reminder.
    """
    run_id = state["run_id"]
    speaker = state["current_speaker"]
    other = "right" if speaker == "left" else "left"

    session = registry.get_or_raise(run_id, speaker)
    transcript = state.get("transcript") or []

    last_other = next(
        (e for e in reversed(transcript) if e.get("speaker") == other),
        None,
    )
    if last_other is None:
        raise RuntimeError(
            "debate_turn: no prior message from the other speaker — did init_debate run?"
        )

    anonymize = bool(state.get("anonymize_in_debate", config.anonymize_in_debate))
    other_label = "The other reviewer" if anonymize else f"Reviewer ({other})"
    prompt = (
        f"## {other_label}'s most recent message\n{last_other['content']}\n\n"
        "Respond. End your message with the required STANCE and KEY_POINT footer."
    )

    response, cost = await session.send(prompt)

    next_turn = state.get("turn_count", 0) + 1
    prior_round = state.get("round_count", 1)
    # A round = 2 turns (left + right). Post-init, turns 3-4 are round 2, etc.
    next_round = 1 + (next_turn - 1) // 2
    entry = _make_transcript_entry(speaker, response, turn=next_turn, round_=next_round)

    new_transcript_estimate = state.get("transcript_token_estimate", 0) + int(
        transcript_token_estimate([entry])
    )

    agreement_update = {
        f"{speaker}_signaled_agreement": entry["stance"] == "AGREE",
    }
    # The OTHER speaker's agreement flag is not modified by this turn; it
    # carries forward via LangGraph's state merge.

    return {
        "transcript": [entry],  # reducer appends to the list
        "transcript_token_estimate": new_transcript_estimate,
        "current_speaker": other,
        "turn_count": next_turn,
        "round_count": max(prior_round, next_round),
        "total_cost_usd": cost,
        **agreement_update,
    }


# ---------------------------------------------------------------------------
# compact — both sides self-summarise
# ---------------------------------------------------------------------------


async def compact(state: VariantBState, *, config: RunConfig) -> dict:
    """Ask both debaters for a compact self-summary in parallel.

    Summaries are appended to the transcript as entries with
    ``speaker == "compaction"`` so the synthesizer can read them as bookmarks.
    """
    run_id = state["run_id"]
    left_session = registry.get_or_raise(run_id, "left")
    right_session = registry.get_or_raise(run_id, "right")

    (left_resp, left_cost), (right_resp, right_cost) = await asyncio.gather(
        left_session.send(_COMPACTION_PROMPT),
        right_session.send(_COMPACTION_PROMPT),
    )

    turn = state.get("turn_count", 0)
    round_ = state.get("round_count", 1)
    left_entry = {
        "speaker": "compaction",
        "by": "left",
        "content": left_resp,
        "turn": turn,
        "round": round_,
    }
    right_entry = {
        "speaker": "compaction",
        "by": "right",
        "content": right_resp,
        "turn": turn,
        "round": round_,
    }

    prior_compactions = state.get("compaction_count", 0)
    # Compaction resets the transcript token estimate — the synthesizer will
    # read the summaries as the effective record past this point.
    return {
        "transcript": [left_entry, right_entry],
        "transcript_token_estimate": transcript_token_estimate(
            [left_entry, right_entry]
        ),
        "compaction_count": prior_compactions + 1,
        "total_cost_usd": left_cost + right_cost,
    }


# ---------------------------------------------------------------------------
# record_termination — pure barrier node that names the reason
# ---------------------------------------------------------------------------


def _determine_termination(state: VariantBState, config: RunConfig) -> str:
    """Return the termination reason using the plan's priority order."""
    hit, reason = over_budget(state)
    if hit:
        return reason
    left_agree = bool(state.get("left_signaled_agreement"))
    right_agree = bool(state.get("right_signaled_agreement"))
    if left_agree and right_agree:
        return "mutual_agreement"
    if state.get("round_count", 0) >= config.max_debate_rounds:
        return "max_rounds"
    transcript = state.get("transcript") or []
    if stable_disagreement(transcript):
        return "stable_disagreement"
    return "unknown"


def record_termination(state: VariantBState, *, config: RunConfig) -> dict:
    """Set ``termination_reason`` and persist the transcript for inspection."""
    reason = _determine_termination(state, config)
    transcript = state.get("transcript") or []
    write_artifact(state, "debate_transcript.md", _render_transcript(transcript))
    return {"termination_reason": reason}


def _render_transcript(transcript: list[dict]) -> str:
    lines: list[str] = []
    for entry in transcript:
        speaker = entry.get("speaker", "?")
        turn = entry.get("turn")
        round_ = entry.get("round")
        header = f"## Turn {turn} (round {round_}) — {speaker}"
        if entry.get("by"):
            header += f" (by={entry['by']})"
        lines.append(header)
        lines.append(entry.get("content", ""))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# synthesize_with_debate — judge reads transcript + both v2 drafts
# ---------------------------------------------------------------------------


async def synthesize_with_debate(state: VariantBState, *, config: RunConfig) -> dict:
    """Produce the final response with the debate transcript as additional context."""
    task = state["task"]
    left = state.get("left_draft_v2") or state.get("left_draft_v1") or ""
    right = state.get("right_draft_v2") or state.get("right_draft_v1") or ""
    transcript = state.get("transcript") or []
    termination = state.get("termination_reason", "unknown")

    debate_section = (
        f"## Debate transcript\n{_render_transcript(transcript)}\n"
        f"## Termination reason\n{termination}\n"
    )
    system_prompt = SYNTHESIS_JUDGE_PROMPT.format(
        debate_section_or_empty=debate_section
    )
    user_message = (
        f"## Task\n{task}\n\n"
        f"## Reviewer 1 final draft\n{left}\n\n"
        f"## Reviewer 2 final draft\n{right}\n\n"
        "Produce the final response now. Treat bilateral agreement in the "
        "debate as a WEAK signal and re-evaluate independently."
    )
    response, cost = await single_query(
        system_prompt,
        user_message,
        cwd=state["chatroom_dir"],
        model=config.models.synthesizer,
    )
    write_artifact(state, "final_plan.md", response)
    return {"final_plan": response, "total_cost_usd": cost}
