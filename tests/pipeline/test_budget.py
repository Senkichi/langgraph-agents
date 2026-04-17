"""Tests for pipeline.budget — cost and wall-clock guards."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from langgraph_agents.pipeline.budget import elapsed_seconds, over_budget


def _fresh_state(**overrides) -> dict:
    base = {
        "total_cost_usd": 0.0,
        "max_total_cost_usd": 5.0,
        "max_wall_clock_seconds": 600,
        "run_start_time": datetime.now(timezone.utc).isoformat(),
    }
    base.update(overrides)
    return base


class TestOverBudget:
    def test_under_both_caps(self):
        hit, reason = over_budget(_fresh_state(total_cost_usd=1.0))
        assert hit is False and reason == ""

    def test_at_cost_cap_triggers(self):
        hit, reason = over_budget(_fresh_state(total_cost_usd=5.0))
        assert hit is True and reason == "cost"

    def test_above_cost_cap_triggers(self):
        hit, reason = over_budget(_fresh_state(total_cost_usd=5.01))
        assert hit is True and reason == "cost"

    def test_zero_cost_cap_means_no_cap(self):
        """max_total_cost_usd == 0 disables the cost ceiling."""
        hit, reason = over_budget(
            _fresh_state(total_cost_usd=1_000_000, max_total_cost_usd=0.0)
        )
        assert hit is False and reason == ""

    def test_expired_wall_clock_triggers(self):
        past = datetime.now(timezone.utc) - timedelta(seconds=3600)
        hit, reason = over_budget(
            _fresh_state(run_start_time=past.isoformat(), max_wall_clock_seconds=60)
        )
        assert hit is True and reason == "timeout"

    def test_zero_wall_clock_cap_means_no_cap(self):
        past = datetime.now(timezone.utc) - timedelta(seconds=3600)
        hit, reason = over_budget(
            _fresh_state(run_start_time=past.isoformat(), max_wall_clock_seconds=0)
        )
        assert hit is False and reason == ""

    def test_cost_cap_checked_before_timeout(self):
        """If both fire, cost wins — deterministic for log/reason analytics."""
        past = datetime.now(timezone.utc) - timedelta(seconds=3600)
        hit, reason = over_budget(
            _fresh_state(
                total_cost_usd=100.0,
                max_total_cost_usd=5.0,
                max_wall_clock_seconds=60,
                run_start_time=past.isoformat(),
            )
        )
        assert hit is True and reason == "cost"

    def test_missing_start_time_disables_timeout(self):
        state = _fresh_state()
        state.pop("run_start_time")
        hit, reason = over_budget(state)
        assert hit is False and reason == ""

    def test_malformed_start_time_is_not_a_crash(self):
        hit, reason = over_budget(_fresh_state(run_start_time="not-iso"))
        assert hit is False and reason == ""


class TestElapsedSeconds:
    def test_zero_when_start_time_missing(self):
        assert elapsed_seconds({}) == 0.0

    def test_non_negative_when_start_in_past(self):
        past = datetime.now(timezone.utc) - timedelta(seconds=10)
        assert elapsed_seconds({"run_start_time": past.isoformat()}) >= 9.0

    def test_zero_when_start_in_future(self):
        """Clock skew guardrail — elapsed never goes negative."""
        future = datetime.now(timezone.utc) + timedelta(seconds=60)
        assert elapsed_seconds({"run_start_time": future.isoformat()}) == 0.0
