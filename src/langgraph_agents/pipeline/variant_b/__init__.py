"""Variant B — four-phase pipeline plus debate loop between revise and synthesize.

Variant B inherits Variant A's phases 1-3 (generate / cross-review / revise)
verbatim. Its surface-area additions are the debate loop (initialize, turn,
compact, record_termination) and a synthesis stage that reads the transcript
in addition to the v2 drafts.
"""

from langgraph_agents.pipeline.variant_b.graph import (
    build_variant_b_graph,
    compile_variant_b,
    run_variant_b,
)

__all__ = ["build_variant_b_graph", "compile_variant_b", "run_variant_b"]
