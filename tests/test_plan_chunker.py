"""Tests for plan chunker node and chunk-loop routing."""

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from langgraph_agents.graphs.plan_build_review import (
    _advance_chunk,
    _route_after_discovery,
    _route_after_build_review,
    _route_entry,
    build_plan_build_review_graph,
)
from langgraph_agents.models import ChunkStep, ExecutionPlan
from langgraph_agents.nodes.plan_chunker import chunk_plan


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestChunkStepModel:
    def test_valid_step(self):
        step = ChunkStep(
            step_id="step_1",
            title="Add models",
            plan_section="Create the SQLAlchemy models...",
        )
        assert step.step_id == "step_1"

    def test_roundtrip(self):
        step = ChunkStep(step_id="s1", title="T", plan_section="P")
        assert ChunkStep.model_validate(step.model_dump()) == step


class TestExecutionPlanModel:
    def test_valid_plan(self):
        plan = ExecutionPlan(
            steps=[
                ChunkStep(step_id="s1", title="First", plan_section="Do X"),
                ChunkStep(step_id="s2", title="Second", plan_section="Do Y"),
            ]
        )
        assert len(plan.steps) == 2

    def test_empty_steps_rejected(self):
        with pytest.raises(ValidationError):
            ExecutionPlan(steps=[])

    def test_single_step_allowed(self):
        plan = ExecutionPlan(
            steps=[ChunkStep(step_id="s1", title="Only", plan_section="Everything")]
        )
        assert len(plan.steps) == 1


# ---------------------------------------------------------------------------
# Chunker node tests
# ---------------------------------------------------------------------------


class TestChunkPlanNode:
    def _make_state(self, **overrides) -> dict:
        defaults = {
            "task": "Build a REST API",
            "current_plan": "1. Create models\n2. Add routes\n3. Write tests",
            "agent_architecture": "Flask app with SQLite",
            "workspace_path": "/tmp/test",
        }
        return {**defaults, **overrides}

    def test_produces_chunks_from_structured_output(self):
        mock_response = {
            "steps": [
                {"step_id": "s1", "title": "Models", "plan_section": "Create models..."},
                {"step_id": "s2", "title": "Routes", "plan_section": "Add routes..."},
            ]
        }
        with patch("langgraph_agents.nodes.plan_chunker.invoke_structured", return_value=mock_response):
            result = chunk_plan(self._make_state())

        assert len(result["chunks"]) == 2
        assert result["chunk_index"] == 0
        assert result["full_plan"] == "1. Create models\n2. Add routes\n3. Write tests"

    def test_preserves_full_plan(self):
        plan = "detailed multi-step plan text"
        mock_response = {
            "steps": [{"step_id": "s1", "title": "All", "plan_section": plan}]
        }
        with patch("langgraph_agents.nodes.plan_chunker.invoke_structured", return_value=mock_response):
            result = chunk_plan(self._make_state(current_plan=plan))

        assert result["full_plan"] == plan

    def test_single_step_plan(self):
        mock_response = {
            "steps": [{"step_id": "s1", "title": "Everything", "plan_section": "Do it all"}]
        }
        with patch("langgraph_agents.nodes.plan_chunker.invoke_structured", return_value=mock_response):
            result = chunk_plan(self._make_state())

        assert len(result["chunks"]) == 1

    def test_contract_rejects_empty_plan(self):
        from langgraph_agents.node_contract import NodeContractError

        with pytest.raises(NodeContractError, match="current_plan"):
            chunk_plan(self._make_state(current_plan=""))

    def test_chunks_are_serialized_dicts(self):
        mock_response = {
            "steps": [
                {"step_id": "s1", "title": "A", "plan_section": "Do A"},
            ]
        }
        with patch("langgraph_agents.nodes.plan_chunker.invoke_structured", return_value=mock_response):
            result = chunk_plan(self._make_state())

        chunk = result["chunks"][0]
        assert isinstance(chunk, dict)
        assert chunk["step_id"] == "s1"
        assert chunk["title"] == "A"
        assert chunk["plan_section"] == "Do A"


# ---------------------------------------------------------------------------
# Advance chunk node tests
# ---------------------------------------------------------------------------


class TestAdvanceChunk:
    def test_increments_index(self):
        state = {
            "chunk_index": 0,
            "chunks": [
                {"step_id": "s1", "title": "A", "plan_section": "Do A"},
                {"step_id": "s2", "title": "B", "plan_section": "Do B"},
            ],
        }
        result = _advance_chunk(state)
        assert result["chunk_index"] == 1

    def test_increments_from_middle(self):
        state = {
            "chunk_index": 2,
            "chunks": [{"step_id": f"s{i}", "title": f"T{i}", "plan_section": f"P{i}"} for i in range(5)],
        }
        result = _advance_chunk(state)
        assert result["chunk_index"] == 3


# ---------------------------------------------------------------------------
# Routing tests
# ---------------------------------------------------------------------------


class TestRouteAfterBuildReview:
    def test_more_chunks_routes_to_advance(self):
        state = {
            "chunks": [{"step_id": "s1"}, {"step_id": "s2"}, {"step_id": "s3"}],
            "chunk_index": 0,
        }
        assert _route_after_build_review(state) == "advance_chunk"

    def test_middle_chunk_routes_to_advance(self):
        state = {
            "chunks": [{"step_id": "s1"}, {"step_id": "s2"}, {"step_id": "s3"}],
            "chunk_index": 1,
        }
        assert _route_after_build_review(state) == "advance_chunk"

    def test_last_chunk_routes_to_e2e(self):
        state = {
            "chunks": [{"step_id": "s1"}, {"step_id": "s2"}],
            "chunk_index": 1,
        }
        assert _route_after_build_review(state) == "e2e_test"

    def test_single_chunk_routes_to_e2e(self):
        state = {
            "chunks": [{"step_id": "s1"}],
            "chunk_index": 0,
        }
        assert _route_after_build_review(state) == "e2e_test"

    def test_empty_chunks_routes_to_e2e(self):
        state = {"chunks": [], "chunk_index": 0}
        assert _route_after_build_review(state) == "e2e_test"


class TestEntryRouting:
    def test_start_always_routes_to_discover(self):
        state = {"skip_plan_review": True}
        assert _route_entry(state) == "discover_architecture"

    def test_no_skip_routes_to_discover(self):
        state = {"skip_plan_review": False}
        assert _route_entry(state) == "discover_architecture"

    def test_missing_flag_routes_to_discover(self):
        state = {}
        assert _route_entry(state) == "discover_architecture"

    def test_skip_plan_review_routes_after_discovery_to_chunker(self):
        state = {"skip_plan_review": True}
        assert _route_after_discovery(state) == "plan_chunker"

    def test_no_skip_routes_after_discovery_to_plan_review(self):
        state = {"skip_plan_review": False}
        assert _route_after_discovery(state) == "plan_review"


# ---------------------------------------------------------------------------
# Graph structure tests
# ---------------------------------------------------------------------------


class TestGraphStructure:
    def test_graph_has_chunker_node(self):
        graph = build_plan_build_review_graph()
        compiled = graph.compile()
        node_names = set(compiled.get_graph().nodes.keys())
        assert "plan_chunker" in node_names

    def test_graph_has_advance_chunk_node(self):
        graph = build_plan_build_review_graph()
        compiled = graph.compile()
        node_names = set(compiled.get_graph().nodes.keys())
        assert "advance_chunk" in node_names

    def test_plan_review_flows_to_chunker(self):
        graph = build_plan_build_review_graph()
        compiled = graph.compile()
        graph_data = compiled.get_graph()
        plan_review_targets = {
            e.target for e in graph_data.edges if e.source == "plan_review"
        }
        assert "plan_chunker" in plan_review_targets

    def test_chunker_flows_to_build_review(self):
        graph = build_plan_build_review_graph()
        compiled = graph.compile()
        graph_data = compiled.get_graph()
        chunker_targets = {
            e.target for e in graph_data.edges if e.source == "plan_chunker"
        }
        assert "build_review" in chunker_targets


# ---------------------------------------------------------------------------
# Build review chunk-awareness tests
# ---------------------------------------------------------------------------


class TestBuildReviewChunkAwareness:
    """Verify _call_build_review assembles chunk-aware coder context."""

    def _make_state(self, **overrides) -> dict:
        defaults = {
            "task": "test task",
            "current_plan": "original plan",
            "current_code": "",
            "workspace_path": "/tmp",
            "e2e_verdict": "",
            "e2e_report": "",
            "e2e_cycle": 0,
            "agent_architecture": "",
            "chunks": [
                {"step_id": "s1", "title": "First step", "plan_section": "Do first thing"},
                {"step_id": "s2", "title": "Second step", "plan_section": "Do second thing"},
            ],
            "chunk_index": 0,
            "full_plan": "The full original plan",
            "resolved_issues": [],
            "persistent_rules": "",
        }
        return {**defaults, **overrides}

    def test_coder_sees_chunk_context(self):
        from langgraph_agents.graphs.plan_build_review import _call_build_review

        with patch("langgraph_agents.graphs.plan_build_review.build_review_app") as mock_app:
            mock_app.invoke.return_value = {"code_diff": "", "resolved_issues": [], "persistent_rules": ""}
            _call_build_review(self._make_state())

        subgraph_input = mock_app.invoke.call_args[0][0]
        plan = subgraph_input["current_plan"]
        assert "step 1 of 2" in plan
        assert "First step" in plan
        assert "Do first thing" in plan
        assert "The full original plan" in plan

    def test_second_chunk_context(self):
        from langgraph_agents.graphs.plan_build_review import _call_build_review

        with patch("langgraph_agents.graphs.plan_build_review.build_review_app") as mock_app:
            mock_app.invoke.return_value = {"code_diff": "", "resolved_issues": [], "persistent_rules": ""}
            _call_build_review(self._make_state(chunk_index=1))

        subgraph_input = mock_app.invoke.call_args[0][0]
        plan = subgraph_input["current_plan"]
        assert "step 2 of 2" in plan
        assert "Second step" in plan
        assert "Do second thing" in plan

    def test_invalid_chunk_index_falls_back_to_full_plan(self):
        from langgraph_agents.graphs.plan_build_review import _call_build_review

        with patch("langgraph_agents.graphs.plan_build_review.build_review_app") as mock_app:
            mock_app.invoke.return_value = {"code_diff": "", "resolved_issues": [], "persistent_rules": ""}
            _call_build_review(self._make_state(chunk_index=5))

        subgraph_input = mock_app.invoke.call_args[0][0]
        assert subgraph_input["current_plan"] == "The full original plan"

    def test_carries_forward_resolved_issues(self):
        from langgraph_agents.graphs.plan_build_review import _call_build_review

        prior_issues = ["Fixed SQL injection in user_query"]
        with patch("langgraph_agents.graphs.plan_build_review.build_review_app") as mock_app:
            mock_app.invoke.return_value = {
                "code_diff": "",
                "resolved_issues": prior_issues + ["New fix"],
                "persistent_rules": "rule1",
            }
            result = _call_build_review(self._make_state(resolved_issues=prior_issues))

        # Verify issues were passed to subgraph
        subgraph_input = mock_app.invoke.call_args[0][0]
        assert subgraph_input["resolved_issues"] == prior_issues

        # Verify result carries forward accumulated issues
        assert result["resolved_issues"] == prior_issues + ["New fix"]
        assert result["persistent_rules"] == "rule1"

    def test_no_chunks_falls_back_to_current_plan(self):
        from langgraph_agents.graphs.plan_build_review import _call_build_review

        with patch("langgraph_agents.graphs.plan_build_review.build_review_app") as mock_app:
            mock_app.invoke.return_value = {"code_diff": "", "resolved_issues": [], "persistent_rules": ""}
            _call_build_review(self._make_state(chunks=[], full_plan=""))

        subgraph_input = mock_app.invoke.call_args[0][0]
        assert subgraph_input["current_plan"] == "original plan"
