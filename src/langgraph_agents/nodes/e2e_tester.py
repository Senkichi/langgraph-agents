"""End-to-end tester: validates that the built code achieves its intended purpose.

Goes beyond "does it run without errors" to evaluate whether the code's actual
outputs match the intent described in the task and plan. Supports three verdicts:
APPROVE (intent achieved), REVISE (intent gaps found), SKIP (environment can't
support execution).
"""

from langgraph_agents.claude_cli import invoke_agent
from langgraph_agents.state import ParentState

SYSTEM_PROMPT = (
    "You are an end-to-end validation agent. Your job is to verify that code "
    "achieves its INTENDED PURPOSE, not just that it runs without errors.\n\n"
    "## Process\n"
    "1. Read the task and plan to understand the intended outcomes\n"
    "2. Read the workspace files to understand what was built\n"
    "3. Figure out how to execute the code — look for existing test suites, "
    "CLI entry points, run scripts, Makefiles, or other execution methods\n"
    "4. Execute two tiers of validation:\n"
    "   - FUNCTIONAL: Run the code/tests, verify no crashes, check exit codes\n"
    "   - QUALITATIVE: Examine actual outputs for correctness, relevance, "
    "completeness, and quality against the stated intent. This is your core "
    "value — the code reviewers already checked for bugs and style.\n\n"
    "## Rules\n"
    "- Do NOT modify project source files. You may create ephemeral test "
    "scripts (e.g., python -c or temp files) to exercise the code.\n"
    "- If the environment genuinely cannot support execution (missing database, "
    "API keys, paid external services), return VERDICT:SKIP with the reason.\n"
    "- Be specific. Show concrete output samples as evidence.\n"
    "- Do not rubber-stamp. If the code runs but produces poor-quality results, "
    "that is a REVISE.\n\n"
    "## Verdict Format\n"
    "End your response with EXACTLY this format:\n"
    "VERDICT:<APPROVE or REVISE or SKIP>\n"
    "REASONING:<your reasoning>\n\n"
    "If REVISE, also include this structured diagnostic report BEFORE the "
    "verdict block:\n"
    "INTENT GAPS: <what the code should achieve vs what it actually produces>\n"
    "EVIDENCE: <concrete output samples, error messages, or test results>\n"
    "ROOT CAUSE: <why the implementation falls short>\n"
    "PROPOSED FIXES: <specific, actionable changes the developer should make>"
)

E2E_TOOLS = ["Read", "Glob", "Grep", "Bash"]


def _format_feedback(response: str) -> str:
    """Ensure the response contains a parseable VERDICT: line."""
    if "VERDICT:" not in response:
        return f"VERDICT:REVISE\n{response}"
    return response


def _parse_verdict(response: str) -> str:
    """Extract the verdict from the response text."""
    for line in response.splitlines():
        if line.startswith("VERDICT:"):
            verdict = line.split(":", 1)[1].strip().upper()
            if verdict in ("APPROVE", "REVISE", "SKIP"):
                return verdict
    return "REVISE"


def _build_e2e_context(state: ParentState) -> str:
    """Build the prompt for the e2e test agent.

    Deliberately excludes any prior e2e_report to avoid anchoring bias —
    the agent evaluates the workspace fresh each time.
    """
    parts = [
        f"## Task\n{state['task']}",
        f"## Approved Plan\n{state['current_plan']}",
    ]
    code_diff = state.get("current_code", "")
    if code_diff:
        parts.append(f"## Code Changes\n```diff\n{code_diff}\n```")
    parts.append(
        "Validate that the code achieves the intent described above. "
        "Run it, examine the outputs, and assess quality — not just correctness."
    )
    return "\n\n".join(parts)


def e2e_test(state: ParentState) -> dict:
    """End-to-end validation: does the code achieve its intended purpose?"""
    workspace = state.get("workspace_path", "")
    context = _build_e2e_context(state)

    response = invoke_agent(
        context,
        system_prompt=SYSTEM_PROMPT,
        cwd=workspace,
        allowed_tools=E2E_TOOLS,
        model="opus",
    )

    response = _format_feedback(response)
    verdict = _parse_verdict(response)

    return {
        "e2e_verdict": verdict,
        "e2e_report": response,
        "e2e_cycle": state.get("e2e_cycle", 0) + 1,
    }
