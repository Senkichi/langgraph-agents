"""Prompt review synthesizer: merges behavioral and architectural review verdicts.

Pure Python — no LLM call. Deterministic: either REVISE means REVISE.
When one reviewer approves and the other revises, the approval is preserved
as a "do not regress" signal.
"""

from langgraph_agents.node_contract import (
    extract_verdict_block,
    is_verdict_value,
    non_empty,
    parse_verdict,
    validate_node,
)
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

    behavioral_revise = parse_verdict(behavioral, "APPROVE", "REVISE") == "REVISE"
    architectural_revise = parse_verdict(architectural, "APPROVE", "REVISE") == "REVISE"

    verdict = "REVISE" if (behavioral_revise or architectural_revise) else "APPROVE"

    parts: list[str] = []
    if behavioral_revise:
        parts.append(
            f"## Behavioral Review (REVISE — must fix)\n{extract_verdict_block(behavioral)}"
        )
    elif architectural_revise:
        parts.append(
            f"## Behavioral Review (APPROVED — do not regress these patterns)\n"
            f"{extract_verdict_block(behavioral)}"
        )

    if architectural_revise:
        parts.append(
            f"## Architectural Review (REVISE — must fix)\n{extract_verdict_block(architectural)}"
        )
    elif behavioral_revise:
        parts.append(
            f"## Architectural Review (APPROVED — do not regress these patterns)\n"
            f"{extract_verdict_block(architectural)}"
        )

    feedback = "\n\n".join(parts) if parts else "Both reviewers approved."

    return {"build_verdict": verdict, "build_feedback": feedback}
