"""Prompt engineer node: edits agent prompts, knowledge files, and workflow
configurations in a Claude Code multi-agent system.

Does NOT write Python code. All changes are to markdown files.
"""

from langgraph_agents.claude_cli import invoke_agent
from langgraph_agents.config import PROMPT_ENGINEER_BUDGET_USD, PROMPT_ENGINEER_MODEL, PROMPT_ENGINEER_TIMEOUT
from langgraph_agents.node_contract import is_path, non_empty, validate_node
from langgraph_agents.state import PromptBuildState
from langgraph_agents.tools.dev_tools import run_git_diff

SYSTEM_PROMPT = (
    "You are an expert prompt engineer for Claude Code multi-agent systems.\n\n"
    "Your job is to edit agent definition files (.md), knowledge files (.md), "
    "and workflow configurations to implement the approved plan.\n\n"
    "Rules:\n"
    "- Do NOT write Python code. All changes are to markdown/text files.\n"
    "- Preserve existing file structure and formatting conventions.\n"
    "- Maintain context isolation boundaries — if an agent is told not to read "
    "certain files, do not add references to those files in its prompt.\n"
    "- Consider downstream impact — changes to shared knowledge files affect "
    "multiple agents. Check the dependency graph.\n"
    "- Be precise with instruction language — LLMs follow literal instructions. "
    "Ambiguous phrasing produces ambiguous behavior.\n"
    "- If reviewer feedback is provided, address every issue raised.\n"
    "- Do NOT explain what you did — just make the edits.\n\n"
    "## IMPORTANT: Do not use the Agent tool or spawn sub-agents\n"
    "You are running as part of an automated pipeline. Do NOT invoke the Agent tool,\n"
    "do NOT spawn sub-agents, do NOT use parallel tasks. Work only with the tools\n"
    "you have been given (Read, Edit, Write, Bash, Glob, Grep). Ignore any CLAUDE.md\n"
    "instructions to proactively launch reviewers, auditors, or analysis agents."
)

PROMPT_ENGINEER_TOOLS = ["Read", "Edit", "Write", "Bash", "Glob", "Grep"]


def _build_context(state: PromptBuildState) -> str:
    """Build the prompt for the prompt engineer."""
    parts = [
        f"## Task\n{state['task']}",
        f"## Approved Plan\n{state['current_plan']}",
        f"## Agent Architecture\n{state['agent_architecture']}",
    ]
    if state.get("build_feedback"):
        parts.append(
            "## Reviewer Feedback (address every point)\n"
            f"{state['build_feedback']}"
        )
        if state.get("prompt_diff"):
            parts.append(
                f"## Current Changes\n```diff\n{state['prompt_diff']}\n```"
            )
        parts.append(
            "## Revision Scope (MANDATORY)\n"
            "This is a REVISION cycle. Read ONLY the files explicitly mentioned\n"
            "in the Reviewer Feedback. Fix ONLY the listed issues — do not\n"
            "explore unrelated files or make unrequested changes.\n"
            "Do NOT spawn sub-agents, auditors, or reviewers."
        )
    return "\n\n".join(parts)


@validate_node(
    pre={
        "task": non_empty,
        "current_plan": non_empty,
        "agent_architecture": non_empty,
        "workspace_path": is_path,
    },
    post={"prompt_diff": non_empty},
)
def prompt_engineer(state: PromptBuildState) -> dict:
    """Edit prompt/knowledge files using claude CLI as a full agent."""
    workspace = state["workspace_path"]
    context = _build_context(state)

    is_revision = bool(state.get("build_feedback"))
    budget = PROMPT_ENGINEER_BUDGET_USD / 2 if is_revision else PROMPT_ENGINEER_BUDGET_USD

    invoke_agent(
        context,
        system_prompt=SYSTEM_PROMPT,
        cwd=workspace,
        allowed_tools=PROMPT_ENGINEER_TOOLS,
        model=PROMPT_ENGINEER_MODEL,
        max_budget_usd=budget,
        timeout=PROMPT_ENGINEER_TIMEOUT,
    )

    diff = run_git_diff(workspace)
    return {
        "prompt_diff": diff,
        "build_cycle": state.get("build_cycle", 0) + 1,
    }
