"""Prompt review synthesizer: merges behavioral and architectural review verdicts.

Pure Python — no LLM call. Deterministic: either REVISE means REVISE.
"""

from langgraph_agents.node_contract import is_verdict_value, non_empty, validate_node
from langgraph_agents.state import PromptBuildState


@validate_node(
    pre={"behavioral_feedback": non_empty, "architectural_feedback": non_empty},
    post={
        "build_verdict": is_verdict_value("APPROVE", "REVISE"),
        "build_feedback": non_empty,
    },
)
def synthesize_prompt_reviews(state: PromptBuildState) -> dict:
    """Merge behavioral and architectural review results into a single verdict."""
    behavioral = state.get("behavioral_feedback", "")
    architectural = state.get("architectural_feedback", "")

    behavioral_revise = "VERDICT:REVISE" in behavioral
    architectural_revise = "VERDICT:REVISE" in architectural

    verdict = "REVISE" if (behavioral_revise or architectural_revise) else "APPROVE"

    parts: list[str] = []
    if behavioral_revise:
        parts.append(f"## Behavioral Review (REVISE)\n{behavioral}")
    elif behavioral:
        parts.append(f"## Behavioral Review (APPROVE)\n{behavioral}")

    if architectural_revise:
        parts.append(f"## Architectural Review (REVISE)\n{architectural}")
    elif architectural:
        parts.append(f"## Architectural Review (APPROVE)\n{architectural}")

    feedback = "\n\n".join(parts) if parts else "Both reviewers approved."

    return {"build_verdict": verdict, "build_feedback": feedback}
