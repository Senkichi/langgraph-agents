"""Backward-compatible re-export of the package-level environment module.

The canonical implementation lives at ``langgraph_agents.environment`` so
the production graph tracer can share it with the dual-pipeline
artifacts writer without crossing a layer boundary. This shim preserves
the historical import path used by ``pipeline/artifacts.py`` and any
external consumers.
"""

from __future__ import annotations

from langgraph_agents.environment import (  # noqa: F401
    _claude_cli_version,
    _git,
    _sdk_version,
    capture,
)

__all__ = ["capture"]
