"""Full 10-config × 5-task eval sweep.

Configs use short model aliases (``opus`` / ``sonnet`` / ``haiku``) that the
bundled Claude Code CLI accepts — the long form (``claude-opus-4-6`` etc.) is
not guaranteed to resolve on this install.

Run:
    uv run --active python run_full_matrix.py

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
from langgraph_agents.pipeline.config import models_all, models_split

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)

OUTPUT_DIR = Path("logs/matrix")
PARALLEL = 3

TASKS = load_corpus(DEFAULT_CORPUS_DIR)

# 10 configs: 6 homogeneous + 4 heterogeneous.
_OVERRIDES_A = {
    "max_total_cost_usd": 3.0,
    "max_wall_clock_seconds": 1200,
    "random_seed": 42,
}
_OVERRIDES_B = {
    "max_total_cost_usd": 5.0,
    "max_wall_clock_seconds": 2400,
    "max_debate_rounds": 3,
    "random_seed": 42,
}

CONFIGS: list[Configuration] = [
    # Variant A homogeneous
    Configuration("A-homo-opus",   "A", models_all("opus"),   overrides=dict(_OVERRIDES_A)),
    Configuration("A-homo-sonnet", "A", models_all("sonnet"), overrides=dict(_OVERRIDES_A)),
    Configuration("A-homo-haiku",  "A", models_all("haiku"),  overrides=dict(_OVERRIDES_A)),
    # Variant B homogeneous
    Configuration("B-homo-opus",   "B", models_all("opus"),   overrides=dict(_OVERRIDES_B)),
    Configuration("B-homo-sonnet", "B", models_all("sonnet"), overrides=dict(_OVERRIDES_B)),
    Configuration("B-homo-haiku",  "B", models_all("haiku"),  overrides=dict(_OVERRIDES_B)),
    # Heterogeneous (tests the diversity hypothesis)
    Configuration("A-het-opus-sonnet",   "A", models_split("opus", "sonnet"),  overrides=dict(_OVERRIDES_A)),
    Configuration("A-het-sonnet-haiku",  "A", models_split("sonnet", "haiku"), overrides=dict(_OVERRIDES_A)),
    Configuration("B-het-opus-sonnet",   "B", models_split("opus", "sonnet"),  overrides=dict(_OVERRIDES_B)),
    Configuration("B-het-sonnet-haiku",  "B", models_split("sonnet", "haiku"), overrides=dict(_OVERRIDES_B)),
]


async def main() -> None:
    t0 = datetime.now(timezone.utc)
    print(f"[full-matrix] {len(TASKS)} tasks × {len(CONFIGS)} configs "
          f"= {len(TASKS) * len(CONFIGS)} runs, parallel={PARALLEL}")
    print(f"[full-matrix] started at {t0.isoformat()}")
    for task in TASKS:
        print(f"    task:   {task.id:<30} ({task.length_hint})")
    for cfg in CONFIGS:
        print(f"    config: {cfg.id:<24} variant={cfg.variant} "
              f"models=({cfg.models.generator_left},{cfg.models.generator_right})")

    results = await run_matrix(
        TASKS,
        CONFIGS,
        output_dir=OUTPUT_DIR,
        parallel=PARALLEL,
        resume=True,
    )

    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    print(f"\n[full-matrix] finished in {elapsed:.0f}s ({elapsed/60:.1f}m)")
    print("[full-matrix] --- results ---")
    header = (
        f"{'config':<22} {'task':<28} {'status':<8} "
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
                f"{r.config_id:<22} {r.task_id:<28} {r.status:<8} "
                f"${r.result.total_cost_usd:>7.4f} "
                f"{r.result.wall_clock_seconds:>8.1f} "
                f"{r.result.termination_reason:<20}"
            )
        elif r.status == "skipped":
            print(f"{r.config_id:<22} {r.task_id:<28} {r.status:<8} (resumed)")
        else:
            print(
                f"{r.config_id:<22} {r.task_id:<28} {r.status:<8} "
                f"error={r.error or ''}"
            )

    print(f"\n[full-matrix] summary")
    print(f"    ok:      {totals.get('ok', 0)}")
    print(f"    skipped: {totals.get('skipped', 0)}")
    print(f"    error:   {totals.get('error', 0)}")
    print(f"    cost:    ${total_cost:.4f}")
    print(f"    wall:    {total_wall:.0f}s ({total_wall/60:.1f}m) across runs")
    print(f"    termination reasons: {terminations}")

    # Dump a machine-readable summary alongside the artifacts.
    summary_path = OUTPUT_DIR / "matrix_summary.json"
    summary_path.write_text(
        json.dumps(
            {
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
    print(f"\n[full-matrix] wrote {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
