"""Tests for pipeline.session.single_query — mocks the subprocess CLI."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import Mock, patch

import pytest

from langgraph_agents.pipeline.session import AgentSession, single_query


def _fake_cli_result(result: str, cost: float, *, is_error: bool = False) -> Mock:
    return Mock(
        returncode=0,
        stdout=json.dumps(
            {
                "is_error": is_error,
                "result": result,
                "total_cost_usd": cost,
                "session_id": "sess-123",
            }
        ),
        stderr="",
    )


class TestSingleQuery:
    def test_returns_response_and_cost(self):
        fake = _fake_cli_result("hello world", 0.15)
        with patch(
            "langgraph_agents.pipeline.session.subprocess.run", return_value=fake
        ):
            response, cost = asyncio.run(
                single_query(
                    "sys prompt",
                    "user msg",
                    cwd="/tmp",
                    model="opus",
                )
            )
        assert response == "hello world"
        assert cost == pytest.approx(0.15)

    def test_zero_cost_when_envelope_missing_field(self):
        fake = Mock(
            returncode=0,
            stdout=json.dumps({"is_error": False, "result": "ok"}),
            stderr="",
        )
        with patch(
            "langgraph_agents.pipeline.session.subprocess.run", return_value=fake
        ):
            response, cost = asyncio.run(
                single_query("s", "u", cwd="/tmp", model="opus")
            )
        assert response == "ok"
        assert cost == 0.0

    def test_nonzero_exit_raises_runtime_error(self):
        fake = Mock(returncode=1, stdout="", stderr="boom")
        with patch(
            "langgraph_agents.pipeline.session.subprocess.run", return_value=fake
        ):
            with pytest.raises(RuntimeError, match="exit 1"):
                asyncio.run(single_query("s", "u", cwd="/tmp", model="opus"))

    def test_is_error_true_raises(self):
        fake = _fake_cli_result("something broke", 0.0, is_error=True)
        with patch(
            "langgraph_agents.pipeline.session.subprocess.run", return_value=fake
        ):
            with pytest.raises(RuntimeError, match="something broke"):
                asyncio.run(single_query("s", "u", cwd="/tmp", model="opus"))

    def test_invalid_json_raises(self):
        fake = Mock(returncode=0, stdout="not json", stderr="")
        with patch(
            "langgraph_agents.pipeline.session.subprocess.run", return_value=fake
        ):
            with pytest.raises(RuntimeError, match="parse"):
                asyncio.run(single_query("s", "u", cwd="/tmp", model="opus"))

    def test_builds_cli_args_with_options(self):
        """Verify allowed_tools and model make it into argv."""
        captured: dict = {}

        def fake_run(*args, **kwargs):
            captured["cmd"] = args[0]
            return _fake_cli_result("ok", 0.0)

        with patch("langgraph_agents.pipeline.session.subprocess.run", side_effect=fake_run):
            asyncio.run(
                single_query(
                    "sys",
                    "msg",
                    cwd="/tmp",
                    model="opus",
                    allowed_tools=["Read", "Bash"],
                    max_budget_usd=2.0,
                )
            )

        cmd = captured["cmd"]
        assert "--model" in cmd and "opus" in cmd
        assert "--allowed-tools" in cmd
        assert "Read,Bash" in cmd
        assert "--max-budget-usd" in cmd
        assert "2.0" in cmd
        assert cmd[-1] == "-"  # stdin sentinel


class TestAgentSessionInterface:
    """SDK is a hard dependency; these tests cover the wrapper's lifecycle
    guards without exercising the real SDK protocol (which would spawn the
    bundled Claude Code CLI subprocess)."""

    def test_constructor_records_inputs(self):
        s = AgentSession(
            "left", "sys", "/tmp", "opus", allowed_tools=["Read"]
        )
        assert s.name == "left"
        assert s.total_cost_usd == 0.0
        assert s.session_id is None
        assert s.turn_count == 0

    def test_send_before_start_raises(self):
        s = AgentSession("x", "sys", "/tmp", "opus")
        with pytest.raises(RuntimeError, match="not started"):
            asyncio.run(s.send("hi"))

    def test_close_before_start_is_noop(self):
        """close() must be safe to call in a finally block even if start
        never succeeded — registry.close_all relies on this."""
        s = AgentSession("x", "sys", "/tmp", "opus")
        asyncio.run(s.close())  # must not raise
