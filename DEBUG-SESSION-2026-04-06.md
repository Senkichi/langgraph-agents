# Debug Session 2026-04-06 — run_todo_implementation.py

## What we were trying to do
Execute `run_todo_implementation.py` — a LangGraph-based orchestrator that runs 16 implementation chunks against the job-cannon workspace, using a plan-build-review graph per chunk.

## Bugs fixed during this session

### 1. UnicodeEncodeError in print (fixed)
**File:** `run_todo_implementation.py:247`
**Error:** `UnicodeEncodeError: 'charmap' codec can't encode character '\u25b6'`
**Fix:** Replaced `▶` with `>>` in `print_chunk_header`.

### 2. Missing `thread_id` in LangGraph invoke (fixed)
**File:** `run_todo_implementation.py:215`
**Error:** `ValueError: Checkpointer requires one or more of the following 'configurable' keys: thread_id, checkpoint_ns, checkpoint_id`
**Fix:** Added `config={"configurable": {"thread_id": f"chunk-{chunk_id}"}}` to `plan_build_review_app.invoke(...)`.

### 3. Wrong initial state shape for state file reset (fixed)
**Error:** `KeyError: 'run_started'` when resetting state file to `{}`
**Fix:** Correct initial shape is `{"run_started": null, "chunks": {}}`.

### 4. `result.stdout` is `None` in `run_git_diff` (NOT fully fixed)
**File:** `src/langgraph_agents/tools/dev_tools.py:23`
**Error:** `AttributeError: 'NoneType' object has no attribute 'strip'`

**Root cause (suspected):** `subprocess.run(..., text=True)` uses Windows cp1252 by default. Git diff output contains bytes cp1252 can't decode (e.g. 0x90). This causes the `_readerthread` in `subprocess` to crash with `UnicodeDecodeError`, leaving `result.stdout = None`.

**Attempted fix:** Added `encoding="utf-8", errors="replace"` and changed `return result.stdout.strip()` to `return (result.stdout or "").strip()`.

**Status: Still failing.** Chunk 10 ran with the fixed code (confirmed by shifted line numbers in traceback) and still crashed with the same `AttributeError`. The truncated traceback for chunk 10 shows `timeout=30,` at line 23 with the error, which is suspicious — this may indicate the traceback display is misleading due to state file truncation, or there's a different code path producing the None.

**Things to investigate:**
- Is `result` itself None (impossible for `subprocess.run`) or is `result.stdout` None?
- Could the `subprocess.run` call be raising an exception that's somehow suppressed, causing `result` to be unbound?
- Is the `_run` closure capturing a stale `result` variable from an outer scope?
- Could LangGraph's threading/retry mechanism be interfering with subprocess?
- Add explicit logging: `print(f"result={result!r}, stdout={result.stdout!r}")` before the return.
- Try `subprocess.run(..., capture_output=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)` as an alternative.
- Try running `git diff HEAD` manually in the workspace to confirm git works there.

## Operational issues

### Ghost process problem
When a background task reports "failed", the underlying Python subprocess may still be running. In this session, `b3iuim3zi` (run 3) was reported failed but kept running for ~2.5 hours, writing to the shared `run_todo_state.json` and clobbering state from the new run (`bkrxmuinn`). Always verify with `tasklist | grep python` or `Get-Process python` before starting a new run.

### Two competing processes
Both `b3iuim3zi` and `bkrxmuinn` were running simultaneously and writing to the same `run_todo_state.json`. The old process always "won" because it progressed further and wrote the full state on each chunk completion. Killed via `Get-Process python | Stop-Process -Force`.

## State of the codebase at end of session
- `run_todo_implementation.py`: fixes 1, 2 applied; correct state reset shape documented
- `src/langgraph_agents/tools/dev_tools.py`: encoding fix applied but insufficient — still needs investigation
- `run_todo_state.json`: should be reset to `{"run_started": null, "chunks": {}}` before next run

## Chunks completed
None — all 10 independent chunks errored (4 before fix, rest after fix but same error).
