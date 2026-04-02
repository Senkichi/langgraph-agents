from langgraph_agents.graphs.orchestrator import build_graph


def test_graph_compiles():
    """Smoke test: graph builds and compiles without error."""
    graph = build_graph()
    compiled = graph.compile()
    assert compiled is not None


def test_graph_has_expected_nodes():
    graph = build_graph()
    compiled = graph.compile()
    node_names = set(compiled.get_graph().nodes.keys())
    assert "researcher" in node_names
    assert "writer" in node_names
