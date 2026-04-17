"""Tests for pipeline.state TypedDict contracts.

These are structural rather than runtime — verify the reducer annotations
exist where LangGraph parallel fan-out nodes need them.
"""

from __future__ import annotations

from typing import get_type_hints

from langgraph_agents.pipeline.state import (
    SharedState,
    VariantAState,
    VariantBState,
)


def test_shared_state_has_required_keys():
    hints = get_type_hints(SharedState, include_extras=True)
    for key in (
        "task",
        "chatroom_dir",
        "run_id",
        "left_draft_v1",
        "right_draft_v1",
        "left_critique_of_right",
        "right_critique_of_left",
        "left_draft_v2",
        "right_draft_v2",
        "total_cost_usd",
        "max_total_cost_usd",
        "max_wall_clock_seconds",
        "run_start_time",
        "final_plan",
        "termination_reason",
    ):
        assert key in hints, f"SharedState missing key: {key}"


def test_variant_a_state_adds_no_new_keys():
    shared_keys = set(get_type_hints(SharedState, include_extras=True).keys())
    a_keys = set(get_type_hints(VariantAState, include_extras=True).keys())
    assert a_keys == shared_keys


def test_variant_b_state_adds_debate_keys():
    shared_keys = set(get_type_hints(SharedState, include_extras=True).keys())
    b_keys = set(get_type_hints(VariantBState, include_extras=True).keys())
    added = b_keys - shared_keys
    for key in (
        "debate_sessions_initialized",
        "transcript",
        "transcript_token_estimate",
        "current_speaker",
        "turn_count",
        "round_count",
        "left_signaled_agreement",
        "right_signaled_agreement",
        "compaction_count",
        "anonymize_in_debate",
    ):
        assert key in added, f"VariantBState missing debate key: {key}"


def test_accumulator_annotations_present():
    """total_cost_usd and transcript must carry Annotated[..., add] for fan-out reducers."""
    from typing import get_args

    hints = get_type_hints(VariantBState, include_extras=True)
    cost_args = get_args(hints["total_cost_usd"])
    # Annotated[float, add] -> get_args returns (float, <builtin function add>)
    assert len(cost_args) >= 2
    assert cost_args[0] is float

    transcript_args = get_args(hints["transcript"])
    assert len(transcript_args) >= 2
    assert transcript_args[0] == list[dict]
