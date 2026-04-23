"""Experiment 2A — Max Debate Rounds Sweep (expanded: 4 rounds × 2 models).

Tests whether raising Variant B's debate round cap improves output quality
on complex tasks, disentangled from model version.

Originally planned as 4 configs (rounds ∈ {1,3,5,7}) on one model. Expanded
to 8 configs (4 rounds × {Opus 4.6, Opus 4.7}) because the short alias
"opus" shifted between 001 baseline (2026-04-18, probably 4.6) and now
(2026-04-23, 4.7). Explicit model IDs are used so the experiment is
reproducible regardless of future alias shifts.

Budget: $10 / 3600s so rounds is the binding constraint.

Run:
    uv run --active python run_exp_2a_rounds.py

Resume:
    Same command — ``has_completed`` skips any run whose ``summary.json`` is
    already present. Safe to interrupt and re-invoke.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from langgraph_agents.eval.corpus import DEFAULT_CORPUS_DIR, load_corpus
from langgraph_agents.eval.matrix import Configuration, run_matrix
from langgraph_agents.pipeline.config import models_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)

OUTPUT_DIR = Path("logs/matrix_2a_rounds")
PARALLEL = 3

_COMPLEX_TASK_IDS = {
    "architectural_review_auth",
    "design_testing_strategy",
    "migration_postgres_dynamo",
}
TASKS = [t for t in load_corpus(DEFAULT_CORPUS_DIR) if t.id in _COMPLEX_TASK_IDS]

_BASE_OVERRIDES = {
    "max_total_cost_usd": 10.0,
    "max_wall_clock_seconds": 3600,
    "random_seed": 42,
}

_ROUNDS = (1, 3, 5, 7)
_MODEL_VARIANTS = (
    ("opus46", "claude-opus-4-6"),
    ("opus47", "claude-opus-4-7"),
)


def _make_config(model_tag: str, model_id: str, rounds: int) -> Configuration:
    return Configuration(
        f"B-{model_tag}-{rounds}rnd",
        "B",
        models_all(model_id),
        overrides={**_BASE_OVERRIDES, "max_debate_rounds": rounds},
    )


CONFIGS: list[Configuration] = [
    _make_config(tag, model_id, rounds)
    for tag, model_id in _MODEL_VARIANTS
    for rounds in _ROUNDS
]


async def main() -> None:
    t0 = datetime.now(timezone.utc)
    print(f"[exp-2a] {len(TASKS)} tasks × {len(CONFIGS)} configs "
          f"= {len(TASKS) * len(CONFIGS)} runs, parallel={PARALLEL}")
    print(f"[exp-2a] started at {t0.isoformat()}")
    for task in TASKS:
        print(f"    task:   {task.id:<30} ({task.length_hint})")
    for cfg in CONFIGS:
        print(f"    config: {cfg.id:<18} rounds={cfg.overrides['max_debate_rounds']} "
              f"model={cfg.models.generator_left}")

    results = await run_matrix(
        TASKS,
        CONFIGS,
        output_dir=OUTPUT_DIR,
        parallel=PARALLEL,
        resume=True,
    )

    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    print(f"\n[exp-2a] finished in {elapsed:.0f}s ({elapsed/60:.1f}m)")
    print("[exp-2a] --- results ---")
    header = (
        f"{'config':<16} {'task':<28} {'status':<8} "
        f"{'cost':>8} {'wall_s':>8} {'term':<20}"
    )
    print(header)
    print("-" * len(header))

    totals = {"ok": 0, "skipped": 0, "error": 0}
    total_cost = 0.0
    total_wall = 0.0
    terminations: dict[str, int] = {}
    for r in results:
        totals[r.status] = totals.get(r.status, 0) + 1
        if r.status == "ok" and r.result is not None:
            total_cost += r.result.total_cost_usd
            total_wall += r.result.wall_clock_seconds
            terminations[r.result.termination_reason] = (
                terminations.get(r.result.termination_reason, 0) + 1
            )
            print(
                f"{r.config_id:<16} {r.task_id:<28} {r.status:<8} "
                f"${r.result.total_cost_usd:>7.4f} "
                f"{r.result.wall_clock_seconds:>8.1f} "
                f"{r.result.termination_reason:<20}"
            )
        elif r.status == "skipped":
            print(f"{r.config_id:<16} {r.task_id:<28} {r.status:<8} (resumed)")
        else:
            print(
                f"{r.config_id:<16} {r.task_id:<28} {r.status:<8} "
                f"error={r.error or ''}"
            )

    print(f"\n[exp-2a] summary")
    print(f"    ok:      {totals.get('ok', 0)}")
    print(f"    skipped: {totals.get('skipped', 0)}")
    print(f"    error:   {totals.get('error', 0)}")
    print(f"    cost:    ${total_cost:.4f}")
    print(f"    wall:    {total_wall:.0f}s ({total_wall/60:.1f}m) across runs")
    print(f"    termination reasons: {terminations}")

    summary_path = OUTPUT_DIR / "matrix_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "experiment": "2a_rounds_sweep",
                "started_at": t0.isoformat(),
                "elapsed_seconds": elapsed,
                "totals": totals,
                "total_cost_usd": total_cost,
                "total_wall_seconds_across_runs": total_wall,
                "terminations": terminations,
                "tasks": [t.id for t in TASKS],
                "configs": [c.id for c in CONFIGS],
                "parallel": PARALLEL,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n[exp-2a] wrote {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
