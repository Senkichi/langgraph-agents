from langgraph.graph import END, START, StateGraph

from langgraph_agents.llm import get_llm  # noqa: F401 — re-exported for backward compat
from langgraph_agents.nodes.researcher import research
from langgraph_agents.nodes.writer import write
from langgraph_agents.state import AgentState


def route_after_research(state: AgentState) -> str:
    """Decide whether to hand off to the writer or finish directly."""
    if state.get("task", "").startswith("research_only:"):
        return END
    return "writer"


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("researcher", research)
    graph.add_node("writer", write)

    graph.add_edge(START, "researcher")
    graph.add_conditional_edges("researcher", route_after_research, {END: END, "writer": "writer"})
    graph.add_edge("writer", END)

    return graph


# Compiled app — import this to invoke the workflow
app = build_graph().compile()
