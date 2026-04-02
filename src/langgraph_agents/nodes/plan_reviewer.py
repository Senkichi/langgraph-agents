from langgraph_agents.claude_cli import invoke_structured
from langgraph_agents.models import PlanVerdict
from langgraph_agents.state import PlanReviewState

SYSTEM_PROMPT = (
    "You are an antagonistic plan reviewer. Your job is to find weaknesses, "
    "gaps, ambiguities, and missing edge cases in implementation plans.\n\n"
    "Be thorough and specific. If the plan is genuinely solid, approve it.\n"
    "Do NOT approve plans that have unresolved issues just to be agreeable."
)

PLAN_VERDICT_SCHEMA = PlanVerdict.model_json_schema()


def _format_verdict(verdict: PlanVerdict) -> str:
    """Format a PlanVerdict into readable feedback text."""
    parts = [f"Verdict: {verdict.verdict}", f"Reasoning: {verdict.reasoning}"]
    if verdict.issues:
        parts.append("Issues:\n" + "\n".join(f"- {i}" for i in verdict.issues))
    if verdict.suggestions:
        parts.append(
            "Suggestions:\n" + "\n".join(f"- {s}" for s in verdict.suggestions)
        )
    return "\n".join(parts)


def review_plan(state: PlanReviewState) -> dict:
    """Antagonistic review of the current plan. Returns structured verdict."""
    content = f"## Task\n{state['task']}\n\n## Plan to Review\n{state['current_plan']}"

    try:
        raw = invoke_structured(
            content,
            schema=PLAN_VERDICT_SCHEMA,
            system_prompt=SYSTEM_PROMPT,
            model="sonnet",
        )
        verdict = PlanVerdict.model_validate(raw)
    except Exception:
        return {
            "plan_verdict": "REVISE",
            "plan_feedback": (
                "Review failed due to parsing error. "
                "Please clarify the plan structure."
            ),
        }

    return {
        "plan_verdict": verdict.verdict,
        "plan_feedback": _format_verdict(verdict),
    }
