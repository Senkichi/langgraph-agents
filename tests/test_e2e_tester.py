from unittest.mock import patch

from langgraph_agents.nodes.e2e_tester import (
    _build_e2e_context,
    _format_feedback,
    _parse_verdict,
    e2e_test,
)


class TestFormatFeedback:
    def test_verdict_present_unchanged(self):
        text = "Analysis...\nVERDICT:APPROVE\nREASONING:All good."
        assert _format_feedback(text) == text

    def test_missing_verdict_defaults_to_revise(self):
        text = "Some analysis without a verdict line."
        result = _format_feedback(text)
        assert result.startswith("VERDICT:REVISE\n")
        assert text in result


class TestParseVerdict:
    def test_approve(self):
        assert _parse_verdict("stuff\nVERDICT:APPROVE\nmore") == "APPROVE"

    def test_revise(self):
        assert _parse_verdict("stuff\nVERDICT:REVISE\nmore") == "REVISE"

    def test_skip(self):
        assert _parse_verdict("stuff\nVERDICT:SKIP\nmore") == "SKIP"

    def test_missing_defaults_to_revise(self):
        assert _parse_verdict("no verdict here") == "REVISE"

    def test_case_insensitive_value(self):
        assert _parse_verdict("VERDICT:approve") == "APPROVE"

    def test_whitespace_in_value(self):
        assert _parse_verdict("VERDICT: APPROVE ") == "APPROVE"

    def test_unknown_verdict_defaults_to_revise(self):
        assert _parse_verdict("VERDICT:MAYBE") == "REVISE"


class TestBuildE2eContext:
    def test_includes_task_and_plan(self):
        state = {
            "task": "Build a widget",
            "current_plan": "Step 1: ...",
            "current_code": "",
            "workspace_path": "/tmp",
            "e2e_verdict": "",
            "e2e_report": "",
            "e2e_cycle": 0,
        }
        context = _build_e2e_context(state)
        assert "Build a widget" in context
        assert "Step 1:" in context

    def test_includes_code_diff_when_present(self):
        state = {
            "task": "task",
            "current_plan": "plan",
            "current_code": "+new line",
            "workspace_path": "/tmp",
            "e2e_verdict": "",
            "e2e_report": "",
            "e2e_cycle": 0,
        }
        context = _build_e2e_context(state)
        assert "+new line" in context

    def test_excludes_prior_e2e_report(self):
        """The context must NOT include prior e2e_report to avoid anchoring."""
        state = {
            "task": "task",
            "current_plan": "plan",
            "current_code": "",
            "workspace_path": "/tmp",
            "e2e_verdict": "REVISE",
            "e2e_report": "OLD REPORT SHOULD NOT APPEAR",
            "e2e_cycle": 1,
        }
        context = _build_e2e_context(state)
        assert "OLD REPORT SHOULD NOT APPEAR" not in context


class TestE2eTestNode:
    def _make_state(self, **overrides) -> dict:
        defaults = {
            "task": "Build a REST API",
            "current_plan": "1. Create endpoints",
            "current_code": "+app.get('/users')",
            "workspace_path": "/tmp/workspace",
            "e2e_verdict": "",
            "e2e_report": "",
            "e2e_cycle": 0,
        }
        return {**defaults, **overrides}

    @patch("langgraph_agents.nodes.e2e_tester.invoke_agent")
    def test_approve_verdict(self, mock_invoke):
        mock_invoke.return_value = (
            "Tests pass. Output quality is good.\n"
            "VERDICT:APPROVE\n"
            "REASONING:All intended outcomes achieved."
        )
        result = e2e_test(self._make_state())
        assert result["e2e_verdict"] == "APPROVE"
        assert result["e2e_cycle"] == 1

    @patch("langgraph_agents.nodes.e2e_tester.invoke_agent")
    def test_revise_verdict_preserves_report(self, mock_invoke):
        report = (
            "INTENT GAPS: API returns empty results\n"
            "EVIDENCE: GET /users returns []\n"
            "ROOT CAUSE: No seed data\n"
            "PROPOSED FIXES: Add fixtures\n"
            "VERDICT:REVISE\n"
            "REASONING:Output does not match intent."
        )
        mock_invoke.return_value = report
        result = e2e_test(self._make_state())
        assert result["e2e_verdict"] == "REVISE"
        assert "INTENT GAPS" in result["e2e_report"]
        assert result["e2e_cycle"] == 1

    @patch("langgraph_agents.nodes.e2e_tester.invoke_agent")
    def test_skip_verdict(self, mock_invoke):
        mock_invoke.return_value = (
            "Cannot execute: requires PostgreSQL.\n"
            "VERDICT:SKIP\n"
            "REASONING:Database not available in test environment."
        )
        result = e2e_test(self._make_state())
        assert result["e2e_verdict"] == "SKIP"
        assert "PostgreSQL" in result["e2e_report"]

    @patch("langgraph_agents.nodes.e2e_tester.invoke_agent")
    def test_missing_verdict_defaults_to_revise(self, mock_invoke):
        mock_invoke.return_value = "The code has issues but I forgot the verdict."
        result = e2e_test(self._make_state())
        assert result["e2e_verdict"] == "REVISE"
        assert result["e2e_report"].startswith("VERDICT:REVISE\n")

    @patch("langgraph_agents.nodes.e2e_tester.invoke_agent")
    def test_cycle_increments_from_current(self, mock_invoke):
        mock_invoke.return_value = "VERDICT:APPROVE\nREASONING:Fine."
        result = e2e_test(self._make_state(e2e_cycle=1))
        assert result["e2e_cycle"] == 2

    @patch("langgraph_agents.nodes.e2e_tester.invoke_agent")
    def test_invokes_with_correct_params(self, mock_invoke):
        mock_invoke.return_value = "VERDICT:APPROVE\nREASONING:OK."
        state = self._make_state(workspace_path="/my/workspace")
        e2e_test(state)
        mock_invoke.assert_called_once()
        call_kwargs = mock_invoke.call_args
        assert call_kwargs.kwargs["cwd"] == "/my/workspace"
        assert call_kwargs.kwargs["model"] == "opus"
        assert call_kwargs.kwargs["allowed_tools"] == ["Read", "Glob", "Grep", "Bash"]
