---
phase: token-optimization
plan: "02"
type: execute
wave: 1
depends_on: []
files_modified:
  - ~/.claude/hooks/token-opt/shared.py
  - ~/.claude/hooks/token-opt/scanner.py
  - ~/.claude/hooks/token-opt/post-tool.py
autonomous: true
requirements:
  - "File anatomy scanner producing token-estimated project index"
  - "Incremental anatomy updates on file write/edit"
  - "Secret-file exclusion before any content extraction"

must_haves:
  truths:
    - "Running `python scanner.py` in a project root produces anatomy.md in .claude/ with one-line descriptions and token estimates for every tracked file"
    - "Anatomy entries follow the format: `- filename — description (~NNN tok)`"
    - "Secret-bearing files (.env, .pem, .key, credentials.*, etc.) are never read or indexed"
    - "Binary files are detected and skipped"
    - "post-tool.py incrementally updates anatomy.md on Write/Edit without a full rescan"
    - "anatomy.md uses atomic write (tmp + rename) to prevent corruption"
  artifacts:
    - path: ~/.claude/hooks/token-opt/scanner.py
      provides: "CLI tool: walks project tree, extracts descriptions, estimates tokens, writes anatomy.md"
    - path: ~/.claude/hooks/token-opt/shared.py
      provides: "Extended with extract_description(), parse_anatomy(), write_anatomy(), is_binary()"
  key_links:
    - from: ~/.claude/hooks/token-opt/scanner.py
      to: ~/.claude/hooks/token-opt/shared.py
      via: "imports extract_description(), estimate_tokens(), is_excluded(), is_binary(), write_anatomy()"
      pattern: import
    - from: ~/.claude/hooks/token-opt/post-tool.py
      to: ~/.claude/hooks/token-opt/shared.py
      via: "imports extract_description(), parse_anatomy(), write_anatomy() for incremental updates"
      pattern: import
---

# File Anatomy Scanner — Implementation Plan

## Objective

Build a project file index (anatomy.md) that gives Claude a token-estimated map of every file
in the project. Claude reads this once per session instead of opening files individually when
the summary suffices. The scanner runs on demand via CLI; incremental updates happen automatically
via the PostToolUse hook from Plan 01.

The anatomy concept is validated by OpenWolf (their highest-value feature alongside read dedup),
but our implementation fixes their security gaps (broad secret-file deny list) and performance
issues (no full re-parse on every incremental update).

## Execution Context

Read these before starting:
- `~/.claude/hooks/token-opt/shared.py` — existing utilities from Plan 01 (or build alongside if wave-parallel)
- `.planning/phases/token-optimization/RESEARCH.md` — architecture and secret-safety decisions

**Important:** This plan extends `shared.py` and `post-tool.py` which are also created/modified
by Plan 01. If running in parallel, coordinate: shared.py additions here are new functions that
don't conflict with Plan 01's functions. The post-tool.py changes here add a new code path
(Write/Edit handling) that Plan 01 stubs but doesn't implement.

<tasks>

<task type="auto">
  <name>Task 1: Description extraction and anatomy I/O in shared.py</name>
  <files>~/.claude/hooks/token-opt/shared.py</files>
  <read_first>~/.claude/hooks/token-opt/shared.py</read_first>
  <action>
    Add these functions to `shared.py` (append — do not modify existing functions from Plan 01):

    **`is_binary(file_path: str) -> bool`:**
    Read first 8192 bytes in binary mode. Return True if null bytes found or if
    UnicodeDecodeError on utf-8 decode attempt. On any IOError return True (safe default: skip).

    **`extract_description(file_path: str, max_bytes: int = 8192) -> str`:**
    Read first max_bytes of file. Extract a one-line description (max 100 chars) using this
    priority cascade:
    1. Python: first docstring (`"""..."""` or `'''...'''`) after any imports
    2. JavaScript/TypeScript: first JSDoc comment (`/** ... */`) or first `//` comment block
    3. Rust/Go/C/Java: first `//` or `///` comment block at file top
    4. Markdown: first non-heading, non-blank line
    5. YAML/TOML: first comment line
    6. HTML: `<title>` content or first `<meta name="description">` content
    7. Shell: first `#` comment after shebang
    8. Fallback: first non-blank, non-comment line, truncated to 100 chars
    On any error: return `"(no description)"`.
    Strip leading `#`, `//`, `"""`, etc. from the extracted line.

    **`parse_anatomy(anatomy_path: Path) -> dict[str, list[dict]]`:**
    Parse anatomy.md into `{section_name: [{filename, description, tokens}, ...]}`.
    Format per line: `- \`filename\` — description (~NNN tok)`
    Section headers are `## directory/` lines.
    Return empty dict on missing file or parse error.

    **`write_anatomy(anatomy_path: Path, sections: dict[str, list[dict]]) -> None`:**
    Serialize sections dict back to anatomy.md format. Use atomic write:
    write to `anatomy_path.with_suffix(".tmp")`, then `os.replace()` to final path.

    **`upsert_anatomy_entry(anatomy_path: Path, rel_path: str, description: str, tokens: int) -> None`:**
    Parse anatomy, find or create the directory section, upsert the file entry, write back.
    This is the incremental update path used by the PostToolUse hook.
  </action>
  <verify>python -c "
import sys; sys.path.insert(0, 'C:/Users/senki/.claude/hooks/token-opt')
from shared import extract_description, parse_anatomy, write_anatomy, is_binary, upsert_anatomy_entry
from pathlib import Path
# Test extract_description on a known Python file
desc = extract_description('C:/Users/senki/.claude/hooks/token-opt/shared.py')
print(f'Description: {desc}')
assert len(desc) > 0 and len(desc) <= 100
print('OK')
"</verify>
  <acceptance_criteria>
    - is_binary correctly identifies binary files (returns True for .exe, .png)
    - extract_description returns a non-empty string <= 100 chars for Python, JS, Markdown files
    - extract_description returns "(no description)" on error or unreadable files
    - parse_anatomy round-trips: write then parse produces identical structure
    - upsert_anatomy_entry adds new entries and updates existing ones
    - write_anatomy uses atomic tmp+rename pattern
  </acceptance_criteria>
  <done>All 5 new functions importable and tested with manual smoke tests. Round-trip test passes.</done>
</task>

<task type="auto">
  <name>Task 2: Anatomy scanner CLI</name>
  <files>~/.claude/hooks/token-opt/scanner.py</files>
  <read_first>~/.claude/hooks/token-opt/shared.py</read_first>
  <action>
    Create `~/.claude/hooks/token-opt/scanner.py`:

    ```python
    #!/usr/bin/env python3
    """Project anatomy scanner — builds token-estimated file index."""
    ```

    **CLI interface** (use argparse):
    - `python scanner.py [project_root]` — defaults to cwd
    - `--output PATH` — anatomy.md output path, default: `{project_root}/.claude/anatomy.md`
    - `--max-files N` — maximum files to index, default: 500
    - `--check` — verify anatomy matches filesystem, exit 1 if stale (no writes)
    - `--quiet` — suppress progress output

    **`scan_project(project_root: Path, max_files: int = 500) -> dict[str, list[dict]]`:**
    1. Walk project_root using os.walk.
    2. Skip directories: `.git`, `node_modules`, `__pycache__`, `.venv`, `venv`, `.tox`,
       `target`, `dist`, `build`, `.next`, `.nuxt`, `.output`, `.cache`, `.sessions`.
    3. For each file:
       a. Compute relative path from project_root.
       b. `is_excluded(rel_path)` → skip.
       c. `is_binary(abs_path)` → skip.
       d. Skip files > 1MB (os.path.getsize).
       e. `extract_description(abs_path)` → get description.
       f. `estimate_tokens(content, rel_path)` where content is the full file read
          (but cap read at 1MB for token estimation — use file size / CHARS_PER_TOKEN for larger).
       g. Add to sections dict keyed by directory part of rel_path (or "." for root files).
    4. Sort sections alphabetically. Sort files within sections alphabetically.
    5. Return sections dict.

    **`check_anatomy(anatomy_path: Path, project_root: Path) -> list[str]`:**
    Parse existing anatomy. Walk filesystem. Return list of discrepancies:
    - Files in anatomy but not on disk → "REMOVED: path"
    - Files on disk but not in anatomy → "NEW: path"
    - Files where token estimate differs by >20% → "CHANGED: path (was ~N, now ~M)"

    **main():**
    1. Parse args.
    2. If --check: run check_anatomy, print discrepancies, exit 1 if any.
    3. Else: run scan_project, write_anatomy, print summary (N files indexed, N sections).

    Print progress to stderr: `[scanner] Scanning... {count}/{total} files`
    Print summary to stdout: `Anatomy written: {path} ({n_files} files, {n_sections} sections)`
  </action>
  <verify>cd /tmp && mkdir -p test_proj/src && echo '"""Test module."""\nx = 1' > test_proj/src/main.py && echo '# Config\nkey: value' > test_proj/config.yaml && python ~/.claude/hooks/token-opt/scanner.py test_proj --output test_proj/anatomy.md && cat test_proj/anatomy.md && rm -rf test_proj</verify>
  <acceptance_criteria>
    - scanner.py produces anatomy.md with correct format (## section headers, - `file` — desc (~N tok) entries)
    - Secret files are excluded (create a .env in test dir, verify it's absent from output)
    - Binary files are excluded
    - --check mode detects new/removed/changed files
    - Files > 1MB are skipped
    - Output is sorted alphabetically by section then filename
    - Max 500 files by default (configurable)
  </acceptance_criteria>
  <done>Scanner produces valid anatomy.md for a test project. --check mode correctly detects discrepancies. Secret and binary files excluded.</done>
</task>

<task type="auto">
  <name>Task 3: Incremental anatomy update in post-tool.py</name>
  <files>~/.claude/hooks/token-opt/post-tool.py</files>
  <read_first>~/.claude/hooks/token-opt/post-tool.py, ~/.claude/hooks/token-opt/shared.py</read_first>
  <action>
    Extend `post-tool.py` to incrementally update anatomy.md when a Write or Edit occurs.

    After the existing session JSONL append (from Plan 01), add:

    ```python
    # Incremental anatomy update on write/edit
    if op == "write" and not is_excluded(normalized):
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
        anatomy_path = Path(project_dir) / ".claude" / "anatomy.md"
        if anatomy_path.exists():
            abs_path = Path(project_dir) / normalized
            if abs_path.exists() and not is_binary(str(abs_path)):
                try:
                    desc = extract_description(str(abs_path))
                    content = abs_path.read_text(encoding="utf-8", errors="ignore")
                    tokens = estimate_tokens(content, normalized)
                    upsert_anatomy_entry(anatomy_path, normalized, desc, tokens)
                except Exception:
                    pass  # Never block Claude Code
    ```

    Key behaviors:
    - Only update if anatomy.md already exists (scanner must run first to create it)
    - Only update for Write/Edit operations, not Read
    - Use the just-written file content (read from disk post-write) for fresh description
    - Skip binary and excluded files
    - Silent failure — never block Claude Code
  </action>
  <verify>
    mkdir -p /tmp/test_incr/.claude && echo -e "## src/\n\n- \`main.py\` — Old description (~10 tok)" > /tmp/test_incr/.claude/anatomy.md && CLAUDE_PROJECT_DIR=/tmp/test_incr echo '{"tool_name":"Write","tool_input":{"file_path":"/tmp/test_incr/src/main.py","content":"\"\"\"Updated module.\"\"\"\nx = 42\n"}}' | python ~/.claude/hooks/token-opt/post-tool.py && cat /tmp/test_incr/.claude/anatomy.md && rm -rf /tmp/test_incr
  </verify>
  <acceptance_criteria>
    - anatomy.md is updated after Write/Edit with new description and token count
    - anatomy.md is NOT created if it doesn't exist (scanner must run first)
    - Existing entries are updated in-place, not duplicated
    - New files are added to the correct directory section
    - Atomic write prevents corruption (no partial anatomy.md on crash)
    - Read operations do NOT trigger anatomy updates
  </acceptance_criteria>
  <done>post-tool.py incrementally updates anatomy.md on write operations. Existing entries updated, new entries added, atomic write confirmed.</done>
</task>

</tasks>

<verification>
Before declaring plan complete:
- [ ] `python scanner.py {some_project_dir}` produces a valid anatomy.md
- [ ] anatomy.md entries follow `- \`filename\` — description (~NNN tok)` format
- [ ] `python scanner.py --check {dir}` exits 1 after adding a new file
- [ ] Incremental update via post-tool.py changes anatomy.md after simulated Write
- [ ] Secret files (.env, .pem) are absent from anatomy.md
- [ ] Binary files (.exe, .png) are absent from anatomy.md
- [ ] `parse_anatomy(path)` → `write_anatomy(path, sections)` round-trip preserves content
</verification>

<success_criteria>
- Scanner indexes up to 500 files with descriptions and token estimates
- Anatomy format is human-readable and parseable
- Incremental updates keep anatomy current without full rescans
- Secret and binary files are systematically excluded
- Atomic writes prevent corruption under any failure mode
</success_criteria>

<output>
After completion, create `.planning/phases/token-optimization/tok-02-SUMMARY.md`
</output>
