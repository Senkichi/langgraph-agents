"""TypedDict state schemas for Variant A and Variant B pipelines.

`SharedState` captures the phases both variants run (generate -> cross-critique
-> revise -> synthesize). `VariantAState` is the shared state verbatim.
`VariantBState` adds debate-phase fields between revise and synthesize.

Cost is reduced across nodes via `operator.add` so parallel fan-out nodes can
each contribute their delta. Transcript in Variant B is similarly append-only.
"""

from __future__ import annotations

from operator import add
from typing import Annotated, Literal

from typing_extensions import TypedDict


class SharedState(TypedDict, total=False):
    """Fields common to Variant A and Variant B.

    `total=False` lets nodes populate fields progressively without requiring
    every run to initialise every key.
    """

    # Inputs
    task: str
    chatroom_dir: str
    run_id: str

    # Phase 1/2/3 outputs
    left_draft_v1: str
    right_draft_v1: str
    left_critique_of_right: str
    right_critique_of_left: str
    left_draft_v2: str
    right_draft_v2: str

    # Cost / time tracking — reduced across parallel nodes
    total_cost_usd: Annotated[float, add]
    max_total_cost_usd: float
    max_wall_clock_seconds: int
    run_start_time: str  # ISO-8601 UTC timestamp

    # Final output
    final_plan: str
    termination_reason: str


class VariantAState(SharedState, total=False):
    """No additional fields — A flows straight from revise to synthesize."""


class VariantBState(SharedState, total=False):
    """Debate-phase state fields layered onto the shared phases."""

    debate_sessions_initialized: bool

    # Transcript is append-only across debate turns.
    transcript: Annotated[list[dict], add]
    transcript_token_estimate: int
    current_speaker: Literal["left", "right"]
    turn_count: int
    round_count: int
    left_signaled_agreement: bool
    right_signaled_agreement: bool
    compaction_count: int
    anonymize_in_debate: bool
