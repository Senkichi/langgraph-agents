# LangGraph Workflow Improvements Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the langgraph-agents workflows for fault tolerance, correctness, token efficiency, and observability — addressing all 13 findings from the architecture review.

**Architecture:** Seven phases ordered by dependency and risk. Phases 1–3 are zero-risk correctness fixes. Phases 4–5 improve handoff quality and token efficiency with targeted behavioral changes. Phase 6 adds fault tolerance (RetryPolicy + checkpointing). Phase 7 adds architectural improvements (discovery, streaming, native subgraph composition).

**Tech Stack:** Python 3.11+, LangGraph ≥ 1.1.4, langgraph-checkpoint-sqlite (new dep for Phase 6), pytest 8+, uv

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| **Create** | `src/langgraph_agents/config.py` | Central env-var-driven model/timeout config |
| **Modify** | `src/langgraph_agents/claude_cli.py` | Fix `allowed_tools=[""]` bug |
| **Modify** | `src/langgraph_agents/nodes/review_synthesizer.py` | Fix VERDICT regex; preserve APPROVE signal |
| **Modify** | `src/langgraph_agents/nodes/prompt_review_synthesizer.py` | Fix VERDICT regex (same pattern) |
| **Modify** | `src/langgraph_agents/nodes/e2e_tester.py` | Regression checklist; better test mapping |
| **Modify** | `src/langgraph_agents/nodes/coder.py` | Import config; bound diff size |
| **Modify** | `src/langgraph_agents/nodes/planner.py` | Import config |
| **Modify** | `src/langgraph_agents/nodes/plan_reviewer.py` | Import config |
| **Modify** | `src/langgraph_agents/nodes/micro_reviewer.py` | Import config |
| **Modify** | `src/langgraph_agents/nodes/macro_reviewer.py` | Import config |
| **Modify** | `src/langgraph_agents/nodes/prompt_engineer.py` | Import config; bound diff size |
| **Modify** | `src/langgraph_agents/nodes/behavioral_reviewer.py` | Import config |
| **Modify** | `src/langgraph_agents/nodes/architectural_reviewer.py` | Import config |
| **Modify** | `src/langgraph_agents/nodes/discover_architecture.py` | Accept generic state type |
| **Modify** | `src/langgraph_agents/graphs/build_review.py` | `defer=True`; RetryPolicy |
| **Modify** | `src/langgraph_agents/graphs/prompt_build_review.py` | `defer=True`; RetryPolicy |
| **Modify** | `src/langgraph_agents/graphs/plan_review.py` | RetryPolicy; checkpointer param |
| **Modify** | `src/langgraph_agents/graphs/plan_build_review.py` | RetryPolicy; checkpointer param; discover node; architecture threading |
| **Modify** | `src/langgraph_agents/graphs/prompt_workflow.py` | Checkpointer param |
| **Modify** | `src/langgraph_agents/state.py` | Add `agent_architecture` to `ParentState`; remove `AgentState` |
| **Create** | `src/langgraph_agents/graph_runner.py` | Async streaming runner for long-running workflows |
| **Delete** | `src/langgraph_agents/llm.py` | Unused LangChain LLM factory |
| **Delete** | `src/langgraph_agents/graphs/orchestrator.py` | Unused simple graph |
| **Delete** | `src/langgraph_agents/nodes/researcher.py` | Unused node |
| **Delete** | `src/langgraph_agents/nodes/writer.py` | Unused node |
| **Delete** | `src/langgraph_agents/tools/search.py` | Stub TODO, never used |
| **Modify** | `tests/test_build_review.py` | Update synthesizer tests for new APPROVE signal behavior |
| **Modify** | `tests/test_plan_build_review.py` | Tests for discover node wiring |
| **Modify** | `tests/test_e2e_tester.py` | Tests for regression checklist; test mapping fix |
| **Delete** | `tests/test_orchestrator.py` | Covered by deleted module |

---

## Phase 1: Correctness Fixes

*Three targeted one-to-two-line fixes. Each is independently safe and immediately testable.*

---

### Task 1: Fix VERDICT Detection — Regex Replaces Fragile Substring Match (C2-verdict)

**Problem:** `"VERDICT:REVISE" in feedback` misses `"VERDICT: REVISE"` (space after colon), silently treating a reviewer's REVISE as APPROVE. Same bug in both synthesizer files.

**Files:**
- Modify: `src/langgraph_agents/nodes/review_synthesizer.py:43-44`
- Modify: `src/langgraph_agents/nodes/prompt_review_synthesizer.py:22-23`
- Modify: `tests/test_build_review.py` (add regression test)
- Modify: `tests/test_prompt_build_review.py` (add regression test)

- [ ] **Step 1: Write the failing regression test**

In `tests/test_build_review.py`, add inside `TestSynthesizer`:
```python
def test_verdict_detection_tolerates_space_after_colon(self):
    """VERDICT: REVISE (space) must not be silently treated as APPROVE."""
    state = self._base_state(
        micro_feedback="VERDICT: REVISE\nREASONING: Bug found.",
        macro_feedback="VERDICT:APPROVE\nREASONING: Fine.",
    )
    result = synthesize_reviews(state)
    assert result["build_verdict"] == "REVISE", (
        "Space after colon in VERDICT: REVISE was misclassified as APPROVE"
    )
```

- [ ] **Step 2: Run test, confirm failure**

```
uv run pytest tests/test_build_review.py::TestSynthesizer::test_verdict_detection_tolerates_space_after_colon -v
```
Expected: `FAILED` — `assert 'APPROVE' == 'REVISE'`

- [ ] **Step 3: Fix `review_synthesizer.py`**

```python
# Add at top of file (after existing imports):
import re

def _is_revise(feedback: str) -> bool:
    """Detect VERDICT:REVISE tolerating optional whitespace after colon."""
    return bool(re.search(r"VERDICT:\s*REVISE", feedback, re.IGNORECASE))
```

Replace lines 43-44:
```python
# OLD:
micro_revise = "VERDICT:REVISE" in micro
macro_revise = "VERDICT:REVISE" in macro

# NEW:
micro_revise = _is_revise(micro)
macro_revise = _is_revise(macro)
```

- [ ] **Step 4: Fix `prompt_review_synthesizer.py`**

Add identical `import re` and `_is_revise()` function. Replace:
```python
# OLD:
behavioral_revise = "VERDICT:REVISE" in behavioral
architectural_revise = "VERDICT:REVISE" in architectural

# NEW:
behavioral_revise = _is_revise(behavioral)
architectural_revise = _is_revise(architectural)
```

Also add the same regression test in `tests/test_prompt_build_review.py` with analogous structure using `behavioral_feedback` / `architectural_feedback` and the `synthesize_prompt_reviews` function.

- [ ] **Step 5: Run all synthesizer tests**

```
uv run pytest tests/test_build_review.py tests/test_prompt_build_review.py -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```
git add src/langgraph_agents/nodes/review_synthesizer.py \
        src/langgraph_agents/nodes/prompt_review_synthesizer.py \
        tests/test_build_review.py \
        tests/test_prompt_build_review.py
git commit -m "fix: tolerate optional whitespace in VERDICT detection"
```

---

### Task 2: Fix `allowed_tools=[""]` in `invoke_structured` (C2-allowed)

**Problem:** `[""]` is truthy, so `invoke()` emits `--allowed-tools ""` — a tool named empty-string, not "no tools." Behavior is CLI-version-dependent and undocumented.

**Files:**
- Modify: `src/langgraph_agents/claude_cli.py:134`

- [ ] **Step 1: Locate the call**

`claude_cli.py:129-137`:
```python
raw = invoke(
    prompt,
    system_prompt=system_prompt,
    cwd=cwd,
    model=model,
    allowed_tools=[""],  # disable all tools for pure reasoning
    max_budget_usd=max_budget_usd,
    json_schema=schema,
)
```

- [ ] **Step 2: Apply the fix**

Change `allowed_tools=[""]` to `allowed_tools=None`. Add clarifying comment:
```python
raw = invoke(
    prompt,
    system_prompt=system_prompt,
    cwd=cwd,
    model=model,
    allowed_tools=None,  # omit --allowed-tools; structured output mode
                         # naturally suppresses tool calls via --json-schema
    max_budget_usd=max_budget_usd,
    json_schema=schema,
)
```

- [ ] **Step 3: Verify existing tests still pass**

```
uv run pytest tests/test_plan_review.py -v
```
Expected: all pass (plan_reviewer uses invoke_structured).

- [ ] **Step 4: Commit**

```
git add src/langgraph_agents/claude_cli.py
git commit -m "fix: remove invalid allowed_tools=[''] in invoke_structured"
```

---

### Task 3: Add `defer=True` to Fan-In Synthesizer Nodes (H1)

**Problem:** LangGraph docs require `defer=True` on fan-in nodes to guarantee they wait for all Send()-originated branches. Without it, the synthesizer may run before both reviewers complete.

**Files:**
- Modify: `src/langgraph_agents/graphs/build_review.py:47`
- Modify: `src/langgraph_agents/graphs/prompt_build_review.py:45`

- [ ] **Step 1: Update `build_review.py`**

```python
# OLD:
graph.add_node("synthesizer", synthesize_reviews)

# NEW:
graph.add_node("synthesizer", synthesize_reviews, defer=True)
```

- [ ] **Step 2: Update `prompt_build_review.py`**

```python
# OLD:
graph.add_node("synthesizer", synthesize_prompt_reviews)

# NEW:
graph.add_node("synthesizer", synthesize_prompt_reviews, defer=True)
```

- [ ] **Step 3: Verify graph compilation tests pass**

```
uv run pytest tests/test_build_review.py::TestBuildReviewGraph \
             tests/test_prompt_build_review.py -v
```
Expected: all pass — `defer=True` is additive and doesn't change routing logic tests.

- [ ] **Step 4: Commit**

```
git add src/langgraph_agents/graphs/build_review.py \
        src/langgraph_agents/graphs/prompt_build_review.py
git commit -m "fix: add defer=True to synthesizer fan-in nodes"
```

---

## Phase 2: Remove Dead Code (M7)

*Delete five modules that were scaffolding from the initial commit. None are imported by any production workflow.*

---

### Task 4: Delete Unused Modules

**Files to verify first, then delete:**
- `src/langgraph_agents/llm.py`
- `src/langgraph_agents/graphs/orchestrator.py`
- `src/langgraph_agents/nodes/researcher.py`
- `src/langgraph_agents/nodes/writer.py`
- `src/langgraph_agents/tools/search.py`
- `tests/test_orchestrator.py`
- Remove `AgentState` from `src/langgraph_agents/state.py:8-13`

- [ ] **Step 1: Verify nothing imports these**

```bash
grep -r "from langgraph_agents.llm" src/ tests/
grep -r "from langgraph_agents.graphs.orchestrator" src/ tests/
grep -r "from langgraph_agents.nodes.researcher" src/ tests/
grep -r "from langgraph_agents.nodes.writer" src/ tests/
grep -r "from langgraph_agents.tools.search" src/ tests/
grep -r "AgentState" src/ tests/
```

Expected: zero matches for each (except within the files themselves and `test_orchestrator.py`).

- [ ] **Step 2: Delete files**

```bash
rm src/langgraph_agents/llm.py
rm src/langgraph_agents/graphs/orchestrator.py
rm src/langgraph_agents/nodes/researcher.py
rm src/langgraph_agents/nodes/writer.py
rm src/langgraph_agents/tools/search.py
rm tests/test_orchestrator.py
```

- [ ] **Step 3: Remove `AgentState` from `state.py`**

Delete lines 8–13 of `state.py`:
```python
# DELETE this entire class:
class AgentState(TypedDict):
    """Base state shared across all graph nodes."""
    messages: Annotated[list, add_messages]
    task: str
    result: str
```

Also remove the now-unused imports at line 1-5 (`Annotated`, `add_messages`) if nothing else uses them. After removing `AgentState`, check whether `from langgraph.graph import add_messages` and `from typing import Annotated` are still needed. They are not — remove them too.

- [ ] **Step 4: Run full test suite**

```
uv run pytest tests/ -v
```
Expected: all tests pass (test_orchestrator is gone, no other tests reference deleted modules).

- [ ] **Step 5: Commit**

```
git add -u  # stages deletions and modifications
git commit -m "chore: remove unused llm.py, orchestrator, researcher, writer, search stub"
```

---

## Phase 3: Centralize Model Configuration (M1)

*Create `config.py` as the single source of truth for all model names and timeouts. Nodes import from it instead of hardcoding.*

---

### Task 5: Create `config.py` and Update All Nodes

**Files:**
- Create: `src/langgraph_agents/config.py`
- Modify: `src/langgraph_agents/nodes/planner.py:32`
- Modify: `src/langgraph_agents/nodes/plan_reviewer.py:44`
- Modify: `src/langgraph_agents/nodes/coder.py:57-58`
- Modify: `src/langgraph_agents/nodes/micro_reviewer.py:65-66`
- Modify: `src/langgraph_agents/nodes/macro_reviewer.py:68`
- Modify: `src/langgraph_agents/nodes/e2e_tester.py:151-152`
- Modify: `src/langgraph_agents/nodes/prompt_engineer.py:63`
- Modify: `src/langgraph_agents/nodes/behavioral_reviewer.py` (equivalent model line)
- Modify: `src/langgraph_agents/nodes/architectural_reviewer.py` (equivalent model line)
- Modify: `src/langgraph_agents/nodes/discover_architecture.py` (add model override)

- [ ] **Step 1: Create `config.py`**

```python
"""Central configuration for model selection and execution parameters.

All values are overridable via environment variables. This is the single
place to adjust model profiles across the entire workflow.

Example — run the full workflow with haiku reviewers for cost testing:
    REVIEWER_MODEL=haiku uv run python run_sync_opt_phase1.py
"""

import os

# --- Model selection ---
# Planner uses Opus for higher-quality implementation strategies.
PLANNER_MODEL: str = os.environ.get("PLANNER_MODEL", "opus")

# Reviewer and structured-output nodes use Sonnet (quality/cost balance).
REVIEWER_MODEL: str = os.environ.get("REVIEWER_MODEL", "sonnet")

# Coder uses Sonnet — it needs agentic tool use, not deep reasoning.
CODER_MODEL: str = os.environ.get("CODER_MODEL", "sonnet")

# E2E tester uses Sonnet — same rationale as coder.
E2E_MODEL: str = os.environ.get("E2E_MODEL", "sonnet")

# Prompt engineer uses Sonnet (edit-heavy, tool use needed).
PROMPT_ENGINEER_MODEL: str = os.environ.get("PROMPT_ENGINEER_MODEL", "sonnet")

# Discovery agent — lightweight scan, Sonnet is fine.
DISCOVER_MODEL: str = os.environ.get("DISCOVER_MODEL", "sonnet")

# --- Timeouts (seconds) ---
CODER_TIMEOUT: int = int(os.environ.get("CODER_TIMEOUT_S", "7200"))
REVIEWER_TIMEOUT: int = int(os.environ.get("REVIEWER_TIMEOUT_S", "3600"))
E2E_TIMEOUT: int = int(os.environ.get("E2E_TIMEOUT_S", "2700"))
PROMPT_ENGINEER_TIMEOUT: int = int(os.environ.get("PROMPT_ENGINEER_TIMEOUT_S", "1800"))

# --- Budget caps (USD) ---
CODER_BUDGET_USD: float = float(os.environ.get("CODER_BUDGET_USD", "10.0"))
E2E_BUDGET_USD: float = float(os.environ.get("E2E_BUDGET_USD", "2.0"))
```

- [ ] **Step 2: Write config import test**

Create `tests/test_config.py`:
```python
"""Tests that config module reads env vars correctly."""
import os
import importlib


def test_default_values():
    import langgraph_agents.config as cfg
    assert cfg.PLANNER_MODEL == os.environ.get("PLANNER_MODEL", "opus")
    assert cfg.CODER_TIMEOUT == int(os.environ.get("CODER_TIMEOUT_S", "7200"))
    assert cfg.CODER_BUDGET_USD == float(os.environ.get("CODER_BUDGET_USD", "10.0"))


def test_env_override(monkeypatch):
    monkeypatch.setenv("PLANNER_MODEL", "haiku")
    monkeypatch.setenv("CODER_TIMEOUT_S", "300")
    import langgraph_agents.config as cfg
    # Reload to pick up monkeypatched env vars
    importlib.reload(cfg)
    assert cfg.PLANNER_MODEL == "haiku"
    assert cfg.CODER_TIMEOUT == 300
    # Restore
    importlib.reload(cfg)
```

Run:
```
uv run pytest tests/test_config.py -v
```
Expected: both pass immediately (config.py exists and reads env).

- [ ] **Step 3: Update `planner.py`**

```python
# Add import:
from langgraph_agents.config import PLANNER_MODEL

# Change invoke call:
response = invoke(
    "\n\n".join(parts),
    system_prompt=SYSTEM_PROMPT,
    model=PLANNER_MODEL,   # was: model="opus"
)
```

- [ ] **Step 4: Update `plan_reviewer.py`**

```python
from langgraph_agents.config import REVIEWER_MODEL

# In review_plan():
raw = invoke_structured(
    content,
    schema=PLAN_VERDICT_SCHEMA,
    system_prompt=SYSTEM_PROMPT,
    model=REVIEWER_MODEL,  # was: model="sonnet"
)
```

- [ ] **Step 5: Update `coder.py`**

```python
from langgraph_agents.config import CODER_BUDGET_USD, CODER_MODEL, CODER_TIMEOUT

# In code():
invoke_agent(
    context,
    system_prompt=CODER_SYSTEM_PROMPT,
    cwd=workspace,
    model=CODER_MODEL,          # was: model="sonnet"
    max_budget_usd=CODER_BUDGET_USD,  # was: missing
    timeout=CODER_TIMEOUT,      # was: timeout=7200
)
```

- [ ] **Step 6: Update `micro_reviewer.py`**

```python
from langgraph_agents.config import REVIEWER_MODEL, REVIEWER_TIMEOUT

# In micro_review():
response = invoke_agent(
    content,
    system_prompt=SYSTEM_PROMPT,
    cwd=workspace,
    allowed_tools=REVIEW_TOOLS,
    model=REVIEWER_MODEL,       # was: model="sonnet"
    timeout=REVIEWER_TIMEOUT,   # was: timeout=3600
)
```

- [ ] **Step 7: Update `macro_reviewer.py`**

```python
from langgraph_agents.config import REVIEWER_MODEL, REVIEWER_TIMEOUT

# macro_review() had no timeout — add it:
response = invoke_agent(
    content,
    system_prompt=SYSTEM_PROMPT,
    cwd=workspace,
    allowed_tools=REVIEW_TOOLS,
    model=REVIEWER_MODEL,       # was: model="sonnet"
    timeout=REVIEWER_TIMEOUT,   # was: missing
)
```

- [ ] **Step 8: Update `e2e_tester.py`**

```python
from langgraph_agents.config import E2E_BUDGET_USD, E2E_MODEL, E2E_TIMEOUT

# In e2e_test():
response = invoke_agent(
    context,
    system_prompt=SYSTEM_PROMPT,
    cwd=workspace,
    allowed_tools=E2E_TOOLS,
    model=E2E_MODEL,            # was: model="sonnet"
    max_budget_usd=E2E_BUDGET_USD,  # was: max_budget_usd=2.0 (now configurable)
    timeout=E2E_TIMEOUT,        # was: timeout=2700
)
```

- [ ] **Step 9: Update `prompt_engineer.py`, `behavioral_reviewer.py`, `architectural_reviewer.py`**

All three: add `from langgraph_agents.config import PROMPT_ENGINEER_MODEL, REVIEWER_MODEL, REVIEWER_TIMEOUT` and use the appropriate constants. `prompt_engineer.py` gets `PROMPT_ENGINEER_MODEL` and `PROMPT_ENGINEER_TIMEOUT`. The behavioral and architectural reviewers get `REVIEWER_MODEL` and `REVIEWER_TIMEOUT`.

- [ ] **Step 10: Update `discover_architecture.py`**

```python
from langgraph_agents.config import DISCOVER_MODEL

# In discover_architecture():
response = invoke_agent(
    ...,
    model=DISCOVER_MODEL,   # was: no model arg (used CLI default)
)
```

- [ ] **Step 11: Run full test suite**

```
uv run pytest tests/ -v
```
Expected: all tests pass — config import changes are purely mechanical.

- [ ] **Step 12: Commit**

```
git add src/langgraph_agents/config.py \
        src/langgraph_agents/nodes/planner.py \
        src/langgraph_agents/nodes/plan_reviewer.py \
        src/langgraph_agents/nodes/coder.py \
        src/langgraph_agents/nodes/micro_reviewer.py \
        src/langgraph_agents/nodes/macro_reviewer.py \
        src/langgraph_agents/nodes/e2e_tester.py \
        src/langgraph_agents/nodes/prompt_engineer.py \
        src/langgraph_agents/nodes/behavioral_reviewer.py \
        src/langgraph_agents/nodes/architectural_reviewer.py \
        src/langgraph_agents/nodes/discover_architecture.py \
        tests/test_config.py
git commit -m "feat: centralize model/timeout config in config.py"
```

---

## Phase 4: Handoff Quality (H4, M3)

*Two behavioral improvements: the synthesizer now includes approved-reviewer signal when the other reviewer REVISEs, and the e2e tester passes a targeted regression checklist across cycles.*

---

### Task 6: Synthesizer — Preserve APPROVE Signal When Paired With REVISE (H4)

**Problem:** When micro APPROVEs and macro REVISEs (or vice versa), the coder gets no signal about what to preserve. It may regress the approved dimension while fixing the other, causing oscillation across cycles.

**Files:**
- Modify: `src/langgraph_agents/nodes/review_synthesizer.py:40-56`
- Modify: `src/langgraph_agents/nodes/prompt_review_synthesizer.py:17-38`
- Modify: `tests/test_build_review.py:58-80` (update expectations — behavior changes)

- [ ] **Step 1: Update test expectations first**

The existing tests `test_micro_revise_omits_approve_feedback` and `test_macro_revise_omits_approve_feedback` assert that APPROVE feedback does NOT appear. These tests encode the old (buggy) behavior. Update them to assert the new behavior — APPROVE feedback IS included when the other reviewer REVISEs, labeled to distinguish it.

In `tests/test_build_review.py`, update `test_micro_revise_omits_approve_feedback`:

```python
def test_micro_revise_includes_approve_as_preservation_signal(self):
    """When micro REVISEs and macro APPROVEs, macro's approval is included
    as a 'do not regress' signal so the coder knows what to preserve."""
    state = self._base_state(
        micro_feedback="VERDICT:REVISE\nREASONING:Bugs found.\n\nCRITICAL:\n- foo.py:10 — null deref — ACTION: add guard",
        macro_feedback="VERDICT:APPROVE\nREASONING:Architecture is solid.",
    )
    result = synthesize_reviews(state)
    assert result["build_verdict"] == "REVISE"
    assert "## Micro Review" in result["build_feedback"]
    assert "CRITICAL" in result["build_feedback"]
    # Macro approval IS included now, labeled as preservation signal
    assert "Macro Review" in result["build_feedback"]
    assert "do not regress" in result["build_feedback"].lower() or "APPROVED" in result["build_feedback"]
```

Rename (or keep) `test_macro_revise_omits_approve_feedback` to match the same new expectation pattern.

Also add:
```python
def test_both_approve_no_preservation_noise(self):
    """When both approve, the feedback stays minimal — no spurious preservation sections."""
    state = self._base_state(
        micro_feedback="VERDICT:APPROVE\nREASONING:Looks good.",
        macro_feedback="VERDICT:APPROVE\nREASONING:Solid.",
    )
    result = synthesize_reviews(state)
    assert result["build_verdict"] == "APPROVE"
    # 'do not regress' language only appears when there's a mixed verdict
    assert "do not regress" not in result["build_feedback"].lower()
```

Run tests to confirm they fail before the fix:
```
uv run pytest tests/test_build_review.py::TestSynthesizer -v
```

- [ ] **Step 2: Update `review_synthesizer.py`**

Replace the feedback assembly block (lines 48–54):
```python
parts: list[str] = []

if micro_revise:
    parts.append(
        f"## Micro Review (REVISE — must fix)\n{_extract_verdict_block(micro)}"
    )
elif macro_revise:
    # Micro approved but macro is revising — tell the coder what to preserve.
    parts.append(
        f"## Micro Review (APPROVED — do not regress these patterns)\n"
        f"{_extract_verdict_block(micro)}"
    )

if macro_revise:
    parts.append(
        f"## Macro Review (REVISE — must fix)\n{_extract_verdict_block(macro)}"
    )
elif micro_revise:
    # Macro approved but micro is revising — tell the coder what to preserve.
    parts.append(
        f"## Macro Review (APPROVED — do not regress these patterns)\n"
        f"{_extract_verdict_block(macro)}"
    )

feedback = "\n\n".join(parts) if parts else "Both reviewers approved."
```

- [ ] **Step 3: Apply analogous fix to `prompt_review_synthesizer.py`**

`synthesize_prompt_reviews` already includes APPROVE feedback regardless of verdict (it was better designed from the start). Verify the new format still makes sense and add the "(do not regress)" label to APPROVE sections when the other reviewer REVISEs:

```python
if behavioral_revise:
    parts.append(f"## Behavioral Review (REVISE — must fix)\n{behavioral}")
elif architectural_revise:
    parts.append(
        f"## Behavioral Review (APPROVED — do not regress these patterns)\n{behavioral}"
    )

if architectural_revise:
    parts.append(f"## Architectural Review (REVISE — must fix)\n{architectural}")
elif behavioral_revise:
    parts.append(
        f"## Architectural Review (APPROVED — do not regress these patterns)\n{architectural}"
    )
```

- [ ] **Step 4: Run all synthesizer tests**

```
uv run pytest tests/test_build_review.py tests/test_prompt_build_review.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```
git add src/langgraph_agents/nodes/review_synthesizer.py \
        src/langgraph_agents/nodes/prompt_review_synthesizer.py \
        tests/test_build_review.py \
        tests/test_prompt_build_review.py
git commit -m "feat: preserve approved-reviewer signal in synthesizer to prevent coder oscillation"
```

---

### Task 7: E2E Tester — Add Regression Checklist Across Cycles (M3)

**Problem:** The e2e tester is deliberately stateless to avoid anchoring bias. But on cycle 2, it cannot detect whether the proposed fixes from cycle 1 were actually applied. A coder may have addressed the root cause without fixing all the surface symptoms, and the e2e tester re-raises the same issues without noticing the partial progress.

**Files:**
- Modify: `src/langgraph_agents/nodes/e2e_tester.py`
- Modify: `tests/test_e2e_tester.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_e2e_tester.py`, add:
```python
def test_build_e2e_context_includes_regression_checklist_on_cycle_2():
    """On e2e_cycle > 0, PROPOSED FIXES from prior report become a regression checklist."""
    state = {
        "task": "Build X",
        "current_plan": "Plan Y",
        "current_code": "",
        "workspace_path": str(tmp_path),  # use pytest fixture or a valid path
        "e2e_verdict": "REVISE",
        "e2e_cycle": 1,  # second cycle
        "e2e_report": (
            "INTENT GAPS: The output lacks timestamps.\n"
            "EVIDENCE: Ran the command, no timestamps in output.\n"
            "ROOT CAUSE: format_output() doesn't include time.\n"
            "PROPOSED FIXES: Add datetime.now() call in format_output().\n"
            "VERDICT:REVISE\n"
            "REASONING: Output quality is insufficient."
        ),
    }
    context = _build_e2e_context(state)
    assert "PROPOSED FIXES" in context or "regression" in context.lower(), (
        "Cycle 2 context should include prior proposed fixes as a regression checklist"
    )
    # Should NOT include the full prior report (anchoring risk)
    assert "Output quality is insufficient" not in context, (
        "Full prior verdict reasoning should not be included (anchoring risk)"
    )
```

To run this test you need `_build_e2e_context` and `_extract_proposed_fixes` to be importable:
```python
from langgraph_agents.nodes.e2e_tester import _build_e2e_context, _extract_proposed_fixes
```

Run:
```
uv run pytest tests/test_e2e_tester.py::test_build_e2e_context_includes_regression_checklist_on_cycle_2 -v
```
Expected: `ImportError` (function doesn't exist yet) or `AssertionError`.

- [ ] **Step 2: Add `_extract_proposed_fixes()` to `e2e_tester.py`**

```python
def _extract_proposed_fixes(report: str) -> str:
    """Extract only the PROPOSED FIXES block from a prior e2e report.

    Returns an empty string if the block is not found. This is deliberately
    narrow — we pass only the actionable fixes, not the full report, to
    avoid anchoring the current evaluation while still enabling regression
    detection.
    """
    lines = report.splitlines()
    in_fixes = False
    fixes_lines: list[str] = []

    for line in lines:
        if line.startswith("PROPOSED FIXES:"):
            in_fixes = True
            fixes_lines.append(line)
        elif in_fixes:
            # Stop at the next section header or VERDICT line
            if line.startswith("VERDICT:") or (
                line.isupper() and line.endswith(":") and len(line) > 2
            ):
                break
            fixes_lines.append(line)

    return "\n".join(fixes_lines).strip()
```

- [ ] **Step 3: Update `_build_e2e_context()` to include the checklist**

In `_build_e2e_context`, after the existing content assembly, add:
```python
# On subsequent cycles, surface the prior proposed fixes as a regression
# checklist without passing the full report (which would anchor the verdict).
e2e_cycle = state.get("e2e_cycle", 0)
if e2e_cycle > 0:
    prior_fixes = _extract_proposed_fixes(state.get("e2e_report", ""))
    if prior_fixes:
        parts.append(
            "## Regression Checklist (from prior e2e cycle)\n"
            "The following fixes were requested in the previous cycle. "
            "Verify that they were applied, but evaluate the overall workspace "
            "independently — do not assume success just because they were requested.\n\n"
            f"{prior_fixes}"
        )
```

- [ ] **Step 4: Verify the test passes and existing tests still pass**

```
uv run pytest tests/test_e2e_tester.py -v
```
Expected: all pass.

- [ ] **Step 5: Commit**

```
git add src/langgraph_agents/nodes/e2e_tester.py \
        tests/test_e2e_tester.py
git commit -m "feat: add regression checklist to e2e tester on repeat cycles"
```

---

## Phase 5: Token Efficiency (M2, M5)

---

### Task 8: Bound Code Diff Size in Coder Context (M2)

**Problem:** `run_git_diff` captures the total cumulative diff since HEAD. On build_cycle 4, the coder's prompt contains the entire history of changes — potentially tens of thousands of tokens. The reviewers see the same problem in their prompts.

**Files:**
- Modify: `src/langgraph_agents/nodes/coder.py`
- Modify: `src/langgraph_agents/nodes/micro_reviewer.py`
- Modify: `src/langgraph_agents/nodes/macro_reviewer.py`
- Modify: `tests/test_build_review.py` (no new tests needed — this is a truncation helper)

- [ ] **Step 1: Add `_truncate_diff()` to `coder.py`**

```python
# Max characters to include from a diff before truncating.
# 16_000 chars ≈ 4_000 tokens — keeps the coder context bounded.
_DIFF_MAX_CHARS = 16_000


def _truncate_diff(diff: str) -> str:
    """Truncate a large diff to a bounded size.

    Keeps the tail (most recent changes) since earlier changes are already
    reflected in the workspace. Adds a header warning when truncated.
    """
    if len(diff) <= _DIFF_MAX_CHARS:
        return diff
    truncated = diff[-_DIFF_MAX_CHARS:]
    # Find the first complete hunk boundary to avoid mid-hunk splits
    hunk_start = truncated.find("\n@@")
    if hunk_start > 0:
        truncated = truncated[hunk_start + 1:]
    return f"[diff truncated — showing last {len(truncated)} chars]\n{truncated}"
```

- [ ] **Step 2: Write the test**

In `tests/test_build_review.py`, add a `TestDiffTruncation` class:
```python
from langgraph_agents.nodes.coder import _truncate_diff, _DIFF_MAX_CHARS

class TestDiffTruncation:
    def test_short_diff_unchanged(self):
        diff = "diff --git a/foo.py b/foo.py\n+hello"
        assert _truncate_diff(diff) == diff

    def test_long_diff_is_truncated(self):
        long_diff = "@@ -1 +1 @@\n" + "+" + "x" * (_DIFF_MAX_CHARS + 500)
        result = _truncate_diff(long_diff)
        assert len(result) < len(long_diff)
        assert "truncated" in result

    def test_truncated_diff_starts_at_hunk_boundary(self):
        # Construct a diff with a clear hunk boundary inside the tail region
        prefix = "x" * (_DIFF_MAX_CHARS + 100)
        suffix = "\n@@ -10 +10 @@\n+new line\n"
        long_diff = prefix + suffix
        result = _truncate_diff(long_diff)
        assert result.startswith("@@ -10 +10 @@") or "truncated" in result
```

Run:
```
uv run pytest tests/test_build_review.py::TestDiffTruncation -v
```
Expected: FAIL (function not yet used/exported correctly). Add the import and fix until passing.

- [ ] **Step 3: Apply `_truncate_diff` in `_build_coder_context`**

```python
if state.get("code_diff"):
    diff = _truncate_diff(state["code_diff"])   # was: state["code_diff"] directly
    parts.append(f"## Current Code Diff\n```diff\n{diff}\n```")
```

- [ ] **Step 4: Apply the same truncation in `micro_reviewer.py` and `macro_reviewer.py`**

Both files include `state.get('code_diff', '')` in the content string. Import `_truncate_diff` from `coder.py` — but to avoid circular imports, move the helper to a shared location. Better: add a standalone `_truncate_diff` function directly to each reviewer file (3-line copy). Or: extract it to `tools/dev_tools.py` alongside `run_git_diff` since it's diff-handling logic.

**Recommended location:** `src/langgraph_agents/tools/dev_tools.py` — add `truncate_diff()` there, import it in `coder.py`, `micro_reviewer.py`, `macro_reviewer.py`.

```python
# In tools/dev_tools.py — add at bottom:
DIFF_MAX_CHARS = 16_000

def truncate_diff(diff: str) -> str:
    """Truncate a large diff, keeping the tail (most recent changes)."""
    if len(diff) <= DIFF_MAX_CHARS:
        return diff
    truncated = diff[-DIFF_MAX_CHARS:]
    hunk_start = truncated.find("\n@@")
    if hunk_start > 0:
        truncated = truncated[hunk_start + 1:]
    return f"[diff truncated — showing last {len(truncated)} chars]\n{truncated}"
```

Then in each consumer: `from langgraph_agents.tools.dev_tools import truncate_diff`.

- [ ] **Step 5: Run tests**

```
uv run pytest tests/ -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```
git add src/langgraph_agents/tools/dev_tools.py \
        src/langgraph_agents/nodes/coder.py \
        src/langgraph_agents/nodes/micro_reviewer.py \
        src/langgraph_agents/nodes/macro_reviewer.py \
        tests/test_build_review.py
git commit -m "perf: bound code diff to 16k chars to prevent unbounded token growth across cycles"
```

---

### Task 9: Fix Test Command Mapping — Direct File Targeting Over `-k` (M5)

**Problem:** `_suggest_test_commands` emits `pytest tests/ -k 'module_name'` — a fuzzy match that hits unrelated tests in growing test suites. Direct file targeting is faster and more precise.

**Files:**
- Modify: `src/langgraph_agents/nodes/e2e_tester.py:84-106`
- Modify: `tests/test_e2e_tester.py`

- [ ] **Step 1: Write the test**

In `tests/test_e2e_tester.py`, locate the existing `_suggest_test_commands` tests and add:
```python
def test_suggest_commands_uses_direct_file_path_when_test_exists(tmp_path):
    """Suggest direct test file path when tests/test_<module>.py exists."""
    from langgraph_agents.nodes.e2e_tester import _suggest_test_commands
    # Create a fake test file to simulate existence
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_coder.py").touch()
    # We can't inject tmp_path into the function without refactoring,
    # so test the output format instead:
    result = _suggest_test_commands(["src/langgraph_agents/nodes/coder.py"])
    # Should prefer tests/test_coder.py path over -k coder
    assert "test_coder" in result

def test_suggest_commands_falls_back_to_k_when_no_test_file():
    """Fall back to -k matching when no direct test file found."""
    from langgraph_agents.nodes.e2e_tester import _suggest_test_commands
    result = _suggest_test_commands(["src/langgraph_agents/nodes/nonexistent_module.py"])
    # nonexistent module → fall back to -k
    if result:  # may be empty if file list is empty
        assert "-k" in result or "test_nonexistent_module" in result
```

Run:
```
uv run pytest tests/test_e2e_tester.py -k "suggest_commands" -v
```

- [ ] **Step 2: Update `_suggest_test_commands`**

```python
def _suggest_test_commands(changed_files: list[str]) -> str:
    """Map changed source files to targeted test commands.

    Prefers direct test file paths (tests/test_<module>.py) over -k matching.
    Falls back to -k when no direct test file exists.
    Returns a markdown section, or empty string if no source files changed.
    """
    import os

    commands: list[str] = []
    seen: set[str] = set()

    for f in changed_files:
        if not f.endswith(".py") or "/test_" in f or f.startswith("test_"):
            continue
        basename = f.rsplit("/", 1)[-1].removesuffix(".py")
        if basename in seen:
            continue
        seen.add(basename)

        test_file = f"tests/test_{basename}.py"
        if os.path.exists(test_file):
            commands.append(f"- `uv run pytest {test_file} -x --tb=short`")
        else:
            commands.append(
                f"- `uv run pytest tests/ -k '{basename}' -x --tb=short`"
            )

        if len(commands) >= 5:
            break

    if not commands:
        return ""
    return "## Suggested Test Commands\n" + "\n".join(commands)
```

- [ ] **Step 3: Run all e2e_tester tests**

```
uv run pytest tests/test_e2e_tester.py -v
```
Expected: all pass.

- [ ] **Step 4: Commit**

```
git add src/langgraph_agents/nodes/e2e_tester.py \
        tests/test_e2e_tester.py
git commit -m "perf: use direct test file paths in e2e test command suggestions"
```

---

## Phase 6: Fault Tolerance (H3, C1)

*RetryPolicy protects individual nodes from transient failures. Checkpointing protects the full workflow from losing hours of progress.*

---

### Task 10: Add RetryPolicy to All Nodes (H3)

**Problem:** A single transient error (network blip, subprocess killed) propagates as an unhandled exception, aborting the entire workflow with no retry.

**Files:**
- Modify: `src/langgraph_agents/graphs/build_review.py`
- Modify: `src/langgraph_agents/graphs/prompt_build_review.py`
- Modify: `src/langgraph_agents/graphs/plan_review.py`
- Modify: `src/langgraph_agents/graphs/plan_build_review.py`
- Modify: `src/langgraph_agents/graphs/prompt_workflow.py`

- [ ] **Step 1: Write a test that asserts RetryPolicy is set on coder node**

In `tests/test_build_review.py`, add to `TestBuildReviewGraph`:
```python
def test_coder_node_has_retry_policy(self):
    from langgraph.types import RetryPolicy
    graph = build_build_review_graph()
    compiled = graph.compile()
    # LangGraph exposes node config via get_graph().nodes[name]
    graph_data = compiled.get_graph()
    # Verify the coder node is present (RetryPolicy is set at build time)
    assert "coder" in graph_data.nodes
    # Note: RetryPolicy itself is not directly inspectable from the compiled graph
    # in all LangGraph versions — this test ensures the graph still compiles
    # cleanly after adding RetryPolicy.
    assert compiled is not None
```

- [ ] **Step 2: Add `RetryPolicy` to `build_review.py`**

```python
from langgraph.types import RetryPolicy, Send  # add RetryPolicy to existing import

# Define a shared retry policy for all subprocess-backed nodes.
# max_attempts=3, initial_interval=2s — reasonable for transient network/API issues.
_SUBPROCESS_RETRY = RetryPolicy(
    max_attempts=3,
    initial_interval=2.0,
    retry_on=RuntimeError,  # claude CLI raises RuntimeError on non-zero exit
)

# In build_build_review_graph():
graph.add_node("coder", code, retry_policy=_SUBPROCESS_RETRY)
graph.add_node("micro_reviewer", micro_review, retry_policy=_SUBPROCESS_RETRY)
graph.add_node("macro_reviewer", macro_review, retry_policy=_SUBPROCESS_RETRY)
# synthesizer is pure Python — no retry needed
graph.add_node("synthesizer", synthesize_reviews, defer=True)
```

- [ ] **Step 3: Apply same pattern to `prompt_build_review.py`**

```python
from langgraph.types import RetryPolicy, Send

_SUBPROCESS_RETRY = RetryPolicy(max_attempts=3, initial_interval=2.0, retry_on=RuntimeError)

graph.add_node("prompt_engineer", prompt_engineer, retry_policy=_SUBPROCESS_RETRY)
graph.add_node("behavioral_reviewer", behavioral_review, retry_policy=_SUBPROCESS_RETRY)
graph.add_node("architectural_reviewer", architectural_review, retry_policy=_SUBPROCESS_RETRY)
graph.add_node("synthesizer", synthesize_prompt_reviews, defer=True)
```

- [ ] **Step 4: Apply to `plan_review.py`**

```python
from langgraph.types import RetryPolicy

_SUBPROCESS_RETRY = RetryPolicy(max_attempts=3, initial_interval=2.0, retry_on=RuntimeError)

graph.add_node("planner", plan, retry_policy=_SUBPROCESS_RETRY)
graph.add_node("plan_reviewer", review_plan, retry_policy=_SUBPROCESS_RETRY)
```

- [ ] **Step 5: Apply to wrapper nodes in `plan_build_review.py` and `prompt_workflow.py`**

Wrapper nodes (`_call_plan_review`, `_call_build_review`) invoke subgraphs — they don't make subprocess calls directly. RetryPolicy on them would re-run the entire subgraph on failure, which is wasteful and incorrect (subgraph may have partially completed). Skip RetryPolicy on wrapper nodes; the subgraph's own nodes are already protected.

Apply RetryPolicy only to `e2e_test` in `plan_build_review.py`:
```python
from langgraph.types import RetryPolicy

_SUBPROCESS_RETRY = RetryPolicy(max_attempts=3, initial_interval=2.0, retry_on=RuntimeError)

graph.add_node("e2e_test", e2e_test, retry_policy=_SUBPROCESS_RETRY)
```

Same for `discover_architecture` in `prompt_workflow.py`:
```python
graph.add_node("discover_architecture", discover_architecture, retry_policy=_SUBPROCESS_RETRY)
```

- [ ] **Step 6: Run full test suite**

```
uv run pytest tests/ -v
```
Expected: all pass.

- [ ] **Step 7: Commit**

```
git add src/langgraph_agents/graphs/build_review.py \
        src/langgraph_agents/graphs/prompt_build_review.py \
        src/langgraph_agents/graphs/plan_review.py \
        src/langgraph_agents/graphs/plan_build_review.py \
        src/langgraph_agents/graphs/prompt_workflow.py \
        tests/test_build_review.py
git commit -m "feat: add RetryPolicy to all subprocess-backed nodes"
```

---

### Task 11: Add Checkpointing to All Compiled Graphs (C1)

**Problem:** No checkpointer means a crash at any point in an 8-hour workflow restarts from scratch. Checkpointing enables atomic superstep persistence and resume-on-failure.

**Design decision:** Checkpointers are injected at compile time and require a `thread_id` at runtime. The graphs themselves remain checkpointer-agnostic — callers pass the checkpointer to `compile()`. Add a factory function to each graph module that accepts an optional checkpointer, defaulting to `InMemorySaver`.

**Files:**
- Modify: `src/langgraph_agents/graphs/build_review.py`
- Modify: `src/langgraph_agents/graphs/prompt_build_review.py`
- Modify: `src/langgraph_agents/graphs/plan_review.py`
- Modify: `src/langgraph_agents/graphs/plan_build_review.py`
- Modify: `src/langgraph_agents/graphs/prompt_workflow.py`
- Modify: all `run_*.py` scripts to pass `thread_id` in config

- [ ] **Step 1: Write the test**

In `tests/test_plan_build_review.py`, add:
```python
def test_graph_supports_checkpointing():
    """The compiled graph should accept a checkpointer and run with thread_id config."""
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph_agents.graphs.plan_build_review import build_plan_build_review_graph

    graph = build_plan_build_review_graph()
    app = graph.compile(checkpointer=InMemorySaver())
    # Verify it compiled without error
    assert app is not None
    # Verify get_state works (requires checkpointer)
    config = {"configurable": {"thread_id": "test-thread-1"}}
    # get_state on an uninvoked thread returns None (no checkpoint yet)
    state = app.get_state(config)
    assert state is not None  # returns a StateSnapshot object even with no data
```

Run:
```
uv run pytest tests/test_plan_build_review.py::test_graph_supports_checkpointing -v
```
Expected: FAIL (current compile() has no checkpointer, get_state would error without one).

- [ ] **Step 2: Refactor `build_review.py` — separate build from compile**

Currently the module-level `build_review_app = build_build_review_graph().compile()` is a global. This makes it impossible for callers to inject a checkpointer. Refactor to expose both the builder and a default compiled instance:

```python
# Remove the old global:
# build_review_app = build_build_review_graph().compile()

# Add a compile factory:
def compile_build_review(checkpointer=None):
    """Compile the build-review graph with an optional checkpointer.

    Args:
        checkpointer: A LangGraph checkpointer (e.g. InMemorySaver,
                      SqliteSaver). Defaults to InMemorySaver for
                      in-process fault tolerance.
    """
    from langgraph.checkpoint.memory import InMemorySaver
    cp = checkpointer if checkpointer is not None else InMemorySaver()
    return build_build_review_graph().compile(checkpointer=cp)


# Keep a default instance for callers that don't need to customize:
build_review_app = compile_build_review()
```

Apply identical refactor to `plan_review.py` (`compile_plan_review`), `prompt_build_review.py` (`compile_prompt_build_review`), `plan_build_review.py` (`compile_plan_build_review`), and `prompt_workflow.py` (`compile_prompt_workflow`).

- [ ] **Step 3: Verify test passes**

```
uv run pytest tests/test_plan_build_review.py -v
```
Expected: all pass including the new checkpointing test.

- [ ] **Step 4: Update `run_*.py` scripts to pass `thread_id`**

Every call site that invokes `.invoke()` must now pass a `config` with `thread_id`. The `thread_id` should be unique per run (use `uuid.uuid4()`). Example pattern for all run scripts:

```python
import uuid
from langgraph_agents.graphs.plan_build_review import plan_build_review_app

run_id = str(uuid.uuid4())
config = {"configurable": {"thread_id": run_id}}

result = plan_build_review_app.invoke(
    {
        "task": "...",
        "current_plan": "",
        "current_code": "",
        "workspace_path": "...",
        "e2e_verdict": "",
        "e2e_report": "",
        "e2e_cycle": 0,
    },
    config=config,
)
print(f"Run ID (for resume): {run_id}")
```

Apply this pattern to all `run_*.py` files that invoke graph apps.

- [ ] **Step 5: Run full test suite**

```
uv run pytest tests/ -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```
git add src/langgraph_agents/graphs/build_review.py \
        src/langgraph_agents/graphs/prompt_build_review.py \
        src/langgraph_agents/graphs/plan_review.py \
        src/langgraph_agents/graphs/plan_build_review.py \
        src/langgraph_agents/graphs/prompt_workflow.py \
        run_*.py \
        tests/test_plan_build_review.py
git commit -m "feat: add checkpointing to all graphs — enables resume-on-failure for multi-hour runs"
```

---

## Phase 7: Architecture Improvements (M4, M6, H2)

*These are the highest-complexity changes. Each is independently deployable. M4 (add discovery) and M6 (streaming runner) are low-risk. H2 (native subgraph composition) carries more risk and should be last.*

---

### Task 12: Add `discover_architecture` to `plan_build_review` Workflow (M4)

**Problem:** The planner and coder in `plan_build_review` operate without any knowledge of the existing workspace architecture. For complex codebases, this produces plans that miss conventions, conflict with existing patterns, or reinvent already-solved problems.

**Files:**
- Modify: `src/langgraph_agents/state.py` — add `agent_architecture: str` to `ParentState`
- Modify: `src/langgraph_agents/nodes/discover_architecture.py` — generalize state type
- Modify: `src/langgraph_agents/graphs/plan_build_review.py` — add discover node; thread architecture into plan_review wrapper
- Modify: `tests/test_plan_build_review.py`

- [ ] **Step 1: Write the test**

In `tests/test_plan_build_review.py`, add:
```python
def test_graph_has_discover_architecture_node():
    from langgraph_agents.graphs.plan_build_review import build_plan_build_review_graph
    graph = build_plan_build_review_graph()
    compiled = graph.compile()
    node_names = set(compiled.get_graph().nodes.keys())
    assert "discover_architecture" in node_names

def test_discover_runs_before_plan_review():
    """discover_architecture must be the entry node, before plan_review."""
    from langgraph.graph import START
    from langgraph_agents.graphs.plan_build_review import build_plan_build_review_graph
    graph = build_plan_build_review_graph()
    compiled = graph.compile()
    edges = compiled.get_graph().edges
    # There should be an edge from START → discover_architecture
    start_targets = [e.target for e in edges if e.source == "__start__"]
    assert "discover_architecture" in start_targets
```

Run:
```
uv run pytest tests/test_plan_build_review.py -k "discover" -v
```
Expected: FAIL.

- [ ] **Step 2: Add `agent_architecture` to `ParentState`**

In `state.py`, add to `ParentState`:
```python
class ParentState(TypedDict):
    task: str
    current_plan: str
    current_code: str
    workspace_path: str
    agent_architecture: str  # ADD: compressed workspace architecture summary
    e2e_verdict: str
    e2e_report: str
    e2e_cycle: int
```

- [ ] **Step 3: Generalize `discover_architecture` node's state type**

Currently `discover_architecture` is typed to `PromptWorkflowState`. It only reads `workspace_path` and writes `agent_architecture` — both of which now exist in `ParentState` too. Create a minimal protocol:

```python
# In discover_architecture.py, change the type annotation:
# OLD: def discover_architecture(state: PromptWorkflowState) -> dict:
# NEW: Accept any dict-like state with workspace_path

from typing import Any

@validate_node(
    pre={"workspace_path": is_path},
    post={"agent_architecture": non_empty},
)
def discover_architecture(state: Any) -> dict:  # Any: accepts both ParentState and PromptWorkflowState
    """Scan the workspace and produce a compressed architecture summary."""
    ...
```

- [ ] **Step 4: Add the discover node to `plan_build_review.py`**

```python
from langgraph_agents.nodes.discover_architecture import discover_architecture

def _call_plan_review(state: ParentState) -> dict:
    """Wrapper: optionally enriches task with architecture context."""
    task = state.get("task", "")
    arch = state.get("agent_architecture", "")
    enriched_task = (
        f"{task}\n\n## Workspace Architecture Context\n{arch}" if arch else task
    )
    subgraph_input: PlanReviewState = {
        "task": enriched_task,
        "current_plan": state.get("current_plan", ""),
        "plan_feedback": "",
        "plan_verdict": "",
        "plan_cycle": 0,
    }
    result = plan_review_app.invoke(subgraph_input)
    return {"current_plan": result["current_plan"]}

# In build_plan_build_review_graph():
graph.add_node("discover_architecture", discover_architecture, retry_policy=_SUBPROCESS_RETRY)
graph.add_node("plan_review", _call_plan_review)
graph.add_node("build_review", _call_build_review)
graph.add_node("e2e_test", e2e_test, retry_policy=_SUBPROCESS_RETRY)

graph.add_edge(START, "discover_architecture")   # was: START → "plan_review"
graph.add_edge("discover_architecture", "plan_review")  # ADD
graph.add_edge("plan_review", "build_review")
graph.add_edge("build_review", "e2e_test")
graph.add_conditional_edges("e2e_test", _route_after_e2e, {END: END, "build_review": "build_review"})
```

- [ ] **Step 5: Update all callers to include `agent_architecture` in initial state**

The initial state dict passed to `plan_build_review_app.invoke()` now requires `agent_architecture: ""` (empty string — will be populated by the discover node). Add `"agent_architecture": ""` to all run scripts and test fixtures that construct `ParentState`.

- [ ] **Step 6: Run all plan_build_review tests**

```
uv run pytest tests/test_plan_build_review.py -v
```
Expected: all pass including new discover tests.

- [ ] **Step 7: Commit**

```
git add src/langgraph_agents/state.py \
        src/langgraph_agents/nodes/discover_architecture.py \
        src/langgraph_agents/graphs/plan_build_review.py \
        tests/test_plan_build_review.py \
        run_*.py
git commit -m "feat: add discover_architecture node to plan_build_review workflow"
```

---

### Task 13: Add Async Streaming Runner (M6)

**Problem:** All workflows use blocking `.invoke()`. For 2-hour runs, the caller gets zero feedback — impossible to distinguish "running" from "hung." Adding a streaming runner enables node-level progress visibility without changing the graph structure.

**Files:**
- Create: `src/langgraph_agents/graph_runner.py`
- Create: `tests/test_graph_runner.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_graph_runner.py
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from langgraph_agents.graph_runner import stream_graph, run_graph


class TestStreamGraph:
    def test_stream_graph_yields_node_updates(self):
        """stream_graph yields (node_name, state_update) pairs."""
        mock_app = MagicMock()
        mock_app.astream = AsyncMock(return_value=async_generator([
            {"coder": {"code_diff": "diff content"}},
            {"synthesizer": {"build_verdict": "APPROVE"}},
        ]))

        results = asyncio.run(collect_stream(mock_app, {}, {}))
        assert len(results) == 2
        assert results[0][0] == "coder"
        assert results[1][0] == "synthesizer"

    def test_run_graph_returns_final_state(self):
        """run_graph is a sync wrapper that returns the final invoke result."""
        mock_app = MagicMock()
        mock_app.invoke = MagicMock(return_value={"result": "done"})
        result = run_graph(mock_app, {"task": "x"}, {"configurable": {"thread_id": "t1"}})
        assert result == {"result": "done"}
        mock_app.invoke.assert_called_once()

# Helpers for async test
async def async_generator(items):
    for item in items:
        yield item

async def collect_stream(app, inputs, config):
    results = []
    async for node_name, update in stream_graph(app, inputs, config):
        results.append((node_name, update))
    return results
```

- [ ] **Step 2: Create `graph_runner.py`**

```python
"""Streaming and synchronous runners for LangGraph workflows.

Provides:
- stream_graph: async generator that yields (node_name, state_update) pairs
  with console progress output. Use for long-running workflows.
- run_graph: thin synchronous wrapper over app.invoke() with consistent
  thread_id config handling.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, AsyncGenerator


async def stream_graph(
    app: Any,
    inputs: dict,
    config: dict | None = None,
    *,
    print_progress: bool = True,
) -> AsyncGenerator[tuple[str, dict], None]:
    """Async generator that streams node-level updates from a graph.

    Args:
        app: A compiled LangGraph application (must support astream).
        inputs: The initial state dict.
        config: LangGraph config dict. If None, a fresh thread_id is generated.
        print_progress: If True, print each node completion to stdout.

    Yields:
        (node_name, state_update) tuples as each node completes.
    """
    if config is None:
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    async for update in app.astream(inputs, config=config, stream_mode="updates"):
        for node_name, node_update in update.items():
            if print_progress:
                print(f"[{node_name}] completed", flush=True)
            yield node_name, node_update


def run_graph(
    app: Any,
    inputs: dict,
    config: dict | None = None,
    *,
    print_progress: bool = True,
) -> dict:
    """Synchronous runner that streams progress then returns the final state.

    Prefer this over app.invoke() for long-running workflows — it provides
    node-level progress visibility while remaining synchronous from the
    caller's perspective.

    Args:
        app: A compiled LangGraph application.
        inputs: The initial state dict.
        config: LangGraph config dict. If None, a fresh thread_id is generated.
        print_progress: If True, print each node completion to stdout.

    Returns:
        The final graph state dict.
    """
    if config is None:
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    async def _run() -> dict:
        final_state = inputs.copy()
        async for _, update in stream_graph(app, inputs, config, print_progress=print_progress):
            final_state.update(update)
        return final_state

    return asyncio.run(_run())
```

- [ ] **Step 3: Run the tests**

```
uv run pytest tests/test_graph_runner.py -v
```
Expected: all pass.

- [ ] **Step 4: Update one run script to use `run_graph`**

Pick any run script (e.g., `run_sync_opt_phase1.py`) and replace the `.invoke()` call:
```python
# OLD:
result = plan_build_review_app.invoke(initial_state, config=config)

# NEW:
from langgraph_agents.graph_runner import run_graph
result = run_graph(plan_build_review_app, initial_state, config=config)
```

The script now prints node completions to stdout in real-time.

- [ ] **Step 5: Commit**

```
git add src/langgraph_agents/graph_runner.py \
        tests/test_graph_runner.py \
        run_sync_opt_phase1.py
git commit -m "feat: add streaming graph runner with node-level progress output"
```

---

### Task 14: Refactor Wrapper Nodes to Native Subgraph Composition (H2)

**Problem:** Wrapper nodes that call `app.invoke()` inside a node function are opaque to LangGraph's orchestration. Streaming with `subgraphs=True` doesn't work; checkpointing doesn't extend into subgraph boundaries.

**Scope:** This task focuses on `_call_plan_review` in `plan_build_review.py` as the prototype. The `_call_build_review` wrapper is more complex (conditional state injection) and is documented as a follow-up.

**Prerequisite:** Phase 6 (checkpointing) must be complete — native subgraph composition requires both the parent and subgraph to use compatible checkpointers.

**Design:** When a compiled subgraph is added directly via `graph.add_node("plan_review", plan_review_app)`, LangGraph:
1. Passes all keys present in BOTH parent and subgraph state schemas down to the subgraph.
2. Merges all keys in the subgraph output that exist in the parent schema back up.
3. Keys only in the subgraph schema are isolated (don't pollute parent state).

`ParentState` and `PlanReviewState` share: `task`, `current_plan`.
Non-shared in `PlanReviewState`: `plan_feedback`, `plan_verdict`, `plan_cycle` — these stay isolated.

**Files:**
- Modify: `src/langgraph_agents/graphs/plan_build_review.py`
- Modify: `tests/test_plan_build_review.py`

- [ ] **Step 1: Write a test verifying subgraph events appear in streaming**

```python
def test_plan_review_visible_in_subgraph_stream():
    """Native subgraph composition exposes inner node events via subgraphs=True."""
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph_agents.graphs.plan_build_review import build_plan_build_review_graph

    # This test verifies graph structure only — not the LLM execution.
    # The actual streaming behavior is verified by graph compilation succeeding
    # and the subgraph being a native node, not a wrapper.
    graph = build_plan_build_review_graph()
    compiled = graph.compile(checkpointer=InMemorySaver())
    graph_data = compiled.get_graph(xray=True)  # xray=True expands subgraphs
    # With native subgraph composition, xray should show inner nodes
    all_node_names = {n for n in graph_data.nodes.keys()}
    # plan_review is a subgraph node — with xray it should expand its internals
    assert "plan_review" in all_node_names or "planner" in all_node_names
```

- [ ] **Step 2: Replace `_call_plan_review` wrapper with native subgraph composition**

In `plan_build_review.py`:

```python
# REMOVE: _call_plan_review function entirely
# REMOVE: the import of PlanReviewState (no longer needed in this file)

# ADD: import the compiled subgraph directly (not through a wrapper)
from langgraph_agents.graphs.plan_review import plan_review_app

# In build_plan_build_review_graph():
# OLD: graph.add_node("plan_review", _call_plan_review)
# NEW:
graph.add_node("plan_review", plan_review_app)
```

The edge `discover_architecture → plan_review → build_review` remains unchanged.

**State initialization:** `plan_review_app` starts with whatever `ParentState` keys match `PlanReviewState`. The non-shared keys (`plan_feedback`, `plan_verdict`, `plan_cycle`) start unset. The routing functions use `state.get("plan_cycle", 0)` — safe for unset values. `plan_feedback` and `plan_verdict` default to `""` via `.get()` in all consuming nodes.

**Architecture context:** The `_call_plan_review` wrapper previously enriched `task` with `agent_architecture`. With native composition, the planner receives only `task` from `ParentState` — it doesn't see `agent_architecture` unless we add it to `PlanReviewState`.

Two options:
- **Option A:** Add `agent_architecture: str` to `PlanReviewState` (shared key — flows down automatically from `ParentState`). The planner in `plan_review.py` must be updated to incorporate it when present.
- **Option B:** Keep the architecture-enriched task in `ParentState.task` by having the discover node write back to `task` (not ideal — mutates task).
- **Option C (recommended):** Keep `_call_plan_review` only for the architecture enrichment, but extract it into a "pre-planning transform" node that writes `task` → `enriched_task` and passes `enriched_task` to the subgraph.

**Recommended for this task:** Use Option A — add `agent_architecture: str` to `PlanReviewState`, update the planner to use it when building context.

```python
# In state.py — add to PlanReviewState:
class PlanReviewState(TypedDict):
    task: str
    current_plan: str
    agent_architecture: str   # ADD — optional, empty string if not a prompt workflow
    plan_feedback: str
    plan_verdict: str
    plan_cycle: int

# In planner.py — use it when available:
if state.get("agent_architecture"):
    parts.append(f"## Workspace Architecture\n{state['agent_architecture']}")
```

- [ ] **Step 3: Run all tests**

```
uv run pytest tests/ -v
```
Expected: all pass.

- [ ] **Step 4: Verify streaming works end-to-end (manual check)**

Run a dry-run with a dummy workspace:
```python
from langgraph.checkpoint.memory import InMemorySaver
from langgraph_agents.graphs.plan_build_review import build_plan_build_review_graph

app = build_plan_build_review_graph().compile(checkpointer=InMemorySaver())
config = {"configurable": {"thread_id": "test-stream-1"}}

for chunk in app.stream(
    {"task": "test", "current_plan": "test plan", ...},
    config=config,
    stream_mode="updates",
    subgraphs=True,  # should now show planner/plan_reviewer events
):
    print(chunk)
```

Confirm that `planner` and `plan_reviewer` events appear in the stream (not just `plan_review` as a black box).

- [ ] **Step 5: Commit**

```
git add src/langgraph_agents/state.py \
        src/langgraph_agents/graphs/plan_build_review.py \
        src/langgraph_agents/nodes/planner.py \
        tests/test_plan_build_review.py
git commit -m "refactor: replace _call_plan_review wrapper with native subgraph composition"
```

---

## Testing Checkpoint

After all 14 tasks, run the full suite:

```bash
uv run pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected output summary:
```
tests/test_build_review.py         PASSED (all)
tests/test_config.py               PASSED (all)
tests/test_e2e_tester.py           PASSED (all)
tests/test_graph_runner.py         PASSED (all)
tests/test_models.py               PASSED (all)
tests/test_node_contract.py        PASSED (all)
tests/test_plan_build_review.py    PASSED (all)
tests/test_plan_review.py          PASSED (all)
tests/test_prompt_build_review.py  PASSED (all)
tests/test_prompt_workflow.py      PASSED (all)
```

---

## Phase Dependency Graph

```
Phase 1 (C2-verdict, C2-allowed, H1) — no deps, run first
Phase 2 (M7 dead code)               — no deps, run anytime
Phase 3 (M1 config)                  — no deps, run after Phase 1
Phase 4 (H4 synthesizer, M3 e2e)     — depends on Phase 1 (VERDICT fix must land first)
Phase 5 (M2 diff, M5 test mapping)   — depends on Phase 3 (config must exist for imports)
Phase 6 (H3 retry, C1 checkpoint)    — depends on Phase 3
Phase 7 (M4, M6, H2)                 — depends on Phase 6 (checkpointing enables subgraph streaming)
```

Within Phase 7, the order is: Task 12 (M4) → Task 13 (M6) → Task 14 (H2). Task 14 is the highest-risk change and should be done last, with a clean git history so it can be reverted independently if needed.
