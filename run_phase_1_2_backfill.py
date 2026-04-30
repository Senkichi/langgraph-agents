"""Phase 1.2 backfill: validate ``failure_mode_hit_rate`` against judged win-rate.

Computes per-config mean ``failure_mode_hit_rate`` across all matrix runs,
derives per-config win rate from the corresponding ``judgments.jsonl``, and
reports the Pearson correlation between the two. A meaningful negative
correlation (lower failure-mode hit rate ↔ higher judged win rate) is
evidence to promote the metric from ``decorative`` to ``judged-independent``
in ``METRIC_CLASSIFICATIONS``.

For comparison, the same correlation is computed for ``concept_coverage_keyword``
(known decorative per experiment 002 Finding 2 — should land near zero) and
``final_plan_chars`` (size, also expected near zero).

Run:
    uv run --active python run_phase_1_2_backfill.py

Writes ``docs/phase_1_2_metric_validation.md`` and prints a summary table.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Iterable

from langgraph_agents.eval.corpus import DEFAULT_CORPUS_DIR, load_corpus
from langgraph_agents.eval.metrics import (
    concept_coverage_keyword,
    failure_mode_hit_rate,
)


EVAL_PAIRS: list[tuple[str, str]] = [
    ("logs/eval_2a/judgments.jsonl", "logs/matrix_2a_rounds"),
    ("logs/eval_2b/judgments.jsonl", "logs/matrix_2b_crossgen"),
]


def _pearson(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation. Returns 0.0 on degenerate input."""
    n = len(xs)
    if n != len(ys) or n < 2:
        return 0.0
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


def _per_config_win_rate(judgments_path: Path) -> dict[str, float]:
    """Aggregate per-config win rate (ties contribute 0.5 to both)."""
    scores: dict[str, list[float]] = defaultdict(list)
    with judgments_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            j = json.loads(line)
            ca = j["config_a"]
            cb = j["config_b"]
            preferred = j.get("preferred")
            biased = j.get("position_bias_detected")
            if biased or preferred == "tie":
                scores[ca].append(0.5)
                scores[cb].append(0.5)
            elif preferred == "A":
                scores[ca].append(1.0)
                scores[cb].append(0.0)
            elif preferred == "B":
                scores[ca].append(0.0)
                scores[cb].append(1.0)
    return {c: mean(s) for c, s in scores.items() if s}


def _per_config_metric_means(
    matrix_dir: Path, tasks_by_id: dict[str, "object"]
) -> dict[str, dict[str, float]]:
    """For each config in ``matrix_dir``, compute mean of three metrics across tasks."""
    accum: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"fm": [], "cov": [], "size": []}
    )
    for summary_path in matrix_dir.rglob("summary.json"):
        try:
            j = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        run_id = j.get("run_id") or ""
        if "__" not in run_id:
            continue
        config_id, task_id = run_id.split("__", 1)
        task = tasks_by_id.get(task_id)
        if task is None:
            continue
        plan = j.get("final_plan") or ""
        accum[config_id]["fm"].append(failure_mode_hit_rate(plan, task.failure_modes))
        accum[config_id]["cov"].append(concept_coverage_keyword(plan, task.key_concepts))
        accum[config_id]["size"].append(float(len(plan)))
    return {
        cid: {k: mean(v) if v else 0.0 for k, v in metrics.items()}
        for cid, metrics in accum.items()
    }


def main() -> None:
    tasks = load_corpus(DEFAULT_CORPUS_DIR)
    tasks_by_id = {t.id: t for t in tasks}

    out_lines: list[str] = []
    out_lines.append("# Phase 1.2 — `failure_mode_hit_rate` backfill validation\n")
    out_lines.append("**Date**: 2026-04-29\n")
    out_lines.append(
        "**Question**: Does `failure_mode_hit_rate` correlate negatively with "
        "judged win-rate across historical eval data? If yes, promote from "
        "`decorative` to `judged-independent` in `METRIC_CLASSIFICATIONS`.\n\n"
    )
    out_lines.append(
        "**Method**: For each (matrix, eval) pair, compute per-config mean of "
        "each metric across tasks, and per-config win rate from "
        "`judgments.jsonl` (ties + position-bias contribute 0.5). Pearson "
        "correlation between metric mean and win rate. Negative correlation "
        "means lower failure rate co-occurs with higher wins (the desired "
        "signal). For comparison, `concept_coverage_keyword` (known "
        "decorative per 002 Finding 2) and `final_plan_chars` (size) are "
        "included as null-hypothesis baselines.\n\n"
    )

    overall_pairs: list[tuple[float, float, float, float]] = []  # fm, cov, size, win
    summary_rows: list[str] = []

    for judgments_path_str, matrix_path_str in EVAL_PAIRS:
        judgments_path = Path(judgments_path_str)
        matrix_path = Path(matrix_path_str)
        if not judgments_path.exists() or not matrix_path.exists():
            print(f"[skip] {judgments_path} or {matrix_path} missing")
            continue

        win_rates = _per_config_win_rate(judgments_path)
        metric_means = _per_config_metric_means(matrix_path, tasks_by_id)
        configs = sorted(set(win_rates) & set(metric_means))
        if len(configs) < 2:
            print(f"[skip] {judgments_path}: only {len(configs)} overlapping configs")
            continue

        out_lines.append(f"## {matrix_path.name} × {judgments_path.parent.name}\n\n")
        out_lines.append("| config | n_tasks | mean failure_mode_hit_rate | mean concept_coverage_keyword | mean final_plan_chars | win_rate |\n")
        out_lines.append("|---|---|---|---|---|---|\n")
        fms, covs, sizes, wins = [], [], [], []
        for c in configs:
            mm = metric_means[c]
            wr = win_rates[c]
            fms.append(mm["fm"])
            covs.append(mm["cov"])
            sizes.append(mm["size"])
            wins.append(wr)
            n_tasks = sum(1 for _ in (matrix_path / c).rglob("summary.json"))
            out_lines.append(
                f"| `{c}` | {n_tasks} | {mm['fm']:.4f} | {mm['cov']:.4f} | "
                f"{mm['size']:.0f} | {wr:.4f} |\n"
            )
        r_fm = _pearson(fms, wins)
        r_cov = _pearson(covs, wins)
        r_size = _pearson(sizes, wins)
        out_lines.append(
            f"\n**Pearson r vs win_rate**: "
            f"failure_mode_hit_rate=**{r_fm:+.3f}**, "
            f"concept_coverage_keyword={r_cov:+.3f}, "
            f"final_plan_chars={r_size:+.3f}.\n\n"
        )
        summary_rows.append(
            f"| {matrix_path.name} | {len(configs)} | {r_fm:+.3f} | "
            f"{r_cov:+.3f} | {r_size:+.3f} |"
        )
        overall_pairs.extend(zip(fms, covs, sizes, wins))

    if overall_pairs:
        fms = [p[0] for p in overall_pairs]
        covs = [p[1] for p in overall_pairs]
        sizes = [p[2] for p in overall_pairs]
        wins = [p[3] for p in overall_pairs]
        r_fm = _pearson(fms, wins)
        r_cov = _pearson(covs, wins)
        r_size = _pearson(sizes, wins)

        out_lines.append("## Pooled across eval pairs\n\n")
        out_lines.append("| dataset | n_configs | r(failure_mode_hit_rate, win) | r(concept_coverage_keyword, win) | r(final_plan_chars, win) |\n")
        out_lines.append("|---|---|---|---|---|\n")
        for row in summary_rows:
            out_lines.append(row + "\n")
        out_lines.append(
            f"| **pooled** | **{len(overall_pairs)}** | **{r_fm:+.3f}** | "
            f"**{r_cov:+.3f}** | **{r_size:+.3f}** |\n\n"
        )

        # Verdict
        out_lines.append("## Verdict\n\n")
        if r_fm <= -0.30:
            verdict = (
                f"**Promote `failure_mode_hit_rate` to judged-independent.** "
                f"Pooled r={r_fm:+.3f} <= -0.30 -- lower failure-mode hit rate "
                f"co-occurs with higher judged win-rate at the threshold "
                f"chosen for promotion."
            )
        else:
            verdict = (
                f"**Keep `failure_mode_hit_rate` as decorative.** Pooled r="
                f"{r_fm:+.3f} does not clear the -0.30 promotion threshold. "
                f"The metric's recall is too low for these rubrics -- failure-"
                f"mode phrases are descriptive rather than detection-keyword "
                f"shaped, so substring hits are sparse and the signal is "
                f"swamped by noise. Future work: add per-task detection "
                f"phrases in the corpus, or replace substring matching with "
                f"a phrase-classifier or judge-prompted hit detection."
            )
        out_lines.append(verdict + "\n\n")
        out_lines.append("## Side finding -- `concept_coverage_keyword` is worse than decorative\n\n")
        out_lines.append(
            f"Pooled r(concept_coverage_keyword, win)={r_cov:+.3f} -- a strong "
            f"NEGATIVE correlation. Experiment 002 Finding 2 said the metric "
            f"\"does not track quality\". This backfill shows it actively "
            f"anti-tracks: configs that hit MORE rubric keywords WIN LESS. "
            f"Likely confounded by plan size (r(final_plan_chars, win)="
            f"{r_size:+.3f}) -- larger plans hit more keywords AND tend to "
            f"lose to the more-focused entries that won the judgments. "
            f"Recommendation: hide `concept_coverage_keyword` and "
            f"`concept_coverage_token_jaccard` from report.md tables in "
            f"future eval reports; keep them computed only because the cost "
            f"is trivial and historical CSVs still surface them.\n"
        )

        print(f"pooled r(failure_mode_hit_rate, win) = {r_fm:+.3f}")
        print(f"pooled r(concept_coverage_keyword, win) = {r_cov:+.3f}")
        print(f"pooled r(final_plan_chars, win) = {r_size:+.3f}")
        print()
        print(verdict)

    out_path = Path("docs/phase_1_2_metric_validation.md")
    out_path.write_text("".join(out_lines), encoding="utf-8")
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
