# tok-01 Summary — Read Lifecycle Hooks

**Status:** COMPLETE  
**Date:** 2026-04-04

## What was built

4 Python files in `~/.claude/hooks/token-opt/` + hook registrations in `settings.json`.

| File | Role |
|------|------|
| `shared.py` | 10-function utility module: path normalization, token estimation, JSONL I/O, session management |
| `session-init.py` | SessionStart hook — creates per-session JSONL, rotates sessions >24h old |
| `pre-read.py` | PreToolUse(Read) hook — classifies FRESH/STALE/SUPERSEDED, warns on stderr |
| `post-tool.py` | PostToolUse(Read|Write|Edit|MultiEdit) hook — appends events to session JSONL |

## Lifecycle verified

1. `session-init.py` creates `~/.claude/.sessions/<id>.jsonl` with `session_start` event
2. `post-tool.py` appends `{"event":"read","path":...,"tokens":...,"ts":...}` on file reads
3. `pre-read.py` stays silent (FRESH) on first read
4. Re-read of same path → SUPERSEDED warning on stderr
5. `post-tool.py` appends `{"event":"write",...}` on edits
6. Re-read after write → STALE warning on stderr

## Design decisions

- **Append-only JSONL** — no read-modify-write; safe under parallel PostToolUse calls
- **post-tool.py async: true** — logging never delays Claude responses
- **pre-read.py synchronous** — stderr warnings must appear before Claude processes the read
- **All hooks exit 0 on any error** — never block Claude Code
- **Excluded paths**: `.claude/`, `.wolf/`, `.git/` prefixes + secret file patterns (`.env*`, `*.key`, etc.)

## Files modified

- `~/.claude/hooks/token-opt/shared.py` (created)
- `~/.claude/hooks/token-opt/session-init.py` (created)
- `~/.claude/hooks/token-opt/pre-read.py` (created)
- `~/.claude/hooks/token-opt/post-tool.py` (created)
- `~/.claude/settings.json` (3 hook registrations added, all existing hooks preserved)
