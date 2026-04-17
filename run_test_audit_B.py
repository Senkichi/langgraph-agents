"""Chunk B: Delete Duplicates & Structural Cleanup.

Remove ~180 duplicate tests, fix stale test names, remove dead code, and fix
structural test infrastructure issues. All changes are deletions, renames, or
mechanical restructuring — no behavioral changes.
"""

from langgraph_agents.graph_runner import run_graph
from langgraph_agents.graphs.plan_build_review import plan_build_review_app

WORKSPACE = r"C:\Users\senki\repos\job-cannon"

TASK = """\
Remove duplicate tests, fix stale names, remove dead code, and fix structural
test infrastructure issues in the job-cannon test suite. These are deletions,
renames, and mechanical restructuring only — no behavioral changes.

Context:
- job-cannon is a personal job search Flask app (Python 3.13, Flask 3.1, SQLite)
- Use `uv run pytest tests/ -v` to verify all changes
- Use `uv run pytest` always (never bare pytest)
- After deletions, run the dedicated test files to confirm they still pass
"""

PLAN = """\
## Chunk B: Delete Duplicates & Structural Cleanup

**Scope**: Remove redundant tests, fix stale names, remove dead code, fix infrastructure issues.
**Files touched** (10): `test_resume.py`, `test_data_enricher.py`, `test_batch_scoring.py`, `test_resume_style_guide.py`, `test_migration.py`, `test_scheduler.py`, `test_logging.py`, `test_dedup_normalizer.py`, `test_ingestion.py`, `test_parsers.py`
**Verification**: `uv run pytest tests/ -v`

### Task

Remove ~180 duplicate tests, fix stale test names, remove dead code, and fix structural test infrastructure issues. All changes are deletions, renames, or mechanical restructuring — no behavioral changes.

---

### Delete Duplicate Tests

#### B1. Remove 4 duplicate classes from `tests/test_resume.py`

These classes are fully duplicated in dedicated files that have MORE thorough coverage:

| Class in test_resume.py | Duplicate of | Lines (approx) |
|---|---|---|
| `TestDocxFormatter` | `test_docx_formatter.py` | ~21-115 |
| `TestDriveUpload` | `test_drive_uploader.py` | ~117-217 |
| `TestDriveServiceScopeCheck` | `test_drive_uploader.py` | ~219-371 |
| `TestDriveStatus` | `test_drive_status.py` | ~379-543 |

**Procedure**: Read `test_resume.py`, identify exact class boundaries, delete the 4 classes and any imports only used by them. Run `uv run pytest tests/test_resume.py tests/test_docx_formatter.py tests/test_drive_uploader.py tests/test_drive_status.py -v` to confirm the dedicated files still pass.

#### B2. Remove 2 duplicate classes from `tests/test_data_enricher.py`

| Class in test_data_enricher.py | Duplicate of |
|---|---|
| `TestSearchSerpapi` (~lines 165-241) | `test_enrichment_tiers.py` |
| `TestEnrichCompanyInfo` (~lines 392-449) | `test_company_enricher.py` |

#### B3. Remove dead meta-test from `tests/test_batch_scoring.py`

Delete `TestDeadCodeRemoved.test_update_session_counter_removed` (~line 273). This asserts that a removed function doesn't exist — a migration guard that served its purpose and is now a permanent no-op.

#### B4. Remove redundant test from `tests/test_resume_style_guide.py`

Delete `test_load_style_guide_returns_dict` (~line 28). Fully redundant with `test_save_load_roundtrip` in the same file.

---

### Fix Stale Names & Misplaced Tests

#### B5. Rename stale migration test names in `tests/test_migration.py`

- `test_migration_count_is_thirteen` (line 405) → `test_migration_count_is_24`. Update docstring and assertion message.
- `test_migrations_count_is_19` (line 1124) → `test_migration_count_matches_current`. Update docstring.

#### B6. Move misplaced Migration 12 tests in `tests/test_migration.py`

`TestMigration14` (line 518) contains 3 tests that belong to Migration 12:
- `test_migration12_adds_retry_after_to_companies`
- `test_migration12_adds_miss_reason_to_companies`
- `test_migration12_retry_count_defaults_to_zero`

Move them to `TestMigration12` class (create it if needed, using the same `migrated_db_class` fixture pattern).

---

### Remove Dead Code & Fix Infrastructure

#### B7. Remove dead `_make_app` helper from `tests/test_scheduler.py` (line 23)

Defined but never called by any test. Delete the function.

#### B8. Fix `add_job.call_args` in `tests/test_scheduler.py` (line 211)

**Problem**: Gets the LAST `add_job` call, which may not be the ingestion job.
**Fix**: Use `call_args_list` and find the ingestion call specifically:
```python
ingestion_call = next(
    c for c in mock_sched.add_job.call_args_list
    if "run_ingestion" in str(c)
)
assert ingestion_call.kwargs.get("replace_existing") is True
```

#### B9. Replace `os.chdir()` in `tests/test_logging.py` (lines 25, 44)

**Problem**: `os.chdir()` changes process-wide CWD. If test fails before `finally`, all subsequent tests run in wrong directory.

**Fix**: Convert from `unittest.TestCase` to plain pytest class and use `monkeypatch.chdir(tmp_path)`:
```python
class TestFileLogging:
    def test_setup_file_logging_attaches_handler(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # ... rest of test, no try/finally needed
```

Also clean up the root logger handler mutations to use `monkeypatch` or `addCleanup`.

#### B10. Fix FK assertion in `tests/test_dedup_normalizer.py` (line 402)

**Problem**: Asserts `events[0]["job_id"] != "old-key-2"` but never verifies the correct new value.
**Fix**: Add positive assertion. Read the test setup to find what the canonical key should be, then:
```python
assert events[0]["job_id"] == expected_canonical_key
```

#### B11. Fix unused fixtures in `tests/test_ingestion.py` (lines 458, 504)

**Problem**: Two tests receive `migrated_db_path` fixture but create own temp DB via `__import__("tempfile")`.
**Fix**: Use the `migrated_db_path` fixture directly, remove the `__import__("tempfile")` / `__import__("os")` calls.

#### B12. Fix conditional assertion in `tests/test_ingestion.py` (line 430)

**Problem**: `if result:` silently skips assertions when parser returns empty list.
**Fix**: `assert len(result) >= 1, "Parser must extract at least one job"`

#### B13. Convert silent-skip tests in `tests/test_parsers.py` (~lines 222, 1135)

**Problem**: `if os.path.exists(email_path):` silently passes without data files.
**Fix**: Convert to `pytest.mark.skipif` so skips are visible in test output:
```python
@pytest.mark.skipif(not os.path.exists(ARCHIVE_PATH), reason="Archived email fixture not present")
def test_real_archived_email(self):
```
"""


def main() -> None:
    print(f"Task prompt: {len(TASK)} chars")
    print(f"Plan: {len(PLAN)} chars")
    print(f"Workspace: {WORKSPACE}")
    print("Starting Chunk B: Delete Duplicates & Structural Cleanup...\n")

    result = run_graph(
        plan_build_review_app,
        {
            "task": TASK,
            "current_plan": PLAN,
            "current_code": "",
            "workspace_path": WORKSPACE,
            "e2e_verdict": "",
            "e2e_report": "",
            "e2e_cycle": 0,
        },
        graph_name="test_audit_b",
    )

    print("\n=== CHUNK B COMPLETE ===")
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
