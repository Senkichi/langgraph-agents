from langgraph.graph import END

from langgraph_agents.graphs.plan_review import build_plan_review_graph


class TestPlanReviewGraph:
    def test_graph_has_expected_nodes(self):
        graph = build_plan_review_graph()
        compiled = graph.compile()
        node_names = set(compiled.get_graph().nodes.keys())
        assert "planner" in node_names
        assert "plan_reviewer" in node_names

    def test_graph_edges_flow_correctly(self):
        """Verify the plan-review graph connects START → planner/reviewer and loops back."""
        graph = build_plan_review_graph()
        compiled = graph.compile()
        graph_data = compiled.get_graph()
        edge_sources = {e.source for e in graph_data.edges}
        assert "__start__" in edge_sources
        assert "planner" in edge_sources
        assert "plan_reviewer" in edge_sources

    def test_route_entry_with_plan_goes_to_reviewer(self):
        from langgraph_agents.graphs.plan_review import _route_entry

        state = {"task": "Build X", "current_plan": "Step 1...", "plan_feedback": "", "plan_verdict": "", "plan_cycle": 0}
        assert _route_entry(state) == "plan_reviewer"

    def test_route_entry_without_plan_goes_to_planner(self):
        from langgraph_agents.graphs.plan_review import _route_entry

        state = {"task": "Build X", "current_plan": "", "plan_feedback": "", "plan_verdict": "", "plan_cycle": 0}
        assert _route_entry(state) == "planner"

    def test_route_after_review_approve_ends(self):
        from langgraph_agents.graphs.plan_review import _route_after_review

        state = {"plan_verdict": "APPROVE", "plan_cycle": 1, "task": "", "current_plan": "", "plan_feedback": ""}
        assert _route_after_review(state) == END

    def test_route_after_review_revise_continues(self):
        from langgraph_agents.graphs.plan_review import _route_after_review

        state = {"plan_verdict": "REVISE", "plan_cycle": 1, "task": "", "current_plan": "", "plan_feedback": ""}
        assert _route_after_review(state) == "planner"

    def test_route_after_review_max_cycles_ends(self):
        from langgraph_agents.graphs.plan_review import _route_after_review

        state = {"plan_verdict": "REVISE", "plan_cycle": 2, "task": "", "current_plan": "", "plan_feedback": ""}
        assert _route_after_review(state) == END
