from typing import Literal

from pydantic import BaseModel, Field


class PlanVerdict(BaseModel):
    """Structured output from the plan reviewer."""

    verdict: Literal["APPROVE", "REVISE"] = Field(
        description=(
            "APPROVE if the plan is ready for implementation. "
            "REVISE if changes are needed."
        ),
    )
    reasoning: str = Field(
        description="Detailed explanation of the decision.",
    )
    issues: list[str] = Field(
        default_factory=list,
        description="Specific issues found. Empty if APPROVE.",
    )
    suggestions: list[str] = Field(
        default_factory=list,
        description="Concrete suggestions for improvement. Empty if APPROVE.",
    )


class CodeVerdict(BaseModel):
    """Structured output from a code reviewer (micro or macro)."""

    verdict: Literal["APPROVE", "REVISE"] = Field(
        description=(
            "APPROVE if the code meets standards. "
            "REVISE if changes are needed."
        ),
    )
    reasoning: str = Field(
        description="Detailed explanation of the decision.",
    )
    issues: list[str] = Field(
        default_factory=list,
        description="Specific issues found. Empty if APPROVE.",
    )
    suggestions: list[str] = Field(
        default_factory=list,
        description="Concrete suggestions for improvement. Empty if APPROVE.",
    )
