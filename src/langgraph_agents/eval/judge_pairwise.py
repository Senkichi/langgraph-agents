"""Pairwise preference judging with position-bias detection and multi-judge support.

For a given ``(task, response_x, response_y)`` triple we ask a judge which
response is stronger. The judge's ``PREFERENCE`` must be parsed strictly —
an unparseable output is reported, not silently mapped to TIE.

Position bias is real and measurable: running the same comparison in both
orders and checking for preference flip is cheap insurance. Multi-judge
cross-checking is the other lever; we expose a helper ``judge_multi`` that
runs every (order × judge) combination and returns a structured result.

Two transports are supported, dispatched by model id in
``judge_backend.classify_by_model``:

* Claude CLI (``opus``/``sonnet``/``haiku`` aliases or ``claude-*`` IDs) →
  :func:`langgraph_agents.pipeline.session.single_query`.
* OpenAI-compatible API (``deepseek-*``, ``gpt-*``, ``o*-*``) →
  :func:`langgraph_agents.eval.judge_backend.query_openai_compatible`.

The dispatch lives inside :func:`judge_single` so callers do not need to
care which transport they hit. ``single_query`` remains imported here so
existing tests that patch
``langgraph_agents.eval.judge_pairwise.single_query`` continue to work for
the Claude path.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Literal

from langgraph_agents.eval.judge_backend import is_openai_compatible, query_openai_compatible
from langgraph_agents.pipeline.prompts import JUDGE_PAIRWISE_PROMPT
from langgraph_agents.pipeline.session import single_query

logger = logging.getLogger(__name__)

Preference = Literal["X", "Y", "TIE", "UNPARSEABLE"]
Confidence = Literal["high", "medium", "low", "unknown"]

_PREF_RE = re.compile(r"^\s*PREFERENCE\s*:\s*(\S+?)\s*$", re.IGNORECASE | re.MULTILINE)
_CONF_RE = re.compile(r"^\s*CONFIDENCE\s*:\s*(\S+?)\s*$", re.IGNORECASE | re.MULTILINE)
_REASON_RE = re.compile(
    r"^\s*REASONING\s*:\s*(.+?)(?=\n\s*\n|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)

_VALID_PREFS = {"X", "Y", "TIE"}
_VALID_CONFS = {"high", "medium", "low"}


@dataclass(frozen=True)
class JudgeVote:
    """One judge's answer for one (X, Y) ordering."""

    preference: Preference
    confidence: Confidence
    reasoning: str
    judge_model: str
    # Tracks whether X/Y were presented in their natural order (X=first, Y=second)
    # or swapped. Always recorded so callers can filter by orientation.
    swapped: bool


@dataclass(frozen=True)
class PairwiseOutcome:
    """Collapsed judgment for one (task, config_a, config_b, judge_model) tuple.

    ``preferred`` is the winner normalised back to ("A", "B", or "tie"):
      - position_bias_detected is True if the judge flipped its vote when the
        order flipped, in which case ``preferred`` is reported as "tie".
    """

    task_id: str
    config_a: str
    config_b: str
    judge_model: str
    preferred: Literal["A", "B", "tie"]
    confidence_natural: Confidence
    confidence_swapped: Confidence
    position_bias_detected: bool
    votes: tuple[JudgeVote, ...] = field(default_factory=tuple)


def parse_judgement(text: str, *, judge_model: str, swapped: bool) -> JudgeVote:
    """Parse a judge response. Returns a ``JudgeVote`` with UNPARSEABLE
    preference when the expected fields are missing or malformed.
    """
    pref_match = _PREF_RE.search(text or "")
    conf_match = _CONF_RE.search(text or "")
    reason_match = _REASON_RE.search(text or "")

    pref_raw = pref_match.group(1).strip().upper().rstrip(".") if pref_match else ""
    preference: Preference = (
        pref_raw if pref_raw in _VALID_PREFS else "UNPARSEABLE"  # type: ignore[assignment]
    )

    conf_raw = conf_match.group(1).strip().lower().rstrip(".") if conf_match else ""
    confidence: Confidence = (
        conf_raw if conf_raw in _VALID_CONFS else "unknown"  # type: ignore[assignment]
    )

    reasoning = reason_match.group(1).strip() if reason_match else ""
    return JudgeVote(
        preference=preference,
        confidence=confidence,
        reasoning=reasoning,
        judge_model=judge_model,
        swapped=swapped,
    )


def _render_prompt(task: str, response_x: str, response_y: str) -> str:
    return JUDGE_PAIRWISE_PROMPT.format(
        task=task, response_x=response_x, response_y=response_y
    )


JUDGE_SYSTEM_PROMPT: str = (
    "You are a strict, calibrated judge comparing AI responses. "
    "Follow the required output format exactly."
)


async def judge_single(
    *,
    task: str,
    response_x: str,
    response_y: str,
    judge_model: str,
    cwd: str,
    swapped: bool = False,
) -> JudgeVote:
    """One judge call for one orientation. No bias mitigation on its own.

    Dispatches by model id: ``deepseek-*`` / ``gpt-*`` / ``o*-*`` go through
    the OpenAI-compatible path; everything else (``opus``/``sonnet``/``haiku``
    aliases plus ``claude-*`` explicit IDs) goes through the Claude CLI via
    :func:`single_query`.
    """
    prompt = _render_prompt(task, response_x, response_y)
    if is_openai_compatible(judge_model):
        response = await query_openai_compatible(
            system_prompt=JUDGE_SYSTEM_PROMPT,
            user_message=prompt,
            model=judge_model,
        )
    else:
        response, _cost = await single_query(
            system_prompt=JUDGE_SYSTEM_PROMPT,
            user_message=prompt,
            cwd=cwd,
            model=judge_model,
        )
    return parse_judgement(response, judge_model=judge_model, swapped=swapped)


def _collapse_votes(
    votes: tuple[JudgeVote, JudgeVote],
    *,
    config_a: str,
    config_b: str,
) -> tuple[Literal["A", "B", "tie"], Confidence, Confidence, bool]:
    """Reduce natural-order + swapped-order votes into a single outcome.

    We map X/Y back to A/B using ``swapped``:
      - swapped=False: X = config_a, Y = config_b
      - swapped=True:  X = config_b, Y = config_a
    """
    natural = next(v for v in votes if not v.swapped)
    swapped = next(v for v in votes if v.swapped)

    def _to_ab(vote: JudgeVote) -> Literal["A", "B", "tie"]:
        if vote.preference == "UNPARSEABLE":
            return "tie"
        if vote.preference == "TIE":
            return "tie"
        if vote.swapped:
            return "B" if vote.preference == "X" else "A"
        return "A" if vote.preference == "X" else "B"

    nat_pref = _to_ab(natural)
    swp_pref = _to_ab(swapped)

    position_bias = (
        nat_pref != swp_pref
        and nat_pref != "tie"
        and swp_pref != "tie"
    )
    if position_bias:
        preferred: Literal["A", "B", "tie"] = "tie"
    else:
        # If one side is tie, trust the non-tie side; otherwise they agree.
        preferred = nat_pref if nat_pref != "tie" else swp_pref

    return preferred, natural.confidence, swapped.confidence, position_bias


async def judge_pair_with_position_check(
    *,
    task_id: str,
    task_body: str,
    response_a: str,
    response_b: str,
    config_a: str,
    config_b: str,
    judge_model: str,
    cwd: str,
) -> PairwiseOutcome:
    """Run the same comparison in both orders with one judge model.

    Position bias is declared when the judge's mapped preference flips. In
    that case ``preferred`` is "tie" and ``position_bias_detected`` is True.
    """
    natural_vote = await judge_single(
        task=task_body,
        response_x=response_a,
        response_y=response_b,
        judge_model=judge_model,
        cwd=cwd,
        swapped=False,
    )
    swapped_vote = await judge_single(
        task=task_body,
        response_x=response_b,
        response_y=response_a,
        judge_model=judge_model,
        cwd=cwd,
        swapped=True,
    )
    preferred, conf_nat, conf_swp, position_bias = _collapse_votes(
        (natural_vote, swapped_vote), config_a=config_a, config_b=config_b
    )
    return PairwiseOutcome(
        task_id=task_id,
        config_a=config_a,
        config_b=config_b,
        judge_model=judge_model,
        preferred=preferred,
        confidence_natural=conf_nat,
        confidence_swapped=conf_swp,
        position_bias_detected=position_bias,
        votes=(natural_vote, swapped_vote),
    )


async def judge_multi(
    *,
    task_id: str,
    task_body: str,
    response_a: str,
    response_b: str,
    config_a: str,
    config_b: str,
    judge_models: list[str],
    cwd: str,
) -> list[PairwiseOutcome]:
    """Run the pairwise-with-check against every judge model sequentially.

    Sequential rather than parallel because judging volume is already high;
    the matrix runner parallelises at the run level, not the judge level.
    """
    outcomes: list[PairwiseOutcome] = []
    for model in judge_models:
        outcome = await judge_pair_with_position_check(
            task_id=task_id,
            task_body=task_body,
            response_a=response_a,
            response_b=response_b,
            config_a=config_a,
            config_b=config_b,
            judge_model=model,
            cwd=cwd,
        )
        outcomes.append(outcome)
    return outcomes
