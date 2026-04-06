"""Utilities for interacting with git in a workspace directory."""

import subprocess


def run_git_diff(workspace_path: str) -> str:
    """Capture changes made in the workspace.

    Tries in order:
    1. Uncommitted changes vs HEAD (working tree + staging area) — covers the common
       case where the agent writes files without committing.
    2. Last commit diff — covers the case where the agent committed its work.
    Returns the first non-empty result.
    """
    def _run(*args: str) -> str:
        result = subprocess.run(
            ["git"] + list(args),
            cwd=workspace_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        return (result.stdout or b"").decode("utf-8", errors="replace").strip()

    try:
        diff = _run("diff", "HEAD")
        if diff:
            return diff

        # Agent may have committed — check the most recent commit.
        commit_count = _run("rev-list", "--count", "HEAD")
        if commit_count.strip().isdigit() and int(commit_count.strip()) >= 1:
            diff = _run("show", "--patch", "--format=", "HEAD")
            if diff:
                return diff

        return "(no changes detected)"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "(git diff unavailable)"


DIFF_MAX_CHARS = 16_000


def truncate_diff(diff: str) -> str:
    """Truncate a large diff, keeping the tail (most recent changes).

    Keeps the tail since earlier changes are already reflected in the workspace.
    Finds a hunk boundary to avoid mid-hunk splits.
    """
    if len(diff) <= DIFF_MAX_CHARS:
        return diff
    truncated = diff[-DIFF_MAX_CHARS:]
    hunk_start = truncated.find("\n@@")
    if hunk_start > 0:
        truncated = truncated[hunk_start + 1:]
    return f"[diff truncated — showing last {len(truncated)} chars]\n{truncated}"
