"""Review synthesizer: merges micro and macro review verdicts.

Pure Python — no LLM call. Deterministic: either REVISE means REVISE.
"""

from langgraph_agents.state import BuildReviewState


def synthesize_reviews(state: BuildReviewState) -> dict:
    """Merge micro and macro review results into a single verdict."""
    micro = state.get("micro_feedback", "")
    macro = state.get("macro_feedback", "")

    micro_revise = "VERDICT:REVISE" in micro
    macro_revise = "VERDICT:REVISE" in macro

    verdict = "REVISE" if (micro_revise or macro_revise) else "APPROVE"

    parts: list[str] = []
    if micro_revise:
        parts.append(f"## Micro Review (REVISE)\n{micro}")
    elif micro:
        parts.append(f"## Micro Review (APPROVE)\n{micro}")

    if macro_revise:
        parts.append(f"## Macro Review (REVISE)\n{macro}")
    elif macro:
        parts.append(f"## Macro Review (APPROVE)\n{macro}")

    feedback = "\n\n".join(parts) if parts else "Both reviewers approved."

    return {"build_verdict": verdict, "build_feedback": feedback}
