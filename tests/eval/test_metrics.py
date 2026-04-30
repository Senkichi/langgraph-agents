"""Tests for eval.metrics — concept coverage, transcript metrics, similarity."""

from __future__ import annotations

import pytest

from langgraph_agents.eval.corpus import Task
from langgraph_agents.eval.metrics import (
    METRIC_CLASSIFICATIONS,
    concept_coverage_keyword,
    concept_coverage_token_jaccard,
    cross_run_similarity,
    estimate_tokens,
    failure_mode_hit_rate,
    run_metrics,
    stance_flip_count,
)


def _task(**overrides) -> Task:
    base = dict(
        id="t",
        name="T",
        body="body",
        length_hint="short",
        key_concepts=("alpha", "beta"),
        failure_modes=(),
    )
    base.update(overrides)
    return Task(**base)


class TestConceptCoverageKeyword:
    def test_all_present(self):
        assert concept_coverage_keyword("alpha beta gamma", ["alpha", "beta"]) == 1.0

    def test_partial(self):
        assert concept_coverage_keyword("alpha only", ["alpha", "beta"]) == 0.5

    def test_none(self):
        assert concept_coverage_keyword("nothing here", ["alpha", "beta"]) == 0.0

    def test_case_insensitive(self):
        assert concept_coverage_keyword("ALPHA Beta", ["alpha", "beta"]) == 1.0

    def test_multi_word_concepts(self):
        assert concept_coverage_keyword(
            "use a partition key per tenant", ["partition key"]
        ) == 1.0

    def test_empty_concepts_returns_one(self):
        """Nothing to miss → full credit."""
        assert concept_coverage_keyword("x", []) == 1.0


class TestConceptCoverageJaccard:
    def test_identical(self):
        assert concept_coverage_token_jaccard("alpha beta", ["alpha", "beta"]) == 1.0

    def test_partial(self):
        val = concept_coverage_token_jaccard("alpha", ["alpha", "beta"])
        assert 0.0 < val < 1.0

    def test_empty_concepts_is_zero(self):
        """Contrast with keyword coverage: Jaccard treats empty as 0.0 so the
        two metrics don't both max out on vacuous input."""
        assert concept_coverage_token_jaccard("alpha", []) == 0.0


class TestFailureModeHitRate:
    def test_all_present(self):
        assert failure_mode_hit_rate(
            "this plan rubber-stamps as 'mostly fine' and ignores constraints",
            ["rubber-stamps as 'mostly fine'", "ignores constraints"],
        ) == 1.0

    def test_partial(self):
        assert failure_mode_hit_rate(
            "this plan ignores constraints",
            ["rubber-stamps as 'mostly fine'", "ignores constraints"],
        ) == 0.5

    def test_none(self):
        assert failure_mode_hit_rate(
            "a careful, well-grounded plan",
            ["rubber-stamps", "horizontal scaling"],
        ) == 0.0

    def test_case_insensitive(self):
        assert failure_mode_hit_rate(
            "RUBBER-STAMPS AS 'MOSTLY FINE'",
            ["rubber-stamps as 'mostly fine'"],
        ) == 1.0

    def test_empty_failure_modes_returns_zero(self):
        """No antipatterns to commit → hit rate = 0 (best case)."""
        assert failure_mode_hit_rate("anything", []) == 0.0

    def test_empty_plan_returns_zero(self):
        assert failure_mode_hit_rate("", ["x"]) == 0.0


class TestMetricClassifications:
    def test_all_metrics_classified(self):
        """Every per-run metric run_metrics emits must be classified."""
        # Compute a sample run_metrics output and check every numeric field
        # has a classification (excluding identifier / non-metric fields).
        task = _task(failure_modes=("alpha-fail",))
        summary = {
            "run_id": "cfg__t",
            "variant": "B",
            "final_plan": "alpha",
            "total_cost_usd": 0.5,
            "wall_clock_seconds": 5.0,
            "termination_reason": "complete",
        }
        m = run_metrics(summary, task)
        non_metric_fields = {
            "run_id", "variant", "config_id", "task_id", "termination_reason",
        }
        for field in m.keys() - non_metric_fields:
            assert field in METRIC_CLASSIFICATIONS, (
                f"metric {field!r} missing from METRIC_CLASSIFICATIONS"
            )

    def test_classifications_are_known_values(self):
        valid = {"decorative", "judged-independent"}
        for metric, klass in METRIC_CLASSIFICATIONS.items():
            assert klass in valid, f"{metric}: unknown classification {klass!r}"


class TestStanceFlipCount:
    def test_counts_flips_per_speaker(self):
        transcript = [
            {"speaker": "left", "stance": "DISAGREE"},
            {"speaker": "right", "stance": "DISAGREE"},
            {"speaker": "left", "stance": "AGREE"},     # flip
            {"speaker": "right", "stance": "DISAGREE"},  # no flip
            {"speaker": "left", "stance": "DISAGREE"},   # flip
        ]
        assert stance_flip_count(transcript) == 2

    def test_ignores_compaction_rows(self):
        transcript = [
            {"speaker": "left", "stance": "AGREE"},
            {"speaker": "compaction", "stance": None},
            {"speaker": "left", "stance": "DISAGREE"},
        ]
        assert stance_flip_count(transcript) == 1

    def test_missing_stance_skipped(self):
        transcript = [
            {"speaker": "left", "stance": "DISAGREE"},
            {"speaker": "left", "stance": None},
            {"speaker": "left", "stance": "AGREE"},
        ]
        # Flip between first and third turn; None doesn't reset tracking.
        assert stance_flip_count(transcript) == 1


class TestRunMetrics:
    def test_variant_a_basic(self):
        task = _task(
            key_concepts=("alpha", "beta", "gamma"),
            failure_modes=("rubber-stamps", "missing detail"),
        )
        summary = {
            "run_id": "cfg__t",
            "variant": "A",
            "final_plan": "alpha and beta — but this plan rubber-stamps the design",
            "total_cost_usd": 1.25,
            "wall_clock_seconds": 12.5,
            "termination_reason": "complete",
        }
        m = run_metrics(summary, task)
        assert m["variant"] == "A"
        assert m["total_cost_usd"] == 1.25
        assert m["concept_coverage_keyword"] == pytest.approx(2 / 3)
        # one of two failure-mode phrases hits ("rubber-stamps")
        assert m["failure_mode_hit_rate"] == 0.5
        assert m["round_count"] is None
        assert m["stance_flip_count"] is None

    def test_variant_b_transcript_metrics(self):
        task = _task()
        summary = {
            "run_id": "cfg__t",
            "variant": "B",
            "final_plan": "alpha",
            "total_cost_usd": 0.5,
            "wall_clock_seconds": 5.0,
            "termination_reason": "mutual_agreement",
        }
        transcript = [
            {"speaker": "left", "stance": "DISAGREE", "round": 1},
            {"speaker": "right", "stance": "DISAGREE", "round": 1},
            {"speaker": "compaction", "by": "left", "round": 2},
            {"speaker": "compaction", "by": "right", "round": 2},
            {"speaker": "left", "stance": "AGREE", "round": 2},
            {"speaker": "right", "stance": "AGREE", "round": 2},
        ]
        m = run_metrics(summary, task, transcript=transcript)
        assert m["round_count"] == 2
        assert m["compaction_count"] == 1  # one compaction = two entries
        assert m["stance_flip_count"] == 2


class TestCrossRunSimilarity:
    def test_identical_plans(self):
        sims = cross_run_similarity({"c1": "alpha beta gamma", "c2": "alpha beta gamma"})
        assert sims[("c1", "c2")] == 1.0

    def test_disjoint_plans(self):
        sims = cross_run_similarity({"c1": "alpha beta", "c2": "delta epsilon"})
        assert sims[("c1", "c2")] == 0.0

    def test_empty_plans_handled(self):
        sims = cross_run_similarity({"c1": "", "c2": ""})
        assert sims[("c1", "c2")] == 1.0


class TestEstimateTokens:
    def test_roughly_chars_over_four(self):
        assert estimate_tokens("a" * 40) == 10
