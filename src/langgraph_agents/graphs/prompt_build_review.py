"""Prompt build-review loop subgraph.

The prompt engineer edits agent prompts and knowledge files, then two
parallel reviewers (behavioral + architectural) critique the changes via
Send() fan-out. A pure-Python synthesizer merges verdicts.
Cycles up to 4 times or until both reviewers approve.
"""

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from langgraph_agents.nodes.architectural_reviewer import architectural_review
from langgraph_agents.nodes.behavioral_reviewer import behavioral_review
from langgraph_agents.nodes.prompt_engineer import prompt_engineer
from langgraph_agents.nodes.prompt_review_synthesizer import synthesize_prompt_reviews
from langgraph_agents.state import PromptBuildState

MAX_BUILD_CYCLES = 4


def _fan_out_to_reviewers(state: PromptBuildState) -> list[Send]:
    """Fan out to both reviewers in parallel."""
    return [
        Send("behavioral_reviewer", state),
        Send("architectural_reviewer", state),
    ]


def _route_after_synthesis(state: PromptBuildState) -> str:
    """Route after synthesis: approve → end, revise → prompt_engineer (up to max cycles)."""
    if state.get("build_verdict") == "APPROVE":
        return END
    if state.get("build_cycle", 0) >= MAX_BUILD_CYCLES:
        return END
    return "prompt_engineer"


def build_prompt_build_review_graph() -> StateGraph:
    """Build the prompt build-review subgraph."""
    graph = StateGraph(PromptBuildState)

    graph.add_node("prompt_engineer", prompt_engineer)
    graph.add_node("behavioral_reviewer", behavioral_review)
    graph.add_node("architectural_reviewer", architectural_review)
    graph.add_node("synthesizer", synthesize_prompt_reviews)

    graph.add_edge(START, "prompt_engineer")
    graph.add_conditional_edges(
        "prompt_engineer",
        _fan_out_to_reviewers,
        ["behavioral_reviewer", "architectural_reviewer"],
    )
    graph.add_edge("behavioral_reviewer", "synthesizer")
    graph.add_edge("architectural_reviewer", "synthesizer")
    graph.add_conditional_edges(
        "synthesizer",
        _route_after_synthesis,
        {END: END, "prompt_engineer": "prompt_engineer"},
    )

    return graph


prompt_build_review_app = build_prompt_build_review_graph().compile()
