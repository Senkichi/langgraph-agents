"""Phase 3: DataForSEO early submit + overlapped poll.

Priority 3 from SYNC_EXECUTION_AUDIT.md.

Expected impact:
  - When DataForSEO is active: sync time reduced from ~450s to ~290-330s
  - DataForSEO's 60-120s processing time now overlaps with Gmail's 60-80s fetch time
"""

from langgraph_agents.graph_runner import run_graph
from langgraph_agents.graphs.plan_build_review import plan_build_review_app

WORKSPACE = r"C:\Users\senki\repos\job-cannon"

TASK_SUMMARY = """\
Refactor DataForSEO source in job-cannon to submit tasks at ingestion start,
poll for results after Gmail and Thordata finish — overlapping DataForSEO's 60-120s processing
with Gmail's 60-80s fetch. Constraints: uv run pytest only, backward-compat fetch_jobs() preserved.
"""

TASK = """\
Refactor the DataForSEO source in job-cannon to submit tasks at the START of ingestion,
then poll for results AFTER other sources (Gmail, Thordata) have finished fetching.
This overlaps DataForSEO's 60-120s processing time with Gmail's 60-80s fetch time.

Context:
- job-cannon is a personal job search Flask app (Python 3.13, SQLite, APScheduler)
- DataForSEO is a Google Jobs SERP API with a task-queue architecture (no live endpoint)
- Current flow: Gmail fetch (~70s) → Thordata fetch (~10s) → DataForSEO submit+poll (~240s)
- Desired flow: DataForSEO submit (non-blocking, ~2s) → Gmail+Thordata (~80s) → DataForSEO poll (~60-120s)
- The poll is synchronous sleep-loop (30s intervals, up to 360s max)
- Current DataForSEO source: job_finder/sources/dataforseo_source.py (352 lines)
- Current pipeline runner: job_finder/web/pipeline_runner.py (624 lines)

Key constraints:
- Use `uv run pytest` for all test commands (never bare pytest)
- Python type hints on all new function signatures
- DataForSEO API uses HTTP Basic Auth with pre-encoded base64 credentials
- The existing `fetch_jobs()` public method must remain unchanged (backward compat for any callers)

--- IMPLEMENTATION PLAN ---

## Priority 3: DataForSEO Early Submit + Overlapped Poll

### Changes in `job_finder/sources/dataforseo_source.py`

The current class has a single `fetch_jobs()` that internally calls:
  1. `_submit_tasks(queries)` → returns list of task_ids
  2. `_collect_results(task_ids)` → polls until ready, returns list[Job]

Split these into public methods:

```python
def submit_tasks(self) -> list[str]:
    \"\"\"Submit search tasks and return task IDs. Non-blocking after HTTP POST.\"\"\"
    # Extract from current _submit_tasks logic
    # Returns [] if source is disabled or no queries configured
    ...

def collect_results(self, task_ids: list[str]) -> list[Job]:
    \"\"\"Poll for completed tasks and fetch results. Blocks until all ready or timeout.\"\"\"
    # Extract from current _collect_results logic
    # Returns [] if task_ids is empty
    ...

def fetch_jobs(self) -> list[Job]:
    \"\"\"Convenience wrapper: submit then collect. Used for backward compat.\"\"\"
    task_ids = self.submit_tasks()
    return self.collect_results(task_ids)
```

Also: reduce initial poll wait from 30s to 45s, reduce retry interval from 30s to 15s.
Add class-level constants:
  POLL_INITIAL_DELAY_SECONDS = 45   # wait before first poll (tasks typically take 60-90s)
  POLL_RETRY_INTERVAL_SECONDS = 15  # wait between subsequent polls

### Changes in `job_finder/web/pipeline_runner.py` — `run_ingestion()`

Restructure the fetch phase from sequential to overlapped:

```python
# Phase 1: Submit DataForSEO tasks (non-blocking ~2s)
dataforseo_task_ids = _submit_dataforseo_tasks(config, summary)

# Phase 2: Fetch other sources (while DataForSEO processes in background)
gmail_jobs = _fetch_gmail(config, runner_conn, summary)
thordata_jobs = _fetch_thordata(config, summary)

# Phase 3: Collect DataForSEO results (tasks likely complete by now)
dataforseo_jobs = _collect_dataforseo_results(config, summary, dataforseo_task_ids)
```

Add two new private functions:
- `_submit_dataforseo_tasks(config, summary) -> list[str]`
  - Creates DataForSEOSource, calls `.submit_tasks()`
  - Returns [] if source disabled or exception
  - Logs: "DataForSEO: submitted {n} tasks"

- `_collect_dataforseo_results(config, summary, task_ids: list[str]) -> list[Job]`
  - Creates DataForSEOSource (same config), calls `.collect_results(task_ids)`
  - Returns [] if task_ids empty
  - Logs timing: f"DataForSEO collect: {elapsed:.1f}s, {n} jobs"

Remove the existing `_fetch_dataforseo()` function (or keep as deprecated alias if tests use it).

### Tests to add in `tests/test_dataforseo_source.py`

1. `test_submit_tasks_returns_task_ids` — mock POST returning task IDs, assert submit_tasks()
   returns the list
2. `test_collect_results_polls_until_ready` — mock tasks_ready returning IDs after 2 polls,
   assert collect_results() returns jobs after correct number of sleep/poll cycles
3. `test_fetch_jobs_combines_submit_and_collect` — assert fetch_jobs() produces same result
   as submit_tasks() then collect_results() in sequence
4. `test_submit_returns_empty_when_disabled` — config with dataforseo disabled,
   assert submit_tasks() returns []

### Verification command
  uv run pytest tests/test_dataforseo_source.py -v --tb=short
"""


def main() -> None:
    print(f"Task prompt: {len(TASK)} chars")
    print(f"Workspace: {WORKSPACE}")
    print("Starting Phase 3: DataForSEO overlapped poll...\n")

    result = run_graph(
      plan_build_review_app,
      {
        "task": TASK_SUMMARY,
        "current_plan": TASK,
        "current_code": "",
        "workspace_path": WORKSPACE,
        "e2e_verdict": "",
        "e2e_report": "",
        "e2e_cycle": 0,
      },
      graph_name="sync_opt_phase3",
    )

    print("\n=== PHASE 3 COMPLETE ===")
    print(f"E2E verdict: {result.get('e2e_verdict', 'N/A')}")
    print(f"E2E cycles: {result.get('e2e_cycle', 0)}")

    if result.get("e2e_report"):
        report = result["e2e_report"]
        print(f"\n=== E2E REPORT ({len(report)} chars) ===")
        if len(report) > 3000:
            print(f"...(showing last 3000 of {len(report)} chars)...")
            report = report[-3000:]
        print(report.encode("utf-8", errors="replace").decode("ascii", errors="replace"))

    if result.get("current_code"):
        diff = result["current_code"]
        print(f"\n=== FINAL DIFF ({len(diff)} chars) ===")
        if len(diff) > 2000:
            print(f"...(truncated, showing last 2000 of {len(diff)} chars)...")
            diff = diff[-2000:]
        print(diff)


if __name__ == "__main__":
    main()
