"""Review synthesizer: merges micro and macro review verdicts.

Pure Python — no LLM call. Deterministic: either REVISE means REVISE.
Extracts only the structured verdict block from each reviewer, discarding
tool-use traces and exploration noise. APPROVE feedback is omitted entirely.
"""

from langgraph_agents.node_contract import is_verdict_value, non_empty, validate_node
from langgraph_agents.state import BuildReviewState


def _extract_verdict_block(feedback: str) -> str:
    """Extract the structured verdict block starting at the VERDICT: line.

    Returns everything from the first VERDICT: line onward, which contains
    the verdict, reasoning, and severity-categorized issues. This strips
    the agent's tool-use exploration traces that precede the final verdict.
    """
    lines = feedback.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("VERDICT:"):
            return "\n".join(lines[i:]).strip()
    return feedback.strip()


@validate_node(
    pre={"micro_feedback": non_empty, "macro_feedback": non_empty},
    post={
        "build_verdict": is_verdict_value("APPROVE", "REVISE"),
        "build_feedback": non_empty,
    },
)
def synthesize_reviews(state: BuildReviewState) -> dict:
    """Merge micro and macro review results into a single verdict.

    Only includes feedback from reviewers that returned REVISE — APPROVE
    feedback is noise for the coder. Extracts only the structured verdict
    block to bound prompt size.
    """
    micro = state.get("micro_feedback", "")
    macro = state.get("macro_feedback", "")

    micro_revise = "VERDICT:REVISE" in micro
    macro_revise = "VERDICT:REVISE" in macro

    verdict = "REVISE" if (micro_revise or macro_revise) else "APPROVE"

    parts: list[str] = []
    if micro_revise:
        parts.append(f"## Micro Review\n{_extract_verdict_block(micro)}")
    if macro_revise:
        parts.append(f"## Macro Review\n{_extract_verdict_block(macro)}")

    feedback = "\n\n".join(parts) if parts else "Both reviewers approved."

    return {"build_verdict": verdict, "build_feedback": feedback}
