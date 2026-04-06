"""Tests for node_contract: validators, decorator, and format_verdict_feedback."""

import logging
from pathlib import Path

import pytest

from langgraph_agents.node_contract import (
    NodeContractError,
    contains_verdict,
    format_verdict_feedback,
    is_non_negative_int,
    is_path,
    is_verdict_value,
    non_empty,
    validate_node,
)


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


class TestNonEmpty:
    def test_valid_string(self):
        assert non_empty("hello") is None

    def test_empty_string(self):
        assert non_empty("") is not None

    def test_whitespace_only(self):
        assert non_empty("   \n\t  ") is not None

    def test_none(self):
        assert non_empty(None) is not None

    def test_non_string(self):
        assert non_empty(42) is not None


class TestIsPath:
    def test_valid_directory(self, tmp_path):
        assert is_path(str(tmp_path)) is None

    def test_nonexistent_path(self):
        assert is_path("/nonexistent/path/abc123") is not None

    def test_empty_string(self):
        assert is_path("") is not None

    def test_none(self):
        assert is_path(None) is not None

    def test_file_not_dir(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        assert is_path(str(f)) is not None


class TestContainsVerdict:
    def test_contains_verdict_approve(self):
        assert contains_verdict("VERDICT:APPROVE\nsome text") is None

    def test_contains_verdict_revise(self):
        assert contains_verdict("stuff\nVERDICT:REVISE\nmore") is None

    def test_missing_verdict(self):
        assert contains_verdict("no verdict here") is not None

    def test_empty(self):
        assert contains_verdict("") is not None

    def test_none(self):
        assert contains_verdict(None) is not None


class TestIsVerdictValue:
    def test_valid_value(self):
        check = is_verdict_value("APPROVE", "REVISE")
        assert check("APPROVE") is None
        assert check("REVISE") is None

    def test_invalid_value(self):
        check = is_verdict_value("APPROVE", "REVISE")
        assert check("SKIP") is not None
        assert check("") is not None

    def test_none(self):
        check = is_verdict_value("APPROVE", "REVISE")
        assert check(None) is not None

    def test_three_values(self):
        check = is_verdict_value("APPROVE", "REVISE", "SKIP")
        assert check("SKIP") is None


class TestIsNonNegativeInt:
    def test_zero(self):
        assert is_non_negative_int(0) is None

    def test_positive(self):
        assert is_non_negative_int(5) is None

    def test_negative(self):
        assert is_non_negative_int(-1) is not None

    def test_float(self):
        assert is_non_negative_int(1.5) is not None

    def test_string(self):
        assert is_non_negative_int("3") is not None

    def test_none(self):
        assert is_non_negative_int(None) is not None


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------


class TestValidateNode:
    def test_passes_with_valid_state(self):
        @validate_node(
            pre={"task": non_empty},
            post={"result": non_empty},
        )
        def my_node(state):
            return {"result": "done"}

        result = my_node({"task": "do something"})
        assert result == {"result": "done"}

    def test_pre_violation_raises(self):
        @validate_node(pre={"task": non_empty})
        def my_node(state):
            return {}

        with pytest.raises(NodeContractError, match="pre\\[task\\]"):
            my_node({"task": ""})

    def test_post_violation_raises(self):
        @validate_node(post={"result": non_empty})
        def my_node(state):
            return {"result": ""}

        with pytest.raises(NodeContractError, match="post\\[result\\]"):
            my_node({})

    def test_multiple_pre_violations_collected(self):
        @validate_node(pre={"a": non_empty, "b": non_empty})
        def my_node(state):
            return {}

        with pytest.raises(NodeContractError) as exc_info:
            my_node({"a": "", "b": ""})

        assert len(exc_info.value.violations) == 2
        assert "pre[a]" in exc_info.value.violations[0]
        assert "pre[b]" in exc_info.value.violations[1]

    def test_multiple_post_violations_collected(self):
        @validate_node(post={"x": non_empty, "y": non_empty})
        def my_node(state):
            return {"x": "", "y": ""}

        with pytest.raises(NodeContractError) as exc_info:
            my_node({})

        assert len(exc_info.value.violations) == 2

    def test_pre_failure_skips_node_execution(self):
        call_count = 0

        @validate_node(pre={"task": non_empty})
        def my_node(state):
            nonlocal call_count
            call_count += 1
            return {}

        with pytest.raises(NodeContractError):
            my_node({"task": ""})

        assert call_count == 0

    def test_preserves_function_name(self):
        @validate_node(pre={"task": non_empty})
        def my_node(state):
            return {}

        assert my_node.__name__ == "my_node"

    def test_no_contracts_passthrough(self):
        @validate_node()
        def my_node(state):
            return {"x": 1}

        assert my_node({"anything": "goes"}) == {"x": 1}

    def test_node_name_in_error(self):
        @validate_node(pre={"task": non_empty})
        def specific_node(state):
            return {}

        with pytest.raises(NodeContractError, match="specific_node"):
            specific_node({"task": ""})

    def test_is_value_error_subclass(self):
        @validate_node(pre={"task": non_empty})
        def my_node(state):
            return {}

        with pytest.raises(ValueError):
            my_node({"task": ""})

    def test_missing_field_in_state(self):
        @validate_node(pre={"task": non_empty})
        def my_node(state):
            return {}

        with pytest.raises(NodeContractError, match="pre\\[task\\]"):
            my_node({})

    def test_missing_field_in_result(self):
        @validate_node(post={"result": non_empty})
        def my_node(state):
            return {}

        with pytest.raises(NodeContractError, match="post\\[result\\]"):
            my_node({})

    def test_with_is_path(self, tmp_path):
        @validate_node(pre={"workspace_path": is_path})
        def my_node(state):
            return {"done": True}

        result = my_node({"workspace_path": str(tmp_path)})
        assert result == {"done": True}

    def test_with_is_path_invalid(self):
        @validate_node(pre={"workspace_path": is_path})
        def my_node(state):
            return {}

        with pytest.raises(NodeContractError, match="directory does not exist"):
            my_node({"workspace_path": "/no/such/dir"})


# ---------------------------------------------------------------------------
# format_verdict_feedback
# ---------------------------------------------------------------------------


class TestFormatVerdictFeedback:
    def test_passthrough_when_verdict_present(self):
        text = "VERDICT:APPROVE\nLooks good."
        assert format_verdict_feedback(text) == text

    def test_injects_verdict_when_missing(self):
        text = "No verdict in this response."
        result = format_verdict_feedback(text)
        assert result.startswith("VERDICT:REVISE\n")
        assert text in result

    def test_logs_warning_when_injecting(self, caplog):
        with caplog.at_level(logging.WARNING, logger="langgraph_agents.node_contract"):
            format_verdict_feedback("missing verdict text")

        assert len(caplog.records) == 1
        assert "missing VERDICT: line" in caplog.records[0].message

    def test_no_warning_when_verdict_present(self, caplog):
        with caplog.at_level(logging.WARNING, logger="langgraph_agents.node_contract"):
            format_verdict_feedback("VERDICT:REVISE\nIssue found.")

        assert len(caplog.records) == 0


# ---------------------------------------------------------------------------
# Integration: decorator + real-ish node
# ---------------------------------------------------------------------------


class TestDecoratorIntegration:
    def test_synthesizer_contract(self):
        """Simulates synthesize_reviews with valid inputs."""

        @validate_node(
            pre={"micro_feedback": non_empty, "macro_feedback": non_empty},
            post={
                "build_verdict": is_verdict_value("APPROVE", "REVISE"),
                "build_feedback": non_empty,
            },
        )
        def fake_synthesizer(state):
            micro_revise = "VERDICT:REVISE" in state["micro_feedback"]
            macro_revise = "VERDICT:REVISE" in state["macro_feedback"]
            verdict = "REVISE" if (micro_revise or macro_revise) else "APPROVE"
            return {"build_verdict": verdict, "build_feedback": "Both approved."}

        result = fake_synthesizer({
            "micro_feedback": "VERDICT:APPROVE\nLooks good.",
            "macro_feedback": "VERDICT:APPROVE\nArchitecture is solid.",
        })
        assert result["build_verdict"] == "APPROVE"

    def test_synthesizer_bad_input_rejected(self):
        @validate_node(
            pre={"micro_feedback": non_empty, "macro_feedback": non_empty},
        )
        def fake_synthesizer(state):
            return {}

        with pytest.raises(NodeContractError, match="micro_feedback"):
            fake_synthesizer({"micro_feedback": "", "macro_feedback": "ok"})

    def test_reviewer_contract_with_format_feedback(self):
        """Simulates a reviewer that uses format_verdict_feedback."""

        @validate_node(
            pre={"current_plan": non_empty},
            post={"micro_feedback": contains_verdict},
        )
        def fake_reviewer(state):
            raw_response = "The code looks fine but has some issues."
            return {"micro_feedback": format_verdict_feedback(raw_response)}

        result = fake_reviewer({"current_plan": "Step 1: ..."})
        assert "VERDICT:REVISE" in result["micro_feedback"]
