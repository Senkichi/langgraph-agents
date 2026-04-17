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


class ChunkStep(BaseModel):
    """A single implementation step decomposed from a larger plan."""

    step_id: str = Field(description="Unique identifier (e.g. 'step_1', 'step_2')")
    title: str = Field(description="Brief title for this implementation step")
    plan_section: str = Field(
        description="Full implementation instructions for the coder — self-contained and actionable",
    )


class ExecutionPlan(BaseModel):
    """Ordered sequence of implementation steps decomposed from an approved plan."""

    steps: list[ChunkStep] = Field(
        description="Ordered list of implementation steps. Each step should be self-contained enough for a single coder pass.",
        min_length=1,
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
