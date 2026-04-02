from langgraph.graph import END

from langgraph_agents.graphs.build_review import (
    _route_after_synthesis,
    build_build_review_graph,
)
from langgraph_agents.nodes.review_synthesizer import synthesize_reviews


class TestBuildReviewGraph:
    def test_graph_compiles(self):
        graph = build_build_review_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_graph_has_expected_nodes(self):
        graph = build_build_review_graph()
        compiled = graph.compile()
        node_names = set(compiled.get_graph().nodes.keys())
        assert "coder" in node_names
        assert "micro_reviewer" in node_names
        assert "macro_reviewer" in node_names
        assert "synthesizer" in node_names


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
    def test_both_approve(self):
        state = {
            "micro_feedback": "VERDICT:APPROVE\nLooks good.",
            "macro_feedback": "VERDICT:APPROVE\nArchitecture is solid.",
            "task": "", "current_plan": "", "code_diff": "", "workspace_path": "",
            "build_verdict": "", "build_feedback": "", "build_cycle": 0, "e2e_feedback": "",
        }
        result = synthesize_reviews(state)
        assert result["build_verdict"] == "APPROVE"

    def test_micro_revise(self):
        state = {
            "micro_feedback": "VERDICT:REVISE\nBugs found.",
            "macro_feedback": "VERDICT:APPROVE\nFine.",
            "task": "", "current_plan": "", "code_diff": "", "workspace_path": "",
            "build_verdict": "", "build_feedback": "", "build_cycle": 0, "e2e_feedback": "",
        }
        result = synthesize_reviews(state)
        assert result["build_verdict"] == "REVISE"
        assert "Micro Review (REVISE)" in result["build_feedback"]

    def test_macro_revise(self):
        state = {
            "micro_feedback": "VERDICT:APPROVE\nClean.",
            "macro_feedback": "VERDICT:REVISE\nBad architecture.",
            "task": "", "current_plan": "", "code_diff": "", "workspace_path": "",
            "build_verdict": "", "build_feedback": "", "build_cycle": 0, "e2e_feedback": "",
        }
        result = synthesize_reviews(state)
        assert result["build_verdict"] == "REVISE"
        assert "Macro Review (REVISE)" in result["build_feedback"]

    def test_both_revise(self):
        state = {
            "micro_feedback": "VERDICT:REVISE\nBugs.",
            "macro_feedback": "VERDICT:REVISE\nDesign issues.",
            "task": "", "current_plan": "", "code_diff": "", "workspace_path": "",
            "build_verdict": "", "build_feedback": "", "build_cycle": 0, "e2e_feedback": "",
        }
        result = synthesize_reviews(state)
        assert result["build_verdict"] == "REVISE"
