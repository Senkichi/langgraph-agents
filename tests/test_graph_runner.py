"""Tests for graph_runner: streaming and synchronous runners."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from langgraph_agents.graph_runner import run_graph, stream_graph


async def async_generator(items):
    for item in items:
        yield item


async def collect_stream(app, inputs, config):
    results = []
    async for node_name, update in stream_graph(app, inputs, config, print_progress=False):
        results.append((node_name, update))
    return results


class TestStreamGraph:
    def test_stream_graph_yields_node_updates(self):
        mock_app = MagicMock()

        async def mock_astream(*args, **kwargs):
            yield {"coder": {"code_diff": "diff content"}}
            yield {"synthesizer": {"build_verdict": "APPROVE"}}

        mock_app.astream = mock_astream
        results = asyncio.run(collect_stream(mock_app, {}, {"configurable": {"thread_id": "t1"}}))
        assert len(results) == 2
        assert results[0][0] == "coder"
        assert results[1][0] == "synthesizer"


class TestRunGraph:
    def test_run_graph_returns_final_state(self):
        mock_app = MagicMock()
        mock_app.invoke = MagicMock(return_value={"result": "done"})
        result = run_graph(mock_app, {"task": "x"}, {"configurable": {"thread_id": "t1"}}, print_progress=False)
        assert result == {"result": "done"}
        mock_app.invoke.assert_called_once()

    def test_run_graph_generates_thread_id_if_missing(self):
        mock_app = MagicMock()
        mock_app.invoke = MagicMock(return_value={})
        run_graph(mock_app, {}, print_progress=False)
        call_config = mock_app.invoke.call_args[1]["config"]
        assert "thread_id" in call_config["configurable"]
