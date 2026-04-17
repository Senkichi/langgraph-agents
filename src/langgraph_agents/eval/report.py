"""Aggregate matrix runs + judgments + metrics into a decision-ready report.

The report is markdown (for reading) plus three CSV dumps (for slicing):

    report.md            — narrative + headline tables
    metrics.csv          — one row per completed run
    judgments.csv        — one row per (task, config_a, config_b, judge)
    win_matrix.csv       — wide-format win rates between every config pair

Aggregation rules (kept simple and explicit):

  - A judgment where ``position_bias_detected`` is True contributes 0.5 to
    both sides (i.e. a tie) when computing win rates.
  - A UNPARSEABLE vote contributes a tie.
  - Judgments are weighted equally across judges. If one judge is known to
    be authoritative, rerun the report with only that judge's rows.
"""

from __future__ import annotations

import csv
import logging
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from statistics import mean
from typing import Iterable, Mapping, Sequence

from .judge_pairwise import PairwiseOutcome

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Win matrix
# ---------------------------------------------------------------------------


def compute_win_matrix(
    outcomes: Sequence[PairwiseOutcome],
) -> dict[tuple[str, str], float]:
    """Return ``{(config_a, config_b): win_rate_of_a_over_b}`` in [0,1].

    A position-bias-flagged judgment contributes a tie (0.5).
    """
    totals: dict[tuple[str, str], list[float]] = defaultdict(list)
    for o in outcomes:
        if o.position_bias_detected or o.preferred == "tie":
            score = 0.5
        elif o.preferred == "A":
            score = 1.0
        else:
            score = 0.0
        totals[(o.config_a, o.config_b)].append(score)

    return {pair: mean(scores) for pair, scores in totals.items() if scores}


def variant_aggregate(
    outcomes: Sequence[PairwiseOutcome],
    *,
    variant_of: Mapping[str, str],
) -> dict:
    """Aggregate preference of A-configs vs B-configs on pairs that span them.

    ``variant_of[config_id]`` must return "A" or "B".
    """
    a_wins = 0.0
    b_wins = 0.0
    comparisons = 0
    for o in outcomes:
        va = variant_of.get(o.config_a)
        vb = variant_of.get(o.config_b)
        if va is None or vb is None or va == vb:
            continue
        comparisons += 1
        if o.position_bias_detected or o.preferred == "tie":
            a_wins += 0.5
            b_wins += 0.5
        elif o.preferred == "A":
            if va == "A":
                a_wins += 1
            else:
                b_wins += 1
        else:
            if vb == "A":
                a_wins += 1
            else:
                b_wins += 1
    if not comparisons:
        return {"comparisons": 0, "a_win_rate": 0.0, "b_win_rate": 0.0}
    return {
        "comparisons": comparisons,
        "a_win_rate": a_wins / comparisons,
        "b_win_rate": b_wins / comparisons,
    }


def termination_distribution(
    metrics_rows: Iterable[Mapping],
) -> dict[str, int]:
    """Count termination_reason values across a set of metric rows."""
    out: dict[str, int] = defaultdict(int)
    for row in metrics_rows:
        out[row.get("termination_reason") or "unknown"] += 1
    return dict(out)


def cost_adjusted_win_rates(
    outcomes: Sequence[PairwiseOutcome],
    metrics_rows: Sequence[Mapping],
) -> dict[str, float]:
    """Win rate per dollar, averaged across all comparisons for a config.

    ``metrics_rows`` provides per-config mean cost. Configs with zero cost
    are reported as ``inf`` (keeps the ordering well-defined in the report).
    """
    # Average cost per config across tasks.
    costs: dict[str, list[float]] = defaultdict(list)
    for row in metrics_rows:
        cid = _config_id_from_row(row)
        if cid is None:
            continue
        costs[cid].append(float(row.get("total_cost_usd") or 0.0))
    mean_cost = {cid: (mean(vs) if vs else 0.0) for cid, vs in costs.items()}

    # Win rate per config: count wins across every outcome in which it appears.
    wins: dict[str, list[float]] = defaultdict(list)
    for o in outcomes:
        if o.position_bias_detected or o.preferred == "tie":
            wins[o.config_a].append(0.5)
            wins[o.config_b].append(0.5)
        elif o.preferred == "A":
            wins[o.config_a].append(1.0)
            wins[o.config_b].append(0.0)
        else:
            wins[o.config_a].append(0.0)
            wins[o.config_b].append(1.0)

    out: dict[str, float] = {}
    for cid, values in wins.items():
        wr = mean(values) if values else 0.0
        c = mean_cost.get(cid, 0.0)
        out[cid] = wr / c if c > 0 else float("inf")
    return out


def _config_id_from_row(row: Mapping) -> str | None:
    run_id = row.get("run_id") or ""
    # run_id == "{config_id}__{task_id}"
    if "__" in run_id:
        return run_id.split("__", 1)[0]
    return None


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _write_csv(path: Path, rows: list[dict], fieldnames: Sequence[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _render_win_matrix_table(
    win_rates: Mapping[tuple[str, str], float], configs: Sequence[str]
) -> str:
    header = "| config | " + " | ".join(configs) + " |"
    sep = "|" + "|".join(["---"] * (len(configs) + 1)) + "|"
    rows = [header, sep]
    for ra in configs:
        cells = [ra]
        for cb in configs:
            if ra == cb:
                cells.append("—")
            elif (ra, cb) in win_rates:
                cells.append(f"{win_rates[(ra, cb)]:.2f}")
            elif (cb, ra) in win_rates:
                cells.append(f"{1.0 - win_rates[(cb, ra)]:.2f}")
            else:
                cells.append("")
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Top-level build
# ---------------------------------------------------------------------------


def build_report(
    *,
    metrics_rows: Sequence[Mapping],
    outcomes: Sequence[PairwiseOutcome],
    variant_of: Mapping[str, str],
    output_dir: Path | str,
) -> Path:
    """Write report artifacts and return the path to ``report.md``.

    The function is deterministic given its inputs — safe to re-run after
    corpus / configuration tweaks.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Metrics CSV
    metrics_fields = [
        "run_id",
        "variant",
        "task_id",
        "total_cost_usd",
        "wall_clock_seconds",
        "termination_reason",
        "final_plan_chars",
        "final_plan_tokens_est",
        "concept_coverage_keyword",
        "concept_coverage_token_jaccard",
        "round_count",
        "compaction_count",
        "stance_flip_count",
    ]
    _write_csv(output_dir / "metrics.csv", [dict(r) for r in metrics_rows], metrics_fields)

    # Judgments CSV
    judgment_fields = [
        "task_id",
        "config_a",
        "config_b",
        "judge_model",
        "preferred",
        "confidence_natural",
        "confidence_swapped",
        "position_bias_detected",
    ]
    _write_csv(
        output_dir / "judgments.csv",
        [_outcome_to_row(o) for o in outcomes],
        judgment_fields,
    )

    # Win matrix CSV
    win_rates = compute_win_matrix(outcomes)
    configs = sorted({c for pair in win_rates.keys() for c in pair})
    win_rows = []
    for ra in configs:
        row = {"config": ra}
        for cb in configs:
            if ra == cb:
                row[cb] = ""
            elif (ra, cb) in win_rates:
                row[cb] = f"{win_rates[(ra, cb)]:.4f}"
            elif (cb, ra) in win_rates:
                row[cb] = f"{1.0 - win_rates[(cb, ra)]:.4f}"
            else:
                row[cb] = ""
        win_rows.append(row)
    _write_csv(output_dir / "win_matrix.csv", win_rows, ["config", *configs])

    # Aggregations for the narrative
    variant_agg = variant_aggregate(outcomes, variant_of=variant_of)
    term_dist = termination_distribution(metrics_rows)
    cost_adj = cost_adjusted_win_rates(outcomes, metrics_rows)

    # Build report.md
    md: list[str] = []
    md.append("# Dual-Pipeline Evaluation Report\n")
    md.append(
        f"- Completed runs analysed: **{len(metrics_rows)}**\n"
        f"- Pairwise judgments collected: **{len(outcomes)}**\n"
        f"- Configurations: **{len(configs)}**\n"
    )

    md.append("\n## Variant A vs Variant B (cross-variant comparisons only)\n")
    md.append(
        f"- Comparisons spanning variants: **{variant_agg['comparisons']}**\n"
        f"- A win-rate: **{variant_agg['a_win_rate']:.2%}**\n"
        f"- B win-rate: **{variant_agg['b_win_rate']:.2%}**\n"
    )

    md.append("\n## Termination reason distribution\n")
    if term_dist:
        for reason, count in sorted(term_dist.items(), key=lambda kv: -kv[1]):
            md.append(f"- `{reason}`: **{count}**\n")
    else:
        md.append("- (no runs)\n")

    md.append("\n## Cost-adjusted win rate (wins per dollar)\n")
    if cost_adj:
        md.append("| config | wins/$ |\n|---|---|\n")
        for cid, rate in sorted(cost_adj.items(), key=lambda kv: -kv[1]):
            md.append(f"| {cid} | {rate if rate == float('inf') else f'{rate:.2f}'} |\n")
    else:
        md.append("- (no cost data)\n")

    md.append("\n## Pairwise win matrix\n")
    md.append("Values are row-vs-column win rate (position-bias flagged → 0.5).\n\n")
    if configs:
        md.append(_render_win_matrix_table(win_rates, configs))
    else:
        md.append("(no pairwise judgments available)")

    report_path = output_dir / "report.md"
    report_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return report_path


def _outcome_to_row(o: PairwiseOutcome) -> dict:
    d = asdict(o)
    d.pop("votes", None)
    d["position_bias_detected"] = "true" if o.position_bias_detected else "false"
    return d
