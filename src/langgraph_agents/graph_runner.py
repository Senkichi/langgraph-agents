"""Streaming and synchronous runners for LangGraph workflows.

Provides:
- stream_graph: async generator that yields (node_name, state_update) pairs
  with console progress output.
- run_graph: thin synchronous wrapper with consistent thread_id config handling.

Both runners create a ``GraphTracer`` when ``TRACE_ENABLED`` is true, emitting
structured JSONL events for observability.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator


def run_graph(
    app: Any,
    inputs: dict,
    config: dict | None = None,
    *,
    print_progress: bool = True,
    graph_name: str = "workflow",
) -> dict:
    """Synchronous runner that invokes the graph and returns the final state.

    When tracing is enabled, creates a ``GraphTracer``, sets it in context,
    and prints a summary on completion. The tracer captures git/CLI/SDK
    provenance into the ``graph_start`` event so trace logs can be paired
    against the exact code revision that produced them — same shape as
    the dual-pipeline ``summary.json`` block.
    """
    from langgraph_agents.config import TRACE_DIR, TRACE_ENABLED, TRACE_LEVEL
    from langgraph_agents.tracer import GraphTracer, set_tracer

    if config is None:
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    tracer: GraphTracer | None = None
    token = None

    if TRACE_ENABLED:
        tracer = GraphTracer(
            run_id=config["configurable"]["thread_id"],
            graph_name=graph_name,
            log_dir=Path(TRACE_DIR),
            trace_level=TRACE_LEVEL,
        )
        token = set_tracer(tracer)
        tracer.graph_start(inputs)

    t0 = time.perf_counter()
    try:
        result = app.invoke(inputs, config=config)
    except Exception:
        if tracer is not None:
            duration_ms = (time.perf_counter() - t0) * 1000
            tracer.graph_end(duration_ms)
        raise
    finally:
        if token is not None:
            set_tracer(None)

    duration_ms = (time.perf_counter() - t0) * 1000

    if tracer is not None:
        summary = tracer.graph_end(duration_ms)
        if print_progress:
            _print_summary(summary)
    elif print_progress:
        print("[workflow] completed", flush=True)

    return result


async def stream_graph(
    app: Any,
    inputs: dict,
    config: dict | None = None,
    *,
    print_progress: bool = True,
    graph_name: str = "workflow",
) -> AsyncGenerator[tuple[str, dict], None]:
    """Async generator that streams node-level updates from a graph.

    When tracing is enabled, creates a ``GraphTracer`` and emits events
    alongside the stream. Prints a summary after iteration completes.
    The first emitted event (``graph_start``) carries an ``environment``
    block with git/CLI/SDK provenance — see ``run_graph`` docstring.
    """
    from langgraph_agents.config import TRACE_DIR, TRACE_ENABLED, TRACE_LEVEL
    from langgraph_agents.tracer import GraphTracer, set_tracer

    if config is None:
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    tracer: GraphTracer | None = None
    token = None

    if TRACE_ENABLED:
        tracer = GraphTracer(
            run_id=config["configurable"]["thread_id"],
            graph_name=graph_name,
            log_dir=Path(TRACE_DIR),
            trace_level=TRACE_LEVEL,
        )
        token = set_tracer(tracer)
        tracer.graph_start(inputs)

    t0 = time.perf_counter()
    try:
        async for update in app.astream(
            inputs, config=config, stream_mode="updates"
        ):
            for node_name, node_update in update.items():
                if print_progress:
                    print(f"[{node_name}] completed", flush=True)
                yield node_name, node_update
    finally:
        duration_ms = (time.perf_counter() - t0) * 1000
        if tracer is not None:
            summary = tracer.graph_end(duration_ms)
            if print_progress:
                _print_summary(summary)
        if token is not None:
            set_tracer(None)


def _print_summary(summary: dict) -> None:
    """Print a human-readable trace summary to console."""
    print(f"\n{'=' * 60}")
    print(f"Trace Summary - {summary.get('graph_name', 'workflow')}")
    print(f"{'=' * 60}")
    print(f"Total duration: {summary['total_duration_s']:.1f}s")
    print(f"Est. tokens in:  {summary['total_tokens_in']:,}")
    print(f"Est. tokens out: {summary['total_tokens_out']:,}")
    print(f"\nPer-node breakdown (sorted by duration):")
    for entry in summary.get("node_breakdown", []):
        pct = entry["pct_of_total"]
        print(
            f"  {entry['node']:.<30s} {entry['total_s']:>7.1f}s  "
            f"({pct:>4.1f}%)  x{entry['cycles']}"
        )
    bottleneck = summary.get("bottleneck")
    if bottleneck:
        print(
            f"\nBottleneck: {bottleneck['node']} "
            f"({bottleneck['pct_of_total']:.0f}% of wall time)"
        )
    print(f"Log: {summary.get('log_file', 'N/A')}")
    print(f"{'=' * 60}\n")
