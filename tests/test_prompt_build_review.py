from langgraph.graph import END

from langgraph_agents.graphs.prompt_build_review import (
    _route_after_synthesis,
    build_prompt_build_review_graph,
)
from langgraph_agents.nodes.prompt_review_synthesizer import synthesize_prompt_reviews


class TestPromptBuildReviewGraph:
    def test_graph_has_expected_nodes(self):
        graph = build_prompt_build_review_graph()
        compiled = graph.compile()
        node_names = set(compiled.get_graph().nodes.keys())
        assert "prompt_engineer" in node_names
        assert "behavioral_reviewer" in node_names
        assert "architectural_reviewer" in node_names
        assert "synthesizer" in node_names

    def test_graph_edges_flow_correctly(self):
        """Verify the prompt build-review graph connects engineer → fan-out → synthesizer."""
        graph = build_prompt_build_review_graph()
        compiled = graph.compile()
        graph_data = compiled.get_graph()
        edge_sources = {e.source for e in graph_data.edges}
        assert "__start__" in edge_sources
        assert "prompt_engineer" in edge_sources
        assert "synthesizer" in edge_sources


class TestRoutingLogic:
    _base = {
        "task": "", "current_plan": "", "agent_architecture": "",
        "prompt_diff": "", "workspace_path": "",
        "behavioral_feedback": "", "architectural_feedback": "",
        "build_feedback": "",
    }

    def test_approve_ends(self):
        state = {**self._base, "build_verdict": "APPROVE", "build_cycle": 1}
        assert _route_after_synthesis(state) == END

    def test_revise_continues(self):
        state = {**self._base, "build_verdict": "REVISE", "build_cycle": 2}
        assert _route_after_synthesis(state) == "prompt_engineer"

    def test_max_cycles_ends(self):
        state = {**self._base, "build_verdict": "REVISE", "build_cycle": 4}
        assert _route_after_synthesis(state) == END


class TestPromptSynthesizer:
    _base = {
        "task": "", "current_plan": "", "agent_architecture": "",
        "prompt_diff": "", "workspace_path": "",
        "build_verdict": "", "build_feedback": "", "build_cycle": 0,
    }

    def test_both_approve(self):
        state = {
            **self._base,
            "behavioral_feedback": "VERDICT:APPROVE\nClear instructions.",
            "architectural_feedback": "VERDICT:APPROVE\nBoundaries intact.",
        }
        result = synthesize_prompt_reviews(state)
        assert result["build_verdict"] == "APPROVE"

    def test_behavioral_revise(self):
        state = {
            **self._base,
            "behavioral_feedback": "VERDICT:REVISE\nAmbiguous instructions.",
            "architectural_feedback": "VERDICT:APPROVE\nFine.",
        }
        result = synthesize_prompt_reviews(state)
        assert result["build_verdict"] == "REVISE"
        assert "Behavioral Review (REVISE" in result["build_feedback"]
        assert "Architectural Review (APPROVED" in result["build_feedback"]

    def test_architectural_revise(self):
        state = {
            **self._base,
            "behavioral_feedback": "VERDICT:APPROVE\nClear.",
            "architectural_feedback": "VERDICT:REVISE\nIsolation boundary violated.",
        }
        result = synthesize_prompt_reviews(state)
        assert result["build_verdict"] == "REVISE"
        assert "Architectural Review (REVISE" in result["build_feedback"]
        assert "Behavioral Review (APPROVED" in result["build_feedback"]

    def test_both_revise(self):
        state = {
            **self._base,
            "behavioral_feedback": "VERDICT:REVISE\nUnclear.",
            "architectural_feedback": "VERDICT:REVISE\nBroken deps.",
        }
        result = synthesize_prompt_reviews(state)
        assert result["build_verdict"] == "REVISE"
