"""Smoke test: Variant A on the smallest sanity task with sonnet everywhere.

Run:
    uv run --active python run_variant_a_smoke.py

Budget: ~$0.20-0.50 wall-time, four LLM calls (2 generate, 2 critic, 2 revise,
1 synth = 7 — the first three pairs run in parallel).
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from langgraph_agents.eval.corpus import load_task
from langgraph_agents.pipeline.artifacts import load_summary
from langgraph_agents.pipeline.config import RunConfig, models_all
from langgraph_agents.pipeline.variant_a.graph import run_variant_a

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)

OUTPUT_DIR = Path("logs/smoke_variant_a")


async def main() -> None:
    task = load_task("src/langgraph_agents/eval/corpus/sanity_prompt_caching.md")
    chatroom = OUTPUT_DIR / "A-homo-sonnet"
    chatroom.mkdir(parents=True, exist_ok=True)

    cfg = RunConfig(
        variant="A",
        models=models_all("sonnet"),
        chatroom_dir=str(chatroom),
        task=task.body,
        run_id=f"smoke__{task.id}",
        max_total_cost_usd=2.0,
        max_wall_clock_seconds=900,
        random_seed=42,
    )

    print(f"[smoke] running Variant A on task {task.id!r} with sonnet...")
    result = await run_variant_a(cfg)
    print(f"[smoke] termination={result.termination_reason} "
          f"cost=${result.total_cost_usd:.4f} "
          f"wall={result.wall_clock_seconds:.1f}s")

    summary = load_summary(cfg.chatroom_dir, cfg.run_id)
    env = summary["environment"]
    print(f"[smoke] env: git_sha={env.get('git_sha')!s:.12} "
          f"git_dirty={env.get('git_dirty')} "
          f"cli={env.get('claude_cli_version')!r} "
          f"sdk={env.get('claude_agent_sdk_version')!r}")

    print("\n[smoke] --- final_plan.md ---")
    print(result.final_plan[:1500])
    if len(result.final_plan) > 1500:
        print(f"... [{len(result.final_plan) - 1500} more chars]")

    # List the artifacts that landed on disk.
    artifacts = sorted(Path(result.artifacts_dir).iterdir())
    print(f"\n[smoke] artifacts ({len(artifacts)}):")
    for p in artifacts:
        print(f"    {p.name:32} {p.stat().st_size:>8} B")


if __name__ == "__main__":
    asyncio.run(main())
