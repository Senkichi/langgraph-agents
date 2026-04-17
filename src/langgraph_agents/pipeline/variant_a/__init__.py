"""Variant A — four-phase pipeline: generate, cross-review, revise, synthesize.

No debate loop. This is the conservative branch; the research literature
strongly supports the reflection-pattern cross-critique setup it implements.
"""

from langgraph_agents.pipeline.variant_a.graph import (
    build_variant_a_graph,
    compile_variant_a,
    run_variant_a,
)

__all__ = ["build_variant_a_graph", "compile_variant_a", "run_variant_a"]
