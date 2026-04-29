"""Tests for the tracer module: GraphTracer, traced_route, context vars."""

import json
import threading
from pathlib import Path

import pytest

from langgraph_agents.tracer import (
    GraphTracer,
    get_current_node,
    get_tracer,
    set_current_node,
    set_tracer,
    traced_route,
)


# ---------------------------------------------------------------------------
# GraphTracer
# ---------------------------------------------------------------------------


class TestGraphTracer:
    def test_creates_log_file(self, tmp_path):
        tracer = GraphTracer("run-1", "test_graph", tmp_path, capture_environment=False)
        tracer.graph_start({})
        tracer.graph_end(100.0)
        assert list(tmp_path.glob("*.jsonl"))

    def test_graph_start_captures_environment_by_default(self, tmp_path, monkeypatch):
        """graph_start emits an environment block paired with run provenance."""
        # Use a stub capture so the test doesn't shell out to git/claude.
        sentinel = {
            "git_sha": "deadbeef",
            "git_branch": "master",
            "git_dirty": False,
            "claude_cli_version": "2.1.118",
            "claude_agent_sdk_version": "0.1.62",
            "python_version": "3.13.5 (CPython, win32)",
            "platform": "Windows-11",
        }
        import langgraph_agents.environment as env_mod

        monkeypatch.setattr(env_mod, "capture", lambda: sentinel)

        tracer = GraphTracer("run-1", "g", tmp_path)
        tracer.graph_start({})
        tracer.graph_end(0)

        events = _read_events(tracer.log_path)
        start = next(e for e in events if e["event_type"] == "graph_start")
        assert start["environment"] == sentinel

    def test_graph_start_omits_environment_when_disabled(self, tmp_path):
        tracer = GraphTracer("run-1", "g", tmp_path, capture_environment=False)
        tracer.graph_start({})
        tracer.graph_end(0)

        events = _read_events(tracer.log_path)
        start = next(e for e in events if e["event_type"] == "graph_start")
        assert start["environment"] is None

    def test_graph_start_environment_failure_is_swallowed(self, tmp_path, monkeypatch):
        """Env capture must never fail a run — git missing, SDK probe blew up, etc."""
        import langgraph_agents.environment as env_mod

        def _boom():
            raise RuntimeError("git not on PATH")

        monkeypatch.setattr(env_mod, "capture", _boom)

        tracer = GraphTracer("run-1", "g", tmp_path)
        tracer.graph_start({})  # must not raise
        tracer.graph_end(0)

        events = _read_events(tracer.log_path)
        start = next(e for e in events if e["event_type"] == "graph_start")
        assert start["environment"] is None

    def test_jsonl_format(self, tmp_path):
        tracer = GraphTracer("run-1", "test_graph", tmp_path)
        tracer.graph_start({"task": "hello"})
        tracer.graph_end(100.0)

        lines = tracer.log_path.read_text().strip().splitlines()
        assert len(lines) == 2
        for line in lines:
            data = json.loads(line)
            assert "event_type" in data
            assert "timestamp" in data
            assert data["run_id"] == "run-1"
            assert data["graph_name"] == "test_graph"

    def test_node_lifecycle_events(self, tmp_path):
        tracer = GraphTracer("run-1", "test_graph", tmp_path)
        tracer.node_start("coder", {"task": "x", "plan": "y"})
        tracer.node_end("coder", 5000.0, {"code_diff": "abc"})
        tracer.graph_end(6000.0)

        events = _read_events(tracer.log_path)
        types = [e["event_type"] for e in events]
        assert "node_start" in types
        assert "node_end" in types

        node_end = next(e for e in events if e["event_type"] == "node_end")
        assert node_end["node_name"] == "coder"
        assert node_end["duration_ms"] == 5000.0

    def test_state_field_sizes_captured(self, tmp_path):
        tracer = GraphTracer("run-1", "g", tmp_path, trace_level="state")
        tracer.node_start("n", {"big_field": "x" * 1000, "small": "hi"})
        tracer.graph_end(0)

        events = _read_events(tracer.log_path)
        start = next(e for e in events if e["event_type"] == "node_start")
        assert start["state_field_sizes"]["big_field"] == 1000
        assert start["state_field_sizes"]["small"] == 2

    def test_timing_level_omits_field_sizes(self, tmp_path):
        tracer = GraphTracer("run-1", "g", tmp_path, trace_level="timing")
        tracer.node_start("n", {"task": "hello"})
        tracer.graph_end(0)

        events = _read_events(tracer.log_path)
        start = next(e for e in events if e["event_type"] == "node_start")
        assert start["state_field_sizes"] == {}

    def test_llm_call_events_at_debug_level(self, tmp_path):
        tracer = GraphTracer("run-1", "g", tmp_path, trace_level="debug")
        tracer.llm_call_start("coder", "sonnet", "prompt text")
        tracer.llm_call_end("coder", "sonnet", 3000.0, "response text")
        tracer.graph_end(0)

        events = _read_events(tracer.log_path)
        types = [e["event_type"] for e in events]
        assert "llm_call_start" in types
        assert "llm_call_end" in types

        start = next(e for e in events if e["event_type"] == "llm_call_start")
        assert start["prompt_chars"] == len("prompt text")
        assert start["estimated_prompt_tokens"] == len("prompt text") // 4

    def test_llm_call_events_omitted_at_state_level(self, tmp_path):
        tracer = GraphTracer("run-1", "g", tmp_path, trace_level="state")
        tracer.llm_call_start("coder", "sonnet", "prompt")
        tracer.llm_call_end("coder", "sonnet", 1000.0, "response")
        tracer.graph_end(0)

        events = _read_events(tracer.log_path)
        types = [e["event_type"] for e in events]
        assert "llm_call_start" not in types
        assert "llm_call_end" not in types

    def test_edge_route_events(self, tmp_path):
        tracer = GraphTracer("run-1", "g", tmp_path, trace_level="state")
        tracer.edge_route("coder", "micro_reviewer", ["micro_reviewer", "macro_reviewer"])
        tracer.graph_end(0)

        events = _read_events(tracer.log_path)
        route = next(e for e in events if e["event_type"] == "edge_route")
        assert route["source_node"] == "coder"
        assert route["chosen_target"] == "micro_reviewer"

    def test_contract_violation_always_logged(self, tmp_path):
        tracer = GraphTracer("run-1", "g", tmp_path, trace_level="timing")
        tracer.contract_violation("coder", "pre", ["task is empty"])
        tracer.graph_end(0)

        events = _read_events(tracer.log_path)
        violation = next(e for e in events if e["event_type"] == "contract_violation")
        assert violation["phase"] == "pre"
        assert "task is empty" in violation["violations"]

    def test_push_pop_graph(self, tmp_path):
        tracer = GraphTracer("run-1", "parent", tmp_path)
        assert tracer.graph_name == "parent"

        tracer.push_graph("build_review")
        assert tracer.graph_name == "build_review"

        tracer.node_start("coder", {})
        events_before_pop = _read_events(tracer.log_path)
        start_evt = next(e for e in events_before_pop if e["event_type"] == "node_start")
        assert start_evt["graph_name"] == "build_review"

        tracer.pop_graph()
        assert tracer.graph_name == "parent"
        tracer.graph_end(0)

    def test_pop_graph_does_not_underflow(self, tmp_path):
        tracer = GraphTracer("run-1", "root", tmp_path)
        tracer.pop_graph()  # should not crash
        assert tracer.graph_name == "root"
        tracer.graph_end(0)

    def test_summary_structure(self, tmp_path):
        tracer = GraphTracer("run-1", "g", tmp_path)
        tracer.node_end("coder", 5000.0, {})
        tracer.node_end("coder", 3000.0, {})
        tracer.node_end("synthesizer", 100.0, {})
        summary = tracer.graph_end(10000.0)

        assert summary["total_duration_s"] == 10.0
        assert len(summary["node_breakdown"]) == 2
        assert summary["node_breakdown"][0]["node"] == "coder"
        assert summary["node_breakdown"][0]["cycles"] == 2
        assert summary["bottleneck"]["node"] == "coder"

    def test_thread_safety(self, tmp_path):
        tracer = GraphTracer("run-1", "g", tmp_path)
        errors = []

        def emit_events(node_name, count):
            try:
                for _ in range(count):
                    tracer.node_start(node_name, {"x": "y"})
                    tracer.node_end(node_name, 10.0, {"r": "s"})
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=emit_events, args=("micro_reviewer", 50)),
            threading.Thread(target=emit_events, args=("macro_reviewer", 50)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        events = _read_events(tracer.log_path)
        # 100 start + 100 end = 200 events
        assert len(events) == 200
        tracer.graph_end(0)


# ---------------------------------------------------------------------------
# Context variables
# ---------------------------------------------------------------------------


class TestContextVars:
    def test_get_set_tracer(self, tmp_path):
        assert get_tracer() is None

        tracer = GraphTracer("run-1", "g", tmp_path)
        token = set_tracer(tracer)
        assert get_tracer() is tracer

        set_tracer(None)
        assert get_tracer() is None
        tracer.graph_end(0)

    def test_get_set_current_node(self):
        set_current_node("unknown")
        assert get_current_node() == "unknown"
        set_current_node("coder")
        assert get_current_node() == "coder"
        set_current_node("unknown")


# ---------------------------------------------------------------------------
# traced_route decorator
# ---------------------------------------------------------------------------


class TestTracedRoute:
    def test_emits_edge_route_when_tracer_active(self, tmp_path):
        tracer = GraphTracer("run-1", "g", tmp_path, trace_level="state")
        set_tracer(tracer)

        @traced_route("e2e_test", ["__end__", "build_review"])
        def my_route(state):
            return "build_review"

        result = my_route({"e2e_verdict": "REVISE"})
        assert result == "build_review"

        events = _read_events(tracer.log_path)
        route_events = [e for e in events if e["event_type"] == "edge_route"]
        assert len(route_events) == 1
        assert route_events[0]["chosen_target"] == "build_review"

        set_tracer(None)
        tracer.graph_end(0)

    def test_noop_when_no_tracer(self):
        set_tracer(None)

        @traced_route("start", ["a", "b"])
        def my_route(state):
            return "a"

        result = my_route({})
        assert result == "a"

    def test_preserves_function_name(self):
        @traced_route("x", ["a"])
        def specific_name(state):
            return "a"

        assert specific_name.__name__ == "specific_name"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_events(path: Path) -> list[dict]:
    """Read all JSONL events from a trace file."""
    return [json.loads(line) for line in path.read_text().strip().splitlines() if line.strip()]
