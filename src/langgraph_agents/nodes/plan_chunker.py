"""Plan chunker node: decomposes an approved plan into ordered implementation steps.

Uses structured output (invoke_structured) to split a monolithic plan into
self-contained steps that each go through a build_review cycle sequentially.
"""

import logging

from langgraph_agents.claude_cli import invoke_structured
from langgraph_agents.config import CHUNKER_MODEL
from langgraph_agents.models import ExecutionPlan
from langgraph_agents.node_contract import non_empty, validate_node
from langgraph_agents.state import ParentState

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an expert plan decomposer. You receive an approved implementation "
    "plan and split it into ordered, self-contained implementation steps.\n\n"
    "Each step must be independently implementable by a coder working in the "
    "same workspace. Steps execute sequentially — later steps can depend on "
    "earlier steps being complete.\n\n"
    "Guidelines:\n"
    "- Each step should be scoped to what a single focused coder session can "
    "complete (roughly 1-3 files modified)\n"
    "- Each step's plan_section must contain all the detail the coder needs — "
    "do not reference other steps\n"
    "- Preserve the technical specificity of the original plan\n"
    "- If the plan is already small enough for a single step, return it as one step\n"
    "- Order steps so that dependencies flow forward (foundational work first)\n\n"
    "Output ONLY the structured JSON. Do not include commentary."
)

EXECUTION_PLAN_SCHEMA = ExecutionPlan.model_json_schema()


def _is_non_empty_list(value: object) -> str | None:
    """Validate that value is a non-empty list."""
    if not isinstance(value, list) or len(value) == 0:
        return f"expected non-empty list, got {type(value).__name__}"
    return None


@validate_node(
    pre={"current_plan": non_empty},
    post={"chunks": _is_non_empty_list},
)
def chunk_plan(state: ParentState) -> dict:
    """Decompose an approved plan into ordered implementation steps."""
    parts = [f"## Task\n{state.get('task', '')}"]

    if state.get("agent_architecture"):
        parts.append(f"## Workspace Architecture\n{state['agent_architecture']}")

    parts.append(f"## Approved Plan to Decompose\n{state['current_plan']}")

    raw = invoke_structured(
        "\n\n".join(parts),
        schema=EXECUTION_PLAN_SCHEMA,
        system_prompt=SYSTEM_PROMPT,
        model=CHUNKER_MODEL,
    )
    plan = ExecutionPlan.model_validate(raw)

    logger.info(
        "Plan decomposed into %d step(s): %s",
        len(plan.steps),
        [s.step_id for s in plan.steps],
    )

    return {
        "chunks": [step.model_dump() for step in plan.steps],
        "chunk_index": 0,
        "full_plan": state["current_plan"],
    }
