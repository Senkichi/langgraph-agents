from langchain_core.messages import SystemMessage

from langgraph_agents.state import AgentState


SYSTEM_PROMPT = (
    "You are a research assistant. Analyze the given task and provide "
    "a thorough, factual response."
)


def research(state: AgentState) -> dict:
    """Research node: processes the task and returns findings."""
    from langgraph_agents.llm import get_llm

    llm = get_llm()
    response = llm.invoke(
        [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    )
    return {"messages": [response], "result": response.content}
