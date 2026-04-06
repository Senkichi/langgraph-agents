# Research: Token Optimization for Claude Code Sessions

**Researched:** 2026-04-04
**Domain:** Claude Code context window efficiency — read deduplication, file indexing, observation enrichment
**Confidence:** HIGH (architecture validated against 3 production tools + 12 alternatives)

---

## Summary

A comprehensive survey of the Claude Code token optimization ecosystem (OpenWolf, RTK, Headroom,
and 12 smaller tools) identified two high-value features missing from the existing
continuous-learning-v2 (CLv2) infrastructure:

1. **Read Lifecycle Management** — event-driven classification of file reads as FRESH, STALE
   (file edited after read), or SUPERSEDED (file re-read later). Headroom's data across 66K
   tool calls found 79% of Read bytes are stale or superseded. OpenWolf reports 71% of repeated
   reads caught and blocked.

2. **File Anatomy (Project Index)** — a token-estimated file map with one-line descriptions that
   Claude can consult instead of opening files. Reduces unnecessary reads and gives Claude
   structural awareness of the codebase.

Additionally, the CLv2 observation schema lacks **token estimation** — a trivial extension that
enables future waste-detection analytics.

## Key Design Decisions from Field Survey

### Read Dedup: Lifecycle Manager > Simple Dedup

Simple dedup (OpenWolf approach) only catches re-reads. Headroom's Read Lifecycle Manager also
catches **stale reads** — where Claude read a file, then edited it, but the old content remains
in context as outdated information. The stale case is higher value because it actively misleads
Claude, not just wastes tokens.

**Decision:** Build a 3-state lifecycle (FRESH/STALE/SUPERSEDED) rather than boolean dedup.

### Concurrency: Append-Only > Read-Modify-Write

OpenWolf's P1 race condition comes from read-modify-write cycles on `_session.json` under
parallel tool calls. Claude Code can fire multiple tool calls in parallel, creating last-writer-wins
data loss.

**Decision:** Use append-only JSONL for session state. Each hook appends one line; the pre-read
hook scans backward for prior entries. Append is atomic under PIPE_BUF on all platforms.

### Anatomy: Scanner + Incremental Hook Updates

The scanner builds the initial index; the PostToolUse hook for Write/Edit keeps it current.
This avoids staleness without periodic rescans.

**Decision:** Python scanner CLI (matches user's stack) + incremental update path in a new
PostToolUse hook.

### Secret Safety

OpenWolf's `extractDescription` reads 12KB of every file and can leak secrets embedded in
docstrings/comments into the anatomy file. Their `.env` guard is insufficient.

**Decision:** Broad deny-list for secret-bearing files (`.env*`, `*.pem`, `*.key`, `credentials.*`,
`.npmrc`, `*secret*`, `*.pfx`, `*.p12`) applied before any content extraction.

### Integration Point: CLv2 Hooks, Not a Parallel System

The existing `observe.sh` fires on every PreToolUse and PostToolUse with `matcher: "*"`. New
hooks should be **separate hook scripts** (not modifications to observe.sh) to maintain single
responsibility, but they share the session identification infrastructure.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Claude Code Hook Events                                  │
├──────────────┬──────────────┬────────────────────────────┤
│ PreToolUse   │ PostToolUse  │ SessionStart               │
│ matcher:Read │ matcher:Read │                            │
│              │ Write|Edit   │                            │
├──────────────┼──────────────┼────────────────────────────┤
│ pre-read.py  │ post-tool.py │ session-init.py            │
│ - scan JSONL │ - Read: log  │ - create session JSONL     │
│ - emit warn  │   tokens     │ - rotate old sessions      │
│   on STALE/  │ - Write/Edit │                            │
│   SUPERSEDED │   : update   │                            │
│              │   anatomy    │                            │
└──────┬───────┴──────┬───────┴────────────┬───────────────┘
       │              │                    │
       ▼              ▼                    ▼
  .session.jsonl  anatomy.md         (session file)
  (append-only)   (atomic write)
```

New files:
- `~/.claude/hooks/token-opt/pre-read.py` — PreToolUse hook for Read
- `~/.claude/hooks/token-opt/post-tool.py` — PostToolUse hook for Read|Write|Edit
- `~/.claude/hooks/token-opt/session-init.py` — SessionStart hook
- `~/.claude/hooks/token-opt/scanner.py` — CLI for full anatomy scan
- `~/.claude/hooks/token-opt/shared.py` — shared utilities (token estimation, paths, anatomy I/O)

## References

- OpenWolf: https://github.com/cytostack/openwolf (302 stars, concept validated, P0 security issues)
- RTK: https://github.com/rtk-ai/rtk (17.7K stars, installed separately for Bash output compression)
- Headroom: https://github.com/chopratejas/headroom (1.2K stars, Read Lifecycle Manager concept source)
- CLv2: ~/.claude/skills/continuous-learning-v2/ (existing observation infrastructure)
