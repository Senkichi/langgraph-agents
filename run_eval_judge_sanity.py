"""Experiment 003 Phase 0.1 — judge self-preference bias sanity check.

Re-judges six already-decided cross-quadrant cells from
``logs/eval_2a/judgments.jsonl`` (Variant B Opus 4.6 vs Variant B Opus 4.7,
round-matched at 3rnd and 7rnd, all three tasks) using a non-Claude judge
(DeepSeek V4 Pro by default). The Claude judges (opus + sonnet) returned
12/12 unanimous wins for the 4.7 side on these cells; this script tests
whether that unanimity survives a cross-family judge.

Design follows ``docs/experiment_003_plan.md`` §3.1:

- Same ``JUDGE_PAIRWISE_PROMPT`` and ``parse_judgement`` parsing as the
  production eval — every variable held constant except judge identity.
- Position-bias correction: each cell judged twice (natural + swapped); a
  flipped vote collapses to "tie".
- Output written atomically to ``logs/eval_judge_sanity/results.json`` with
  per-cell records, raw reasoning text, and an aggregate scoring against
  the §3.1 decision rule (robust / inflated / refuted).

The judge transport is shared with the production eval pipeline via
``langgraph_agents.eval.judge_backend.query_openai_compatible`` — pass any
model id the backend recognises (deepseek-*, gpt-*, o*-*) via ``--model``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from langgraph_agents.eval.judge_backend import classify_by_model, query_openai_compatible
from langgraph_agents.eval.judge_pairwise import (
    JUDGE_SYSTEM_PROMPT,
    JudgeVote,
    parse_judgement,
)
from langgraph_agents.pipeline.prompts import JUDGE_PAIRWISE_PROMPT

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent
MATRIX_DIR = REPO_ROOT / "logs" / "matrix_2a_rounds"
OUT_DIR = REPO_ROOT / "logs" / "eval_judge_sanity"

DEFAULT_MODEL = "deepseek-v4-pro"

# Six cross-quadrant cells. Round-matched (3rnd-vs-3rnd, 7rnd-vs-7rnd) so
# the only varying axis is model generation. config_a is always 4.6,
# config_b is always 4.7; preferred="B" means the judge picked 4.7.
TASKS = ("architectural_review_auth", "design_testing_strategy", "migration_postgres_dynamo")
CONFIG_PAIRS = (("B-opus46-3rnd", "B-opus47-3rnd"), ("B-opus46-7rnd", "B-opus47-7rnd"))


@dataclass(frozen=True)
class Cell:
    task_id: str
    config_a: str  # 4.6 side
    config_b: str  # 4.7 side


@dataclass(frozen=True)
class CellResult:
    task_id: str
    config_a: str
    config_b: str
    judge_model: str
    natural_preference: str
    swapped_preference: str
    natural_confidence: str
    swapped_confidence: str
    natural_reasoning: str
    swapped_reasoning: str
    preferred: Literal["A", "B", "tie"]
    position_bias_detected: bool
    claude_consensus_preferred: Literal["A", "B", "tie"]
    agrees_with_claude: bool


def _read_response(config: str, task: str) -> str:
    p = MATRIX_DIR / config / f"{config}__{task}" / "final_plan.md"
    if not p.exists():
        raise FileNotFoundError(f"missing artifact: {p}")
    return p.read_text(encoding="utf-8")


def _read_task(task: str) -> str:
    # Prefer the corpus file (canonical). Fall back to the per-run task.md.
    corpus = REPO_ROOT / "src" / "langgraph_agents" / "eval" / "corpus" / f"{task}.md"
    if corpus.exists():
        body = corpus.read_text(encoding="utf-8")
        # Strip the "## Expected response shape" rubric — judge must not see it.
        head = body.split("## Expected response shape", 1)[0]
        # Strip the leading "# Task: <name>" line for parity with the pipeline.
        lines = head.splitlines()
        if lines and lines[0].lstrip().startswith("# Task"):
            lines = lines[1:]
        return "\n".join(lines).strip()
    fallback = MATRIX_DIR / "B-opus46-3rnd" / f"B-opus46-3rnd__{task}" / "task.md"
    return fallback.read_text(encoding="utf-8")


def _claude_consensus(cell: Cell) -> Literal["A", "B", "tie"]:
    """The collapsed Claude-judge verdict (opus + sonnet) for this cell."""
    src = REPO_ROOT / "logs" / "eval_2a" / "judgments.jsonl"
    pref: set[str] = set()
    for line in src.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        if (
            rec["task_id"] == cell.task_id
            and rec["config_a"] == cell.config_a
            and rec["config_b"] == cell.config_b
        ):
            pref.add(rec["preferred"])
    if not pref:
        raise RuntimeError(f"no Claude judgments found for {cell}")
    if len(pref) > 1:
        return "tie"
    only = next(iter(pref))
    return only  # type: ignore[return-value]


async def _judge_once(*, task_body: str, response_x: str, response_y: str, model: str, swapped: bool) -> JudgeVote:
    """Single judge call via the shared backend. Same wire path as production eval."""
    prompt = JUDGE_PAIRWISE_PROMPT.format(task=task_body, response_x=response_x, response_y=response_y)
    text = await query_openai_compatible(
        system_prompt=JUDGE_SYSTEM_PROMPT,
        user_message=prompt,
        model=model,
    )
    return parse_judgement(text, judge_model=model, swapped=swapped)


def _collapse(natural: JudgeVote, swapped: JudgeVote) -> tuple[Literal["A", "B", "tie"], bool]:
    """Same X/Y → A/B mapping the production eval uses."""

    def to_ab(vote: JudgeVote) -> Literal["A", "B", "tie"]:
        if vote.preference in ("UNPARSEABLE", "TIE"):
            return "tie"
        if vote.swapped:
            return "B" if vote.preference == "X" else "A"
        return "A" if vote.preference == "X" else "B"

    nat = to_ab(natural)
    swp = to_ab(swapped)
    bias = nat != swp and nat != "tie" and swp != "tie"
    if bias:
        return "tie", True
    return (nat if nat != "tie" else swp), False


async def _run_async(*, model: str, force: bool) -> int:
    out_path = OUT_DIR / "results.json"
    if out_path.exists() and not force:
        logger.error("output already exists at %s — pass --force to overwrite", out_path)
        return 2

    cells = [Cell(task, a, b) for (a, b) in CONFIG_PAIRS for task in TASKS]
    logger.info("planned cells: %d (× 2 orders = %d API calls)", len(cells), len(cells) * 2)
    for c in cells:
        cons = _claude_consensus(c)
        logger.info("  %s | %s vs %s | Claude says: %s", c.task_id, c.config_a, c.config_b, cons)

    backend = classify_by_model(model)
    if backend == "claude_cli":
        raise RuntimeError(
            f"model {model!r} resolves to the Claude CLI transport — this script "
            "is designed to test a non-Claude (cross-family) judge against the "
            "Claude-judge baseline. Pick a deepseek-* / gpt-* / o*-* model."
        )
    logger.info("judge model=%s (provider=%s)", model, backend.provider)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    results: list[CellResult] = []
    for i, cell in enumerate(cells, 1):
        logger.info("[%d/%d] judging %s : %s vs %s", i, len(cells), cell.task_id, cell.config_a, cell.config_b)
        task_body = _read_task(cell.task_id)
        resp_a = _read_response(cell.config_a, cell.task_id)
        resp_b = _read_response(cell.config_b, cell.task_id)

        natural = await _judge_once(
            task_body=task_body, response_x=resp_a, response_y=resp_b, model=model, swapped=False
        )
        swapped = await _judge_once(
            task_body=task_body, response_x=resp_b, response_y=resp_a, model=model, swapped=True
        )
        preferred, bias = _collapse(natural, swapped)
        consensus = _claude_consensus(cell)
        results.append(
            CellResult(
                task_id=cell.task_id,
                config_a=cell.config_a,
                config_b=cell.config_b,
                judge_model=model,
                natural_preference=natural.preference,
                swapped_preference=swapped.preference,
                natural_confidence=natural.confidence,
                swapped_confidence=swapped.confidence,
                natural_reasoning=natural.reasoning,
                swapped_reasoning=swapped.reasoning,
                preferred=preferred,
                position_bias_detected=bias,
                claude_consensus_preferred=consensus,
                agrees_with_claude=(preferred == consensus),
            )
        )
        logger.info(
            "    judge verdict: %s (bias=%s) | Claude consensus: %s | agrees=%s",
            preferred, bias, consensus, preferred == consensus,
        )

    n_total = len(results)
    n_agree = sum(1 for r in results if r.agrees_with_claude)
    n_b_wins = sum(1 for r in results if r.preferred == "B")
    n_a_wins = sum(1 for r in results if r.preferred == "A")
    n_tie = sum(1 for r in results if r.preferred == "tie")
    n_bias = sum(1 for r in results if r.position_bias_detected)

    # Decision rule per docs/experiment_003_plan.md §3.1. Win-rate for the
    # 4.7 side with ties counted as 0.5.
    judge_pref_47 = (n_b_wins + 0.5 * n_tie) / n_total if n_total else 0.0
    if judge_pref_47 >= 0.85:
        verdict = "robust"
    elif judge_pref_47 >= 0.55:
        verdict = "inflated"
    else:
        verdict = "refuted"

    aggregate = {
        "provider": backend.provider,
        "judge_model": model,
        "n_cells": n_total,
        "n_agree_with_claude": n_agree,
        "n_b_wins": n_b_wins,
        "n_a_wins": n_a_wins,
        "n_tie": n_tie,
        "n_position_bias": n_bias,
        "judge_pref_for_4_7": round(judge_pref_47, 3),
        "verdict": verdict,
        "decision_rule": "robust >=0.85 / inflated 0.55-0.85 / refuted <0.55",
    }

    payload = {
        "experiment": "003-phase-0.1-judge-bias-sanity",
        "claude_baseline_unanimity": "12/12 in favor of 4.7 (B side) across opus + sonnet judges",
        "aggregate": aggregate,
        "cells": [asdict(r) for r in results],
    }

    tmp = out_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(out_path)
    logger.info("wrote %s (verdict=%s, judge-pref-4.7=%.2f)", out_path, verdict, judge_pref_47)
    return 0


def _dry_run(model: str) -> int:
    cells = [Cell(task, a, b) for (a, b) in CONFIG_PAIRS for task in TASKS]
    logger.info("planned cells: %d (× 2 orders = %d API calls)", len(cells), len(cells) * 2)
    for c in cells:
        cons = _claude_consensus(c)
        logger.info("  %s | %s vs %s | Claude says: %s", c.task_id, c.config_a, c.config_b, cons)
    backend = classify_by_model(model)
    if backend == "claude_cli":
        logger.info("model %s resolves to Claude CLI — not a valid cross-family judge", model)
    else:
        logger.info("model=%s provider=%s base_url=%s", model, backend.provider, backend.base_url or "<default>")
    logger.info("dry-run mode — no API calls dispatched")
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"judge model id; transport is inferred from the prefix (default: {DEFAULT_MODEL})",
    )
    p.add_argument("--dry-run", action="store_true", help="list planned calls, do not invoke the API")
    p.add_argument("--force", action="store_true", help="overwrite an existing results.json")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args(argv)
    if args.dry_run:
        return _dry_run(args.model)
    return asyncio.run(_run_async(model=args.model, force=args.force))


if __name__ == "__main__":
    sys.exit(main())
