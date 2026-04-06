"""End-to-end tester: validates that the built code achieves its intended purpose.

Goes beyond "does it run without errors" to evaluate whether the code's actual
outputs match the intent described in the task and plan. Supports three verdicts:
APPROVE (intent achieved), REVISE (intent gaps found), SKIP (environment can't
support execution).
"""

import re

from langgraph_agents.claude_cli import invoke_agent
from langgraph_agents.node_contract import (
    format_verdict_feedback,
    is_path,
    is_verdict_value,
    non_empty,
    parse_verdict,
    validate_node,
)
from langgraph_agents.state import ParentState

SYSTEM_PROMPT = (
    "You are an end-to-end validation agent. Your job is to verify that code "
    "achieves its INTENDED PURPOSE, not just that it runs without errors.\n\n"
    "## Process\n"
    "1. Read the task and plan to understand the intended outcomes\n"
    "2. Read the changed files in the workspace to understand what was built\n"
    "3. Run ONLY the tests directly related to the changed files — suggested "
    "test commands are provided below when available. Do NOT run the full "
    "test suite.\n"
    "4. Execute two tiers of validation:\n"
    "   - FUNCTIONAL: Run targeted tests, verify no crashes, check exit codes\n"
    "   - QUALITATIVE: Examine actual outputs for correctness, relevance, "
    "completeness, and quality against the stated intent. Exercise 1-2 "
    "representative inputs, not exhaustive datasets. This is your core "
    "value — the code reviewers already checked for bugs and style.\n\n"
    "## Time Management\n"
    "- If test execution exceeds 2 minutes, stop and evaluate what you have\n"
    "- Prefer `pytest <file> -x --tb=short` for fast, focused feedback\n"
    "- Do NOT explore the entire workspace — focus on changed files and their "
    "direct dependencies\n\n"
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


def _extract_changed_files(diff: str) -> list[str]:
    """Extract file paths from a unified diff."""
    files: list[str] = []
    for match in re.finditer(r"^\+\+\+ b/(.+)$", diff, re.MULTILINE):
        path = match.group(1).strip()
        if path and path != "/dev/null":
            files.append(path)
    return sorted(set(files))


def _suggest_test_commands(changed_files: list[str]) -> str:
    """Map changed source files to likely test commands.

    Returns a markdown section with suggested pytest commands, or empty
    string if no source files were changed.
    """
    test_targets: list[str] = []
    for f in changed_files:
        # Skip non-Python files and test files themselves
        if not f.endswith(".py") or "/test_" in f or f.startswith("test_"):
            continue
        # Extract module basename: "src/pkg/foo.py" → "foo"
        basename = f.rsplit("/", 1)[-1].removesuffix(".py")
        test_targets.append(basename)

    if not test_targets:
        return ""

    commands = [
        f"- `uv run pytest tests/ -k '{name}' -x --tb=short`"
        for name in sorted(set(test_targets))[:5]
    ]
    return "## Suggested Test Commands\n" + "\n".join(commands)


def _build_e2e_context(state: ParentState) -> str:
    """Build the prompt for the e2e test agent.

    Deliberately excludes any prior e2e_report to avoid anchoring bias —
    the agent evaluates the workspace fresh each time. Includes
    pre-computed test commands derived from the code diff.
    """
    parts = [
        f"## Task\n{state['task']}",
        f"## Approved Plan\n{state['current_plan']}",
    ]
    code_diff = state.get("current_code", "")
    if code_diff:
        parts.append(f"## Code Changes\n```diff\n{code_diff}\n```")
        test_cmds = _suggest_test_commands(_extract_changed_files(code_diff))
        if test_cmds:
            parts.append(test_cmds)
    parts.append(
        "Validate that the code achieves the intent described above. "
        "Run the suggested test commands (or targeted equivalents), examine "
        "the outputs, and assess quality — not just correctness."
    )
    return "\n\n".join(parts)


@validate_node(
    pre={"task": non_empty, "current_plan": non_empty, "workspace_path": is_path},
    post={
        "e2e_verdict": is_verdict_value("APPROVE", "REVISE", "SKIP"),
        "e2e_report": non_empty,
    },
)
def e2e_test(state: ParentState) -> dict:
    """End-to-end validation: does the code achieve its intended purpose?"""
    workspace = state.get("workspace_path", "")
    context = _build_e2e_context(state)

    response = invoke_agent(
        context,
        system_prompt=SYSTEM_PROMPT,
        cwd=workspace,
        allowed_tools=E2E_TOOLS,
        model="sonnet",
        max_budget_usd=2.0,
        timeout=2700,
    )

    response = format_verdict_feedback(response)
    verdict = parse_verdict(response, "APPROVE", "REVISE", "SKIP")

    return {
        "e2e_verdict": verdict,
        "e2e_report": response,
        "e2e_cycle": state.get("e2e_cycle", 0) + 1,
    }
