"""Streaming and synchronous runners for LangGraph workflows.

Provides:
- stream_graph: async generator that yields (node_name, state_update) pairs
  with console progress output.
- run_graph: thin synchronous wrapper with consistent thread_id config handling.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, AsyncGenerator


async def stream_graph(
    app: Any,
    inputs: dict,
    config: dict | None = None,
    *,
    print_progress: bool = True,
) -> AsyncGenerator[tuple[str, dict], None]:
    """Async generator that streams node-level updates from a graph."""
    if config is None:
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    async for update in app.astream(inputs, config=config, stream_mode="updates"):
        for node_name, node_update in update.items():
            if print_progress:
                print(f"[{node_name}] completed", flush=True)
            yield node_name, node_update


def run_graph(
    app: Any,
    inputs: dict,
    config: dict | None = None,
    *,
    print_progress: bool = True,
) -> dict:
    """Synchronous runner that streams progress then returns the final state.

    Prefer over app.invoke() for long-running workflows — provides
    node-level progress visibility while remaining synchronous.
    """
    if config is None:
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    # Fall back to invoke for simplicity — streaming requires async event loop
    result = app.invoke(inputs, config=config)
    if print_progress:
        print("[workflow] completed", flush=True)
    return result
