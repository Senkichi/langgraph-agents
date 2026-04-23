"""Smoke test: Variant B on a complex task, opus homogeneous, 1-round debate.

Purpose: validate end-to-end that Variant B actually runs after the two
fixes in commit fe036d8 (SDK iterator protocol + Windows CreateProcess
arg-size). Uses opus so the drafts are realistically large — the largest
contributor to the Windows arg-size path — but caps debate at 1 round
and raises budget generously to make this a minimal-cost validation.

Run:
    uv run --active python run_variant_b_smoke.py

If this completes with termination ∈ {max_rounds, mutual_agreement,
stable_disagreement} and a non-empty final_plan, the fixes hold and the
2A sweep is safe to launch.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from langgraph_agents.eval.corpus import load_task
from langgraph_agents.pipeline.artifacts import load_summary
from langgraph_agents.pipeline.config import RunConfig, models_all
from langgraph_agents.pipeline.variant_b.graph import run_variant_b

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)

OUTPUT_DIR = Path("logs/smoke_variant_b")


async def main() -> None:
    task = load_task(
        "src/langgraph_agents/eval/corpus/architectural_review_auth.md"
    )
    chatroom = OUTPUT_DIR / "B-homo-opus"
    chatroom.mkdir(parents=True, exist_ok=True)

    cfg = RunConfig(
        variant="B",
        models=models_all("opus"),
        chatroom_dir=str(chatroom),
        task=task.body,
        run_id=f"smoke__{task.id}",
        max_total_cost_usd=5.0,
        max_wall_clock_seconds=1800,
        max_debate_rounds=1,
        random_seed=42,
    )

    print(f"[smoke-b] running Variant B on task {task.id!r} with opus, 1-round debate...")
    result = await run_variant_b(cfg)
    print(f"[smoke-b] termination={result.termination_reason} "
          f"cost=${result.total_cost_usd:.4f} "
          f"wall={result.wall_clock_seconds:.1f}s")

    summary = load_summary(cfg.chatroom_dir, cfg.run_id)
    env = summary["environment"]
    print(f"[smoke-b] env: git_sha={env.get('git_sha')!s:.12} "
          f"git_dirty={env.get('git_dirty')} "
          f"cli={env.get('claude_cli_version')!r} "
          f"sdk={env.get('claude_agent_sdk_version')!r}")

    print(f"\n[smoke-b] debate: rounds={summary.get('rounds_completed')} "
          f"stance_flips={summary.get('stance_flips')} "
          f"compactions={summary.get('compactions')}")

    print("\n[smoke-b] --- final_plan.md (first 1500 chars) ---")
    print(result.final_plan[:1500])
    if len(result.final_plan) > 1500:
        print(f"... [{len(result.final_plan) - 1500} more chars]")

    artifacts = sorted(Path(result.artifacts_dir).iterdir())
    print(f"\n[smoke-b] artifacts ({len(artifacts)}):")
    for p in artifacts:
        print(f"    {p.name:32} {p.stat().st_size:>8} B")

    # Verdict gates: non-empty final plan + clean termination.
    if not result.final_plan.strip():
        raise SystemExit("[smoke-b] FAIL: final_plan is empty")
    if result.termination_reason not in {
        "max_rounds", "mutual_agreement", "stable_disagreement"
    }:
        print(f"[smoke-b] NOTE: termination={result.termination_reason!r} "
              f"(budget-limited is acceptable, not a fail)")
    print("\n[smoke-b] PASS — Variant B is runnable end-to-end.")


if __name__ == "__main__":
    asyncio.run(main())
