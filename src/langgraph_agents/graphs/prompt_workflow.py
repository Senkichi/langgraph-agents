"""Parent graph for prompt engineering workflows.

Discovers the agent architecture, runs plan-review (reused as-is),
then runs prompt-build-review with specialized prompt engineering nodes.

Usage:
    from langgraph_agents.graphs.prompt_workflow import prompt_workflow_app

    result = prompt_workflow_app.invoke({
        "task": "Fix the resume-engine's bullet redundancy scoring...",
        "current_plan": "",
        "agent_architecture": "",
        "prompt_diff": "",
        "workspace_path": "C:/Users/senki/repos/resume-engine",
    })
"""

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from langgraph_agents.graphs.plan_review import plan_review_app
from langgraph_agents.graphs.prompt_build_review import prompt_build_review_app
from langgraph_agents.nodes.discover_architecture import discover_architecture
from langgraph_agents.state import (
    PlanReviewState,
    PromptBuildState,
    PromptWorkflowState,
)
from langgraph_agents.tracer import get_tracer


def _call_plan_review(state: PromptWorkflowState) -> dict:
    """Wrapper: enriches task with architecture context, invokes plan_review."""
    tracer = get_tracer()
    if tracer is not None:
        tracer.push_graph("plan_review")

    enriched_task = (
        f"{state.get('task', '')}\n\n"
        f"## Agent Architecture Context\n{state.get('agent_architecture', '')}"
    )
    subgraph_input: PlanReviewState = {
        "task": enriched_task,
        "current_plan": state.get("current_plan", ""),
        "agent_architecture": state.get("agent_architecture", ""),
        "plan_feedback": "",
        "plan_verdict": "",
        "plan_cycle": 0,
    }
    try:
        result = plan_review_app.invoke(subgraph_input)
        return {"current_plan": result["current_plan"]}
    finally:
        if tracer is not None:
            tracer.pop_graph()


def _call_prompt_build_review(state: PromptWorkflowState) -> dict:
    """Wrapper: transforms parent state → prompt build-review subgraph."""
    tracer = get_tracer()
    if tracer is not None:
        tracer.push_graph("prompt_build_review")

    subgraph_input: PromptBuildState = {
        "task": state.get("task", ""),
        "current_plan": state["current_plan"],
        "agent_architecture": state.get("agent_architecture", ""),
        "prompt_diff": "",
        "workspace_path": state.get("workspace_path", ""),
        "behavioral_feedback": "",
        "architectural_feedback": "",
        "build_verdict": "",
        "build_feedback": "",
        "build_cycle": 0,
    }
    try:
        result = prompt_build_review_app.invoke(subgraph_input)
        return {"prompt_diff": result.get("prompt_diff", "")}
    finally:
        if tracer is not None:
            tracer.pop_graph()


_SUBPROCESS_RETRY = RetryPolicy(
    max_attempts=3,
    initial_interval=2.0,
    retry_on=RuntimeError,
)


def build_prompt_workflow_graph() -> StateGraph:
    """Build the parent prompt workflow graph."""
    graph = StateGraph(PromptWorkflowState)

    graph.add_node("discover_architecture", discover_architecture, retry_policy=_SUBPROCESS_RETRY)
    graph.add_node("plan_review", _call_plan_review)
    graph.add_node("prompt_build_review", _call_prompt_build_review)

    graph.add_edge(START, "discover_architecture")
    graph.add_edge("discover_architecture", "plan_review")
    graph.add_edge("plan_review", "prompt_build_review")
    graph.add_edge("prompt_build_review", END)

    return graph


def compile_prompt_workflow(checkpointer=None):
    """Compile the prompt workflow graph with an optional checkpointer."""
    from langgraph.checkpoint.memory import InMemorySaver

    cp = checkpointer if checkpointer is not None else InMemorySaver()
    return build_prompt_workflow_graph().compile(checkpointer=cp)


prompt_workflow_app = compile_prompt_workflow()
