"""Review synthesizer: merges micro and macro review verdicts.

Pure Python — no LLM call. Deterministic: either REVISE means REVISE.
Extracts only the structured verdict block from each reviewer, discarding
tool-use traces and exploration noise. When one reviewer approves and the
other revises, the approval is preserved as a "do not regress" signal.
"""

from langgraph_agents.node_contract import (
    extract_verdict_block,
    is_verdict_value,
    non_empty,
    parse_verdict,
    validate_node,
)
from langgraph_agents.state import BuildReviewState


@validate_node(
    pre={"micro_feedback": non_empty, "macro_feedback": non_empty},
    post={
        "build_verdict": is_verdict_value("APPROVE", "REVISE"),
        "build_feedback": non_empty,
    },
)
def synthesize_reviews(state: BuildReviewState) -> dict:
    """Merge micro and macro review results into a single verdict.

    When one reviewer revises and the other approves, the approval is
    included as a "do not regress" signal so the coder preserves what works.
    """
    micro = state.get("micro_feedback", "")
    macro = state.get("macro_feedback", "")

    micro_revise = parse_verdict(micro, "APPROVE", "REVISE") == "REVISE"
    macro_revise = parse_verdict(macro, "APPROVE", "REVISE") == "REVISE"

    verdict = "REVISE" if (micro_revise or macro_revise) else "APPROVE"

    parts: list[str] = []

    if micro_revise:
        parts.append(
            f"## Micro Review (REVISE — must fix)\n{extract_verdict_block(micro)}"
        )
    elif macro_revise:
        parts.append(
            f"## Micro Review (APPROVED — do not regress these patterns)\n"
            f"{extract_verdict_block(micro)}"
        )

    if macro_revise:
        parts.append(
            f"## Macro Review (REVISE — must fix)\n{extract_verdict_block(macro)}"
        )
    elif micro_revise:
        parts.append(
            f"## Macro Review (APPROVED — do not regress these patterns)\n"
            f"{extract_verdict_block(macro)}"
        )

    feedback = "\n\n".join(parts) if parts else "Both reviewers approved."

    return {"build_verdict": verdict, "build_feedback": feedback}
