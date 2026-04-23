"""Environment provenance capture for run summaries.

Each completed run persists a small ``environment`` dict into ``summary.json``
so the eval framework can tell later whether two runs came from the same
code / CLI / Python / SDK. This is the minimum required to spot "my matrix
sweep straddled a pipeline edit" — a common self-inflicted eval wound.

All probes are best-effort: a missing git binary, a detached HEAD, or an
unavailable SDK all degrade to ``None`` rather than crashing the run.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _git(*args: str) -> str | None:
    """Run ``git <args>`` at the repo root. Return stdout stripped, or None."""
    kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
            encoding="utf-8",
            **kwargs,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.debug("git %s failed: %s", args, exc)
        return None
    if result.returncode != 0:
        return None
    out = (result.stdout or "").strip()
    return out or None


def _claude_cli_version() -> str | None:
    """Probe the claude CLI for its version. None if unavailable."""
    kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            **kwargs,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.debug("claude --version failed: %s", exc)
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or "").strip() or None


def _sdk_version() -> str | None:
    """Return the installed ``claude-agent-sdk`` version, or None."""
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("claude-agent-sdk")
        except PackageNotFoundError:
            return None
    except ImportError:
        return None


def capture() -> dict[str, Any]:
    """Snapshot the environment at run-finalisation time.

    Returned keys:
      - ``git_sha``: HEAD commit, or None.
      - ``git_branch``: current branch, or None (detached HEAD).
      - ``git_dirty``: True if the working tree has uncommitted changes.
      - ``claude_cli_version``: output of ``claude --version``, or None.
      - ``claude_agent_sdk_version``: installed PyPI version, or None.
      - ``python_version``: ``3.13.5 (CPython, win32)`` etc.
      - ``platform``: ``platform.platform()`` for OS debugging.
    """
    sha = _git("rev-parse", "HEAD")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    # `git status --porcelain` emits nothing on a clean tree.
    dirty_probe = _git("status", "--porcelain")
    git_dirty = bool(dirty_probe) if dirty_probe is not None else None

    return {
        "git_sha": sha,
        "git_branch": branch if branch != "HEAD" else None,
        "git_dirty": git_dirty,
        "claude_cli_version": _claude_cli_version(),
        "claude_agent_sdk_version": _sdk_version(),
        "python_version": (
            f"{platform.python_version()} "
            f"({platform.python_implementation()}, {sys.platform})"
        ),
        "platform": platform.platform(),
    }
