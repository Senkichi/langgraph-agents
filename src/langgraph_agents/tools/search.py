from langchain_core.tools import tool


@tool
def web_search(query: str) -> str:
    """Search the web for information on a topic."""
    # TODO: Replace with real search implementation (e.g., Tavily, DuckDuckGo)
    return f"Search results for: {query}"
