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
            "resolved_issues": [], "persistent_rules": "",
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

    def test_micro_revise_includes_approve_as_preservation_signal(self):
        """When micro REVISEs and macro APPROVEs, macro's approval is included
        as a 'do not regress' signal so the coder knows what to preserve."""
        state = self._base_state(
            micro_feedback="VERDICT:REVISE\nREASONING:Bugs found.\n\nCRITICAL:\n- foo.py:10 — null deref — ACTION: add guard",
            macro_feedback="VERDICT:APPROVE\nREASONING:Architecture is solid.",
        )
        result = synthesize_reviews(state)
        assert result["build_verdict"] == "REVISE"
        assert "## Micro Review" in result["build_feedback"]
        assert "CRITICAL" in result["build_feedback"]
        assert "Macro Review" in result["build_feedback"]
        assert "do not regress" in result["build_feedback"].lower() or "APPROVED" in result["build_feedback"]

    def test_macro_revise_includes_approve_as_preservation_signal(self):
        """When macro REVISEs and micro APPROVEs, micro's approval is included."""
        state = self._base_state(
            micro_feedback="VERDICT:APPROVE\nREASONING:Clean.",
            macro_feedback="VERDICT:REVISE\nREASONING:Bad architecture.\n\nMAJOR:\n- api.py:5 — no separation — ACTION: extract service layer",
        )
        result = synthesize_reviews(state)
        assert result["build_verdict"] == "REVISE"
        assert "## Macro Review" in result["build_feedback"]
        assert "Micro Review" in result["build_feedback"]
        assert "do not regress" in result["build_feedback"].lower() or "APPROVED" in result["build_feedback"]

    def test_both_approve_no_preservation_noise(self):
        """When both approve, the feedback stays minimal — no spurious preservation sections."""
        state = self._base_state(
            micro_feedback="VERDICT:APPROVE\nREASONING:Looks good.",
            macro_feedback="VERDICT:APPROVE\nREASONING:Solid.",
        )
        result = synthesize_reviews(state)
        assert result["build_verdict"] == "APPROVE"
        assert "do not regress" not in result["build_feedback"].lower()

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

    def test_synthesizer_accumulates_resolved_issues_on_approve(self):
        """When verdict is APPROVE and prior feedback had CRITICAL items, they become resolved."""
        state = self._base_state(
            micro_feedback="VERDICT:APPROVE\nREASONING:Fixed.",
            macro_feedback="VERDICT:APPROVE\nREASONING:Good.",
            build_feedback="CRITICAL:\n- foo.py:10 — null deref — ACTION: add guard",
        )
        result = synthesize_reviews(state)
        assert result["build_verdict"] == "APPROVE"
        assert "foo.py:10" in result["resolved_issues"][0]

    def test_synthesizer_does_not_populate_resolved_on_revise(self):
        state = self._base_state(
            micro_feedback="VERDICT:REVISE\nREASONING:Still broken.",
            macro_feedback="VERDICT:APPROVE\nREASONING:OK.",
            build_feedback="CRITICAL:\n- bar.py:5 — bad logic — ACTION: fix",
        )
        result = synthesize_reviews(state)
        assert result["build_verdict"] == "REVISE"
        assert result["resolved_issues"] == []

    def test_synthesizer_preserves_existing_resolved_issues(self):
        state = self._base_state(
            micro_feedback="VERDICT:APPROVE\nREASONING:All good.",
            macro_feedback="VERDICT:APPROVE\nREASONING:Solid.",
            resolved_issues=["prior_issue"],
            build_feedback="MAJOR:\n- baz.py:1 — perf — ACTION: optimize",
        )
        result = synthesize_reviews(state)
        assert "prior_issue" in result["resolved_issues"]
