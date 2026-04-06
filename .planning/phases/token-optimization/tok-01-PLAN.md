---
phase: token-optimization
plan: "01"
type: execute
wave: 1
depends_on: []
files_modified:
  - ~/.claude/hooks/token-opt/shared.py
  - ~/.claude/hooks/token-opt/session-init.py
  - ~/.claude/hooks/token-opt/pre-read.py
  - ~/.claude/hooks/token-opt/post-tool.py
  - ~/.claude/settings.json
autonomous: true
requirements:
  - "Read lifecycle management (FRESH/STALE/SUPERSEDED classification)"
  - "Per-session file operation tracking via append-only JSONL"
  - "Stderr warnings on stale and superseded reads"

must_haves:
  truths:
    - "When Claude reads a file it already read this session, stderr warns with token estimate and SUPERSEDED label"
    - "When Claude reads a file it edited since last reading, stderr warns with STALE label"
    - "Fresh reads pass through with no warning"
    - "Session state uses append-only JSONL — no read-modify-write races under parallel tool calls"
    - "Hooks exit cleanly (code 0) on any error — never block Claude Code"
    - "Files under .claude/ and .wolf/ are excluded from tracking"
  artifacts:
    - path: ~/.claude/hooks/token-opt/shared.py
      provides: "Token estimation, path normalization, JSONL I/O, secret-file deny list"
    - path: ~/.claude/hooks/token-opt/session-init.py
      provides: "SessionStart hook — creates session JSONL file, rotates sessions older than 24h"
    - path: ~/.claude/hooks/token-opt/pre-read.py
      provides: "PreToolUse hook for Read — scans session JSONL, classifies as FRESH/STALE/SUPERSEDED, emits stderr"
    - path: ~/.claude/hooks/token-opt/post-tool.py
      provides: "PostToolUse hook for Read|Write|Edit — logs file operations with timestamps and token estimates"
  key_links:
    - from: ~/.claude/hooks/token-opt/pre-read.py
      to: ~/.claude/hooks/token-opt/shared.py
      via: "imports scan_session_file(), estimate_tokens(), normalize_path()"
      pattern: import
    - from: ~/.claude/hooks/token-opt/post-tool.py
      to: ~/.claude/hooks/token-opt/shared.py
      via: "imports append_session_event(), estimate_tokens()"
      pattern: import
    - from: ~/.claude/hooks/token-opt/session-init.py
      to: ~/.claude/hooks/token-opt/shared.py
      via: "imports session_file_path(), rotate_old_sessions()"
      pattern: import
---

# Read Lifecycle Hooks — Implementation Plan

<objective>
Build Claude Code hooks that track file read/write operations per session and warn on stale/superseded reads. Uses append-only JSONL for race-free session state under parallel tool calls.

Headroom's production data shows 79% of Read bytes are stale (67%) or superseded (12%). This is the highest-ROI token optimization available.

Output: 4 Python files in ~/.claude/hooks/token-opt/ + hook registrations in settings.json.
</objective>

<execution_context>
@C:/Users/senki/.claude/get-shit-done/workflows/execute-plan.md
@C:/Users/senki/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/token-optimization/RESEARCH.md
@C:/Users/senki/.claude/settings.json
@C:/Users/senki/.claude/skills/continuous-learning-v2/hooks/observe.sh (lines 1-50: stdin reading pattern, python resolution)
</context>

<tasks>

<task type="auto">
  <name>Task 1: Shared utilities module</name>
  <files>C:/Users/senki/.claude/hooks/token-opt/shared.py</files>
  <read_first>
    - C:/Users/senki/.claude/skills/continuous-learning-v2/hooks/observe.sh (lines 1-50: stdin reading and python detection patterns)
  </read_first>
  <action>
    Create directory `~/.claude/hooks/token-opt/` if it does not exist.
    Create `~/.claude/hooks/token-opt/shared.py` with these components:

    **Constants:**
    - `SESSION_DIR`: `Path(os.path.expanduser("~/.claude/.sessions/"))`
    - `CHARS_PER_TOKEN`: `{"code": 3.5, "prose": 4.0, "mixed": 3.75}`
    - `SECRET_DENY_PATTERNS`: `[".env*", "*.pem", "*.key", "*.pfx", "*.p12", "*.jks", "credentials.*", ".npmrc", ".netrc", "*secret*", "*.keystore", "id_rsa*", "id_ed25519*", "*.cert"]`
    - `INTERNAL_PATH_PREFIXES`: `[".claude/", ".wolf/", ".git/"]`
    - `CODE_EXTENSIONS`: `{".py", ".rs", ".go", ".js", ".ts", ".c", ".cpp", ".java", ".rb", ".sh", ".jsx", ".tsx"}`
    - `PROSE_EXTENSIONS`: `{".md", ".txt", ".rst", ".adoc"}`

    **Functions (all wrapped in try/except returning safe defaults on failure):**

    1. `normalize_path(file_path: str, project_dir: str | None = None) -> str`:
       Replace backslashes with forward slashes. If project_dir provided, make path relative via os.path.relpath. Return lowercase on Windows (os.name == "nt").

    2. `is_excluded(normalized_path: str) -> bool`:
       Return True if path starts with any INTERNAL_PATH_PREFIXES or basename matches any SECRET_DENY_PATTERNS (use fnmatch.fnmatch).

    3. `detect_file_type(file_path: str) -> str`:
       Returns "code", "prose", or "mixed" based on Path(file_path).suffix.

    4. `estimate_tokens(content: str, file_path: str) -> int`:
       Use detect_file_type to classify, then return `int(len(content) / CHARS_PER_TOKEN[file_type])`.

    5. `session_file_path(session_id: str) -> Path`:
       Return `SESSION_DIR / f"{session_id}.jsonl"`.

    6. `current_session_file() -> Path | None`:
       List SESSION_DIR for .jsonl files, return most recently modified, or None if dir missing or empty.

    7. `rotate_old_sessions(max_age_hours: int = 24) -> int`:
       Delete .jsonl files in SESSION_DIR older than max_age_hours. Return count deleted.

    8. `append_session_event(session_path: Path, event: dict) -> None`:
       JSON-serialize event dict, append as single line to session_path. Use open mode "a" (atomic under PIPE_BUF for lines under 4096 bytes).

    9. `scan_session_file(session_path: Path, target_path: str) -> dict`:
       Read all lines from session_path. For each JSON line where `path == target_path`, track: `last_read_ts`, `last_write_ts`, `read_count`, `last_read_tokens`. Return dict with these keys (all None if file never seen).

    10. `read_stdin() -> dict`:
        Read all of stdin, parse as JSON, return dict. On any error (empty stdin, invalid JSON) return empty dict.
  </action>
  <verify>
    <automated>python -c "import sys; sys.path.insert(0, 'C:/Users/senki/.claude/hooks/token-opt'); import shared; assert hasattr(shared, 'normalize_path'); assert hasattr(shared, 'is_excluded'); assert hasattr(shared, 'estimate_tokens'); assert hasattr(shared, 'scan_session_file'); assert hasattr(shared, 'read_stdin'); assert shared.estimate_tokens('x = 1', 'test.py') > 0; assert shared.is_excluded('.env.local'); assert shared.is_excluded('.claude/settings.json'); assert not shared.is_excluded('src/main.py'); print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - shared.py exists at ~/.claude/hooks/token-opt/shared.py
    - All 10 functions are defined and importable
    - normalize_path converts backslashes and handles relative paths
    - is_excluded catches .env, .pem, .claude/ paths
    - estimate_tokens returns int > 0 for non-empty strings
    - scan_session_file returns dict with last_read_ts, last_write_ts, read_count keys
  </acceptance_criteria>
  <done>Shared utilities module created with all 10 functions importable and type-correct.</done>
</task>

<task type="auto">
  <name>Task 2: Session init hook</name>
  <files>C:/Users/senki/.claude/hooks/token-opt/session-init.py</files>
  <read_first>
    - C:/Users/senki/.claude/hooks/token-opt/shared.py
  </read_first>
  <action>
    Create `~/.claude/hooks/token-opt/session-init.py` — a SessionStart hook script.

    The script:
    1. Reads stdin JSON via `read_stdin()`. Extracts `session_id`. If missing, generates one: `f"session-{datetime.now():%Y%m%d-%H%M%S}"`.
    2. Creates `SESSION_DIR` if it does not exist (`mkdir -p` equivalent).
    3. Calls `rotate_old_sessions(max_age_hours=24)` to clean up stale session files.
    4. Creates the session JSONL file via `session_file_path(session_id)` — touch if not exists.
    5. Appends a `{"event": "session_start", "ts": "<ISO8601>", "session_id": "<id>"}` line.
    6. Entire `main()` wrapped in try/except that always calls `sys.exit(0)`.

    Import pattern:
    ```python
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from shared import read_stdin, session_file_path, rotate_old_sessions, append_session_event, SESSION_DIR
    ```
  </action>
  <verify>
    <automated>echo '{"session_id":"test-verify-01"}' | python "C:/Users/senki/.claude/hooks/token-opt/session-init.py" && python -c "from pathlib import Path; p = Path.home() / '.claude' / '.sessions' / 'test-verify-01.jsonl'; assert p.exists(), f'{p} not found'; import json; lines = p.read_text().strip().split('\n'); data = json.loads(lines[0]); assert data['event'] == 'session_start'; assert data['session_id'] == 'test-verify-01'; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - session-init.py creates .jsonl file in ~/.claude/.sessions/
    - First line of JSONL is a session_start event with session_id and ISO timestamp
    - Rotates sessions older than 24h on startup
    - Exits 0 on any error (never blocks Claude Code)
    - Exits 0 on empty or malformed stdin
  </acceptance_criteria>
  <done>Session init hook creates JSONL files and rotates old sessions. Exits cleanly on all error paths.</done>
</task>

<task type="auto">
  <name>Task 3: Pre-read classification hook</name>
  <files>C:/Users/senki/.claude/hooks/token-opt/pre-read.py</files>
  <read_first>
    - C:/Users/senki/.claude/hooks/token-opt/shared.py
  </read_first>
  <action>
    Create `~/.claude/hooks/token-opt/pre-read.py` — a PreToolUse hook (matcher: Read).

    The script:
    1. `read_stdin()` → extract `tool_input.file_path` (fallback to `tool_input.path`).
    2. `normalize_path(file_path, os.environ.get("CLAUDE_PROJECT_DIR"))`.
    3. If `is_excluded(normalized)`: `sys.exit(0)` silently.
    4. `current_session_file()` → if None: `sys.exit(0)`.
    5. `scan_session_file(session_path, normalized)` → get file history dict.
    6. Classification logic:
       - If `last_write_ts is not None` AND `last_read_ts is not None` AND `last_write_ts > last_read_ts`:
         **STALE** — `print(f"[token-opt] STALE: {basename} was edited after last read. Context has outdated content (~{tokens} tok).", file=sys.stderr)`
       - Elif `read_count >= 1`:
         **SUPERSEDED** — `print(f"[token-opt] SUPERSEDED: {basename} already read this session (~{tokens} tok). Consider if the prior read suffices.", file=sys.stderr)`
       - Else:
         **FRESH** — no output.
    7. Always `sys.exit(0)` — warnings are advisory, never block the read.
    8. Entire `main()` wrapped in try/except that always calls `sys.exit(0)`.

    Import pattern: same `sys.path.insert(0, ...)` as session-init.py.
    Imports: `read_stdin, normalize_path, is_excluded, current_session_file, scan_session_file`.
  </action>
  <verify>
    <automated>echo '{"session_id":"test-classify"}' | python "C:/Users/senki/.claude/hooks/token-opt/session-init.py" && echo '{"tool_name":"Read","tool_input":{"file_path":"src/main.py"},"tool_output":{"content":"x = 1"}}' | python "C:/Users/senki/.claude/hooks/token-opt/post-tool.py" && echo '{"tool_name":"Read","tool_input":{"file_path":"src/main.py"}}' | python "C:/Users/senki/.claude/hooks/token-opt/pre-read.py" 2>&1 | grep -q "SUPERSEDED" && echo "OK"</automated>
  </verify>
  <acceptance_criteria>
    - Outputs nothing for fresh reads (first read of a file)
    - Warns on stderr with STALE label when file was edited after last read
    - Warns on stderr with SUPERSEDED label when file was already read this session
    - Warning includes basename and approximate token count
    - Exits 0 on any error
    - Exits 0 on empty or malformed stdin
    - Excluded paths (.env, .claude/) produce no output
  </acceptance_criteria>
  <done>Pre-read hook classifies reads correctly. FRESH silent, STALE and SUPERSEDED warn on stderr with token estimates.</done>
</task>

<task type="auto">
  <name>Task 4: Post-tool logging hook</name>
  <files>C:/Users/senki/.claude/hooks/token-opt/post-tool.py</files>
  <read_first>
    - C:/Users/senki/.claude/hooks/token-opt/shared.py
  </read_first>
  <action>
    Create `~/.claude/hooks/token-opt/post-tool.py` — a PostToolUse hook (matcher: Read|Write|Edit|MultiEdit).

    The script:
    1. `read_stdin()` → extract `tool_name` and `tool_input`.
    2. Extract `file_path` from tool_input:
       - Read: `tool_input.get("file_path") or tool_input.get("path")`
       - Write/Edit/MultiEdit: `tool_input.get("file_path")`
    3. `normalize_path(file_path, os.environ.get("CLAUDE_PROJECT_DIR"))`. If `is_excluded(normalized)`: `sys.exit(0)`.
    4. `current_session_file()` → if None: `sys.exit(0)`.
    5. Determine operation type:
       - `tool_name == "Read"` → `op = "read"`
       - `tool_name in ("Write", "Edit", "MultiEdit")` → `op = "write"`
    6. Estimate tokens:
       - Read: try `tool_output = data.get("tool_output", {})`, then content from `tool_output.get("content", "")` if dict, else str(tool_output). Fallback: `tool_input.get("limit", 0) * 80` chars estimate. Use `estimate_tokens(content, normalized)`.
       - Write: use `len(tool_input.get("content", ""))` with `estimate_tokens()`.
       - Edit: use `len(tool_input.get("new_string", ""))` with `estimate_tokens()`.
    7. `append_session_event(session_path, {"event": op, "ts": datetime.now(timezone.utc).isoformat(), "path": normalized, "tokens": estimated_tokens})`.
    8. Entire `main()` wrapped in try/except that always calls `sys.exit(0)`.

    Import pattern: same `sys.path.insert(0, ...)` as other hooks.
    Imports: `read_stdin, normalize_path, is_excluded, current_session_file, append_session_event, estimate_tokens`.
  </action>
  <verify>
    <automated>echo '{"session_id":"test-log"}' | python "C:/Users/senki/.claude/hooks/token-opt/session-init.py" && echo '{"tool_name":"Read","tool_input":{"file_path":"src/app.py"},"tool_output":{"content":"def main():\n    pass\n"}}' | python "C:/Users/senki/.claude/hooks/token-opt/post-tool.py" && python -c "from pathlib import Path; import json; p = sorted(Path.home().joinpath('.claude','.sessions').glob('test-log.jsonl'))[-1]; lines = p.read_text().strip().split('\n'); events = [json.loads(l) for l in lines]; reads = [e for e in events if e.get('event') == 'read']; assert len(reads) >= 1; assert reads[0]['path'] == 'src/app.py'; assert reads[0]['tokens'] > 0; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - Appends read events with schema: `{"event": "read", "ts": "<ISO>", "path": "<normalized>", "tokens": <int>}`
    - Appends write events with schema: `{"event": "write", "ts": "<ISO>", "path": "<normalized>", "tokens": <int>}`
    - Token estimates are non-zero for non-empty content
    - Excluded paths are silently skipped
    - Exits 0 on any error
    - Exits 0 on empty or malformed stdin
  </acceptance_criteria>
  <done>Post-tool hook appends read/write events to session JSONL with timestamps and token estimates.</done>
</task>

<task type="auto">
  <name>Task 5: Register hooks in settings.json</name>
  <files>C:/Users/senki/.claude/settings.json</files>
  <read_first>
    - C:/Users/senki/.claude/settings.json
    - C:/Users/senki/.claude/hooks/token-opt/session-init.py
    - C:/Users/senki/.claude/hooks/token-opt/pre-read.py
    - C:/Users/senki/.claude/hooks/token-opt/post-tool.py
  </read_first>
  <action>
    Edit `~/.claude/settings.json` to register all three new hooks. CRITICAL: preserve ALL existing hooks — append to existing arrays, do not replace them.

    **SessionStart** — append to `hooks.SessionStart[0].hooks` array (after existing gsd-check-update, pattern-nudge, cleanup-stale-artifacts):
    ```json
    {
      "type": "command",
      "command": "python \"C:/Users/senki/.claude/hooks/token-opt/session-init.py\"",
      "timeout": 5
    }
    ```

    **PreToolUse** — add a NEW entry to the `hooks.PreToolUse` array (do NOT modify existing Bash or Write|Edit or wildcard entries):
    ```json
    {
      "matcher": "Read",
      "hooks": [
        {
          "type": "command",
          "command": "python \"C:/Users/senki/.claude/hooks/token-opt/pre-read.py\"",
          "timeout": 5
        }
      ]
    }
    ```

    **PostToolUse** — add a NEW entry to the `hooks.PostToolUse` array (do NOT modify existing gsd-context-monitor or CLv2 observe entries):
    ```json
    {
      "matcher": "Read|Write|Edit|MultiEdit",
      "hooks": [
        {
          "type": "command",
          "command": "python \"C:/Users/senki/.claude/hooks/token-opt/post-tool.py\"",
          "timeout": 5,
          "async": true
        }
      ]
    }
    ```

    Design notes:
    - `post-tool.py` uses `async: true` because it only appends to JSONL (no Claude-visible output needed)
    - `pre-read.py` is synchronous because its stderr warnings must appear before Claude processes the read
    - `session-init.py` has 5s timeout as a safety bound
  </action>
  <verify>
    <automated>python -c "
import json
d = json.load(open('C:/Users/senki/.claude/settings.json'))
hooks = d['hooks']
# New hooks exist
assert any('token-opt/session-init' in str(h) for h in hooks.get('SessionStart', [])), 'session-init missing'
assert any('token-opt/pre-read' in str(h) for h in hooks.get('PreToolUse', [])), 'pre-read missing'
assert any('token-opt/post-tool' in str(h) for h in hooks.get('PostToolUse', [])), 'post-tool missing'
# Existing hooks preserved
assert any('gsd-check-update' in str(h) for h in hooks.get('SessionStart', [])), 'gsd-check-update gone'
assert any('block-no-verify' in str(h) for h in hooks.get('PreToolUse', [])), 'block-no-verify gone'
assert any('gsd-context-monitor' in str(h) for h in hooks.get('PostToolUse', [])), 'gsd-context-monitor gone'
assert any('observe.sh' in str(h) for h in hooks.get('PostToolUse', [])), 'CLv2 observe gone'
print('All hooks registered, existing hooks preserved')
"</automated>
  </verify>
  <acceptance_criteria>
    - settings.json is valid JSON after edit
    - All 3 new hooks are registered with correct matchers
    - All pre-existing hooks preserved: gsd-check-update, pattern-nudge, cleanup-stale-artifacts (SessionStart); block-no-verify, gsd-prompt-guard, CLv2 observe (PreToolUse); gsd-context-monitor, CLv2 observe (PostToolUse); desktop-notify (Stop); session-pattern-collector (SessionEnd); pre-compact (PreCompact)
    - pre-read.py is synchronous (no async flag)
    - post-tool.py has async: true
    - session-init.py has timeout: 5
  </acceptance_criteria>
  <done>All 3 hook registrations added to settings.json. All existing hooks preserved. JSON valid.</done>
</task>

</tasks>

<verification>
1. `python -c "import sys; sys.path.insert(0, 'C:/Users/senki/.claude/hooks/token-opt'); import shared; print('shared imports OK')"` -- shared module imports
2. `echo '{"session_id":"final-verify"}' | python "C:/Users/senki/.claude/hooks/token-opt/session-init.py"` -- creates session file
3. `echo '{"tool_name":"Read","tool_input":{"file_path":"test.py"},"tool_output":{"content":"x=1"}}' | python "C:/Users/senki/.claude/hooks/token-opt/post-tool.py"` -- appends read event
4. `echo '{"tool_name":"Read","tool_input":{"file_path":"test.py"}}' | python "C:/Users/senki/.claude/hooks/token-opt/pre-read.py" 2>&1` -- shows SUPERSEDED warning
5. `echo '{"tool_name":"Write","tool_input":{"file_path":"test.py","content":"y=2"}}' | python "C:/Users/senki/.claude/hooks/token-opt/post-tool.py"` -- appends write event
6. `echo '{"tool_name":"Read","tool_input":{"file_path":"test.py"}}' | python "C:/Users/senki/.claude/hooks/token-opt/pre-read.py" 2>&1` -- shows STALE warning
7. `python -c "import json; json.load(open('C:/Users/senki/.claude/settings.json')); print('settings.json valid')"` -- JSON valid
8. Confirm existing CLv2 observe, gsd, block-no-verify, desktop-notify hooks all still present in settings.json
</verification>

<success_criteria>
- All 4 hook scripts execute without error on well-formed and malformed input
- Session JSONL tracks reads and writes with timestamps and token estimates
- Pre-read hook correctly classifies FRESH/STALE/SUPERSEDED based on session history
- No race conditions — append-only JSONL, no read-modify-write
- Zero impact on existing hooks — all pre-existing hooks preserved in settings.json
</success_criteria>

<output>
After completion, create `.planning/phases/token-optimization/tok-01-SUMMARY.md`
</output>
