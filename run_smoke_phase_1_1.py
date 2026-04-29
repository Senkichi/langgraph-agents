"""Smoke: Variant A + Opus 4.7 across the 6 new Phase 1.1 corpus tasks.

Plan §4.1 quality gate — confirms each new task body executes end-to-end on
the production pipeline without parser / format errors before the corpus is
trusted by Phase 2.1's matrix.

Budget: ~$1/run on Variant A 4.7 (plan §10) × 6 runs ≈ $6 imputed,
~10–15 min wall at parallel=3.

Run:
    uv run --active python run_smoke_phase_1_1.py

Resume:
    Same command — already-complete runs are skipped via has_completed.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from langgraph_agents.eval.corpus import DEFAULT_CORPUS_DIR, load_task
from langgraph_agents.eval.matrix import Configuration, run_matrix
from langgraph_agents.pipeline.config import models_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)

OUTPUT_DIR = Path("logs/smoke_phase_1_1")

NEW_TASK_IDS = [
    "perf_tuning_hot_path",
    "api_design_review",
    "incident_postmortem",
    "migration_with_downtime",
    "caching_consistency",
    "refactor_legacy_module",
]

# No per-run cost cap: smoke data showed Variant A on 4.7 lands at ~$2.44/run
# natural mean (n=2). The pipeline default of $20 is effectively uncapped at
# our workload size. Wall cap stays — bounds runaway runs without truncating
# natural completion (the longest natural-completion smoke run was 829s; cap
# at 1200s gives ~45% headroom).
CONFIG = Configuration(
    id="A-homo-opus47",
    variant="A",
    models=models_all("claude-opus-4-7"),
    overrides={
        "max_wall_clock_seconds": 1200,
        "random_seed": 42,
    },
)

PARALLEL = 3


async def main() -> None:
    tasks = [load_task(DEFAULT_CORPUS_DIR / f"{tid}.md") for tid in NEW_TASK_IDS]
    t0 = datetime.now(timezone.utc)
    print(f"[smoke-1.1] {len(tasks)} tasks × 1 config, parallel={PARALLEL}")
    print(f"[smoke-1.1] started at {t0.isoformat()}")
    for t in tasks:
        print(f"    task: {t.id}")
    print(f"    config: {CONFIG.id} (model=claude-opus-4-7)")

    results = await run_matrix(
        tasks,
        [CONFIG],
        output_dir=OUTPUT_DIR,
        parallel=PARALLEL,
        resume=True,
    )

    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    print(f"\n[smoke-1.1] finished in {elapsed:.0f}s ({elapsed/60:.1f}m)")
    print("[smoke-1.1] --- results ---")
    header = (
        f"{'task':<28} {'status':<8} {'cost':>8} {'wall_s':>8} "
        f"{'term':<22} {'plan_chars':>10}"
    )
    print(header)
    print("-" * len(header))

    totals = {"ok": 0, "skipped": 0, "error": 0}
    total_cost = 0.0
    for r in results:
        totals[r.status] = totals.get(r.status, 0) + 1
        if r.status == "ok" and r.result is not None:
            total_cost += r.result.total_cost_usd
            print(
                f"{r.task_id:<28} {r.status:<8} "
                f"${r.result.total_cost_usd:>7.4f} "
                f"{r.result.wall_clock_seconds:>8.1f} "
                f"{r.result.termination_reason:<22} "
                f"{len(r.result.final_plan):>10}"
            )
        elif r.status == "skipped":
            print(f"{r.task_id:<28} {r.status:<8} (resumed)")
        else:
            print(f"{r.task_id:<28} {r.status:<8} error={r.error or ''}")

    print(f"\n[smoke-1.1] summary")
    print(f"    ok:      {totals.get('ok', 0)}")
    print(f"    skipped: {totals.get('skipped', 0)}")
    print(f"    error:   {totals.get('error', 0)}")
    print(f"    cost:    ${total_cost:.4f}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = OUTPUT_DIR / "matrix_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "experiment": "smoke_phase_1_1",
                "started_at": t0.isoformat(),
                "elapsed_seconds": elapsed,
                "totals": totals,
                "total_cost_usd": total_cost,
                "tasks": [t.id for t in tasks],
                "config": CONFIG.id,
                "parallel": PARALLEL,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n[smoke-1.1] wrote {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
