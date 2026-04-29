"""Experiment 003 Phase 0.1 — judge self-preference bias sanity check.

Re-judges six already-decided cross-quadrant cells from
``logs/eval_2a/judgments.jsonl`` (Variant B Opus 4.6 vs Variant B Opus 4.7,
round-matched at 3rnd and 7rnd, all three tasks) using a non-Claude judge
(DeepSeek V4 Pro by default — same OpenAI-compatible API surface, ~6× cheaper
than GPT-4o, and the cost margin matters because Phase 0.1 may escalate to a
permanent third judge across Phases 2–3 if it finds bias). The Claude judges
(opus + sonnet) returned 12/12 unanimous wins for the 4.7 side on these cells;
this script tests whether that unanimity survives a cross-family judge.

Design follows ``docs/experiment_003_plan.md`` §3.1:

- Same ``JUDGE_PAIRWISE_PROMPT`` and ``parse_judgement`` parsing as the
  Claude pipeline — every variable held constant except judge identity.
- Position-bias correction: each cell judged twice (natural + swapped); a
  flipped vote collapses to "tie" the same way the Claude eval does.
- Output written atomically to ``logs/eval_judge_sanity/results.json`` with
  both per-cell records and an aggregate. The decision rule from §3.1 is
  evaluated and recorded so the outcome is unambiguous.

Provider routing is env-driven so the same script can run against any
OpenAI-compatible endpoint without code changes:

  JUDGE_SANITY_PROVIDER  one of: deepseek (default), openai, custom
  JUDGE_SANITY_MODEL     model id (defaults: deepseek-v4-pro / gpt-4o-2024-11-20)
  JUDGE_SANITY_BASE_URL  override base_url (used when PROVIDER=custom)
  JUDGE_SANITY_API_KEY   override env var name (used when PROVIDER=custom)

Cost (DeepSeek V4 Pro, current promo pricing): ~12 calls × ~$0.007 ≈ $0.08.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

# Reuse the production judge primitives so the only thing that varies is
# the model that emits the verdict.
from langgraph_agents.eval.judge_pairwise import parse_judgement
from langgraph_agents.pipeline.prompts import JUDGE_PAIRWISE_PROMPT

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent
MATRIX_DIR = REPO_ROOT / "logs" / "matrix_2a_rounds"
OUT_DIR = REPO_ROOT / "logs" / "eval_judge_sanity"

# Six cross-quadrant cells. Round-matched (3rnd-vs-3rnd, 7rnd-vs-7rnd) so
# the only varying axis is model generation. config_a is always 4.6,
# config_b is always 4.7; preferred="B" means the judge picked 4.7.
TASKS = ("architectural_review_auth", "design_testing_strategy", "migration_postgres_dynamo")
CONFIG_PAIRS = (("B-opus46-3rnd", "B-opus47-3rnd"), ("B-opus46-7rnd", "B-opus47-7rnd"))

JUDGE_SYSTEM_PROMPT = (
    "You are a strict, calibrated judge comparing AI responses. "
    "Follow the required output format exactly."
)

# Provider routing — every entry is OpenAI-compatible at the wire level.
PROVIDERS: dict[str, dict[str, str | None]] = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-v4-pro",
    },
    "openai": {
        "base_url": None,  # SDK default
        "api_key_env": "OPENAI_API_KEY",
        "default_model": "gpt-4o-2024-11-20",
    },
}


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    base_url: str | None
    api_key: str
    model: str


def _resolve_provider(model_override: str | None, provider_override: str | None) -> ProviderConfig:
    """Pick provider/base_url/api_key/model from CLI args + env vars.

    PROVIDER=custom uses JUDGE_SANITY_BASE_URL + JUDGE_SANITY_API_KEY_ENV +
    JUDGE_SANITY_MODEL — the escape hatch for any other OpenAI-compatible
    endpoint (Azure, OpenRouter, a vLLM host, etc.).
    """
    provider = provider_override or os.environ.get("JUDGE_SANITY_PROVIDER", "deepseek")
    if provider == "custom":
        base_url = os.environ.get("JUDGE_SANITY_BASE_URL")
        key_env = os.environ.get("JUDGE_SANITY_API_KEY_ENV", "JUDGE_SANITY_API_KEY")
        api_key = os.environ.get(key_env, "")
        model = model_override or os.environ.get("JUDGE_SANITY_MODEL", "")
        if not (base_url and api_key and model):
            raise RuntimeError(
                "PROVIDER=custom requires JUDGE_SANITY_BASE_URL, "
                f"{key_env}, and JUDGE_SANITY_MODEL (or --model) to all be set"
            )
        return ProviderConfig(provider, base_url, api_key, model)
    if provider not in PROVIDERS:
        raise RuntimeError(f"unknown provider {provider!r}; known: {sorted(PROVIDERS)} or 'custom'")
    cfg = PROVIDERS[provider]
    key_env = cfg["api_key_env"]
    assert key_env is not None
    api_key = os.environ.get(key_env, "")
    if not api_key:
        raise RuntimeError(f"{key_env} not set (provider={provider})")
    default_model = cfg["default_model"]
    assert default_model is not None
    model = model_override or os.environ.get("JUDGE_SANITY_MODEL", default_model)
    return ProviderConfig(provider, cfg["base_url"], api_key, model)


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
    natural_preference: str  # raw X/Y/TIE/UNPARSEABLE from natural-order call
    swapped_preference: str  # raw X/Y/TIE/UNPARSEABLE from swapped-order call
    natural_confidence: str
    swapped_confidence: str
    natural_reasoning: str
    swapped_reasoning: str
    preferred: Literal["A", "B", "tie"]
    position_bias_detected: bool
    claude_consensus_preferred: Literal["A", "B", "tie"]  # what Claude judges said
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
        # Also strip the leading "# Task: <name>" line for parity with the pipeline.
        lines = head.splitlines()
        if lines and lines[0].lstrip().startswith("# Task"):
            lines = lines[1:]
        return "\n".join(lines).strip()
    fallback = MATRIX_DIR / "B-opus46-3rnd" / f"B-opus46-3rnd__{task}" / "task.md"
    return fallback.read_text(encoding="utf-8")


def _claude_consensus(cell: Cell) -> Literal["A", "B", "tie"]:
    """The collapsed Claude-judge verdict (opus + sonnet) for this cell.

    All six cells are 12/12 unanimous in the existing ``logs/eval_2a/judgments.jsonl``;
    we look it up rather than hard-code, so a corrupted source file fails loudly.
    """
    src = REPO_ROOT / "logs" / "eval_2a" / "judgments.jsonl"
    pref: set[str] = set()
    for line in src.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        if rec["task_id"] == cell.task_id and rec["config_a"] == cell.config_a and rec["config_b"] == cell.config_b:
            pref.add(rec["preferred"])
    if not pref:
        raise RuntimeError(f"no Claude judgments found for {cell}")
    if len(pref) > 1:
        return "tie"
    only = next(iter(pref))
    return only  # type: ignore[return-value]


def _judge_once(client, *, task_body: str, response_x: str, response_y: str, model: str, swapped: bool):
    """Single judge call. Returns the parsed JudgeVote.

    ``max_tokens`` must be generous because thinking-mode models (DeepSeek V4
    Pro, OpenAI o-series) consume completion budget on internal reasoning
    before emitting any visible content. The first run of this script used
    max_tokens=600 and every call returned empty ``content`` because the
    model spent the whole budget reasoning. 8000 is well within DeepSeek V4's
    384K cap and is only billed on tokens actually emitted.

    If ``content`` still comes back empty but ``reasoning_content`` is
    populated, we attempt a last-ditch parse against the reasoning body —
    the model often restates its answer in chain-of-thought even when it
    fails to land the formatted block.
    """
    prompt = JUDGE_PAIRWISE_PROMPT.format(
        task=task_body, response_x=response_x, response_y=response_y
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        max_tokens=8000,
    )
    msg = resp.choices[0].message
    text = msg.content or ""
    if not text:
        rc = getattr(msg, "reasoning_content", None) or ""
        if rc:
            logger.warning(
                "empty content (finish_reason=%s, completion_tokens=%s) — "
                "falling back to reasoning_content (%d chars)",
                resp.choices[0].finish_reason, getattr(resp.usage, "completion_tokens", "?"), len(rc),
            )
            text = rc
    return parse_judgement(text, judge_model=model, swapped=swapped)


def _collapse(natural, swapped) -> tuple[Literal["A", "B", "tie"], bool]:
    """Same X/Y → A/B mapping the production eval uses."""

    def to_ab(vote) -> Literal["A", "B", "tie"]:
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


def run(*, provider: str | None, model: str | None, dry_run: bool, force: bool) -> int:
    out_path = OUT_DIR / "results.json"
    if out_path.exists() and not force:
        logger.error("output already exists at %s — pass --force to overwrite", out_path)
        return 2

    cells = [Cell(task, a, b) for (a, b) in CONFIG_PAIRS for task in TASKS]
    logger.info("planned cells: %d (× 2 orders = %d API calls)", len(cells), len(cells) * 2)
    for c in cells:
        cons = _claude_consensus(c)
        logger.info("  %s | %s vs %s | Claude says: %s", c.task_id, c.config_a, c.config_b, cons)

    if dry_run:
        # Dry-run does not require an api key — we want this branch to work
        # against an unconfigured shell so the wiring can be inspected without
        # provisioning credentials.
        try:
            cfg = _resolve_provider(model, provider)
            logger.info("provider=%s model=%s base_url=%s", cfg.provider, cfg.model, cfg.base_url or "<default>")
        except RuntimeError as exc:
            logger.info("provider not configured (%s) — set the appropriate env var before live run", exc)
        logger.info("dry-run mode — no API calls dispatched")
        return 0

    cfg = _resolve_provider(model, provider)
    logger.info("provider=%s model=%s base_url=%s", cfg.provider, cfg.model, cfg.base_url or "<default>")

    from openai import OpenAI

    client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url) if cfg.base_url else OpenAI(api_key=cfg.api_key)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    results: list[CellResult] = []
    for i, cell in enumerate(cells, 1):
        logger.info("[%d/%d] judging %s : %s vs %s", i, len(cells), cell.task_id, cell.config_a, cell.config_b)
        task_body = _read_task(cell.task_id)
        resp_a = _read_response(cell.config_a, cell.task_id)
        resp_b = _read_response(cell.config_b, cell.task_id)

        natural = _judge_once(
            client, task_body=task_body, response_x=resp_a, response_y=resp_b, model=cfg.model, swapped=False
        )
        swapped = _judge_once(
            client, task_body=task_body, response_x=resp_b, response_y=resp_a, model=cfg.model, swapped=True
        )
        preferred, bias = _collapse(natural, swapped)
        consensus = _claude_consensus(cell)
        results.append(
            CellResult(
                task_id=cell.task_id,
                config_a=cell.config_a,
                config_b=cell.config_b,
                judge_model=cfg.model,
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
    n_b_wins = sum(1 for r in results if r.preferred == "B")  # B = 4.7 side
    n_a_wins = sum(1 for r in results if r.preferred == "A")
    n_tie = sum(1 for r in results if r.preferred == "tie")
    n_bias = sum(1 for r in results if r.position_bias_detected)

    # Decision rule per docs/experiment_003_plan.md §3.1.
    # Cross-family judge's win-rate for the 4.7 side, with ties counted as
    # 0.5 (standard tie-handling in pairwise-preference reporting).
    judge_pref_47 = (n_b_wins + 0.5 * n_tie) / n_total if n_total else 0.0
    if judge_pref_47 >= 0.85:
        verdict = "robust"
    elif judge_pref_47 >= 0.55:
        verdict = "inflated"
    else:
        verdict = "refuted"

    aggregate = {
        "provider": cfg.provider,
        "judge_model": cfg.model,
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


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--provider",
        default=None,
        choices=("deepseek", "openai", "custom"),
        help="judge provider (default: deepseek; env: JUDGE_SANITY_PROVIDER)",
    )
    p.add_argument(
        "--model",
        default=None,
        help="model id; if omitted, uses provider default (env: JUDGE_SANITY_MODEL)",
    )
    p.add_argument("--dry-run", action="store_true", help="list planned calls, do not invoke the API")
    p.add_argument("--force", action="store_true", help="overwrite an existing results.json")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args(argv)
    return run(provider=args.provider, model=args.model, dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    sys.exit(main())
