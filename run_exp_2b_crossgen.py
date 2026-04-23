"""Experiment 2B — Cross-Generation Heterogeneous (Opus 4.6 × 4.7).

Tests whether pairing two models of equivalent tier but different training
(Opus 4.6 × Opus 4.7) produces the diversity benefit seen in 001's
heterogeneous configs without the capability gap that dragged down
weaker-model pairings.

Three configs:
    - B-homo-opus46:         all roles = claude-opus-4-6
    - B-homo-opus47:         all roles = claude-opus-4-7
    - B-het-opus46-opus47:   left = 4.6, right = 4.7, synthesizer = 4.7

Note: the two homogeneous configs are parameter-identical to 2A's
B-opus46-3rnd and B-opus47-3rnd. We re-run them here in a dedicated
matrix dir so this experiment's eval pipeline stays self-contained.
Expect the repeated runs to land within the single-run variance band
(since seeded the same).

Run:
    uv run --active python run_exp_2b_crossgen.py
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from langgraph_agents.eval.corpus import DEFAULT_CORPUS_DIR, load_corpus
from langgraph_agents.eval.matrix import Configuration, run_matrix
from langgraph_agents.pipeline.config import ModelConfig, models_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)

OUTPUT_DIR = Path("logs/matrix_2b_crossgen")
PARALLEL = 3

_COMPLEX_TASK_IDS = {
    "architectural_review_auth",
    "design_testing_strategy",
    "migration_postgres_dynamo",
}
TASKS = [t for t in load_corpus(DEFAULT_CORPUS_DIR) if t.id in _COMPLEX_TASK_IDS]

_OPUS46 = "claude-opus-4-6"
_OPUS47 = "claude-opus-4-7"

_BASE_OVERRIDES = {
    "max_total_cost_usd": 10.0,
    "max_wall_clock_seconds": 3600,
    "max_debate_rounds": 3,
    "random_seed": 42,
}


def _het_model_config(left: str, right: str, synth: str) -> ModelConfig:
    return ModelConfig(
        generator_left=left,
        generator_right=right,
        critic_left=left,
        critic_right=right,
        reviser_left=left,
        reviser_right=right,
        synthesizer=synth,
        debater_left=left,
        debater_right=right,
    )


CONFIGS: list[Configuration] = [
    Configuration(
        "B-homo-opus46", "B", models_all(_OPUS46),
        overrides=dict(_BASE_OVERRIDES),
    ),
    Configuration(
        "B-homo-opus47", "B", models_all(_OPUS47),
        overrides=dict(_BASE_OVERRIDES),
    ),
    Configuration(
        "B-het-opus46-opus47", "B",
        _het_model_config(left=_OPUS46, right=_OPUS47, synth=_OPUS47),
        overrides=dict(_BASE_OVERRIDES),
    ),
]


async def main() -> None:
    t0 = datetime.now(timezone.utc)
    print(f"[exp-2b] {len(TASKS)} tasks × {len(CONFIGS)} configs "
          f"= {len(TASKS) * len(CONFIGS)} runs, parallel={PARALLEL}")
    print(f"[exp-2b] started at {t0.isoformat()}")
    for task in TASKS:
        print(f"    task:   {task.id:<30} ({task.length_hint})")
    for cfg in CONFIGS:
        print(f"    config: {cfg.id:<22} "
              f"left={cfg.models.generator_left} "
              f"right={cfg.models.generator_right} "
              f"synth={cfg.models.synthesizer}")

    results = await run_matrix(
        TASKS, CONFIGS,
        output_dir=OUTPUT_DIR,
        parallel=PARALLEL,
        resume=True,
    )

    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    print(f"\n[exp-2b] finished in {elapsed:.0f}s ({elapsed/60:.1f}m)")

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

    print(f"[exp-2b] summary: ok={totals['ok']} skipped={totals['skipped']} "
          f"error={totals['error']} cost=${total_cost:.4f} "
          f"wall={total_wall:.0f}s terminations={terminations}")

    summary_path = OUTPUT_DIR / "matrix_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "experiment": "2b_crossgen",
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
    print(f"[exp-2b] wrote {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
