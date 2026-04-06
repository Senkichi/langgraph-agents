"""Chunk A: Fix All Broken, Wrong, and Weak Tests.

Fixes 2 zero-signal, 11 HIGH-severity broken/misleading, and 14 MEDIUM-severity
tautological/weak assertions across the test suite. Modifications only — no
deletions, no new files.
"""

from langgraph_agents.graphs.plan_build_review import plan_build_review_app

WORKSPACE = r"C:\Users\senki\repos\job-cannon"

TASK = """\
Fix all broken, wrong, and weak tests across the job-cannon test suite.
These are modifications to existing tests only — no deletions, no new files.

Context:
- job-cannon is a personal job search Flask app (Python 3.13, Flask 3.1, SQLite)
- Use `uv run pytest tests/ -v` to verify all changes
- config.yaml must ONLY be modified with surgical Edit tool, NEVER full Write
- Tests use pytest; `uv run pytest` always (never bare pytest)
"""

PLAN = '''\
## Chunk A: Fix All Broken, Wrong, and Weak Tests

**Scope**: Every test that exists but provides wrong/zero/weak signal.
**Files touched** (18): `test_notifier.py`, `test_agentic_enricher.py`, `test_data_enricher.py`, `test_views.py`, `test_eval_provider.py`, `test_model_provider.py`, `test_scoring_runner.py`, `test_detections_blueprint.py`, `test_costs.py`, `test_backfill_enrichment.py`, `test_resume_feedback.py`, `test_rejection_analyzer.py`, `test_parsers.py`, `test_profile.py`, `test_resume_validator.py`, `test_pipeline.py`, `test_description_reformatter.py`, `test_expiry_checker.py`
**Verification**: `uv run pytest tests/ -v`

### Task

Fix 2 zero-signal tests (always pass), 11 HIGH-severity broken/misleading tests, and 14 MEDIUM-severity tautological or weak assertions across the test suite. All changes are modifications to existing tests — no deletions, no new files.

### Implementation Plan

Each fix below is tagged with its severity and the exact location. The coder should read each test, understand what it claims to verify, then fix the assertion to actually verify that claim.

---

### CRITICAL — Zero-Signal Tests (always pass)

#### A1. `tests/test_notifier.py:39` — `test_does_not_block_caller`

**Problem**: Patches `send_notification` itself (`patch("job_finder.web.notifier.send_notification")`), then calls the mock. Measures MagicMock return time. Proves nothing about real non-blocking behavior.

**Fix**: Patch `threading.Thread` instead (not the function under test). Call the real `send_notification`, measure wall-clock time, verify thread was started but not joined:

```python
def test_does_not_block_caller(self):
    """send_notification returns immediately without waiting for thread."""
    import time
    from job_finder.web.notifier import send_notification

    with patch("threading.Thread") as mock_thread:
        t_instance = MagicMock()
        mock_thread.return_value = t_instance
        start = time.time()
        send_notification("Title", "Body")
        elapsed = time.time() - start
        assert elapsed < 1.0, f"send_notification blocked for {elapsed:.2f}s"
        t_instance.start.assert_called_once()
```

#### A2. `tests/test_agentic_enricher.py:560` — `test_company_bypass_for_long_pages_with_short_names`

**Problem**: Calls `enrich_single_job()`, stores result, then function body ends with comments but zero `assert` statements.

**Fix**: Read `job_finder/web/agentic_enricher.py` to determine what `enrich_single_job` returns for a 2-char company name ("Zo") with 0 meaningful tokens. The comments at lines 584-586 say "The job should be skipped since no meaningful tokens exist." Add assertion matching the actual skip behavior — either `assert result is None` or `assert result == ""` or whatever the skip return value is. If the function actually proceeds (bypass means "skip the check, not skip the job"), assert the result contains enriched text.

---

### HIGH — Broken or Misleading Tests

#### A3. `tests/test_notifier.py:88` — `test_no_url_omits_on_click`

**Problem**: Creates `fake_toast` and `captured_kwargs` but never executes the thread target. `captured_kwargs` stays empty. Only asserts `daemon=True` (already tested elsewhere).

**Fix**: Follow the pattern from `test_passes_url_as_on_click` (line 61-86 in same file) — capture the thread target, execute it with `win11toast.toast` mocked, assert `on_click` is NOT in kwargs:

```python
def test_no_url_omits_on_click(self):
    """send_notification without url does not pass on_click to toast."""
    import sys
    from job_finder.web.notifier import send_notification

    with patch("threading.Thread") as mock_thread:
        t_instance = MagicMock()
        mock_thread.return_value = t_instance
        send_notification("Title", "Body")  # no url
        target_fn = mock_thread.call_args.kwargs["target"]

    mock_toast = MagicMock()
    fake_win11toast = MagicMock()
    fake_win11toast.toast = mock_toast
    with patch.dict(sys.modules, {"win11toast": fake_win11toast}):
        target_fn()

    mock_toast.assert_called_once()
    _, toast_kwargs = mock_toast.call_args
    assert "on_click" not in toast_kwargs, "on_click must not be passed when url is None"
```

#### A4. `tests/test_notifier.py:145` — `test_no_exception_on_toast_error`

**Problem**: Uses `builtins.__import__` mock raising `RuntimeError`, but real failure is `ImportError` from `from win11toast import toast`. The `__import__` approach is unreliable for `from X import Y`.

**Fix**: Use `sys.modules` patching to inject a mock module whose `toast` raises:

```python
def test_no_exception_on_toast_error(self):
    """send_notification silently swallows any exception from toast."""
    import sys
    from job_finder.web.notifier import send_notification

    with patch("threading.Thread") as mock_thread:
        captured_target = []
        def capture_thread_call(*args, **kwargs):
            captured_target.append(kwargs.get("target"))
            m = MagicMock()
            return m
        mock_thread.side_effect = capture_thread_call
        send_notification("Title", "Body")

    failing_module = MagicMock()
    failing_module.toast.side_effect = RuntimeError("toast crash!")
    with patch.dict(sys.modules, {"win11toast": failing_module}):
        assert captured_target and captured_target[0]
        try:
            captured_target[0]()
        except Exception as e:
            raise AssertionError(f"Thread target must swallow exceptions, got: {e}")
```

#### A5. `tests/test_views.py:1886` — `test_expand_no_load_trigger`

**Problem**: Fetches route, decodes data, then function ends. No assertion about the absence of `hx-trigger=load`.

**Fix**: Add the assertion:
```python
data = response.data.decode()
assert 'hx-trigger="load"' not in data, "Regular expand must not include hx-trigger=load"
```

#### A6. `tests/test_views.py:1443` — `test_profile_degrades_gracefully_when_preferences_query_raises`

**Problem**: `FailingConn` delegates non-preferences queries to a new `:memory:` DB with no schema/data. All non-preferences queries also fail, masking the real degradation path.

**Fix**: `FailingConn` must delegate to the real app DB for non-preferences queries. Get the DB path from `app.config["DB_PATH"]`:

```python
class PreferencesFailingConn:
    def __init__(self, real_db_path):
        self._real = sqlite3.connect(real_db_path)
        self._real.row_factory = sqlite3.Row

    def execute(self, sql, *args, **kwargs):
        if "resume_preferences_detected" in sql:
            raise sqlite3.OperationalError("no such table")
        return self._real.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)
```

#### A7. `tests/test_eval_provider.py` ~line 772 — `test_unknown_variant_falls_back_to_default`

**Problem**: "default" variant returns `_BASE_SYSTEM_PROMPT` (plain) but unknown variant falls back to `_SYSTEM_PROMPT` (fewshot). Either a bug locked in by a test, or intentional asymmetry with a misleading name.

**Fix**:
1. Read the `reconstruct_prompt` (or equivalent) in `eval_provider.py` to trace the logic
2. If intentional: rename to `test_unknown_variant_falls_back_to_fewshot_prompt` and add a comment explaining why
3. If a bug: fix the implementation so unknown falls back to `_BASE_SYSTEM_PROMPT` like "default" does, then update the test assertion

#### A8. `tests/test_model_provider.py` lines 87-137 — `resolve_provider_config` full-dict equality

**Problem**: 5+ tests assert `result == {entire dict with every key}`. Adding any new field breaks all simultaneously.

**Fix**: For each test, assert only the fields the test logically cares about (per its name/docstring). Keep ONE test as the comprehensive shape test that validates all keys exist:

```python
# Shape test (one only):
def test_resolve_provider_config_returns_all_expected_keys(self):
    result = resolve_provider_config(...)
    expected_keys = {"provider", "model", "prompt_variant", "fallback", "fallback_chain", "daily_limits", "throttle_delays"}
    assert set(result.keys()) == expected_keys

# Specific tests (assert only what they test):
def test_anthropic_default_config(self):
    result = resolve_provider_config(...)
    assert result["provider"] == "anthropic"
    assert result["model"] == "claude-sonnet-4-6"
```

Also parametrize the 6 nearly-identical `test_call_model_skips_budget_for_*` tests (lines 316-408):
```python
@pytest.mark.parametrize("provider_name", ["gemini", "ollama", "ollm", "openrouter", "sambanova"])
def test_call_model_skips_budget_for_free_provider(self, provider_name, ...):
```

#### A9. `tests/test_data_enricher.py` ~line 817 — `test_sonnet_receives_all_fragments`

**Problem**: `"DDG" in str(fragments)` matches dict key names like `ddg_snippet`, not actual DDG content. Passes even with empty DDG text.

**Fix**: Assert on the actual content value passed to Sonnet, not the stringified dict. Read the test to find the DDG text value from the mock setup, then:
```python
call_args = mock_sonnet.call_args
fragments = ...  # extract fragments argument
assert "expected DDG text content" in str(fragments.values()), "DDG content must reach Sonnet"
```

#### A10. `tests/test_scoring_runner.py:132` — `patch.object(sr, "enrich_job", None)`

**Problem**: Patching to `None` instead of a callable. Code path change would cause confusing `TypeError: 'NoneType' is not callable`.

**Fix**: `patch.object(sr, "enrich_job", MagicMock())`. Same for `enrich_company_info` at line 223.

#### A11. `tests/test_expiry_checker.py:184` — hardcoded `"inconclusive"` string

**Problem**: Uses string literal instead of module constant. If constant value changes, mock returns wrong value.

**Fix**:
```python
from job_finder.web.expiry_checker import INCONCLUSIVE
mock_ats.return_value = INCONCLUSIVE
```

---

### MEDIUM — Tautological or Weak Assertions

For each fix below: read the test, read the template/implementation it tests, replace the loose assertion with a precise one.

#### A12. `tests/test_notifier.py:353` — `test_body_distinguishes_80_and_100_percent`

**Problem**: `"100" in bodies[100.0]` always true since it's the percentage.
**Fix**:
```python
assert "80" in bodies[80.0]
assert "100" in bodies[100.0]
assert bodies[80.0] != bodies[100.0], "80% and 100% bodies must differ"
```

#### A13. `tests/test_views.py:995` — `test_single_source_job_does_not_show_source_count_badge`

**Problem**: `"sources" not in data or "greenhouse" in data` — "greenhouse" always appears.
**Fix**: Remove the tautological second assertion. Keep only: `assert "1 sources" not in data` and add `assert "1 source" not in data`.

#### A14. `tests/test_views.py:1012` — `test_multi_source_job_shows_enrichment_indicator`

**Problem**: `"sources" in data` always true on jobs page, making OR chain vacuous.
**Fix**: Remove the `"sources" in data` fallback:
```python
assert "&#10024;" in data or "sparkle" in data.lower(), "Enrichment sparkle must appear"
```
If neither pattern exists in the actual template, read the template and assert on the real enrichment indicator markup.

#### A15. `tests/test_detections_blueprint.py:267` — `test_dashboard_shows_correct_pending_count`

**Problem**: `"1" in body` matches any "1" in full HTML.
**Fix**: Read the dashboard template to find the pending count element, assert on a specific pattern like `">1</span>"` or `"1 pending"`.

#### A16. `tests/test_costs.py:218` — `test_costs_html_contains_budget_progress_bar`

**Problem**: `"budget" in html.lower()` matches nav/headings.
**Fix**: Read the costs template, find the progress bar element, assert on its specific class or tag (e.g., `"progress"` element, `role="progressbar"`, or a specific CSS class).

#### A17. `tests/test_backfill_enrichment.py:149` — `test_convergence_multiple_passes`

**Problem**: `total_enriched > 5` but expected ~30.
**Fix**: `assert total_enriched >= 25, f"Expected ~30 enrichments (5 jobs * ~6 tiers), got {total_enriched}"`

#### A18. `tests/test_backfill_enrichment.py:213` — `test_cost_estimate_counts_tiers`

**Problem**: `"null" in captured.out.lower()` always true.
**Fix**: Read the implementation's output format and assert the specific tier count text.

#### A19. `tests/test_resume_feedback.py:768` — `test_consolidation_skips_when_budget_exceeded`

**Problem**: OR assertion too permissive.
**Fix**: `assert result.get("consolidated") is False`

#### A20. `tests/test_rejection_analyzer.py:404` — `test_route_flashes_no_unreviewed_message`

**Problem**: `"0" in m` matches any flash containing "0".
**Fix**: `assert any("no unreviewed" in m.lower() for m in messages)`

#### A21. `tests/test_rejection_analyzer.py:429` — `test_route_flashes_success_with_count`

**Problem**: `"1" in m` matches any message containing "1".
**Fix**: `assert any("analyzed" in m.lower() for m in messages)`

#### A22. `tests/test_parsers.py:579` — `test_parses_indeed_alert_jobs`

**Problem**: `len(jobs) >= 2` when fixture has 3 jobs.
**Fix**: `assert len(jobs) == 3`

#### A23. `tests/test_profile.py:548,575` — `test_post_profile_save_redirects_on_success`

**Problem**: Accepts status `200, 302, 204` — any behavior passes.
**Fix**: Read the route to determine the correct status code, assert only that one.

#### A24. `tests/test_resume_validator.py:370` — `test_fix_only_sends_error_violations`

**Problem**: Checks errors present but never verifies warnings absent.
**Fix**: Add `assert "em dash" not in user_content.lower(), "Warnings must NOT be sent to fix pass"`.

#### A25. `tests/test_resume_validator.py:648` — `test_validator_failure_does_not_block_generation`

**Problem**: `if row[1] is not None:` skips the assertion.
**Fix**: Make unconditional: `assert row[1] is not None, "validation_report must be stored"`

#### A26. `tests/test_pipeline.py:128` — `test_pipeline_shows_rejected_collapsed`

**Problem**: `b"hidden" in response.data` matches any "hidden" CSS class.
**Fix**: Read the pipeline template and assert on the specific rejected section element + hidden class together.

#### A27. `tests/test_description_reformatter.py:255,392` — cost recording assertions

**Problem**: Claim to test cost recording but only check `mock_call.call_count`. Never verify DB rows.
**Fix**: If `call_model` is mocked (preventing real cost recording), rename the tests to reflect what they actually test (e.g., `test_reformat_calls_model_per_job`) and update the docstrings. If cost recording is NOT mocked, add a DB assertion: `conn.execute("SELECT COUNT(*) FROM scoring_costs").fetchone()[0] >= 1`.
'''


def main() -> None:
    print(f"Task prompt: {len(TASK)} chars")
    print(f"Plan: {len(PLAN)} chars")
    print(f"Workspace: {WORKSPACE}")
    print("Starting Chunk A: Fix All Broken, Wrong, and Weak Tests...\n")

    result = plan_build_review_app.invoke({
        "task": TASK,
        "current_plan": PLAN,
        "current_code": "",
        "workspace_path": WORKSPACE,
        "e2e_verdict": "",
        "e2e_report": "",
        "e2e_cycle": 0,
    })

    print("\n=== CHUNK A COMPLETE ===")
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
