"""Tests for eval.report — aggregations and output file shapes."""

from __future__ import annotations

import csv
from pathlib import Path

from langgraph_agents.eval.judge_pairwise import JudgeVote, PairwiseOutcome
from langgraph_agents.eval.report import (
    build_report,
    compute_win_matrix,
    cost_adjusted_win_rates,
    termination_distribution,
    variant_aggregate,
)


def _outcome(
    a="cfgA",
    b="cfgB",
    preferred="A",
    bias=False,
    task="t1",
    judge="opus",
):
    return PairwiseOutcome(
        task_id=task,
        config_a=a,
        config_b=b,
        judge_model=judge,
        preferred=preferred,
        confidence_natural="high",
        confidence_swapped="high",
        position_bias_detected=bias,
        votes=(),
    )


class TestComputeWinMatrix:
    def test_single_outcome(self):
        wm = compute_win_matrix([_outcome(preferred="A")])
        assert wm[("cfgA", "cfgB")] == 1.0

    def test_tie_gives_half(self):
        wm = compute_win_matrix([_outcome(preferred="tie")])
        assert wm[("cfgA", "cfgB")] == 0.5

    def test_position_bias_gives_half(self):
        wm = compute_win_matrix([_outcome(preferred="A", bias=True)])
        assert wm[("cfgA", "cfgB")] == 0.5

    def test_averages_across_outcomes(self):
        outcomes = [
            _outcome(preferred="A", task="t1"),
            _outcome(preferred="B", task="t2"),
        ]
        wm = compute_win_matrix(outcomes)
        assert wm[("cfgA", "cfgB")] == 0.5


class TestVariantAggregate:
    def test_cross_variant_counted(self):
        outcomes = [
            _outcome(a="A1", b="B1", preferred="A"),  # A beats B
            _outcome(a="A2", b="B1", preferred="B"),  # B beats A
        ]
        agg = variant_aggregate(
            outcomes, variant_of={"A1": "A", "A2": "A", "B1": "B"}
        )
        assert agg["comparisons"] == 2
        assert agg["a_win_rate"] == 0.5
        assert agg["b_win_rate"] == 0.5

    def test_same_variant_ignored(self):
        outcomes = [_outcome(a="A1", b="A2", preferred="A")]
        agg = variant_aggregate(outcomes, variant_of={"A1": "A", "A2": "A"})
        assert agg["comparisons"] == 0


class TestTerminationDistribution:
    def test_counts(self):
        rows = [
            {"termination_reason": "complete"},
            {"termination_reason": "complete"},
            {"termination_reason": "mutual_agreement"},
            {"termination_reason": "max_rounds"},
        ]
        td = termination_distribution(rows)
        assert td == {"complete": 2, "mutual_agreement": 1, "max_rounds": 1}

    def test_empty_input(self):
        assert termination_distribution([]) == {}


class TestCostAdjustedWinRates:
    def test_rate_per_dollar(self):
        outcomes = [_outcome(a="A1", b="B1", preferred="A")]
        metrics = [
            {"run_id": "A1__t1", "total_cost_usd": 2.0},
            {"run_id": "B1__t1", "total_cost_usd": 1.0},
        ]
        adj = cost_adjusted_win_rates(outcomes, metrics)
        # A1 won once → win_rate = 1.0, cost = 2.0 → 0.5 wins/$
        assert adj["A1"] == 0.5
        # B1 lost once → win_rate = 0.0, cost = 1.0 → 0.0 wins/$
        assert adj["B1"] == 0.0


class TestBuildReport:
    def test_writes_expected_files(self, tmp_path):
        metrics = [
            {
                "run_id": "A1__t1",
                "variant": "A",
                "task_id": "t1",
                "total_cost_usd": 1.0,
                "wall_clock_seconds": 10.0,
                "termination_reason": "complete",
                "final_plan_chars": 120,
                "final_plan_tokens_est": 30,
                "concept_coverage_keyword": 1.0,
                "concept_coverage_token_jaccard": 0.5,
                "round_count": None,
                "compaction_count": None,
                "stance_flip_count": None,
            },
            {
                "run_id": "B1__t1",
                "variant": "B",
                "task_id": "t1",
                "total_cost_usd": 2.0,
                "wall_clock_seconds": 20.0,
                "termination_reason": "mutual_agreement",
                "final_plan_chars": 150,
                "final_plan_tokens_est": 37,
                "concept_coverage_keyword": 1.0,
                "concept_coverage_token_jaccard": 0.6,
                "round_count": 2,
                "compaction_count": 0,
                "stance_flip_count": 1,
            },
        ]
        outcomes = [_outcome(a="A1", b="B1", preferred="A")]
        path = build_report(
            metrics_rows=metrics,
            outcomes=outcomes,
            variant_of={"A1": "A", "B1": "B"},
            output_dir=tmp_path,
        )
        assert path.exists()
        assert (tmp_path / "metrics.csv").exists()
        assert (tmp_path / "judgments.csv").exists()
        assert (tmp_path / "win_matrix.csv").exists()

        # Headline numbers land in the markdown.
        content = path.read_text(encoding="utf-8")
        assert "Variant A vs Variant B" in content
        assert "Termination reason distribution" in content
        assert "mutual_agreement" in content

        # Metrics CSV round-trips.
        with (tmp_path / "metrics.csv").open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2
        assert rows[0]["run_id"] == "A1__t1"

    def test_empty_inputs_dont_crash(self, tmp_path):
        path = build_report(
            metrics_rows=[],
            outcomes=[],
            variant_of={},
            output_dir=tmp_path,
        )
        assert path.exists()
