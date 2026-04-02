from langgraph_agents.graphs.prompt_workflow import build_prompt_workflow_graph


class TestPromptWorkflowGraph:
    def test_graph_compiles(self):
        graph = build_prompt_workflow_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_graph_has_expected_nodes(self):
        graph = build_prompt_workflow_graph()
        compiled = graph.compile()
        node_names = set(compiled.get_graph().nodes.keys())
        assert "discover_architecture" in node_names
        assert "plan_review" in node_names
        assert "prompt_build_review" in node_names

    def test_graph_edges_flow_correctly(self):
        """Verify the parent graph has the expected linear flow."""
        graph = build_prompt_workflow_graph()
        compiled = graph.compile()
        graph_data = compiled.get_graph()
        edge_sources = {e.source for e in graph_data.edges}
        assert "__start__" in edge_sources
        assert "discover_architecture" in edge_sources
        assert "plan_review" in edge_sources
        assert "prompt_build_review" in edge_sources
