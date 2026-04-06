"""Chunk C: Add Missing Coverage.

Net-new tests for 4 systematic coverage gaps: malformed AI responses,
safe_json_load type mismatch, budget gate zero boundary, batch error
continuation, and caplog companions for 7 source-inspection-only log tests.
"""

from langgraph_agents.graphs.plan_build_review import plan_build_review_app

WORKSPACE = r"C:\Users\senki\repos\job-cannon"

TASK = """\
Add targeted new tests for systematic coverage gaps in the job-cannon test suite.
These are all net-new tests added to existing test files — no deletions.

Context:
- job-cannon is a personal job search Flask app (Python 3.13, Flask 3.1, SQLite, APScheduler)
- Use `uv run pytest` always (never bare pytest)
- Verification: `uv run pytest tests/test_scoring.py tests/test_db_helpers.py tests/test_ingestion.py tests/test_interview_prep.py tests/test_rejection_analyzer.py tests/test_log_levels.py -v -k "malformed or type_mismatch or batch_error or budget_zero or caplog"`
- Tests use pytest fixtures from conftest.py (app factory, test DB, mock Claude)
- Read conftest.py before writing any new tests to understand available fixtures
"""

PLAN = '''\
## Chunk C: Add Missing Coverage

**Scope**: Net-new tests for systematic coverage gaps identified in the audit.
**Files touched** (6): `test_scoring.py`, `test_db_helpers.py`, `test_ingestion.py`, `test_interview_prep.py`, `test_rejection_analyzer.py`, `test_log_levels.py`
**Verification**: `uv run pytest tests/test_scoring.py tests/test_db_helpers.py tests/test_ingestion.py tests/test_interview_prep.py tests/test_rejection_analyzer.py tests/test_log_levels.py -v -k "malformed or type_mismatch or batch_error or budget_zero or caplog"`

### Task

Add targeted tests for 4 systematic coverage gaps: malformed AI responses, `safe_json_load` type mismatch, budget gate zero boundary, and batch error continuation. Also add runtime (`caplog`) companion tests for 7 source-inspection-only log-level tests.

---

### 1. Malformed AI Response Tests

No test anywhere verifies behavior when AI models return JSON missing expected keys. Add 1-2 tests per critical module.

#### C1. `tests/test_scoring.py` — add to `TestHaikuScorer`

```python
def test_haiku_malformed_response_returns_none(self, ...):
    """Haiku returning JSON without 'score' key does not crash."""
```
- Read `haiku_scorer.py` to find what keys it accesses from the response
- Mock the Claude client to return `{"summary": "good"}` (missing `score`)
- Assert the function returns `None` or a default, not an unhandled `KeyError`

#### C2. `tests/test_scoring.py` — add to Sonnet section

```python
def test_sonnet_malformed_response_returns_none(self, ...):
    """Sonnet returning JSON without expected keys does not crash."""
```
- Same approach: mock response with missing keys, assert graceful handling

#### C3. `tests/test_interview_prep.py`

```python
def test_generate_handles_malformed_opus_response(self, ...):
    """Opus returning unexpected schema does not crash interview prep."""
```
- Mock Opus to return `{"random": "data"}` instead of expected structure
- Assert function returns gracefully

#### C4. `tests/test_rejection_analyzer.py`

```python
def test_analyze_handles_malformed_opus_response(self, ...):
    """Opus returning JSON without 'patterns' key does not crash."""
```

For each test: read the module's response parsing code to identify what keys are accessed, mock to return a response missing those keys, assert graceful handling.

---

### 2. `safe_json_load` Type Mismatch

#### C5. `tests/test_db_helpers.py`

```python
def test_valid_json_scalar_returns_scalar_not_default(self):
    """safe_json_load with valid JSON string literal returns the string, not default.

    Documents that callers passing default=[] could get a string back
    if the stored JSON is a valid scalar.
    """
    result = safe_json_load('"just a string"', default=[])
    assert result == "just a string"
    assert not isinstance(result, list)
```

---

### 3. Budget Gate Zero Boundary

#### C6. `tests/test_scoring.py` — add to `TestCostGate`

Read `cost_gate` implementation first to determine if 0.0 means "zero budget" or "unlimited."

```python
def test_cost_gate_zero_budget_with_zero_spend(self, ...):
    """cost_gate with budget=0.0 and zero spend -- verify boundary behavior."""
    # Insert 0 cost rows, call cost_gate with budget=0.0
    # Assert based on implementation's boundary semantics

def test_cost_gate_zero_budget_with_positive_spend(self, ...):
    """cost_gate with budget=0.0 and actual spend returns False."""
    # Insert a small cost row, call cost_gate with budget=0.0
    # Assert False (over budget)
```

---

### 4. Batch Error Continuation

#### C7. `tests/test_ingestion.py`

```python
def test_run_ingestion_continues_after_single_source_failure(self, ...):
    """If one source raises during ingestion, other sources still run."""
```
- Read `pipeline_runner.run_ingestion` to verify it has try/except per source
- Mock gmail to raise, mock thordata/serpapi to return jobs
- Assert the non-failing sources' results were processed
- If the implementation doesn't have per-source error isolation, this test correctly fails — revealing a real gap

---

### 5. Log-Level Runtime Companions (caplog tests)

7 tests in `tests/test_log_levels.py` use only `inspect.getsource()` + substring matching with no runtime verification. Add a `caplog`-based companion for each, following the pattern already established in that file (see existing caplog tests at lines 72-121, 196-237, 296-335).

#### C8-C14. Tests to add:

| Source-inspection test | Companion to add |
|---|---|
| `test_zero_job_email_routed_to_activity_feed_logs_at_debug` (line 123) | Trigger the zero-job email path with mocks, assert `caplog` has DEBUG record |
| `test_haiku_no_result_logs_at_debug` (line 148) | Mock Haiku to return None, assert DEBUG log |
| `test_cost_gate_false_logs_at_info` (line 247) | Set up exceeded budget, assert INFO log |
| `test_budget_exceeded_error_logs_at_info` (line 273) | Raise BudgetExceededError, assert INFO log |
| `test_blocked_wipe_logs_at_debug` (line 416) | Trigger blocked wipe path, assert DEBUG log |
| `test_paste_jd_budget_cap_logs_at_info` (line 443) | Trigger paste JD budget cap, assert INFO log |
| `test_rescore_budget_cap_logs_at_info` (line 462) | Trigger rescore budget cap, assert INFO log |

For each:
1. Read the source-inspection test to identify the target code path
2. Read the target module to understand what setup triggers that log call
3. Write a companion test that exercises the real code path with appropriate mocks
4. Use `caplog.at_level(logging.DEBUG)` and assert on both message content and log level

Note: Some may require significant fixture setup (Flask app, mock DB). Use existing fixtures from `conftest.py`. If a particular test requires excessive setup for the value it provides, document why in a comment and keep only the source-inspection version -- but this should be the exception, not the rule.
'''


def main() -> None:
    print(f"Task prompt: {len(TASK)} chars")
    print(f"Plan: {len(PLAN)} chars")
    print(f"Workspace: {WORKSPACE}")
    print("Starting Chunk C: Add Missing Coverage...\n")

    result = plan_build_review_app.invoke({
        "task": TASK,
        "current_plan": PLAN,
        "current_code": "",
        "workspace_path": WORKSPACE,
        "e2e_verdict": "",
        "e2e_report": "",
        "e2e_cycle": 0,
    })

    print("\n=== CHUNK C COMPLETE ===")
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
