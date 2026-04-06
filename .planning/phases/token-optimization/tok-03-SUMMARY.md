# tok-03 Summary — CLv2 Observation Enrichment

## Changes Implemented

### Task 1 — `observe.sh` enrichment (3 edits)

**Edit 1A-extract** (Block 1, parsing stage):
Added `file_path` extraction from raw `tool_input` dict **before** the input is JSON-stringified/truncated. Covers tools: `Read`, `Write`, `Edit`, `MultiEdit`. Backslashes normalized to forward slashes for cross-platform consistency.

**Edit 1A-print** (Block 1, parsing stage):
Added `"file_path": file_path` to the Block 1 PARSED JSON output, making it available to the downstream Block 2.

**Edit 1B** (Block 2, writing stage):
Two new observation fields always emitted (null when not applicable):

| Field | Type | When non-null |
|-------|------|---------------|
| `file_path` | `str \| null` | Read/Write/Edit/MultiEdit events |
| `estimated_tokens` | `int \| null` | Read `tool_complete` events with non-empty output |

Token estimation formula (applied to 5000-char-truncated output):
```
cpt = 3.5  # code files (.py .rs .go .js .ts .c .cpp .java .rb .sh .jsx .tsx)
cpt = 4.0  # prose files (.md .txt .rst .adoc)
cpt = 3.75 # everything else
estimated_tokens = max(1, int(len(output) / cpt))
```

### Task 2 — `post-tool.py` anatomy freshness reminder

Inserted between anatomy upsert (L61) and session-path assignment (L64). Fires once per session on the first Write/Edit/MultiEdit call:

- **Missing anatomy.md** → prints warning to stderr suggesting `scanner.py`
- **Stale anatomy.md (>72h)** → prints age in hours to stderr

Detection of "first write": counts `"event":"write"` occurrences in the session JSONL file. Zero count means the current event hasn't been appended yet (happens at L92), so this is the session's first write operation.

## Design Notes

### Token formula duplication

The `cpt` constants are duplicated between `observe.sh` inline Python and `shared.py`. This is **intentional**: `observe.sh` runs as a standalone bash subprocess with no import path to `~/.claude/hooks/token-opt/shared.py`. The alternative (subprocess-calling the shared module) would add latency on every hook invocation. The constants are stable values unlikely to drift, but if they change in `shared.py`, `observe.sh` must be updated in sync.

### Schema change is additive and null-safe

Both `file_path` and `estimated_tokens` are always present in every new observation (null when not applicable). Consumers that read existing JSONL (e.g., `instinct-cli.py analyze`) will find `None` for both fields on observations written before this patch, and concrete values on observations written after — no schema migration needed.

### `estimated_tokens` represents observation-ingested tokens

The estimate is based on the 5000-char truncated output, not the full file. This is intentional: it measures "tokens that entered the CLv2 observation store," which is the relevant signal for context budget analysis.

## Files Modified

- `~/.claude/skills/continuous-learning-v2/hooks/observe.sh`
- `~/.claude/hooks/token-opt/post-tool.py`

## Verification Passed

- `post-tool.py` compiles without syntax errors (`py_compile.compile`)
- All five grep markers confirmed present in modified files
- Edit 1A extraction at correct position (before stringification)
- Edit 1B token formula matches `shared.py` L113 formula exactly
- Edit 2A anatomy check wrapped in isolated `try/except` — cannot affect main session-logging flow
