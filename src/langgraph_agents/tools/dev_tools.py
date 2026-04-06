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
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout.strip()

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
