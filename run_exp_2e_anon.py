"""Experiment 2E — Anonymization Toggle.

Tests whether the anonymize_in_debate flag (drafts labeled "Proposal A/B"
vs. "Your draft / Their draft") affects debate dynamics or output quality.

Two configs: B-homo-opus47 with anonymization on vs. off. Pinned to Opus
4.7 explicitly for reproducibility — anonymization is a current-flagship
question, and running on one model suffices to measure the effect.

Run:
    uv run --active python run_exp_2e_anon.py

Resume:
    Same command.
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

OUTPUT_DIR = Path("logs/matrix_2e_anon")
PARALLEL = 3

_COMPLEX_TASK_IDS = {
    "architectural_review_auth",
    "design_testing_strategy",
    "migration_postgres_dynamo",
}
TASKS = [t for t in load_corpus(DEFAULT_CORPUS_DIR) if t.id in _COMPLEX_TASK_IDS]

_MODEL_ID = "claude-opus-4-7"
_BASE_OVERRIDES = {
    "max_total_cost_usd": 10.0,
    "max_wall_clock_seconds": 3600,
    "max_debate_rounds": 3,
    "random_seed": 42,
}

CONFIGS: list[Configuration] = [
    Configuration(
        "B-opus47-anon-on", "B", models_all(_MODEL_ID),
        overrides={**_BASE_OVERRIDES, "anonymize_in_debate": True},
    ),
    Configuration(
        "B-opus47-anon-off", "B", models_all(_MODEL_ID),
        overrides={**_BASE_OVERRIDES, "anonymize_in_debate": False},
    ),
]


async def main() -> None:
    t0 = datetime.now(timezone.utc)
    print(f"[exp-2e] {len(TASKS)} tasks × {len(CONFIGS)} configs "
          f"= {len(TASKS) * len(CONFIGS)} runs, parallel={PARALLEL}")
    print(f"[exp-2e] started at {t0.isoformat()}")
    for task in TASKS:
        print(f"    task:   {task.id:<30} ({task.length_hint})")
    for cfg in CONFIGS:
        print(f"    config: {cfg.id:<22} anon={cfg.overrides['anonymize_in_debate']}")

    results = await run_matrix(
        TASKS, CONFIGS,
        output_dir=OUTPUT_DIR,
        parallel=PARALLEL,
        resume=True,
    )

    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    print(f"\n[exp-2e] finished in {elapsed:.0f}s ({elapsed/60:.1f}m)")

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

    print(f"[exp-2e] summary: ok={totals['ok']} skipped={totals['skipped']} "
          f"error={totals['error']} cost=${total_cost:.4f} "
          f"wall={total_wall:.0f}s terminations={terminations}")

    summary_path = OUTPUT_DIR / "matrix_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "experiment": "2e_anon_toggle",
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
    print(f"[exp-2e] wrote {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
