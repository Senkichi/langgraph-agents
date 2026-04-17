"""Tests for the matrix runner — structure, dispatch, resume, error capture."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from langgraph_agents.eval.corpus import Task
from langgraph_agents.eval.matrix import (
    Configuration,
    MatrixResult,
    default_configurations,
    load_matrix_summaries,
    run_matrix,
)
from langgraph_agents.pipeline.config import RunConfig, RunResult, models_all


def _task(id: str = "t1") -> Task:
    return Task(
        id=id,
        name=id,
        body=f"task {id}",
        length_hint="short",
        key_concepts=("foo",),
    )


def _cfg(id: str = "cfg1", variant="A") -> Configuration:
    return Configuration(id=id, variant=variant, models=models_all("opus"))


def _fake_run_result(run_config: RunConfig, plan: str = "PLAN", cost: float = 0.5) -> RunResult:
    from langgraph_agents.pipeline.artifacts import run_dir, write_summary

    artifacts_dir = str(run_dir(run_config.chatroom_dir, run_config.run_id))
    r = RunResult(
        variant=run_config.variant,
        run_id=run_config.run_id,
        final_plan=plan,
        total_cost_usd=cost,
        wall_clock_seconds=1.0,
        termination_reason="complete",
        artifacts_dir=artifacts_dir,
        config=run_config,
    )
    write_summary(r)
    return r


class TestConfiguration:
    def test_to_run_config_defaults(self, tmp_path):
        c = _cfg()
        t = _task()
        rc = c.to_run_config(t, chatroom_dir=str(tmp_path))
        assert rc.variant == "A"
        assert rc.run_id == "cfg1__t1"
        assert rc.task == "task t1"

    def test_overrides_applied(self, tmp_path):
        c = Configuration(
            id="cx",
            variant="B",
            models=models_all("opus"),
            overrides={"max_debate_rounds": 5, "anonymize_in_debate": False},
        )
        rc = c.to_run_config(_task("t2"), chatroom_dir=str(tmp_path))
        assert rc.max_debate_rounds == 5
        assert rc.anonymize_in_debate is False


class TestRunMatrix:
    def test_runs_every_pair(self, tmp_path):
        calls: list[str] = []

        async def fake_runner(rc: RunConfig) -> RunResult:
            calls.append(rc.run_id)
            return _fake_run_result(rc)

        tasks = [_task("t1"), _task("t2")]
        configs = [_cfg("ca"), _cfg("cb")]
        results = asyncio.run(
            run_matrix(tasks, configs, output_dir=tmp_path, runner=fake_runner)
        )
        assert len(results) == 4
        assert all(r.status == "ok" for r in results)
        assert set(calls) == {"ca__t1", "ca__t2", "cb__t1", "cb__t2"}

    def test_resume_skips_completed(self, tmp_path):
        """A second call should skip runs whose summary.json already exists."""
        async def fake_runner(rc: RunConfig) -> RunResult:
            return _fake_run_result(rc)

        tasks = [_task("t1")]
        configs = [_cfg("ca")]
        asyncio.run(run_matrix(tasks, configs, output_dir=tmp_path, runner=fake_runner))

        calls: list[str] = []

        async def tracking_runner(rc: RunConfig) -> RunResult:
            calls.append(rc.run_id)
            return _fake_run_result(rc)

        results = asyncio.run(
            run_matrix(tasks, configs, output_dir=tmp_path, runner=tracking_runner)
        )
        assert calls == [], "Already-complete runs must be skipped on resume"
        assert all(r.status == "skipped" for r in results)

    def test_resume_false_forces_rerun(self, tmp_path):
        async def fake_runner(rc: RunConfig) -> RunResult:
            return _fake_run_result(rc)

        tasks = [_task("t1")]
        configs = [_cfg("ca")]
        asyncio.run(run_matrix(tasks, configs, output_dir=tmp_path, runner=fake_runner))

        calls: list[str] = []

        async def tracker(rc: RunConfig) -> RunResult:
            calls.append(rc.run_id)
            return _fake_run_result(rc)

        asyncio.run(
            run_matrix(tasks, configs, output_dir=tmp_path, runner=tracker, resume=False)
        )
        assert calls == ["ca__t1"]

    def test_error_captured_per_run(self, tmp_path):
        async def sometimes_fails(rc: RunConfig) -> RunResult:
            if rc.run_id.endswith("__t2"):
                raise RuntimeError("simulated failure")
            return _fake_run_result(rc)

        tasks = [_task("t1"), _task("t2")]
        configs = [_cfg("cx")]
        results = asyncio.run(
            run_matrix(tasks, configs, output_dir=tmp_path, runner=sometimes_fails)
        )
        by_run_id = {r.run_id: r for r in results}
        assert by_run_id["cx__t1"].status == "ok"
        assert by_run_id["cx__t2"].status == "error"
        assert "simulated failure" in by_run_id["cx__t2"].error

    def test_semaphore_bounds_concurrency(self, tmp_path):
        import threading

        active = 0
        max_active = 0
        lock = threading.Lock()

        async def slow_runner(rc: RunConfig) -> RunResult:
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            with lock:
                active -= 1
            return _fake_run_result(rc)

        tasks = [_task(f"t{i}") for i in range(5)]
        configs = [_cfg("cx")]
        asyncio.run(
            run_matrix(tasks, configs, output_dir=tmp_path, runner=slow_runner, parallel=2)
        )
        assert max_active <= 2


class TestLoadMatrixSummaries:
    def test_collects_completed(self, tmp_path):
        async def fake_runner(rc: RunConfig) -> RunResult:
            return _fake_run_result(rc, plan=f"plan-{rc.run_id}")

        tasks = [_task("t1"), _task("t2")]
        configs = [_cfg("ca")]
        asyncio.run(run_matrix(tasks, configs, output_dir=tmp_path, runner=fake_runner))

        loaded = load_matrix_summaries(tmp_path, configs, tasks)
        assert set(loaded.keys()) == {("ca", "t1"), ("ca", "t2")}
        assert loaded[("ca", "t1")]["final_plan"] == "plan-ca__t1"


class TestDefaultConfigurations:
    def test_contains_both_variants(self):
        configs = default_configurations()
        variants = {c.variant for c in configs}
        assert variants == {"A", "B"}
        assert len(configs) == 10
