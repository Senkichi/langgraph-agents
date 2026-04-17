"""Review synthesizer: merges micro and macro review verdicts.

Pure Python — no LLM call. Deterministic: either REVISE means REVISE.
Extracts only the structured verdict block from each reviewer, discarding
tool-use traces and exploration noise. When one reviewer approves and the
other revises, the approval is preserved as a "do not regress" signal.

Also accumulates resolved_issues (CRITICAL/MAJOR items confirmed fixed) and
persistent_rules (constraints derived from resolved CRITICALs) across cycles.
"""

from langgraph_agents.node_contract import (
    extract_verdict_block,
    is_verdict_value,
    non_empty,
    parse_verdict,
    validate_node,
)
from langgraph_agents.state import BuildReviewState

_MAX_PERSISTENT_RULES = 5
_MAX_RESOLVED_ISSUES = 20


def _extract_critical_major_issues(feedback_block: str) -> list[str]:
    """Extract file:line issue descriptions from CRITICAL and MAJOR sections."""
    issues: list[str] = []
    in_target_section = False
    for line in feedback_block.splitlines():
        if line.startswith(("CRITICAL:", "MAJOR:")):
            in_target_section = True
        elif line.startswith(("MINOR:", "VERDICT:", "REASONING:", "##")):
            in_target_section = False
        elif in_target_section and line.startswith("- "):
            issues.append(line[2:].strip())
    return issues


def _derive_rule(issue_line: str) -> str:
    """Convert a resolved CRITICAL issue line to a brief constraint rule."""
    if " — ACTION: " in issue_line:
        action = issue_line.split(" — ACTION: ", 1)[1].strip()
        rule = action[0].upper() + action[1:]
        return rule if rule.endswith(".") else rule + "."
    return issue_line.strip()


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

    # --- Accumulate resolved issues ---
    existing_resolved = list(state.get("resolved_issues") or [])
    new_resolved: list[str] = []
    if verdict == "APPROVE" and state.get("build_feedback"):
        new_resolved = _extract_critical_major_issues(state["build_feedback"])
    resolved_issues = (existing_resolved + new_resolved)[-_MAX_RESOLVED_ISSUES:]

    # --- Derive persistent rules from resolved CRITICALs ---
    existing_rules_text = (state.get("persistent_rules") or "").strip()
    existing_rules = [r for r in existing_rules_text.splitlines() if r.strip()]

    new_critical: list[str] = []
    if verdict == "APPROVE" and state.get("build_feedback"):
        in_critical = False
        for line in state["build_feedback"].splitlines():
            if line.startswith("CRITICAL:"):
                in_critical = True
            elif line.startswith(("MAJOR:", "MINOR:", "VERDICT:", "##")):
                in_critical = False
            elif in_critical and line.startswith("- "):
                new_critical.append(line[2:].strip())

    new_rules = [_derive_rule(issue) for issue in new_critical]
    all_rules = existing_rules + new_rules
    seen: set[str] = set()
    deduped: list[str] = []
    for rule in reversed(all_rules):
        if rule not in seen:
            seen.add(rule)
            deduped.insert(0, rule)
    persistent_rules = "\n".join(deduped[:_MAX_PERSISTENT_RULES])

    return {
        "build_verdict": verdict,
        "build_feedback": feedback,
        "resolved_issues": resolved_issues,
        "persistent_rules": persistent_rules,
    }
