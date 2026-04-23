"""Experiment 2A eval — same pipeline as run_eval.py, pointed at 2A dirs.

Three phases: metrics → pairwise preference judging → report generation.

Only 4 configs × 3 tasks, so the judgment budget is modest:
    C(4, 2) = 6 pairs × 3 tasks × 2 judges × 2 orderings = 72 LLM calls.

Run:     uv run --active python run_eval_2a.py
Resume:  Same command — completed judgments in judgments.jsonl are skipped.
Metrics only:  uv run --active python run_eval_2a.py --metrics-only
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Point the run_eval module at the 2A directories before importing anything
# that freezes the paths. run_eval reads MATRIX_DIR / EVAL_DIR / JUDGMENTS_PATH
# / SIMILARITY_PATH at import time into module-level constants, so we rebind
# them here before touching its functions.
import run_eval  # noqa: E402

run_eval.MATRIX_DIR = Path("logs/matrix_2a_rounds")
run_eval.EVAL_DIR = Path("logs/eval_2a")
run_eval.JUDGMENTS_PATH = run_eval.EVAL_DIR / "judgments.jsonl"
run_eval.SIMILARITY_PATH = run_eval.EVAL_DIR / "cross_run_similarity.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    t0 = datetime.now(timezone.utc)
    metrics_only = "--metrics-only" in sys.argv

    config_ids = run_eval._discover_configs()
    from langgraph_agents.eval.corpus import DEFAULT_CORPUS_DIR, load_corpus

    # Filter the corpus to only tasks this experiment used, so cross-similarity
    # / metrics / judging all align with what's actually on disk.
    complex_ids = {
        "architectural_review_auth",
        "design_testing_strategy",
        "migration_postgres_dynamo",
    }
    tasks = [t for t in load_corpus(DEFAULT_CORPUS_DIR) if t.id in complex_ids]

    logger.info("eval pipeline started at %s", t0.isoformat())
    logger.info(
        "%d configs x %d tasks = %d runs",
        len(config_ids),
        len(tasks),
        len(config_ids) * len(tasks),
    )
    if metrics_only:
        logger.info("--metrics-only: skipping judging phase")
    else:
        logger.info(
            "judge models: %s, parallel: %d", run_eval.JUDGE_MODELS, run_eval.PARALLEL
        )

    summaries = run_eval._load_all_summaries(config_ids, tasks)
    logger.info("loaded %d summaries from %s", len(summaries), run_eval.MATRIX_DIR)

    metrics_rows = run_eval.run_metrics_pass(summaries, tasks)
    run_eval.compute_cross_run_similarities(summaries, tasks)

    if metrics_only:
        _, outcomes = run_eval._load_completed_judgments()
    else:
        outcomes = await run_eval.run_judging_pass(config_ids, tasks, summaries)

    report_path = run_eval.run_report(config_ids, metrics_rows, outcomes)

    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    logger.info(
        "eval pipeline finished in %.0fs (%.1fm)", elapsed, elapsed / 60
    )
    print(f"\nDone. Report: {report_path}")
    print(f"Elapsed: {elapsed:.0f}s ({elapsed/60:.1f}m)")


if __name__ == "__main__":
    asyncio.run(main())
