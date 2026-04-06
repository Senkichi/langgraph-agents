"""Phase 2: Pre-ingestion batch dedup + runs table pruning.

Priorities 2 and 7 from SYNC_EXECUTION_AUDIT.md.

Expected impact:
  - ~1,080 unnecessary scorer/upsert/company-update calls eliminated per sync
  - runs table growth permanently bounded at <10K rows
"""

from langgraph_agents.graphs.plan_build_review import plan_build_review_app

WORKSPACE = r"C:\Users\senki\repos\job-cannon"

TASK_SUMMARY = """\
Implement pre-ingestion batch dedup and runs table pruning in job-cannon's pipeline_runner.py.
Eliminates ~1,080 unnecessary scorer/upsert/company-update calls per sync; bounds runs table at <10K rows.
Constraints: uv run pytest only, raw SQLite SQL, Python type hints on all new signatures.
"""

TASK = """\
Implement pre-ingestion batch dedup and runs table pruning in the job-cannon ingestion
pipeline. These are two independent, low-effort changes to pipeline_runner.py and scheduler.py.

Context:
- job-cannon is a personal job search Flask app (Python 3.13, SQLite, APScheduler)
- The ingestion pipeline combines jobs from Gmail, Thordata, and DataForSEO sources
- After combining all_jobs, ~97-99% are already-known duplicates (same dedup_key in DB)
- Each duplicate still goes through: scorer.score_jobs(), upsert_job(), _upsert_job_company()
- The `runs` table has 7,546 rows with no TTL; growing ~100-1,000/day (mostly parse failures)
- The orphan_cleanup scheduler job exists and is the right place to add TTL pruning

Key constraints:
- Use `uv run pytest` for all test commands (never bare pytest)
- SQLite raw SQL only (no ORM)
- Python type hints on all new function signatures
- Prefer editing existing files over creating new ones

--- IMPLEMENTATION PLAN ---

## Priority 2: Pre-Ingestion Batch Dedup

### Goal
Skip scoring, full upsert merging, and company updates for jobs whose `dedup_key` already
exists and whose source data hasn't changed.

### Changes in `job_finder/web/pipeline_runner.py`

In `run_ingestion()`, AFTER combining all sources into `all_jobs` but BEFORE the per-job loop:

```python
# Batch pre-check: identify already-known dedup_keys
candidate_keys = [job.dedup_key for job in all_jobs]
existing_keys: set[str] = set()
if candidate_keys:
    placeholders = ",".join("?" * len(candidate_keys))
    rows = runner_conn.execute(
        f"SELECT dedup_key FROM jobs WHERE dedup_key IN ({placeholders})",
        candidate_keys,
    ).fetchall()
    existing_keys = {r[0] for r in rows}
```

Then in the per-job loop, use `existing_keys` to route:
- If `job.dedup_key in existing_keys`: call a new lightweight `_touch_existing_job(job, runner_conn, summary)` helper
- Else: call the existing `_score_and_persist()` path

### New `_touch_existing_job()` helper

```python
def _touch_existing_job(job: Job, conn: sqlite3.Connection, summary: dict) -> None:
    \"\"\"Lightweight update for already-known jobs: touch last_seen and merge sources only.\"\"\"
    conn.execute(
        \"\"\"
        UPDATE jobs
        SET last_seen = datetime('now'),
            sources = (
                SELECT json_group_array(DISTINCT value)
                FROM (
                    SELECT value FROM json_each(sources)
                    UNION
                    SELECT value FROM json_each(json_array(?))
                )
            )
        WHERE dedup_key = ?
        \"\"\",
        (job.source, job.dedup_key),
    )
    conn.commit()
    summary["jobs_updated"] = summary.get("jobs_updated", 0) + 1
```

This skips: scorer.score_jobs(), upsert_job() full merge logic, _upsert_job_company().

**Important guard:** If job.salary_min is not None or job.salary_max is not None, route to
full upsert_job() instead of _touch_existing_job() — new salary data must be merged.

### Log addition

After the loop, add to the sync log/summary:
  f"Pre-dedup: {len(existing_keys)} known, {len(all_jobs) - len(existing_keys)} new"

## Priority 7: `runs` Table Pruning

### Goal
Prevent unbounded growth of the `runs` table.

### Changes in `job_finder/web/scheduler.py`

Find the `orphan_cleanup` scheduled job function. Add at the end:

```python
# Prune parse_failure noise (keep 30 days)
conn.execute(\"\"\"
    DELETE FROM runs
    WHERE timestamp < datetime('now', '-30 days')
      AND source LIKE '%parse_failure%'
\"\"\")
# Prune all old runs (keep 90 days)
conn.execute(\"\"\"
    DELETE FROM runs
    WHERE timestamp < datetime('now', '-90 days')
\"\"\")
conn.commit()
```

### Tests to add (in `tests/test_pipeline_runner.py` or relevant test file)

1. `test_batch_dedup_skips_scorer_for_known_jobs` — insert a job into test DB, run ingestion
   with that job in the source list, assert scorer was NOT called for it
2. `test_batch_dedup_calls_scorer_for_new_jobs` — job not in DB, assert scorer IS called
3. `test_touch_existing_job_updates_last_seen` — call _touch_existing_job, assert last_seen
   updated and sources merged

### Verification command
  uv run pytest tests/test_pipeline_runner.py -v --tb=short -k "dedup or touch"
"""


def main() -> None:
    print(f"Task prompt: {len(TASK)} chars")
    print(f"Workspace: {WORKSPACE}")
    print("Starting Phase 2: Batch dedup + runs pruning...\n")

    result = plan_build_review_app.invoke({
        "task": TASK_SUMMARY,
        "current_plan": TASK,
        "current_code": "",
        "workspace_path": WORKSPACE,
        "e2e_verdict": "",
        "e2e_report": "",
        "e2e_cycle": 0,
    })

    print("\n=== PHASE 2 COMPLETE ===")
    print(f"E2E verdict: {result.get('e2e_verdict', 'N/A')}")
    print(f"E2E cycles: {result.get('e2e_cycle', 0)}")

    if result.get("e2e_report"):
        report = result["e2e_report"]
        print(f"\n=== E2E REPORT ({len(report)} chars) ===")
        if len(report) > 3000:
            print(f"...(showing last 3000 of {len(report)} chars)...")
            report = report[-3000:]
        print(report)

    if result.get("current_code"):
        diff = result["current_code"]
        print(f"\n=== FINAL DIFF ({len(diff)} chars) ===")
        if len(diff) > 2000:
            print(f"...(truncated, showing last 2000 of {len(diff)} chars)...")
            diff = diff[-2000:]
        print(diff)


if __name__ == "__main__":
    main()
