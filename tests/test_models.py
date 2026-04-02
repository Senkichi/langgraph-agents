import pytest
from pydantic import ValidationError

from langgraph_agents.models import CodeVerdict, PlanVerdict


class TestPlanVerdict:
    def test_approve_verdict(self):
        v = PlanVerdict(verdict="APPROVE", reasoning="Looks good.")
        assert v.verdict == "APPROVE"
        assert v.issues == []
        assert v.suggestions == []

    def test_revise_verdict_with_issues(self):
        v = PlanVerdict(
            verdict="REVISE",
            reasoning="Needs work.",
            issues=["Missing error handling", "No tests"],
            suggestions=["Add try/except blocks"],
        )
        assert v.verdict == "REVISE"
        assert len(v.issues) == 2
        assert len(v.suggestions) == 1

    def test_invalid_verdict_rejected(self):
        with pytest.raises(ValidationError):
            PlanVerdict(verdict="REJECT", reasoning="Bad.")

    def test_missing_reasoning_rejected(self):
        with pytest.raises(ValidationError):
            PlanVerdict(verdict="APPROVE")


class TestCodeVerdict:
    def test_approve_verdict(self):
        v = CodeVerdict(verdict="APPROVE", reasoning="Clean code.")
        assert v.verdict == "APPROVE"

    def test_revise_verdict(self):
        v = CodeVerdict(
            verdict="REVISE",
            reasoning="Has bugs.",
            issues=["Off-by-one error"],
        )
        assert v.verdict == "REVISE"
        assert len(v.issues) == 1

    def test_serialization_roundtrip(self):
        v = PlanVerdict(
            verdict="REVISE",
            reasoning="Test.",
            issues=["A"],
            suggestions=["B"],
        )
        data = v.model_dump()
        v2 = PlanVerdict.model_validate(data)
        assert v == v2
