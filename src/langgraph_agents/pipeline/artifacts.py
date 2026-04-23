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

Writes are atomic: content is written to ``<name>.tmp`` and then renamed onto
the final path. ``os.replace`` is POSIX + Windows atomic for same-filesystem
renames, so a crashed run either leaves the old artifact in place or no
artifact at all — never a half-written one. This matters because the matrix
runner uses ``summary.json`` presence as the resume-on-crash signal.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from . import environment as _environment
from .config import RunConfig, RunResult


def run_dir(chatroom_dir: str, run_id: str) -> Path:
    """Return the artifact directory for a run, creating it if missing."""
    path = Path(chatroom_dir) / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_dir_from_state(state: Mapping) -> Path:
    """Convenience: resolve ``run_dir`` from a state dict."""
    return run_dir(state["chatroom_dir"], state["run_id"])


def _atomic_write_text(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` atomically via a sibling ``.tmp`` file.

    A sibling temp keeps the write on the same filesystem so ``os.replace``
    is atomic. The temp is uniquified with the process id so concurrent
    writers targeting the same path from the same parent (pytest with
    xdist, matrix runner parallelism) don't stomp each other's tmp files.
    """
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def write_artifact(state: Mapping, filename: str, content: str) -> Path:
    """Write ``content`` to ``<run_dir>/<filename>`` and return the path."""
    path = run_dir_from_state(state) / filename
    _atomic_write_text(path, content)
    return path


def write_config(config: RunConfig) -> Path:
    """Dump the run config to ``config.json`` inside the run dir."""
    path = run_dir(config.chatroom_dir, config.run_id) / "config.json"
    _atomic_write_text(path, config.to_json())
    return path


def write_task(config: RunConfig) -> Path:
    """Dump the task text to ``task.md`` inside the run dir."""
    path = run_dir(config.chatroom_dir, config.run_id) / "task.md"
    _atomic_write_text(path, config.task)
    return path


def write_summary(result: RunResult) -> Path:
    """Dump the final run result to ``summary.json``. Its presence marks completion.

    Written last and atomically — if the process crashes before this call,
    the matrix runner will re-execute the run on resume.

    Environment provenance (git sha, CLI/SDK versions) is captured here if
    the caller didn't already supply it, so every summary on disk carries
    enough metadata to pair-check against a later code revision.
    """
    if result.environment is None:
        import dataclasses

        result = dataclasses.replace(result, environment=_environment.capture())
    path = Path(result.artifacts_dir) / "summary.json"
    _atomic_write_text(path, result.to_json())
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
