from unittest.mock import patch

from langgraph_agents.node_contract import parse_verdict
from langgraph_agents.nodes.e2e_tester import (
    _build_e2e_context,
    _extract_changed_files,
    _extract_proposed_fixes,
    _suggest_test_commands,
    e2e_test,
)
from langgraph_agents.tools.dev_tools import DIFF_MAX_CHARS, truncate_diff


class TestParseVerdictE2E:
    """Tests for parse_verdict in the e2e context (APPROVE/REVISE/SKIP)."""

    def test_approve(self):
        assert parse_verdict("stuff\nVERDICT:APPROVE\nmore", "APPROVE", "REVISE", "SKIP") == "APPROVE"

    def test_revise(self):
        assert parse_verdict("stuff\nVERDICT:REVISE\nmore", "APPROVE", "REVISE", "SKIP") == "REVISE"

    def test_skip(self):
        assert parse_verdict("stuff\nVERDICT:SKIP\nmore", "APPROVE", "REVISE", "SKIP") == "SKIP"

    def test_missing_defaults_to_revise(self):
        assert parse_verdict("no verdict here", "APPROVE", "REVISE", "SKIP") == "REVISE"

    def test_case_insensitive_value(self):
        assert parse_verdict("VERDICT:approve", "APPROVE", "REVISE", "SKIP") == "APPROVE"

    def test_whitespace_in_value(self):
        assert parse_verdict("VERDICT: APPROVE ", "APPROVE", "REVISE", "SKIP") == "APPROVE"

    def test_unknown_verdict_defaults_to_revise(self):
        assert parse_verdict("VERDICT:MAYBE", "APPROVE", "REVISE", "SKIP") == "REVISE"


class TestExtractChangedFiles:
    def test_extracts_paths_from_unified_diff(self):
        diff = (
            "--- a/src/foo.py\n"
            "+++ b/src/foo.py\n"
            "@@ -1,3 +1,4 @@\n"
            "+new line\n"
            "--- a/src/bar.py\n"
            "+++ b/src/bar.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        )
        assert _extract_changed_files(diff) == ["src/bar.py", "src/foo.py"]

    def test_deduplicates(self):
        diff = "+++ b/src/foo.py\n+++ b/src/foo.py\n"
        assert _extract_changed_files(diff) == ["src/foo.py"]

    def test_excludes_dev_null(self):
        diff = "+++ b//dev/null\n+++ b/src/real.py\n"
        assert "src/real.py" in _extract_changed_files(diff)

    def test_empty_diff(self):
        assert _extract_changed_files("") == []

    def test_no_plus_lines(self):
        assert _extract_changed_files("just some text\nno diff markers") == []


class TestSuggestTestCommands:
    def test_maps_source_files_to_test_commands(self):
        files = ["src/pkg/enricher.py", "src/pkg/scorer.py"]
        result = _suggest_test_commands(files)
        assert "## Suggested Test Commands" in result
        assert "enricher" in result
        assert "scorer" in result
        assert "-x --tb=short" in result

    def test_skips_test_files(self):
        files = ["tests/test_foo.py", "src/bar.py"]
        result = _suggest_test_commands(files)
        assert "bar" in result
        assert "test_foo" not in result

    def test_skips_non_python_files_and_surfaces_them(self):
        files = ["README.md", "config.yaml", "src/app.py"]
        result = _suggest_test_commands(files)
        assert "app" in result
        # Non-Python files should be surfaced in their own section
        assert "Non-Python" in result or "README" not in result.split("Suggested Test Commands")[0]

    def test_returns_empty_for_no_source_files(self):
        assert _suggest_test_commands(["tests/test_a.py"]) == ""

    def test_caps_at_five_commands(self):
        files = [f"src/mod{i}.py" for i in range(10)]
        result = _suggest_test_commands(files)
        assert result.count("uv run pytest") <= 5

    def test_skips_test_files_with_leading_slash(self):
        files = ["src/utils/test_helper.py", "src/core.py"]
        result = _suggest_test_commands(files)
        assert "core" in result
        assert "test_helper" not in result

    def test_non_python_files_surfaced(self):
        files = ["schema.sql", "config.yaml"]
        result = _suggest_test_commands(files)
        assert "Changed Non-Python Files" in result
        assert "schema.sql" in result


class TestExtractProposedFixes:
    def test_returns_section_content(self):
        report = (
            "INTENT GAPS: missing feature\n"
            "EVIDENCE: test fails\n"
            "ROOT CAUSE: incomplete impl\n"
            "PROPOSED FIXES: Add the missing handler\n"
            "- Update router.py to handle /users endpoint\n"
            "VERDICT:REVISE\n"
            "REASONING:Needs work."
        )
        result = _extract_proposed_fixes(report)
        assert "Add the missing handler" in result
        assert "Update router.py" in result
        assert "VERDICT" not in result

    def test_returns_empty_when_absent(self):
        report = "VERDICT:APPROVE\nREASONING:All good."
        assert _extract_proposed_fixes(report) == ""


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

    def test_includes_test_commands_when_diff_has_source_files(self):
        diff = (
            "--- a/src/enricher.py\n"
            "+++ b/src/enricher.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        )
        state = {
            "task": "task",
            "current_plan": "plan",
            "current_code": diff,
            "workspace_path": "/tmp",
            "e2e_verdict": "",
            "e2e_report": "",
            "e2e_cycle": 0,
        }
        context = _build_e2e_context(state)
        assert "Suggested Test Commands" in context
        assert "enricher" in context

    def test_no_test_commands_when_only_test_files_changed(self):
        diff = "+++ b/tests/test_foo.py\n"
        state = {
            "task": "task",
            "current_plan": "plan",
            "current_code": diff,
            "workspace_path": "/tmp",
            "e2e_verdict": "",
            "e2e_report": "",
            "e2e_cycle": 0,
        }
        context = _build_e2e_context(state)
        assert "Suggested Test Commands" not in context

    def test_includes_prior_fixes_on_reentry(self):
        state = {
            "task": "task",
            "current_plan": "plan",
            "current_code": "",
            "workspace_path": "/tmp",
            "e2e_verdict": "REVISE",
            "e2e_report": "PROPOSED FIXES: Add handler\n- Fix router\nVERDICT:REVISE\nREASONING:bad",
            "e2e_cycle": 1,
        }
        context = _build_e2e_context(state)
        assert "Regression Checklist" in context
        assert "Add handler" in context

    def test_omits_prior_fixes_on_first_cycle(self):
        state = {
            "task": "task",
            "current_plan": "plan",
            "current_code": "",
            "workspace_path": "/tmp",
            "e2e_verdict": "",
            "e2e_report": "",
            "e2e_cycle": 0,
        }
        context = _build_e2e_context(state)
        assert "Regression Checklist" not in context


class TestDiffTruncation:
    def test_short_diff_unchanged(self):
        diff = "diff --git a/foo.py b/foo.py\n+hello"
        assert truncate_diff(diff) == diff

    def test_long_diff_is_truncated(self):
        long_diff = "@@ -1 +1 @@\n" + "+" + "x" * (DIFF_MAX_CHARS + 500)
        result = truncate_diff(long_diff)
        assert len(result) < len(long_diff)
        assert "truncated" in result

    def test_truncated_diff_starts_at_hunk_boundary(self):
        prefix = "x" * (DIFF_MAX_CHARS + 100)
        suffix = "\n@@ -10 +10 @@\n+new line\n"
        long_diff = prefix + suffix
        result = truncate_diff(long_diff)
        assert "@@ -10 +10 @@" in result


class TestE2eTestNode:
    def _make_state(self, tmp_path, **overrides) -> dict:
        defaults = {
            "task": "Build a REST API",
            "current_plan": "1. Create endpoints",
            "current_code": "+app.get('/users')",
            "workspace_path": str(tmp_path),
            "e2e_verdict": "",
            "e2e_report": "",
            "e2e_cycle": 0,
        }
        return {**defaults, **overrides}

    @patch("langgraph_agents.nodes.e2e_tester.invoke_agent")
    def test_approve_verdict(self, mock_invoke, tmp_path):
        mock_invoke.return_value = (
            "Tests pass. Output quality is good.\n"
            "VERDICT:APPROVE\n"
            "REASONING:All intended outcomes achieved."
        )
        result = e2e_test(self._make_state(tmp_path))
        assert result["e2e_verdict"] == "APPROVE"
        assert result["e2e_cycle"] == 1

    @patch("langgraph_agents.nodes.e2e_tester.invoke_agent")
    def test_revise_verdict_preserves_report(self, mock_invoke, tmp_path):
        report = (
            "INTENT GAPS: API returns empty results\n"
            "EVIDENCE: GET /users returns []\n"
            "ROOT CAUSE: No seed data\n"
            "PROPOSED FIXES: Add fixtures\n"
            "VERDICT:REVISE\n"
            "REASONING:Output does not match intent."
        )
        mock_invoke.return_value = report
        result = e2e_test(self._make_state(tmp_path))
        assert result["e2e_verdict"] == "REVISE"
        assert "INTENT GAPS" in result["e2e_report"]
        assert result["e2e_cycle"] == 1

    @patch("langgraph_agents.nodes.e2e_tester.invoke_agent")
    def test_skip_verdict(self, mock_invoke, tmp_path):
        mock_invoke.return_value = (
            "Cannot execute: requires PostgreSQL.\n"
            "VERDICT:SKIP\n"
            "REASONING:Database not available in test environment."
        )
        result = e2e_test(self._make_state(tmp_path))
        assert result["e2e_verdict"] == "SKIP"
        assert "PostgreSQL" in result["e2e_report"]

    @patch("langgraph_agents.nodes.e2e_tester.invoke_agent")
    def test_missing_verdict_defaults_to_revise(self, mock_invoke, tmp_path):
        mock_invoke.return_value = "The code has issues but I forgot the verdict."
        result = e2e_test(self._make_state(tmp_path))
        assert result["e2e_verdict"] == "REVISE"
        assert result["e2e_report"].startswith("VERDICT:REVISE\n")

    @patch("langgraph_agents.nodes.e2e_tester.invoke_agent")
    def test_cycle_increments_from_current(self, mock_invoke, tmp_path):
        mock_invoke.return_value = "VERDICT:APPROVE\nREASONING:Fine."
        result = e2e_test(self._make_state(tmp_path, e2e_cycle=1))
        assert result["e2e_cycle"] == 2

    @patch("langgraph_agents.nodes.e2e_tester.invoke_agent")
    def test_invokes_with_correct_params(self, mock_invoke, tmp_path):
        mock_invoke.return_value = "VERDICT:APPROVE\nREASONING:OK."
        state = self._make_state(tmp_path)
        result = e2e_test(state)
        mock_invoke.assert_called_once()
        call_kwargs = mock_invoke.call_args
        from langgraph_agents.config import E2E_BUDGET_USD, E2E_MODEL, E2E_TIMEOUT

        assert call_kwargs.kwargs["cwd"] == str(tmp_path)
        assert call_kwargs.kwargs["model"] == E2E_MODEL
        assert call_kwargs.kwargs["allowed_tools"] == ["Read", "Glob", "Grep", "Bash"]
        assert call_kwargs.kwargs["max_budget_usd"] == E2E_BUDGET_USD
        assert call_kwargs.kwargs["timeout"] == E2E_TIMEOUT
        assert result["e2e_verdict"] == "APPROVE"
        assert result["e2e_cycle"] == 1
