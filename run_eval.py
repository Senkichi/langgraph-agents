"""Structured metrics + pairwise preference judging + report generation.

Three phases, run sequentially:

1. Metrics    — deterministic, no LLM calls. Reads from logs/matrix/.
2. Judging    — LLM calls via Claude CLI. 45 pairs × 5 tasks × 2 judges
               × 2 orderings = 900 LLM calls. Resume-safe via judgments.jsonl.
3. Report     — aggregates metrics + judgments into logs/eval/report.md.

Run:     uv run --active python run_eval.py
Resume:  Same command — completed judgments are skipped.
Metrics only:  uv run --active python run_eval.py --metrics-only
"""
from __future__ import annotations

import asyncio
import csv
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

from langgraph_agents.eval.corpus import DEFAULT_CORPUS_DIR, Task, load_corpus
from langgraph_agents.eval.judge_pairwise import (
    PairwiseOutcome,
    judge_pair_with_position_check,
)
from langgraph_agents.eval.metrics import cross_run_similarity, run_metrics
from langgraph_agents.eval.report import build_report
from langgraph_agents.pipeline.artifacts import has_completed, load_summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

MATRIX_DIR = Path("logs/matrix")
EVAL_DIR = Path("logs/eval")
JUDGMENTS_PATH = EVAL_DIR / "judgments.jsonl"
SIMILARITY_PATH = EVAL_DIR / "cross_run_similarity.csv"

JUDGE_MODELS = ["opus", "sonnet"]
PARALLEL = 3

CWD = str(Path.cwd())


def _discover_configs() -> list[str]:
    if not MATRIX_DIR.exists():
        raise FileNotFoundError(f"Matrix directory not found: {MATRIX_DIR}")
    return sorted(
        d.name
        for d in MATRIX_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )


def _variant_of(config_id: str) -> str:
    return "A" if config_id.startswith("A-") else "B"


def _load_all_summaries(
    config_ids: list[str],
    tasks: list[Task],
) -> dict[tuple[str, str], dict]:
    summaries: dict[tuple[str, str], dict] = {}
    for config_id in config_ids:
        chatroom_dir = str(MATRIX_DIR / config_id)
        for task in tasks:
            run_id = f"{config_id}__{task.id}"
            if has_completed(chatroom_dir, run_id):
                summaries[(config_id, task.id)] = load_summary(chatroom_dir, run_id)
    return summaries


# ---------------------------------------------------------------------------
# Phase 1: Metrics
# ---------------------------------------------------------------------------


def run_metrics_pass(
    summaries: dict[tuple[str, str], dict],
    tasks: list[Task],
) -> list[dict]:
    logger.info("=== Phase 1: Structured metrics ===")
    task_by_id = {t.id: t for t in tasks}
    rows: list[dict] = []

    for (config_id, task_id), summary in sorted(summaries.items()):
        run_id = f"{config_id}__{task_id}"
        row = run_metrics(
            summary,
            task_by_id[task_id],
            run_dir=MATRIX_DIR / config_id / run_id,
        )
        row["run_id"] = run_id
        rows.append(row)

    logger.info("metrics: %d runs processed", len(rows))

    print(
        f"\n{'run_id':<50} {'cost':>7} {'wall':>7} {'term':<18} "
        f"{'chars':>7} {'cov_kw':>7} {'cov_jac':>7}"
    )
    print("-" * 116)
    for r in rows:
        print(
            f"{r['run_id']:<50} "
            f"${r['total_cost_usd']:>6.2f} "
            f"{r['wall_clock_seconds']:>6.0f}s "
            f"{r['termination_reason']:<18} "
            f"{r['final_plan_chars']:>7} "
            f"{r['concept_coverage_keyword']:>7.2%} "
            f"{r['concept_coverage_token_jaccard']:>7.4f}"
        )

    _print_aggregates(rows)
    return rows


def _print_aggregates(rows: list[dict]) -> None:
    by_variant: dict[str, list[dict]] = defaultdict(list)
    by_task: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_variant[r["variant"]].append(r)
        by_task[r["task_id"]].append(r)

    print("\n--- By variant ---")
    print(f"{'variant':<10} {'n':>3} {'avg_cost':>10} {'avg_wall':>10} {'avg_cov_kw':>10}")
    for v in sorted(by_variant):
        rs = by_variant[v]
        n = len(rs)
        print(
            f"{v:<10} {n:>3} "
            f"${sum(r['total_cost_usd'] for r in rs) / n:>9.2f} "
            f"{sum(r['wall_clock_seconds'] for r in rs) / n:>9.0f}s "
            f"{sum(r['concept_coverage_keyword'] for r in rs) / n:>10.2%}"
        )

    print("\n--- By task ---")
    print(f"{'task':<35} {'n':>3} {'avg_cost':>10} {'avg_cov_kw':>10}")
    for t in sorted(by_task):
        rs = by_task[t]
        n = len(rs)
        print(
            f"{t:<35} {n:>3} "
            f"${sum(r['total_cost_usd'] for r in rs) / n:>9.2f} "
            f"{sum(r['concept_coverage_keyword'] for r in rs) / n:>10.2%}"
        )


def compute_cross_run_similarities(
    summaries: dict[tuple[str, str], dict],
    tasks: list[Task],
) -> None:
    all_sims: list[dict] = []

    print("\n--- Cross-run similarity (token Jaccard, per task) ---")
    for task in tasks:
        plans = {
            config_id: summary.get("final_plan") or ""
            for (config_id, task_id), summary in summaries.items()
            if task_id == task.id
        }
        if len(plans) < 2:
            continue

        sims = cross_run_similarity(plans)
        for (a, b), sim in sorted(sims.items()):
            all_sims.append(
                {"task_id": task.id, "config_a": a, "config_b": b, "token_jaccard": sim}
            )

        values = list(sims.values())
        mean_sim = sum(values) / len(values)
        min_sim = min(values)
        max_sim = max(values)
        print(
            f"  {task.id:<35} {len(sims):>3} pairs  "
            f"mean={mean_sim:.3f}  min={min_sim:.3f}  max={max_sim:.3f}"
        )

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    with SIMILARITY_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, ["task_id", "config_a", "config_b", "token_jaccard"]
        )
        writer.writeheader()
        writer.writerows(all_sims)
    logger.info("cross-run similarity: %d rows → %s", len(all_sims), SIMILARITY_PATH)


# ---------------------------------------------------------------------------
# Phase 2: Judging
# ---------------------------------------------------------------------------


def _judgment_key(
    task_id: str, config_a: str, config_b: str, judge_model: str
) -> str:
    return f"{task_id}|{config_a}|{config_b}|{judge_model}"


def _load_completed_judgments() -> (
    tuple[dict[str, PairwiseOutcome], list[PairwiseOutcome]]
):
    completed: dict[str, PairwiseOutcome] = {}
    if not JUDGMENTS_PATH.exists():
        return completed, []

    for line in JUDGMENTS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            outcome = PairwiseOutcome(
                task_id=d["task_id"],
                config_a=d["config_a"],
                config_b=d["config_b"],
                judge_model=d["judge_model"],
                preferred=d["preferred"],
                confidence_natural=d["confidence_natural"],
                confidence_swapped=d["confidence_swapped"],
                position_bias_detected=d["position_bias_detected"],
            )
            key = _judgment_key(
                outcome.task_id, outcome.config_a, outcome.config_b, outcome.judge_model
            )
            completed[key] = outcome
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("skipping malformed judgment line: %s", exc)

    logger.info("loaded %d completed judgments from %s", len(completed), JUDGMENTS_PATH)
    return completed, list(completed.values())


def _save_judgment(outcome: PairwiseOutcome) -> None:
    d = {
        "task_id": outcome.task_id,
        "config_a": outcome.config_a,
        "config_b": outcome.config_b,
        "judge_model": outcome.judge_model,
        "preferred": outcome.preferred,
        "confidence_natural": outcome.confidence_natural,
        "confidence_swapped": outcome.confidence_swapped,
        "position_bias_detected": outcome.position_bias_detected,
    }
    with JUDGMENTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(d) + "\n")


async def run_judging_pass(
    config_ids: list[str],
    tasks: list[Task],
    summaries: dict[tuple[str, str], dict],
) -> list[PairwiseOutcome]:
    logger.info("=== Phase 2: Pairwise preference judging ===")
    EVAL_DIR.mkdir(parents=True, exist_ok=True)

    completed, outcomes = _load_completed_judgments()
    task_by_id = {t.id: t for t in tasks}

    final_plans: dict[tuple[str, str], str] = {
        (config_id, task_id): summary.get("final_plan") or ""
        for (config_id, task_id), summary in summaries.items()
    }

    jobs: list[tuple[str, str, str, str]] = []
    for task in tasks:
        for config_a, config_b in combinations(config_ids, 2):
            if (config_a, task.id) not in final_plans:
                continue
            if (config_b, task.id) not in final_plans:
                continue
            for judge_model in JUDGE_MODELS:
                key = _judgment_key(task.id, config_a, config_b, judge_model)
                if key not in completed:
                    jobs.append((task.id, config_a, config_b, judge_model))

    total = len(jobs) + len(completed)
    logger.info(
        "judging: %d total, %d already complete, %d remaining (%d LLM calls)",
        total,
        len(completed),
        len(jobs),
        len(jobs) * 2,
    )

    if not jobs:
        logger.info("judging: nothing to do — all pairs already judged")
        return outcomes

    semaphore = asyncio.Semaphore(PARALLEL)
    done_count = 0
    lock = asyncio.Lock()

    async def one_judgment(
        task_id: str, config_a: str, config_b: str, judge_model: str
    ) -> PairwiseOutcome:
        nonlocal done_count
        task = task_by_id[task_id]
        response_a = final_plans[(config_a, task_id)]
        response_b = final_plans[(config_b, task_id)]

        async with semaphore:
            outcome = await judge_pair_with_position_check(
                task_id=task_id,
                task_body=task.body,
                response_a=response_a,
                response_b=response_b,
                config_a=config_a,
                config_b=config_b,
                judge_model=judge_model,
                cwd=CWD,
            )

        async with lock:
            done_count += 1
            _save_judgment(outcome)
            bias = " [BIAS]" if outcome.position_bias_detected else ""
            logger.info(
                "[%d/%d] %s: %s vs %s judge=%s -> %s%s",
                done_count,
                len(jobs),
                task_id,
                config_a,
                config_b,
                judge_model,
                outcome.preferred,
                bias,
            )

        return outcome

    new_outcomes = await asyncio.gather(
        *(one_judgment(*job) for job in jobs),
        return_exceptions=True,
    )

    errors = 0
    for result in new_outcomes:
        if isinstance(result, Exception):
            errors += 1
            logger.error("judgment failed: %s", result)
        else:
            outcomes.append(result)

    bias_count = sum(1 for o in outcomes if o.position_bias_detected)
    logger.info(
        "judging complete: %d judgments (%d errors), %d position-bias (%.1f%%)",
        len(outcomes),
        errors,
        bias_count,
        100 * bias_count / len(outcomes) if outcomes else 0,
    )
    return outcomes


# ---------------------------------------------------------------------------
# Phase 3: Report
# ---------------------------------------------------------------------------


def run_report(
    config_ids: list[str],
    metrics_rows: list[dict],
    outcomes: list[PairwiseOutcome],
) -> Path:
    logger.info("=== Phase 3: Report generation ===")
    variant_of = {cid: _variant_of(cid) for cid in config_ids}
    report_path = build_report(
        metrics_rows=metrics_rows,
        outcomes=outcomes,
        variant_of=variant_of,
        output_dir=EVAL_DIR,
    )
    logger.info("report written to %s", report_path)
    return report_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    t0 = datetime.now(timezone.utc)
    metrics_only = "--metrics-only" in sys.argv

    config_ids = _discover_configs()
    tasks = load_corpus(DEFAULT_CORPUS_DIR)

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
        logger.info("judge models: %s, parallel: %d", JUDGE_MODELS, PARALLEL)

    summaries = _load_all_summaries(config_ids, tasks)
    logger.info("loaded %d summaries from %s", len(summaries), MATRIX_DIR)

    metrics_rows = run_metrics_pass(summaries, tasks)
    compute_cross_run_similarities(summaries, tasks)

    if metrics_only:
        _, outcomes = _load_completed_judgments()
    else:
        outcomes = await run_judging_pass(config_ids, tasks, summaries)

    report_path = run_report(config_ids, metrics_rows, outcomes)

    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    logger.info(
        "eval pipeline finished in %.0fs (%.1fm)", elapsed, elapsed / 60
    )
    print(f"\nDone. Report: {report_path}")
    print(f"Elapsed: {elapsed:.0f}s ({elapsed/60:.1f}m)")


if __name__ == "__main__":
    asyncio.run(main())
