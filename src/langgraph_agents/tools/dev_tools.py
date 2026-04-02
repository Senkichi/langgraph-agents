"""Development tools for the coder and reviewer agents.

All file operations are relative to a workspace_path that is injected at
agent-creation time via tool binding (functools.partial or closure).
"""

import glob as globlib
import os
import subprocess

from langchain_core.tools import tool


def make_dev_tools(workspace_path: str) -> list:
    """Create dev tools bound to a specific workspace directory.

    Returns a list of @tool-decorated callables with the workspace baked in.
    """

    @tool
    def write_file(path: str, content: str) -> str:
        """Create or overwrite a file. Path is relative to the workspace."""
        full = os.path.join(workspace_path, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Wrote {len(content)} chars to {path}"

    @tool
    def read_file(path: str) -> str:
        """Read a file's contents. Path is relative to the workspace."""
        full = os.path.join(workspace_path, path)
        with open(full, encoding="utf-8") as f:
            return f.read()

    @tool
    def edit_file(path: str, old: str, new: str) -> str:
        """Replace the first occurrence of `old` with `new` in a file."""
        full = os.path.join(workspace_path, path)
        with open(full, encoding="utf-8") as f:
            content = f.read()
        if old not in content:
            return f"ERROR: old string not found in {path}"
        content = content.replace(old, new, 1)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Edited {path}"

    @tool
    def list_files(pattern: str = "**/*") -> str:
        """List files matching a glob pattern relative to the workspace."""
        matches = globlib.glob(
            os.path.join(workspace_path, pattern), recursive=True
        )
        relative = [os.path.relpath(m, workspace_path) for m in matches if os.path.isfile(m)]
        return "\n".join(sorted(relative)) if relative else "No files found."

    @tool
    def run_command(cmd: str) -> str:
        """Run a shell command in the workspace directory. Returns stdout+stderr."""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=workspace_path,
                capture_output=True,
                text=True,
                timeout=120,
            )
            output = result.stdout
            if result.stderr:
                output += f"\nSTDERR:\n{result.stderr}"
            if result.returncode != 0:
                output += f"\nEXIT CODE: {result.returncode}"
            return output or "(no output)"
        except subprocess.TimeoutExpired:
            return "ERROR: command timed out after 120s"

    return [write_file, read_file, edit_file, list_files, run_command]


def make_review_tools(workspace_path: str) -> list:
    """Create read-only tools for reviewer agents."""
    all_tools = make_dev_tools(workspace_path)
    # Reviewers get: read_file, list_files, run_command (indices 1, 3, 4)
    return [all_tools[1], all_tools[3], all_tools[4]]


def run_git_diff(workspace_path: str) -> str:
    """Capture the current git diff in the workspace."""
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=workspace_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        diff = result.stdout.strip()
        if not diff:
            # Fall back to showing all untracked files
            result = subprocess.run(
                ["git", "diff"],
                cwd=workspace_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            diff = result.stdout.strip()
        return diff or "(no changes detected)"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "(git diff unavailable)"
