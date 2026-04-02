from langchain_core.messages import SystemMessage

from langgraph_agents.state import AgentState


SYSTEM_PROMPT = (
    "You are a writing assistant. Take the research provided and "
    "produce clear, well-structured output."
)


def write(state: AgentState) -> dict:
    """Writer node: synthesizes research into a polished response."""
    from langgraph_agents.llm import get_llm

    llm = get_llm()
    response = llm.invoke(
        [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    )
    return {"messages": [response], "result": response.content}
