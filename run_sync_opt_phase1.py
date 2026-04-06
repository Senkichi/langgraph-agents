"""Phase 1: Gmail message-level dedup + parse failure dedup.

Priorities 1 and 4 from SYNC_EXECUTION_AUDIT.md.

Expected impact:
  - Gmail API calls: ~1,100/sync → ~20-50/sync
  - Sync time: -40-60s
  - runs table growth: ~1,000/day → <20/day
"""

from langgraph_agents.graphs.plan_build_review import plan_build_review_app

WORKSPACE = r"C:\Users\senki\repos\job-cannon"

TASK_SUMMARY = """\
Implement Gmail message-level deduplication and parse failure log dedup in job-cannon.
Eliminates re-fetching and re-parsing ~1,100 already-seen Gmail messages per sync.
Constraints: uv run pytest only, raw SQLite SQL, Python type hints on all new signatures.
"""

TASK = """\
Implement Gmail message-level deduplication and parse failure log dedup in the job-cannon
ingestion pipeline. These are two interrelated fixes that together eliminate the biggest
source of waste: re-fetching and re-parsing 1,100 already-seen Gmail messages every sync.

Context:
- job-cannon is a personal job search Flask app (Python 3.13, SQLite, APScheduler)
- The ingestion pipeline runs 3x/day via APScheduler
- Gmail is the dominant source: ~1,100 emails fetched per sync, but only 11-27 are new
- The same emails are re-fetched, re-decoded, re-parsed on every sync — 3x/day for 7 days
- The `email_parse_log` table already exists with UNIQUE on `message_id` (currently unused for per-message tracking)
- The `runs` table has 7,546 rows, growing ~1,000/day from parse failure spam

Key constraints:
- Use `uv run pytest` for all test commands (never bare pytest)
- config.yaml must ONLY be modified with surgical Edit tool, NEVER full Write
- SQLite raw SQL only (no ORM)
- Python type hints on all new function signatures

--- IMPLEMENTATION PLAN ---

## Priority 1: Gmail Message-Level Dedup

### Goal
Skip re-fetching and re-parsing Gmail messages already processed in a previous sync.

### Changes

#### 1. `job_finder/sources/gmail_source.py` — Add message-level dedup

Current `fetch_jobs()` signature (around line 135):
  def fetch_jobs(self, lookback_days: int = 7) -> list[Job]

New behavior:
- Accept an optional `processed_message_ids: set[str] | None = None` parameter
- After `_search_messages()` collects all message IDs, filter out IDs already in the set
- Log the skip count: `f"Gmail: skipping {skipped} already-processed messages"`
- After parsing each message (success or failure), accumulate message_id in a new return value
- Change return type to `tuple[list[Job], list[str]]` where the second element is the list
  of message_ids that were processed (both successful and failed parses)

#### 2. `job_finder/web/pipeline_runner.py` — `_fetch_gmail()` wire-up

Before calling `source.fetch_jobs()`, query:
  SELECT message_id FROM email_parse_log
  WHERE processed_at >= datetime('now', '-{lookback_days} days')

Pass resulting set as `processed_message_ids` to `GmailSource.fetch_jobs()`.

After `fetch_jobs()` returns, bulk-insert the newly processed message_ids into `email_parse_log`:
  INSERT OR IGNORE INTO email_parse_log (message_id, sender, subject, processed_at, job_count)
  VALUES (?, 'gmail', '', datetime('now'), 0)

This prevents re-processing on the next sync.

Log: `f"Gmail dedup: {len(known_ids)} known, {len(new_ids)} new, {skipped} skipped"`

## Priority 4: Parse Failure Log Dedup

### Goal
Stop creating duplicate `runs` entries for the same failing emails every sync.

### Changes

#### 1. `job_finder/web/pipeline_runner.py` — Stop logging repeated failures

The parse failure path (around line 242-258) currently creates a `runs` row for every email
that parses to zero jobs. Since Priority 1 means those emails are now skipped on subsequent
syncs, this problem is largely eliminated for free.

However, add an explicit guard for the first-time failure case:
- Only insert a parse_failure `runs` row if this message_id is NOT already in `email_parse_log`
- This prevents duplicate failure rows if the same email fails on two consecutive runs before
  the dedup kicks in

#### 2. `job_finder/web/scheduler.py` (or `pipeline_runner.py`) — Add runs table TTL pruning

Add to the orphan_cleanup or _run_enrichment_backfill job:
  conn.execute(\"\"\"
      DELETE FROM runs
      WHERE timestamp < datetime('now', '-30 days')
        AND source LIKE '%parse_failure%'
  \"\"\")
  conn.execute(\"\"\"
      DELETE FROM runs
      WHERE timestamp < datetime('now', '-90 days')
  \"\"\")

### Schema verification

The `email_parse_log` table already exists. Verify it has these columns (check db_migrate.py):
  message_id TEXT UNIQUE
  sender TEXT
  subject TEXT
  processed_at TEXT
  job_count INTEGER

If `processed_at` or `job_count` columns are missing, add a migration in `db_migrate.py`.

### Tests to add in `tests/test_gmail_source.py` (or existing test file)

1. `test_fetch_jobs_skips_known_message_ids` — mock _search_messages returning 3 IDs, pass 2 as
   processed_message_ids, assert only 1 message is fetched via _get_message
2. `test_fetch_jobs_returns_processed_ids` — assert returned tuple[1] contains the message_ids
   that were actually processed
3. `test_fetch_jobs_no_dedup_arg` — backward compat: no processed_message_ids means all fetched

### Verification command
  uv run pytest tests/test_gmail_source.py -v --tb=short
"""


def main() -> None:
    print(f"Task prompt: {len(TASK)} chars")
    print(f"Workspace: {WORKSPACE}")
    print("Starting Phase 1: Gmail dedup + parse failure dedup...\n")

    result = plan_build_review_app.invoke({
        "task": TASK_SUMMARY,
        "current_plan": TASK,
        "current_code": "",
        "workspace_path": WORKSPACE,
        "e2e_verdict": "",
        "e2e_report": "",
        "e2e_cycle": 0,
    })

    print("\n=== PHASE 1 COMPLETE ===")
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
