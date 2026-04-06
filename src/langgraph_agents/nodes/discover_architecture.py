"""Discovery node: scans a Claude Code agent workspace and builds a compressed
architecture summary for downstream nodes.

Reads agent files, knowledge files, CLAUDE.md, and design specs to produce:
agents + roles, knowledge file consumers, dependency graph, isolation
boundaries, and shared sync points.
"""

from langgraph_agents.claude_cli import invoke_agent
from langgraph_agents.node_contract import is_path, non_empty, validate_node
from langgraph_agents.state import PromptWorkflowState

SYSTEM_PROMPT = (
    "You are an expert at analyzing Claude Code multi-agent systems.\n\n"
    "Scan this workspace and produce a COMPRESSED architecture summary with "
    "these sections:\n\n"
    "## Agents\n"
    "For each agent: name, role (1 sentence), defining file path.\n\n"
    "## Knowledge Files\n"
    "For each knowledge file: name, purpose (1 sentence), which agents read it.\n\n"
    "## Dependency Graph\n"
    "Which agents depend on which knowledge files. Show as: agent → [files].\n\n"
    "## Isolation Boundaries\n"
    "What each agent is explicitly told NOT to read or do. Note any "
    "prompt-enforced (not technical) isolation.\n\n"
    "## Shared Sync Points\n"
    "Files read by 3+ agents. These are high-impact change targets.\n\n"
    "## Review Pipeline\n"
    "How quality review works: which agents review, what criteria, "
    "what they can/cannot see.\n\n"
    "Be concise — this summary will be injected into downstream agent contexts. "
    "Aim for under 2000 words. Prioritize structural relationships over content details."
)

DISCOVERY_TOOLS = ["Read", "Glob", "Grep"]


@validate_node(
    pre={"workspace_path": is_path},
    post={"agent_architecture": non_empty},
)
def discover_architecture(state: PromptWorkflowState) -> dict:
    """Scan the workspace and produce a compressed architecture summary."""
    workspace = state["workspace_path"]

    response = invoke_agent(
        "Analyze this project's agent architecture. Read all agent definition "
        "files, knowledge files, CLAUDE.md, and any design specs. Produce the "
        "structured architecture summary.",
        system_prompt=SYSTEM_PROMPT,
        cwd=workspace,
        allowed_tools=DISCOVERY_TOOLS,
    )
    return {"agent_architecture": response}
