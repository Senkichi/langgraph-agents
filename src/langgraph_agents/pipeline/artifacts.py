"""Run-artifact layout on disk.

Every phase writes its outputs under ``<chatroom_dir>/<run_id>/``. The eval
framework reads from this layout rather than from in-memory state, so the on-
disk shape is part of the contract.

Layout:

    <chatroom_dir>/<run_id>/
        config.json
        task.md
        left_draft_v1.md
        right_draft_v1.md
        left_critique_of_right.md
        right_critique_of_left.md
        left_draft_v2.md
        right_draft_v2.md
        debate_transcript.md     # Variant B only
        final_plan.md
        summary.json
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from .config import RunConfig, RunResult


def run_dir(chatroom_dir: str, run_id: str) -> Path:
    """Return the artifact directory for a run, creating it if missing."""
    path = Path(chatroom_dir) / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_dir_from_state(state: Mapping) -> Path:
    """Convenience: resolve ``run_dir`` from a state dict."""
    return run_dir(state["chatroom_dir"], state["run_id"])


def write_artifact(state: Mapping, filename: str, content: str) -> Path:
    """Write ``content`` to ``<run_dir>/<filename>`` and return the path."""
    path = run_dir_from_state(state) / filename
    path.write_text(content, encoding="utf-8")
    return path


def write_config(config: RunConfig) -> Path:
    """Dump the run config to ``config.json`` inside the run dir."""
    path = run_dir(config.chatroom_dir, config.run_id) / "config.json"
    path.write_text(config.to_json(), encoding="utf-8")
    return path


def write_task(config: RunConfig) -> Path:
    """Dump the task text to ``task.md`` inside the run dir."""
    path = run_dir(config.chatroom_dir, config.run_id) / "task.md"
    path.write_text(config.task, encoding="utf-8")
    return path


def write_summary(result: RunResult) -> Path:
    """Dump the final run result to ``summary.json``. Its presence marks completion."""
    path = Path(result.artifacts_dir) / "summary.json"
    path.write_text(result.to_json(), encoding="utf-8")
    return path


def has_completed(chatroom_dir: str, run_id: str) -> bool:
    """True if a prior run completed (summary.json present).

    Used by the matrix runner to skip already-finished configurations on
    resume-after-crash.
    """
    return (Path(chatroom_dir) / run_id / "summary.json").is_file()


def load_artifact(chatroom_dir: str, run_id: str, filename: str) -> str:
    """Read a named artifact from a run dir. Raises ``FileNotFoundError`` if absent."""
    return (Path(chatroom_dir) / run_id / filename).read_text(encoding="utf-8")


def load_summary(chatroom_dir: str, run_id: str) -> dict[str, Any]:
    """Load ``summary.json`` as a dict."""
    path = Path(chatroom_dir) / run_id / "summary.json"
    return json.loads(path.read_text(encoding="utf-8"))
