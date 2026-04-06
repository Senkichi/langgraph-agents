from langgraph.graph import END

from langgraph_agents.graphs.build_review import (
    _route_after_synthesis,
    build_build_review_graph,
)
from langgraph_agents.nodes.review_synthesizer import synthesize_reviews


class TestBuildReviewGraph:
    def test_graph_has_expected_nodes(self):
        graph = build_build_review_graph()
        compiled = graph.compile()
        node_names = set(compiled.get_graph().nodes.keys())
        assert "coder" in node_names
        assert "micro_reviewer" in node_names
        assert "macro_reviewer" in node_names
        assert "synthesizer" in node_names

    def test_graph_edges_flow_correctly(self):
        """Verify the build-review graph connects START → coder → fan-out → synthesizer."""
        graph = build_build_review_graph()
        compiled = graph.compile()
        graph_data = compiled.get_graph()
        edge_sources = {e.source for e in graph_data.edges}
        assert "__start__" in edge_sources
        assert "coder" in edge_sources
        assert "synthesizer" in edge_sources


class TestRoutingLogic:
    def test_approve_ends(self):
        state = {"build_verdict": "APPROVE", "build_cycle": 1, "task": "", "current_plan": "", "code_diff": "", "workspace_path": "", "micro_feedback": "", "macro_feedback": "", "build_feedback": "", "e2e_feedback": ""}
        assert _route_after_synthesis(state) == END

    def test_revise_continues(self):
        state = {"build_verdict": "REVISE", "build_cycle": 2, "task": "", "current_plan": "", "code_diff": "", "workspace_path": "", "micro_feedback": "", "macro_feedback": "", "build_feedback": "", "e2e_feedback": ""}
        assert _route_after_synthesis(state) == "coder"

    def test_max_cycles_ends(self):
        state = {"build_verdict": "REVISE", "build_cycle": 4, "task": "", "current_plan": "", "code_diff": "", "workspace_path": "", "micro_feedback": "", "macro_feedback": "", "build_feedback": "", "e2e_feedback": ""}
        assert _route_after_synthesis(state) == END


class TestSynthesizer:
    def _base_state(self, **overrides) -> dict:
        defaults = {
            "micro_feedback": "", "macro_feedback": "",
            "task": "", "current_plan": "", "code_diff": "", "workspace_path": "",
            "build_verdict": "", "build_feedback": "", "build_cycle": 0, "e2e_feedback": "",
        }
        return {**defaults, **overrides}

    def test_both_approve(self):
        state = self._base_state(
            micro_feedback="VERDICT:APPROVE\nREASONING:Looks good.",
            macro_feedback="VERDICT:APPROVE\nREASONING:Architecture is solid.",
        )
        result = synthesize_reviews(state)
        assert result["build_verdict"] == "APPROVE"
        assert result["build_feedback"] == "Both reviewers approved."

    def test_micro_revise_omits_approve_feedback(self):
        state = self._base_state(
            micro_feedback="VERDICT:REVISE\nREASONING:Bugs found.\n\nCRITICAL:\n- foo.py:10 — null deref — ACTION: add guard",
            macro_feedback="VERDICT:APPROVE\nREASONING:Fine.",
        )
        result = synthesize_reviews(state)
        assert result["build_verdict"] == "REVISE"
        assert "## Micro Review" in result["build_feedback"]
        # APPROVE macro feedback should NOT appear
        assert "Macro Review" not in result["build_feedback"]
        assert "CRITICAL" in result["build_feedback"]

    def test_macro_revise_omits_approve_feedback(self):
        state = self._base_state(
            micro_feedback="VERDICT:APPROVE\nREASONING:Clean.",
            macro_feedback="VERDICT:REVISE\nREASONING:Bad architecture.\n\nMAJOR:\n- api.py:5 — no separation — ACTION: extract service layer",
        )
        result = synthesize_reviews(state)
        assert result["build_verdict"] == "REVISE"
        assert "## Macro Review" in result["build_feedback"]
        # APPROVE micro feedback should NOT appear
        assert "Micro Review" not in result["build_feedback"]

    def test_both_revise(self):
        state = self._base_state(
            micro_feedback="VERDICT:REVISE\nREASONING:Bugs.",
            macro_feedback="VERDICT:REVISE\nREASONING:Design issues.",
        )
        result = synthesize_reviews(state)
        assert result["build_verdict"] == "REVISE"
        assert "## Micro Review" in result["build_feedback"]
        assert "## Macro Review" in result["build_feedback"]

    def test_verdict_detection_tolerates_space_after_colon(self):
        """VERDICT: REVISE (space) must not be silently treated as APPROVE."""
        state = self._base_state(
            micro_feedback="VERDICT: REVISE\nREASONING: Bug found.",
            macro_feedback="VERDICT:APPROVE\nREASONING: Fine.",
        )
        result = synthesize_reviews(state)
        assert result["build_verdict"] == "REVISE", (
            "Space after colon in VERDICT: REVISE was misclassified as APPROVE"
        )

    def test_extracts_verdict_block_strips_exploration_traces(self):
        """Agent tool-use traces before the VERDICT: line should be stripped."""
        micro_with_traces = (
            "I read foo.py and found several issues.\n"
            "Running tests... 3 passed, 1 failed.\n"
            "VERDICT:REVISE\n"
            "REASONING:One test fails.\n\n"
            "CRITICAL:\n"
            "- foo.py:42 — off-by-one — ACTION: use < not <="
        )
        state = self._base_state(
            micro_feedback=micro_with_traces,
            macro_feedback="VERDICT:APPROVE\nREASONING:OK.",
        )
        result = synthesize_reviews(state)
        # Exploration traces should be stripped
        assert "I read foo.py" not in result["build_feedback"]
        assert "Running tests" not in result["build_feedback"]
        # Structured content preserved
        assert "VERDICT:REVISE" in result["build_feedback"]
        assert "CRITICAL" in result["build_feedback"]
