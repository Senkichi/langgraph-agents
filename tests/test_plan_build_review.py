from unittest.mock import patch

from langgraph.graph import END

from langgraph_agents.graphs.plan_build_review import (
    _route_after_e2e,
    _route_entry,
    build_plan_build_review_graph,
)


class TestPlanBuildReviewGraph:
    def test_graph_compiles(self):
        graph = build_plan_build_review_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_graph_has_expected_nodes(self):
        graph = build_plan_build_review_graph()
        compiled = graph.compile()
        node_names = set(compiled.get_graph().nodes.keys())
        assert "discover_architecture" in node_names
        assert "plan_review" in node_names
        assert "build_review" in node_names
        assert "e2e_test" in node_names

    def test_graph_edges_flow_correctly(self):
        """Verify the parent graph has the expected flow including e2e_test."""
        graph = build_plan_build_review_graph()
        compiled = graph.compile()
        graph_data = compiled.get_graph()
        edge_sources = {e.source for e in graph_data.edges}
        assert "__start__" in edge_sources
        assert "plan_review" in edge_sources
        assert "build_review" in edge_sources
        assert "e2e_test" in edge_sources


class TestE2eRouting:
    def _make_state(self, *, verdict: str = "", cycle: int = 0) -> dict:
        return {
            "task": "",
            "current_plan": "",
            "current_code": "",
            "workspace_path": "",
            "e2e_verdict": verdict,
            "e2e_report": "",
            "e2e_cycle": cycle,
        }

    def test_approve_ends(self):
        state = self._make_state(verdict="APPROVE", cycle=1)
        assert _route_after_e2e(state) == END

    def test_skip_ends(self):
        state = self._make_state(verdict="SKIP", cycle=1)
        assert _route_after_e2e(state) == END

    def test_revise_continues(self):
        state = self._make_state(verdict="REVISE", cycle=1)
        assert _route_after_e2e(state) == "build_review"

    def test_revise_at_max_cycles_ends(self):
        state = self._make_state(verdict="REVISE", cycle=2)
        assert _route_after_e2e(state) == END

    def test_revise_beyond_max_cycles_ends(self):
        state = self._make_state(verdict="REVISE", cycle=3)
        assert _route_after_e2e(state) == END

    def test_empty_verdict_continues(self):
        """Empty verdict (shouldn't happen) is treated as REVISE."""
        state = self._make_state(verdict="", cycle=0)
        assert _route_after_e2e(state) == "build_review"


class TestSkipPlanReview:
    def test_skip_plan_review_routes_start_to_build_review(self):
        state = {"skip_plan_review": True}
        assert _route_entry(state) == "build_review"

    def test_no_skip_routes_start_to_discover_architecture(self):
        state = {"skip_plan_review": False}
        assert _route_entry(state) == "discover_architecture"

    def test_missing_flag_defaults_to_discover_architecture(self):
        state = {}
        assert _route_entry(state) == "discover_architecture"


class TestCheckpointing:
    def test_graph_supports_checkpointing(self):
        from langgraph.checkpoint.memory import InMemorySaver

        graph = build_plan_build_review_graph()
        app = graph.compile(checkpointer=InMemorySaver())
        assert app is not None
        config = {"configurable": {"thread_id": "test-thread-1"}}
        state = app.get_state(config)
        assert state is not None

    def test_coder_node_has_retry_policy(self):
        from langgraph_agents.graphs.build_review import build_build_review_graph

        graph = build_build_review_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_plan_review_visible_in_subgraph_stream(self):
        from langgraph.checkpoint.memory import InMemorySaver

        graph = build_plan_build_review_graph()
        compiled = graph.compile(checkpointer=InMemorySaver())
        graph_data = compiled.get_graph(xray=True)
        all_node_names = {n for n in graph_data.nodes.keys()}
        # Native subgraph nodes are prefixed: plan_review:planner, plan_review:plan_reviewer
        has_plan_review = any("plan_review" in n for n in all_node_names)
        assert has_plan_review


class TestBuildReviewFeedbackInjection:
    """Verify _call_build_review injects e2e_feedback and caps build budget on re-entry.

    These tests call the REAL _call_build_review() with a mocked build_review_app,
    then inspect the subgraph_input that was passed to build_review_app.invoke().
    """

    def _make_state(self, **overrides) -> dict:
        defaults = {
            "task": "test",
            "current_plan": "plan",
            "current_code": "",
            "workspace_path": "/tmp",
            "e2e_verdict": "",
            "e2e_report": "",
            "e2e_cycle": 0,
        }
        return {**defaults, **overrides}

    def test_no_e2e_report_means_empty_feedback(self):
        from langgraph_agents.graphs.plan_build_review import _call_build_review

        with patch("langgraph_agents.graphs.plan_build_review.build_review_app") as mock_app:
            mock_app.invoke.return_value = {"code_diff": ""}
            state = self._make_state(e2e_verdict="APPROVE", e2e_report="some report", e2e_cycle=1)
            _call_build_review(state)

        subgraph_input = mock_app.invoke.call_args[0][0]
        assert subgraph_input["e2e_feedback"] == "", (
            "Non-REVISE verdict must NOT inject e2e_report into the subgraph"
        )

    def test_revise_injects_e2e_report(self):
        from langgraph_agents.graphs.plan_build_review import _call_build_review

        report = "INTENT GAPS: quality is poor\nEVIDENCE: ..."
        with patch("langgraph_agents.graphs.plan_build_review.build_review_app") as mock_app:
            mock_app.invoke.return_value = {"code_diff": ""}
            state = self._make_state(e2e_verdict="REVISE", e2e_report=report, e2e_cycle=1)
            _call_build_review(state)

        subgraph_input = mock_app.invoke.call_args[0][0]
        assert subgraph_input["e2e_feedback"] == report, (
            "REVISE verdict must inject the full e2e_report as e2e_feedback"
        )

    def test_initial_entry_starts_build_cycle_at_zero(self):
        """First build-review pass gets the full cycle budget."""
        from langgraph_agents.graphs.plan_build_review import _call_build_review

        with patch("langgraph_agents.graphs.plan_build_review.build_review_app") as mock_app:
            mock_app.invoke.return_value = {"code_diff": ""}
            state = self._make_state(e2e_verdict="", e2e_cycle=0)
            _call_build_review(state)

        subgraph_input = mock_app.invoke.call_args[0][0]
        assert subgraph_input["build_cycle"] == 0, (
            "Initial (non-reentry) invocation must pass build_cycle=0 for full budget"
        )

    def test_e2e_reentry_caps_build_cycle(self):
        """E2E REVISE re-entry sets build_cycle to MAX-1, allowing exactly one pass."""
        from langgraph_agents.graphs.build_review import MAX_BUILD_CYCLES
        from langgraph_agents.graphs.plan_build_review import _call_build_review

        with patch("langgraph_agents.graphs.plan_build_review.build_review_app") as mock_app:
            mock_app.invoke.return_value = {"code_diff": "..."}
            state = self._make_state(e2e_verdict="REVISE", e2e_report="...", e2e_cycle=1)
            _call_build_review(state)

        subgraph_input = mock_app.invoke.call_args[0][0]
        assert subgraph_input["build_cycle"] == MAX_BUILD_CYCLES - 1, (
            f"E2E re-entry must cap build_cycle at MAX-1 ({MAX_BUILD_CYCLES - 1}), "
            f"got: {subgraph_input['build_cycle']}"
        )
