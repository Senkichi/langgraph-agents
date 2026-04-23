"""Tiny directional matrix: 2 configs (A vs B, same models) × 2 tasks = 4 runs.

Goal: isolate the effect of Variant B's debate loop on the same model pairing
and same tasks — just enough signal to decide whether a fuller sweep is worth
the money. Budget: ~$2-4, wall ~10-20 min.

Run:
    uv run --active python run_tiny_matrix.py
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from langgraph_agents.eval.corpus import load_task
from langgraph_agents.eval.matrix import Configuration, run_matrix
from langgraph_agents.pipeline.config import models_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)

OUTPUT_DIR = Path("logs/tiny_matrix")

TASKS = [
    load_task("src/langgraph_agents/eval/corpus/sanity_prompt_caching.md"),
    load_task("src/langgraph_agents/eval/corpus/design_testing_strategy.md"),
]

CONFIGS = [
    Configuration(
        id="A-homo-sonnet",
        variant="A",
        models=models_all("sonnet"),
        overrides={
            "max_total_cost_usd": 2.0,
            "max_wall_clock_seconds": 900,
            "random_seed": 42,
        },
    ),
    Configuration(
        id="B-homo-sonnet",
        variant="B",
        models=models_all("sonnet"),
        overrides={
            "max_total_cost_usd": 3.0,
            "max_wall_clock_seconds": 1500,
            "max_debate_rounds": 3,
            "random_seed": 42,
        },
    ),
]


async def main() -> None:
    print(f"[tiny-matrix] {len(TASKS)} tasks × {len(CONFIGS)} configs "
          f"= {len(TASKS) * len(CONFIGS)} runs")
    for task in TASKS:
        print(f"    task: {task.id} ({task.length_hint})")
    for cfg in CONFIGS:
        print(f"    config: {cfg.id} (variant={cfg.variant})")

    results = await run_matrix(
        TASKS,
        CONFIGS,
        output_dir=OUTPUT_DIR,
        parallel=2,
        resume=True,
    )

    print("\n[tiny-matrix] --- results ---")
    header = f"{'config':<20} {'task':<30} {'status':<8} {'cost':>8} {'wall_s':>8} {'term':<20}"
    print(header)
    print("-" * len(header))
    total_cost = 0.0
    for r in results:
        if r.status == "ok" and r.result is not None:
            total_cost += r.result.total_cost_usd
            print(
                f"{r.config_id:<20} {r.task_id:<30} {r.status:<8} "
                f"${r.result.total_cost_usd:>7.4f} "
                f"{r.result.wall_clock_seconds:>8.1f} "
                f"{r.result.termination_reason:<20}"
            )
        else:
            print(
                f"{r.config_id:<20} {r.task_id:<30} {r.status:<8} "
                f"{'-':>8} {'-':>8} {r.error or '':<40}"
            )

    print(f"\n[tiny-matrix] total cost: ${total_cost:.4f}")
    print(f"[tiny-matrix] artifacts under: {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
