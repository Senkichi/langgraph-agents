# Combined LangGraph Workflow Improvements Plan

> **Consolidated from:**
> - `docs/superpowers/plans/2026-04-05-langgraph-improvements.md` (architecture review — 13 findings, 7 phases, 14 tasks)
> - `.planning/phases/workflow-efficiency/PLAN.md` (node/state/script audit — 5 phases, ~15 sub-tasks)
>
> **Goal:** Harden the langgraph-agents workflows for fault tolerance, correctness, token efficiency, and observability — addressing all findings from both audits in a single dependency-ordered sequence.

**Tech Stack:** Python 3.11+, LangGraph >= 1.1.4, langgraph-checkpoint-sqlite (Phase 7), pytest 8+, uv

---

## Conflict Resolutions

| Item | Superpowers | Workflow Efficiency | Resolution |
|------|-------------|---------------------|------------|
| VERDICT detection | Per-file regex `re.search` | Shared `parse_verdict()` in `node_contract.py` | **Efficiency wins** — DRYs 3 independent strategies into one utility |
| `allowed_tools=[""]` | Bug — change to `None` | Intended — document with constant | **Superpowers wins** — `None` is correct; `--json-schema` suppresses tools |
| APPROVE feedback in synthesizer | Add "do not regress" labels | Suppress APPROVE traces in prompt synthesizer | **Both needed** — complementary fixes for different synthesizer files |
| Budget caps | Centralized in `config.py` | Hardcoded `max_budget_usd=1.5` | **Superpowers wins** — Phase 1E is subsumed by config.py |
| Test command mapping | Direct file targeting | Non-Python file coverage | **Merge** — single rewrite covers both |

---

## Phase Dependency Graph

```
Phase 1 (Correctness)     ── no deps
Phase 2 (Dead Code)       ── no deps
Phase 3 (Config)          ── after Phase 2 (clean imports)
Phase 4 (Handoff Quality) ── after Phase 1 (verdict fix must land first)
Phase 5 (State Schema)    ── after Phase 4 (synthesizer changes must land first)
Phase 6 (Token + E2E)     ── after Phase 1, 3
Phase 7 (Fault Tolerance) ── after Phase 3
Phase 8 (Run Scripts)     ── after Phase 3, 5
Phase 9 (Architecture)    ── after Phase 7 (checkpointing enables subgraph streaming)
```

Phases 1 and 2 can run in parallel. Phases 4, 6, 7 can run in parallel after their deps.

---

## File Map

| Action | File | Phases |
|--------|------|--------|
| **Modify** | `src/langgraph_agents/node_contract.py` | 1 |
| **Modify** | `src/langgraph_agents/nodes/review_synthesizer.py` | 1, 4, 5 |
| **Modify** | `src/langgraph_agents/nodes/prompt_review_synthesizer.py` | 1, 4 |
| **Modify** | `src/langgraph_agents/nodes/e2e_tester.py` | 1, 6 |
| **Modify** | `src/langgraph_agents/claude_cli.py` | 1 |
| **Modify** | `src/langgraph_agents/graphs/build_review.py` | 1, 7 |
| **Modify** | `src/langgraph_agents/graphs/prompt_build_review.py` | 1, 7 |
| **Modify** | `src/langgraph_agents/tools/dev_tools.py` | 1, 2, 6 |
| **Modify** | `src/langgraph_agents/nodes/macro_reviewer.py` | 1, 3, 6 |
| **Modify** | `src/langgraph_agents/nodes/micro_reviewer.py` | 3, 6 |
| **Delete** | `src/langgraph_agents/llm.py` | 2 |
| **Delete** | `src/langgraph_agents/graphs/orchestrator.py` | 2 |
| **Delete** | `src/langgraph_agents/nodes/researcher.py` | 2 |
| **Delete** | `src/langgraph_agents/nodes/writer.py` | 2 |
| **Delete** | `src/langgraph_agents/tools/search.py` | 2 |
| **Delete** | `tests/test_orchestrator.py` | 2 |
| **Modify** | `src/langgraph_agents/state.py` | 2, 5, 8, 9 |
| **Create** | `src/langgraph_agents/config.py` | 3 |
| **Modify** | `src/langgraph_agents/nodes/planner.py` | 3, 9 |
| **Modify** | `src/langgraph_agents/nodes/plan_reviewer.py` | 3 |
| **Modify** | `src/langgraph_agents/nodes/coder.py` | 3, 5 |
| **Modify** | `src/langgraph_agents/nodes/prompt_engineer.py` | 3 |
| **Modify** | `src/langgraph_agents/nodes/behavioral_reviewer.py` | 3, 8 |
| **Modify** | `src/langgraph_agents/nodes/architectural_reviewer.py` | 3, 8 |
| **Modify** | `src/langgraph_agents/nodes/discover_architecture.py` | 3, 9 |
| **Modify** | `src/langgraph_agents/graphs/plan_review.py` | 7 |
| **Modify** | `src/langgraph_agents/graphs/plan_build_review.py` | 5, 7, 8, 9 |
| **Modify** | `src/langgraph_agents/graphs/prompt_workflow.py` | 7 |
| **Create** | `src/langgraph_agents/graph_runner.py` | 9 |
| **Modify** | `run_sync_opt_phase1.py` | 8 |
| **Modify** | `run_sync_opt_phase2.py` | 8 |
| **Modify** | `run_sync_opt_phase3.py` | 8 |
| **Modify** | All `run_*.py` scripts | 7, 8, 9 |
| **Create** | `tests/test_config.py` | 3 |
| **Create** | `tests/test_graph_runner.py` | 9 |
| **Modify** | `tests/test_build_review.py` | 1, 4, 5, 6 |
| **Modify** | `tests/test_plan_build_review.py` | 7, 9 |
| **Modify** | `tests/test_plan_review.py` | 7 |
| **Modify** | `tests/test_e2e_tester.py` | 6 |
| **Modify** | `tests/test_node_contract.py` | 1 |

---

## Phase 1: Correctness Fixes

*Zero-risk, independently testable, no schema changes. Ship first.*

---

### 1A: Shared `parse_verdict` + `extract_verdict_block` utilities

**Source:** Efficiency P1-A (superior to Superpowers Task 1)

**Problem:** Three files use three different VERDICT detection strategies:
- `review_synthesizer.py:43` — `"VERDICT:REVISE" in micro` (string containment)
- `prompt_review_synthesizer.py:22` — same string containment
- `e2e_tester.py:_parse_verdict` — `.strip().upper()` approach

`"VERDICT:REVISE" in text` misses `"VERDICT: REVISE"` (space after colon), silently treating REVISE as APPROVE. Additionally, `_extract_verdict_block` is defined only locally in `review_synthesizer.py` but needed in `prompt_review_synthesizer.py`.

**Files:**
- Modify: `src/langgraph_agents/node_contract.py`
- Modify: `src/langgraph_agents/nodes/review_synthesizer.py`
- Modify: `src/langgraph_agents/nodes/prompt_review_synthesizer.py`
- Modify: `src/langgraph_agents/nodes/e2e_tester.py`
- Modify: `tests/test_node_contract.py`
- Modify: `tests/test_build_review.py`

#### `node_contract.py` — add two shared utilities after existing validators

```python
def parse_verdict(text: str, *allowed: str) -> str:
    """Extract VERDICT: value from text, normalizing whitespace and case.

    Returns the first matching VERDICT: line value, uppercased and stripped.
    Falls back to "REVISE" if no VERDICT: line found (safe default — never silently approves).
    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("VERDICT:"):
            value = stripped.split(":", 1)[1].strip().upper()
            if not allowed or value in allowed:
                return value
    return "REVISE"


def extract_verdict_block(feedback: str) -> str:
    """Extract the structured verdict block starting at the VERDICT: line.

    Strips the agent's tool-use exploration traces that precede the verdict.
    Returns everything from the first VERDICT: line onward.
    """
    lines = feedback.splitlines()
    for i, line in enumerate(lines):
        if line.strip().upper().startswith("VERDICT:"):
            return "\n".join(lines[i:]).strip()
    return feedback.strip()
```

#### `review_synthesizer.py` — replace local detection + `_extract_verdict_block`

```python
# Remove the local _extract_verdict_block definition (lines 12-23).
# Add to imports:
from langgraph_agents.node_contract import extract_verdict_block, parse_verdict

# In synthesize_reviews():
# Replace:
#   micro_revise = "VERDICT:REVISE" in micro
#   macro_revise = "VERDICT:REVISE" in macro
# With:
micro_revise = parse_verdict(micro, "APPROVE", "REVISE") == "REVISE"
macro_revise = parse_verdict(macro, "APPROVE", "REVISE") == "REVISE"

# Replace all calls to _extract_verdict_block(x) with extract_verdict_block(x)
```

#### `prompt_review_synthesizer.py` — fix VERDICT detection

```python
# Add to imports:
from langgraph_agents.node_contract import extract_verdict_block, parse_verdict

# Replace:
#   behavioral_revise = "VERDICT:REVISE" in behavioral
#   architectural_revise = "VERDICT:REVISE" in architectural
# With:
behavioral_revise = parse_verdict(behavioral, "APPROVE", "REVISE") == "REVISE"
architectural_revise = parse_verdict(architectural, "APPROVE", "REVISE") == "REVISE"
```

#### `e2e_tester.py` — replace local `_parse_verdict` with shared utility

```python
# Add to imports:
from langgraph_agents.node_contract import parse_verdict

# Remove the local _parse_verdict() function entirely.

# In e2e_test(), replace:
#   verdict = _parse_verdict(response)
# With:
verdict = parse_verdict(response, "APPROVE", "REVISE", "SKIP")
```

#### Tests

**`tests/test_node_contract.py`** — add:

```python
from langgraph_agents.node_contract import parse_verdict, extract_verdict_block

class TestParseVerdict:
    def test_exact_match(self):
        assert parse_verdict("VERDICT:REVISE\nREASONING:Bug.", "APPROVE", "REVISE") == "REVISE"

    def test_space_after_colon(self):
        assert parse_verdict("VERDICT: REVISE\nREASONING:Bug.", "APPROVE", "REVISE") == "REVISE"

    def test_lowercase_input(self):
        assert parse_verdict("verdict: approve\nreasoning:ok", "APPROVE", "REVISE") == "APPROVE"

    def test_fallback_on_no_match(self):
        assert parse_verdict("No verdict here", "APPROVE", "REVISE") == "REVISE"

    def test_unallowed_value_falls_through(self):
        assert parse_verdict("VERDICT:UNKNOWN\nVERDICT:APPROVE", "APPROVE", "REVISE") == "APPROVE"

class TestExtractVerdictBlock:
    def test_strips_tool_traces(self):
        text = "Tool use: read file\nOutput: ...\nVERDICT:REVISE\nREASONING:Bug found."
        result = extract_verdict_block(text)
        assert result.startswith("VERDICT:REVISE")
        assert "Tool use" not in result

    def test_no_verdict_returns_full_text(self):
        text = "No verdict here"
        assert extract_verdict_block(text) == "No verdict here"
```

**`tests/test_build_review.py`** — add regression test:

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

**Commit:** `fix: consolidate verdict parsing into shared parse_verdict utility`

---

### 1B: Fix `allowed_tools=[""]` in `invoke_structured`

**Source:** Superpowers Task 2

**Problem:** `[""]` is truthy, so `invoke()` emits `--allowed-tools ""` — a tool named empty-string, not "no tools." Behavior is CLI-version-dependent and undocumented.

**File:** `src/langgraph_agents/claude_cli.py:129-137`

```python
# OLD:
raw = invoke(
    prompt,
    system_prompt=system_prompt,
    cwd=cwd,
    model=model,
    allowed_tools=[""],  # disable all tools for pure reasoning
    max_budget_usd=max_budget_usd,
    json_schema=schema,
)

# NEW:
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

**Verify:** `uv run pytest tests/test_plan_review.py -v` (plan_reviewer uses invoke_structured).

**Commit:** `fix: remove invalid allowed_tools=[''] in invoke_structured`

---

### 1C: Add `defer=True` to synthesizer fan-in nodes

**Source:** Superpowers Task 3

**Problem:** LangGraph docs require `defer=True` on fan-in nodes to guarantee they wait for all Send()-originated branches. Without it, the synthesizer may run before both reviewers complete.

**Files:**
- `src/langgraph_agents/graphs/build_review.py:47`
- `src/langgraph_agents/graphs/prompt_build_review.py:45`

```python
# build_review.py — OLD:
graph.add_node("synthesizer", synthesize_reviews)
# NEW:
graph.add_node("synthesizer", synthesize_reviews, defer=True)

# prompt_build_review.py — OLD:
graph.add_node("synthesizer", synthesize_prompt_reviews)
# NEW:
graph.add_node("synthesizer", synthesize_prompt_reviews, defer=True)
```

**Verify:** `uv run pytest tests/test_build_review.py::TestBuildReviewGraph tests/test_prompt_build_review.py -v`

**Commit:** `fix: add defer=True to synthesizer fan-in nodes`

---

### 1D: Fix `run_git_diff` to capture committed changes

**Source:** Efficiency P1-C

**Problem:** `dev_tools.py:run_git_diff` calls `git diff HEAD`. If the coder commits its work, `git diff HEAD` returns empty. The fallback `git diff` (no args) is always a subset and also empty after a clean commit. Result: `code_diff = "(no changes detected)"` — reviewers issue quality verdicts against nothing. The `non_empty` validator passes on the sentinel string.

**File:** `src/langgraph_agents/tools/dev_tools.py`

```python
def run_git_diff(workspace_path: str) -> str:
    """Capture changes made in the workspace.

    Tries in order:
    1. Uncommitted changes vs HEAD (working tree + staging area) — covers the common
       case where the agent writes files without committing.
    2. Last commit diff — covers the case where the agent committed its work.
    Returns the first non-empty result.
    """
    def _run(*args: str) -> str:
        result = subprocess.run(
            ["git"] + list(args),
            cwd=workspace_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout.strip()

    try:
        diff = _run("diff", "HEAD")
        if diff:
            return diff

        # Agent may have committed — check the most recent commit.
        # Verify at least one commit exists before attempting HEAD~1.
        commit_count = _run("rev-list", "--count", "HEAD")
        if commit_count.strip().isdigit() and int(commit_count.strip()) >= 1:
            diff = _run("show", "--patch", "--format=", "HEAD")
            if diff:
                return diff

        return "(no changes detected)"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "(git diff unavailable)"
```

**Note:** `git show --patch --format= HEAD` outputs the diff of the most recent commit without the commit header, identical in format to `git diff HEAD` output.

**Commit:** `fix: run_git_diff falls back to last commit when working tree is clean`

---

### 1E: Macro reviewer timeout parity

**Source:** Efficiency P1-B (budget caps deferred to Phase 3 config.py)

**Problem:** `macro_reviewer.py` omits `timeout=`, defaulting to 1800s vs `micro_reviewer.py`'s explicit 3600s.

**File:** `src/langgraph_agents/nodes/macro_reviewer.py:60-68`

```python
response = invoke_agent(
    content,
    system_prompt=SYSTEM_PROMPT,
    cwd=workspace,
    allowed_tools=REVIEW_TOOLS,
    model="sonnet",
    timeout=3600,          # add this line (parity with micro_reviewer)
)
```

**Commit:** `fix: add timeout=3600 to macro_reviewer for parity with micro_reviewer`

---

## Phase 2: Dead Code Removal

*Delete unused scaffolding. Reduces confusion and import surface.*

---

### 2A: Delete unused modules

**Source:** Superpowers Task 4

**Files to verify then delete:**
- `src/langgraph_agents/llm.py`
- `src/langgraph_agents/graphs/orchestrator.py`
- `src/langgraph_agents/nodes/researcher.py`
- `src/langgraph_agents/nodes/writer.py`
- `src/langgraph_agents/tools/search.py`
- `tests/test_orchestrator.py`

**Pre-check:**

```bash
grep -r "from langgraph_agents.llm" src/ tests/
grep -r "from langgraph_agents.graphs.orchestrator" src/ tests/
grep -r "from langgraph_agents.nodes.researcher" src/ tests/
grep -r "from langgraph_agents.nodes.writer" src/ tests/
grep -r "from langgraph_agents.tools.search" src/ tests/
grep -r "AgentState" src/ tests/
```

Expected: zero matches for each (except within the files themselves and `test_orchestrator.py`).

**Also remove `AgentState` from `state.py:8-13`:**

```python
# DELETE this entire class:
class AgentState(TypedDict):
    """Base state shared across all graph nodes."""
    messages: Annotated[list, add_messages]
    task: str
    result: str
```

Also remove the now-unused imports (`Annotated`, `add_messages`) if nothing else uses them.

**Verify:** `uv run pytest tests/ -v` — all tests pass, `test_orchestrator.py` is gone.

**Commit:** `chore: remove unused llm.py, orchestrator, researcher, writer, search stub`

---

### 2B: Delete LangChain tool functions from dev_tools.py

**Source:** Efficiency P1-E

**Problem:** `make_dev_tools()` and `make_review_tools()` create LangChain `@tool` callables. The current architecture routes all agent calls through `invoke_agent` -> `claude` CLI subprocess. These functions are never called and create architectural confusion.

**File:** `src/langgraph_agents/tools/dev_tools.py`

**Change:** Delete `make_dev_tools()`, `make_review_tools()`, and all imports used only by dead code (`glob as globlib`, `os`, `from langchain_core.tools import tool`). Keep only `run_git_diff()` and its imports.

The resulting file:

```python
"""Utilities for interacting with git in a workspace directory."""

import subprocess


def run_git_diff(workspace_path: str) -> str:
    # ... (updated implementation from 1D)
```

**Pre-check:** `grep -r "make_dev_tools\|make_review_tools" src/ tests/` — confirm no callers.

**Commit:** `chore: remove unused LangChain tool factory functions from dev_tools`

---

## Phase 3: Centralized Model Configuration

*Single source of truth for all model names, timeouts, and budgets. Subsumes Phase 1E's hardcoded timeout.*

---

### 3A: Create `config.py` and update all nodes

**Source:** Superpowers Task 5 (subsumes Efficiency P1-B budget caps)

#### Step 1: Create `src/langgraph_agents/config.py`

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
REVIEWER_BUDGET_USD: float = float(os.environ.get("REVIEWER_BUDGET_USD", "1.5"))
```

#### Step 2: Create `tests/test_config.py`

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
    importlib.reload(cfg)
    assert cfg.PLANNER_MODEL == "haiku"
    assert cfg.CODER_TIMEOUT == 300
    importlib.reload(cfg)
```

#### Step 3: Update `planner.py`

```python
from langgraph_agents.config import PLANNER_MODEL

# Change invoke call:
response = invoke(
    "\n\n".join(parts),
    system_prompt=SYSTEM_PROMPT,
    model=PLANNER_MODEL,   # was: model="opus"
)
```

#### Step 4: Update `plan_reviewer.py`

```python
from langgraph_agents.config import REVIEWER_MODEL

raw = invoke_structured(
    content,
    schema=PLAN_VERDICT_SCHEMA,
    system_prompt=SYSTEM_PROMPT,
    model=REVIEWER_MODEL,  # was: model="sonnet"
)
```

#### Step 5: Update `coder.py`

```python
from langgraph_agents.config import CODER_BUDGET_USD, CODER_MODEL, CODER_TIMEOUT

invoke_agent(
    context,
    system_prompt=CODER_SYSTEM_PROMPT,
    cwd=workspace,
    model=CODER_MODEL,               # was: model="sonnet"
    max_budget_usd=CODER_BUDGET_USD,  # was: missing
    timeout=CODER_TIMEOUT,            # was: timeout=7200
)
```

#### Step 6: Update `micro_reviewer.py`

```python
from langgraph_agents.config import REVIEWER_BUDGET_USD, REVIEWER_MODEL, REVIEWER_TIMEOUT

response = invoke_agent(
    content,
    system_prompt=SYSTEM_PROMPT,
    cwd=workspace,
    allowed_tools=REVIEW_TOOLS,
    model=REVIEWER_MODEL,               # was: model="sonnet"
    max_budget_usd=REVIEWER_BUDGET_USD,  # was: missing
    timeout=REVIEWER_TIMEOUT,            # was: timeout=3600
)
```

#### Step 7: Update `macro_reviewer.py`

```python
from langgraph_agents.config import REVIEWER_BUDGET_USD, REVIEWER_MODEL, REVIEWER_TIMEOUT

response = invoke_agent(
    content,
    system_prompt=SYSTEM_PROMPT,
    cwd=workspace,
    allowed_tools=REVIEW_TOOLS,
    model=REVIEWER_MODEL,               # was: model="sonnet"
    max_budget_usd=REVIEWER_BUDGET_USD,  # was: missing
    timeout=REVIEWER_TIMEOUT,            # was: missing (added in 1E)
)
```

#### Step 8: Update `e2e_tester.py`

```python
from langgraph_agents.config import E2E_BUDGET_USD, E2E_MODEL, E2E_TIMEOUT

response = invoke_agent(
    context,
    system_prompt=SYSTEM_PROMPT,
    cwd=workspace,
    allowed_tools=E2E_TOOLS,
    model=E2E_MODEL,                # was: model="sonnet"
    max_budget_usd=E2E_BUDGET_USD,  # was: max_budget_usd=2.0
    timeout=E2E_TIMEOUT,            # was: timeout=2700
)
```

#### Step 9: Update `prompt_engineer.py`, `behavioral_reviewer.py`, `architectural_reviewer.py`

All three: import appropriate config constants and use them. `prompt_engineer.py` gets `PROMPT_ENGINEER_MODEL` and `PROMPT_ENGINEER_TIMEOUT`. Behavioral and architectural reviewers get `REVIEWER_MODEL` and `REVIEWER_TIMEOUT`.

#### Step 10: Update `discover_architecture.py`

```python
from langgraph_agents.config import DISCOVER_MODEL

response = invoke_agent(
    ...,
    model=DISCOVER_MODEL,   # was: no model arg (used CLI default)
)
```

**Verify:** `uv run pytest tests/ -v`

**Commit:** `feat: centralize model/timeout/budget config in config.py`

---

## Phase 4: Handoff Quality

*Depends on Phase 1 (verdict fix must land first).*

---

### 4A: Synthesizer preserves APPROVE signal when paired with REVISE

**Source:** Superpowers Task 6

**Problem:** When micro APPROVEs and macro REVISEs (or vice versa), the coder gets no signal about what to preserve. It may regress the approved dimension while fixing the other, causing oscillation across cycles.

**Files:**
- Modify: `src/langgraph_agents/nodes/review_synthesizer.py:40-56`
- Modify: `tests/test_build_review.py`

#### Step 1: Update test expectations

The existing tests `test_micro_revise_omits_approve_feedback` and `test_macro_revise_omits_approve_feedback` assert that APPROVE feedback does NOT appear. These encode the old (buggy) behavior.

In `tests/test_build_review.py`, update:

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
    assert "Macro Review" in result["build_feedback"]
    assert "do not regress" in result["build_feedback"].lower() or "APPROVED" in result["build_feedback"]


def test_both_approve_no_preservation_noise(self):
    """When both approve, the feedback stays minimal — no spurious preservation sections."""
    state = self._base_state(
        micro_feedback="VERDICT:APPROVE\nREASONING:Looks good.",
        macro_feedback="VERDICT:APPROVE\nREASONING:Solid.",
    )
    result = synthesize_reviews(state)
    assert result["build_verdict"] == "APPROVE"
    assert "do not regress" not in result["build_feedback"].lower()
```

#### Step 2: Update `review_synthesizer.py`

Replace the feedback assembly block (lines 48-54):

```python
parts: list[str] = []

if micro_revise:
    parts.append(
        f"## Micro Review (REVISE — must fix)\n{extract_verdict_block(micro)}"
    )
elif macro_revise:
    # Micro approved but macro is revising — tell the coder what to preserve.
    parts.append(
        f"## Micro Review (APPROVED — do not regress these patterns)\n"
        f"{extract_verdict_block(micro)}"
    )

if macro_revise:
    parts.append(
        f"## Macro Review (REVISE — must fix)\n{extract_verdict_block(macro)}"
    )
elif micro_revise:
    # Macro approved but micro is revising — tell the coder what to preserve.
    parts.append(
        f"## Macro Review (APPROVED — do not regress these patterns)\n"
        f"{extract_verdict_block(macro)}"
    )

feedback = "\n\n".join(parts) if parts else "Both reviewers approved."
```

#### Step 3: Apply analogous fix to `prompt_review_synthesizer.py`

```python
def synthesize_prompt_reviews(state: PromptBuildState) -> dict:
    behavioral = state.get("behavioral_feedback", "")
    architectural = state.get("architectural_feedback", "")

    behavioral_revise = parse_verdict(behavioral, "APPROVE", "REVISE") == "REVISE"
    architectural_revise = parse_verdict(architectural, "APPROVE", "REVISE") == "REVISE"

    verdict = "REVISE" if (behavioral_revise or architectural_revise) else "APPROVE"

    parts: list[str] = []
    if behavioral_revise:
        parts.append(f"## Behavioral Review (REVISE — must fix)\n{extract_verdict_block(behavioral)}")
    elif architectural_revise:
        parts.append(
            f"## Behavioral Review (APPROVED — do not regress these patterns)\n{extract_verdict_block(behavioral)}"
        )

    if architectural_revise:
        parts.append(f"## Architectural Review (REVISE — must fix)\n{extract_verdict_block(architectural)}")
    elif behavioral_revise:
        parts.append(
            f"## Architectural Review (APPROVED — do not regress these patterns)\n{extract_verdict_block(architectural)}"
        )

    feedback = "\n\n".join(parts) if parts else "Both reviewers approved."

    return {"build_verdict": verdict, "build_feedback": feedback}
```

**Verify:** `uv run pytest tests/test_build_review.py tests/test_prompt_build_review.py -v`

**Commit:** `feat: preserve approved-reviewer signal in synthesizer to prevent coder oscillation`

---

## Phase 5: State Schema Extensions

*Depends on Phase 4 (synthesizer changes must land first).*

---

### 5A: `resolved_issues` regression contract

**Source:** Efficiency P3-A

**Problem:** The coder has no mechanism to know which issues were fixed in a prior build cycle. It can re-introduce a regression, and reviewers can re-raise issues already addressed.

#### `state.py` — add field to `BuildReviewState`

```python
class BuildReviewState(TypedDict):
    task: str
    current_plan: str
    code_diff: str
    workspace_path: str
    micro_feedback: str
    macro_feedback: str
    build_verdict: str
    build_feedback: str
    build_cycle: int
    e2e_feedback: str
    resolved_issues: list[str]   # confirmed-fixed CRITICAL/MAJOR issues
```

#### `plan_build_review.py:_call_build_review` — initialize

```python
subgraph_input: BuildReviewState = {
    ...
    "e2e_feedback": e2e_feedback,
    "resolved_issues": [],       # starts empty; synthesizer accumulates
}
```

#### `review_synthesizer.py` — extract and accumulate

```python
def _extract_critical_major_issues(feedback_block: str) -> list[str]:
    """Extract file:line issue descriptions from CRITICAL and MAJOR sections."""
    issues: list[str] = []
    in_target_section = False
    for line in feedback_block.splitlines():
        if line.startswith(("CRITICAL:", "MAJOR:")):
            in_target_section = True
        elif line.startswith(("MINOR:", "VERDICT:", "REASONING:", "##")):
            in_target_section = False
        elif in_target_section and line.startswith("- "):
            issues.append(line[2:].strip())
    return issues


def synthesize_reviews(state: BuildReviewState) -> dict:
    # ... existing verdict + feedback logic from Phase 4A ...

    # Accumulate resolved issues: when verdict is APPROVE and there was prior
    # REVISE feedback, those CRITICAL/MAJOR issues are now confirmed fixed.
    existing_resolved = list(state.get("resolved_issues", []))
    new_resolved: list[str] = []
    if verdict == "APPROVE" and state.get("build_feedback"):
        new_resolved = _extract_critical_major_issues(state["build_feedback"])
    resolved_issues = existing_resolved + new_resolved

    return {
        "build_verdict": verdict,
        "build_feedback": feedback,
        "resolved_issues": resolved_issues,
    }
```

#### `coder.py:_build_coder_context` — inject as "Do Not Reintroduce"

```python
def _build_coder_context(state: BuildReviewState) -> str:
    parts = [f"## Task\n{state['task']}", f"## Approved Plan\n{state['current_plan']}"]

    resolved = state.get("resolved_issues", [])
    if resolved:
        issue_list = "\n".join(f"- {issue}" for issue in resolved)
        parts.append(
            "## Do Not Reintroduce (confirmed fixed in a prior cycle — keep these passing)\n"
            + issue_list
        )

    if state.get("e2e_feedback"):
        parts.append(
            "## End-to-End Test Findings (address these FIRST)\n"
            f"{state['e2e_feedback']}"
        )
    if state.get("build_feedback"):
        parts.append(f"## Reviewer Feedback\n{state['build_feedback']}")
        if state.get("code_diff"):
            parts.append(f"## Current Code Diff\n```diff\n{state['code_diff']}\n```")

    return "\n\n".join(parts)
```

**Tests:** `tests/test_build_review.py` — add:
- `test_synthesizer_accumulates_resolved_issues_on_approve`
- `test_synthesizer_does_not_populate_resolved_on_revise`
- `test_synthesizer_preserves_existing_resolved_issues`

**Commit:** `feat: add resolved_issues tracking to prevent coder regressions across cycles`

---

### 5B: `persistent_rules` accumulation

**Source:** Efficiency P5-B

**Problem:** Lessons learned in cycle 1 (e.g., "always use context managers for DB connections") are lost in cycle 2 when `build_feedback` is overwritten.

#### `state.py` — add to `BuildReviewState`

```python
persistent_rules: str  # constraint list derived from resolved CRITICALs; bounded at 5 rules
```

#### `review_synthesizer.py` — derive rules from resolved CRITICALs

```python
_MAX_PERSISTENT_RULES = 5

def _derive_rule(issue_line: str) -> str:
    """Convert a resolved CRITICAL issue line to a brief constraint rule.

    Input:  "foo.py:42 — bare except swallows all errors — ACTION: catch specific types"
    Output: "Catch specific exception types, never bare except."
    """
    if " — ACTION: " in issue_line:
        action = issue_line.split(" — ACTION: ", 1)[1].strip()
        rule = action[0].upper() + action[1:]
        return rule if rule.endswith(".") else rule + "."
    return issue_line.strip()


def synthesize_reviews(state: BuildReviewState) -> dict:
    # ... existing logic ...

    # Derive persistent rules from newly resolved CRITICAL issues only
    existing_rules_text = state.get("persistent_rules", "").strip()
    existing_rules = [r for r in existing_rules_text.splitlines() if r.strip()]

    new_critical: list[str] = []
    if verdict == "APPROVE" and state.get("build_feedback"):
        in_critical = False
        for line in state["build_feedback"].splitlines():
            if line.startswith("CRITICAL:"):
                in_critical = True
            elif line.startswith(("MAJOR:", "MINOR:", "VERDICT:", "##")):
                in_critical = False
            elif in_critical and line.startswith("- "):
                new_critical.append(line[2:].strip())

    new_rules = [_derive_rule(issue) for issue in new_critical]
    all_rules = existing_rules + new_rules
    # Deduplicate (preserve order, keep last occurrence) and cap
    seen: set[str] = set()
    deduped: list[str] = []
    for rule in reversed(all_rules):
        if rule not in seen:
            seen.add(rule)
            deduped.insert(0, rule)
    persistent_rules = "\n".join(deduped[:_MAX_PERSISTENT_RULES])

    return {
        "build_verdict": verdict,
        "build_feedback": feedback,
        "resolved_issues": resolved_issues,
        "persistent_rules": persistent_rules,
    }
```

#### `coder.py:_build_coder_context` — inject as "Engineering Constraints"

```python
# Insert after task/plan block, before DO NOT REINTRODUCE:
if state.get("persistent_rules"):
    parts.append(
        "## Engineering Constraints (learned from prior cycles — treat as hard rules)\n"
        + state["persistent_rules"]
    )
```

#### `plan_build_review.py:_call_build_review` — initialize

```python
subgraph_input: BuildReviewState = {
    ...
    "resolved_issues": [],
    "persistent_rules": "",
}
```

**Commit:** `feat: accumulate persistent_rules from resolved CRITICALs across build cycles`

---

## Phase 6: Token Efficiency & E2E Improvements

*Depends on Phases 1 and 3.*

---

### 6A: E2E regression checklist

**Source:** Merged — Superpowers Task 7 + Efficiency P4-A

**Problem:** The e2e tester is stateless to avoid anchoring bias. But on cycle 2, it re-discovers issues already addressed. Lightweight mitigation: inject only PROPOSED FIXES as verification checklist.

**File:** `src/langgraph_agents/nodes/e2e_tester.py`

```python
def _extract_proposed_fixes(report: str) -> str:
    """Extract only the PROPOSED FIXES block from a prior e2e report.

    Returns an empty string if the block is not found. Deliberately narrow —
    passes only actionable fixes to avoid anchoring the current evaluation.
    """
    lines = report.splitlines()
    in_fixes = False
    fixes_lines: list[str] = []

    for line in lines:
        if line.startswith("PROPOSED FIXES:"):
            in_fixes = True
            # Include content on the same line after the header
            rest = line.split(":", 1)[1].strip()
            if rest:
                fixes_lines.append(rest)
        elif in_fixes:
            if line.startswith("VERDICT:") or (
                line.isupper() and line.endswith(":") and len(line) > 2
            ):
                break
            fixes_lines.append(line)

    return "\n".join(fixes_lines).strip()
```

In `_build_e2e_context`, after existing content assembly:

```python
# On subsequent cycles, surface prior proposed fixes as a regression checklist.
# Intentionally does NOT include the full prior e2e_report (anti-anchoring).
e2e_cycle = state.get("e2e_cycle", 0)
if e2e_cycle > 0:
    prior_fixes = _extract_proposed_fixes(state.get("e2e_report", ""))
    if prior_fixes:
        parts.append(
            "## Regression Checklist (from prior e2e cycle)\n"
            "The following fixes were requested in the previous cycle. "
            "Verify that they were applied, but evaluate the overall workspace "
            "independently — do not assume success just because they were requested.\n\n"
            + prior_fixes
        )
```

**Tests:** `tests/test_e2e_tester.py` — add:
- `test_extract_proposed_fixes_returns_section_content`
- `test_extract_proposed_fixes_returns_empty_when_absent`
- `test_build_e2e_context_includes_prior_fixes_on_reentry`
- `test_build_e2e_context_omits_prior_fixes_on_first_cycle`

**Commit:** `feat: add regression checklist to e2e tester on repeat cycles`

---

### 6B: Test command mapping — direct file targeting + non-Python coverage

**Source:** Merged — Superpowers Task 9 + Efficiency P1-D

**Problem:** `_suggest_test_commands` uses fuzzy `-k` matching (hits unrelated tests) and silently ignores non-Python files (SQL migrations, YAML configs, Jinja2 templates).

**File:** `src/langgraph_agents/nodes/e2e_tester.py`

```python
def _suggest_test_commands(changed_files: list[str]) -> str:
    """Map changed source files to targeted test commands.

    Prefers direct test file paths (tests/test_<module>.py) over -k matching.
    Also surfaces changed non-Python files for manual test discovery.
    """
    import os

    commands: list[str] = []
    non_python_changed: list[str] = []
    seen: set[str] = set()

    for f in changed_files:
        if not f.endswith(".py"):
            non_python_changed.append(f)
            continue
        if "/test_" in f or f.startswith("test_"):
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

    section_parts: list[str] = []

    if commands:
        section_parts.append("## Suggested Test Commands\n" + "\n".join(commands))

    if non_python_changed:
        file_list = "\n".join(f"- `{f}`" for f in sorted(non_python_changed)[:10])
        section_parts.append(
            "## Changed Non-Python Files (locate tests manually)\n" + file_list
        )

    return "\n\n".join(section_parts)
```

**Commit:** `perf: direct test file targeting + non-Python file coverage in e2e test suggestions`

---

### 6C: Bound code diff size

**Source:** Superpowers Task 8

**Problem:** On build_cycle 4, the coder's prompt contains the entire cumulative diff — potentially tens of thousands of tokens. Reviewers see the same problem.

**File:** `src/langgraph_agents/tools/dev_tools.py` — add at bottom:

```python
DIFF_MAX_CHARS = 16_000

def truncate_diff(diff: str) -> str:
    """Truncate a large diff, keeping the tail (most recent changes).

    Keeps the tail since earlier changes are already reflected in the workspace.
    Finds a hunk boundary to avoid mid-hunk splits.
    """
    if len(diff) <= DIFF_MAX_CHARS:
        return diff
    truncated = diff[-DIFF_MAX_CHARS:]
    hunk_start = truncated.find("\n@@")
    if hunk_start > 0:
        truncated = truncated[hunk_start + 1:]
    return f"[diff truncated — showing last {len(truncated)} chars]\n{truncated}"
```

**Consumers:** Import and apply in `coder.py`, `micro_reviewer.py`, `macro_reviewer.py`:

```python
from langgraph_agents.tools.dev_tools import truncate_diff

# In coder.py _build_coder_context:
if state.get("code_diff"):
    diff = truncate_diff(state["code_diff"])
    parts.append(f"## Current Code Diff\n```diff\n{diff}\n```")

# In micro_reviewer.py and macro_reviewer.py — same pattern for code_diff in content
```

**Tests:** `tests/test_build_review.py` — add `TestDiffTruncation`:

```python
from langgraph_agents.tools.dev_tools import truncate_diff, DIFF_MAX_CHARS

class TestDiffTruncation:
    def test_short_diff_unchanged(self):
        diff = "diff --git a/foo.py b/foo.py\n+hello"
        assert truncate_diff(diff) == diff

    def test_long_diff_is_truncated(self):
        long_diff = "@@ -1 +1 @@\n" + "+" + "x" * (DIFF_MAX_CHARS + 500)
        result = truncate_diff(long_diff)
        assert len(result) < len(long_diff)
        assert "truncated" in result

    def test_truncated_diff_starts_at_hunk_boundary(self):
        prefix = "x" * (DIFF_MAX_CHARS + 100)
        suffix = "\n@@ -10 +10 @@\n+new line\n"
        long_diff = prefix + suffix
        result = truncate_diff(long_diff)
        assert result.startswith("@@ -10 +10 @@") or "truncated" in result
```

**Commit:** `perf: bound code diff to 16k chars to prevent unbounded token growth`

---

### 6D: Truncate plan context in reviewers

**Source:** Efficiency P5-D

**Problem:** For large plans (5,000-8,000 chars), full plan in reviewer context wastes tokens. Reviewers have `Read`/`Glob` workspace access for the full plan.

**Files:** `src/langgraph_agents/nodes/micro_reviewer.py`, `src/langgraph_agents/nodes/macro_reviewer.py`

```python
_PLAN_CONTEXT_LIMIT = 1500  # chars; full plan available via workspace Read if needed

def _truncate_plan_for_reviewer(plan: str) -> str:
    if len(plan) <= _PLAN_CONTEXT_LIMIT:
        return plan
    return (
        plan[:_PLAN_CONTEXT_LIMIT]
        + f"\n\n... [plan truncated at {_PLAN_CONTEXT_LIMIT} chars — "
        "read the full plan from the workspace if alignment verification requires it]"
    )
```

In both reviewer `invoke_agent` content strings, replace:
```python
f"## Plan\n{state['current_plan']}\n\n"
```
with:
```python
f"## Plan\n{_truncate_plan_for_reviewer(state['current_plan'])}\n\n"
```

**Risk note:** Monitor macro reviewer REVISE rates after deployment — a drop may indicate it's missing plan details.

**Commit:** `perf: truncate plan context in reviewer prompts to 1500 chars`

---

## Phase 7: Fault Tolerance

*Depends on Phase 3 (config must exist).*

---

### 7A: RetryPolicy on all subprocess-backed nodes

**Source:** Superpowers Task 10

**Problem:** A single transient error (network blip, subprocess killed) propagates as an unhandled exception, aborting the entire workflow with no retry.

**Files:** All graph files.

#### `build_review.py`

```python
from langgraph.types import RetryPolicy, Send  # add RetryPolicy to existing import

_SUBPROCESS_RETRY = RetryPolicy(
    max_attempts=3,
    initial_interval=2.0,
    retry_on=RuntimeError,  # claude CLI raises RuntimeError on non-zero exit
)

# In build_build_review_graph():
graph.add_node("coder", code, retry_policy=_SUBPROCESS_RETRY)
graph.add_node("micro_reviewer", micro_review, retry_policy=_SUBPROCESS_RETRY)
graph.add_node("macro_reviewer", macro_review, retry_policy=_SUBPROCESS_RETRY)
graph.add_node("synthesizer", synthesize_reviews, defer=True)  # pure Python — no retry
```

#### `prompt_build_review.py`

```python
from langgraph.types import RetryPolicy, Send

_SUBPROCESS_RETRY = RetryPolicy(max_attempts=3, initial_interval=2.0, retry_on=RuntimeError)

graph.add_node("prompt_engineer", prompt_engineer, retry_policy=_SUBPROCESS_RETRY)
graph.add_node("behavioral_reviewer", behavioral_review, retry_policy=_SUBPROCESS_RETRY)
graph.add_node("architectural_reviewer", architectural_review, retry_policy=_SUBPROCESS_RETRY)
graph.add_node("synthesizer", synthesize_prompt_reviews, defer=True)
```

#### `plan_review.py`

```python
from langgraph.types import RetryPolicy

_SUBPROCESS_RETRY = RetryPolicy(max_attempts=3, initial_interval=2.0, retry_on=RuntimeError)

graph.add_node("planner", plan, retry_policy=_SUBPROCESS_RETRY)
graph.add_node("plan_reviewer", review_plan, retry_policy=_SUBPROCESS_RETRY)
```

#### `plan_build_review.py`

Skip RetryPolicy on wrapper nodes (`_call_plan_review`, `_call_build_review`) — they invoke subgraphs, and re-running the entire subgraph on failure is wasteful and incorrect.

Apply only to `e2e_test`:
```python
from langgraph.types import RetryPolicy

_SUBPROCESS_RETRY = RetryPolicy(max_attempts=3, initial_interval=2.0, retry_on=RuntimeError)

graph.add_node("e2e_test", e2e_test, retry_policy=_SUBPROCESS_RETRY)
```

#### `prompt_workflow.py`

```python
graph.add_node("discover_architecture", discover_architecture, retry_policy=_SUBPROCESS_RETRY)
```

**Test:** `tests/test_build_review.py` — add:

```python
def test_coder_node_has_retry_policy(self):
    from langgraph_agents.graphs.build_review import build_build_review_graph
    graph = build_build_review_graph()
    compiled = graph.compile()
    assert compiled is not None  # graph compiles cleanly with RetryPolicy
```

**Commit:** `feat: add RetryPolicy to all subprocess-backed nodes`

---

### 7B: Checkpointing on all compiled graphs

**Source:** Superpowers Task 11

**Problem:** No checkpointer means a crash at any point in an 8-hour workflow restarts from scratch.

**Design:** Checkpointers are injected at compile time. Graphs stay checkpointer-agnostic. Add a `compile_*()` factory to each graph module accepting an optional checkpointer, defaulting to `InMemorySaver`.

#### Refactor pattern (apply to all 5 graph modules):

```python
# In build_review.py — remove old global:
# build_review_app = build_build_review_graph().compile()

# Add compile factory:
def compile_build_review(checkpointer=None):
    """Compile the build-review graph with an optional checkpointer."""
    from langgraph.checkpoint.memory import InMemorySaver
    cp = checkpointer if checkpointer is not None else InMemorySaver()
    return build_build_review_graph().compile(checkpointer=cp)

# Keep default instance:
build_review_app = compile_build_review()
```

Apply identical refactor to:
- `plan_review.py` -> `compile_plan_review()`
- `prompt_build_review.py` -> `compile_prompt_build_review()`
- `plan_build_review.py` -> `compile_plan_build_review()`
- `prompt_workflow.py` -> `compile_prompt_workflow()`

#### Update all `run_*.py` scripts to pass `thread_id`:

```python
import uuid

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

**Test:** `tests/test_plan_build_review.py` — add:

```python
def test_graph_supports_checkpointing():
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph_agents.graphs.plan_build_review import build_plan_build_review_graph

    graph = build_plan_build_review_graph()
    app = graph.compile(checkpointer=InMemorySaver())
    assert app is not None
    config = {"configurable": {"thread_id": "test-thread-1"}}
    state = app.get_state(config)
    assert state is not None
```

**Commit:** `feat: add checkpointing to all graphs — enables resume-on-failure`

---

## Phase 8: Run Script & Prompt Workflow Improvements

*Depends on Phases 3 and 5.*

---

### 8A: Separate task summary from plan text in sync optimization runners

**Source:** Efficiency P2-A

**Problem:** `run_sync_opt_phase1.py:133`, `run_sync_opt_phase2.py:133`, `run_sync_opt_phase3.py:120` all set `current_plan=TASK` where `TASK` is a 3,000+ character combined task+plan document. This causes the full plan content to be duplicated twice in every coder call, and the plan reviewer to evaluate a task description as an implementation plan.

**Pattern for each file:** Extract a short `TASK_SUMMARY` (2-4 sentences) and use existing `TASK` as `current_plan`.

#### `run_sync_opt_phase1.py`

```python
TASK_SUMMARY = """\
Implement Gmail message-level deduplication and parse failure log dedup in job-cannon.
Eliminates re-fetching and re-parsing ~1,100 already-seen Gmail messages per sync.
Constraints: uv run pytest only, raw SQLite SQL, Python type hints on all new signatures.
"""

# In main():
result = plan_build_review_app.invoke({
    "task": TASK_SUMMARY,       # was: TASK
    "current_plan": TASK,       # unchanged
    ...
})
```

#### `run_sync_opt_phase2.py`

```python
TASK_SUMMARY = """\
Implement pre-ingestion batch dedup and runs table pruning in job-cannon's pipeline_runner.py.
Eliminates ~1,080 unnecessary scorer/upsert/company-update calls per sync; bounds runs table at <10K rows.
Constraints: uv run pytest only, raw SQLite SQL, Python type hints on all new signatures.
"""
```

#### `run_sync_opt_phase3.py`

```python
TASK_SUMMARY = """\
Refactor DataForSEO source in job-cannon to submit tasks at ingestion start,
poll for results after Gmail and Thordata finish — overlapping DataForSEO's 60-120s processing
with Gmail's 60-80s fetch. Constraints: uv run pytest only, backward-compat fetch_jobs() preserved.
"""
```

**Note:** `run_test_audit_A/B/C.py` already have separate TASK and PLAN variables — no changes needed.

**Commit:** `fix: separate task summary from plan text in sync optimization runners`

---

### 8B: Prompt workflow reviewer verdict format upgrade

**Source:** Efficiency P5-A

**Problem:** `behavioral_reviewer.py` and `architectural_reviewer.py` use the old flat verdict format (`ISSUES:<comma-separated>`). The code reviewers use severity-structured format (`CRITICAL:/MAJOR:/MINOR:` with file:line and ACTION). The prompt engineer receives weaker, less actionable feedback.

**Files:** `src/langgraph_agents/nodes/behavioral_reviewer.py`, `src/langgraph_agents/nodes/architectural_reviewer.py`

In both files, replace the verdict format instructions at the end of `SYSTEM_PROMPT`:

```python
# Remove:
"End your response with your final verdict using EXACTLY this format:\n"
"VERDICT:<APPROVE or REVISE>\n"
"REASONING:<your reasoning>\n"
"ISSUES:<comma-separated list of issues, or NONE>\n"
"SUGGESTIONS:<comma-separated list of suggestions, or NONE>"

# Replace with (behavioral):
"End your response with your final verdict using EXACTLY this format:\n\n"
"VERDICT:<APPROVE or REVISE>\n"
"REASONING:<1-3 sentences>\n\n"
"If REVISE, categorize every issue by severity. Each issue MUST include\n"
"the file path, approximate line number, and a concrete ACTION to take:\n\n"
"CRITICAL:\n"
"- <file>:<line> — <what is wrong> — ACTION: <specific fix>\n\n"
"MAJOR:\n"
"- <file>:<line> — <what is wrong> — ACTION: <specific fix>\n\n"
"MINOR:\n"
"- <suggestion, not a blocker>\n\n"
"Omit empty severity sections.\n"
"CRITICAL = instruction that will cause wrong behavior or contradicts existing prompts.\n"
"MAJOR = ambiguous instruction, missing edge case, intent-instruction gap.\n"
"MINOR = clarity improvement, naming, minor phrasing."
```

```python
# Replace with (architectural):
# Same structure, different severity definitions:
"CRITICAL = isolation boundary violation, contract break, or dependency inconsistency.\n"
"MAJOR = wrong abstraction layer, incomplete downstream update, duplication risk.\n"
"MINOR = naming consistency, minor structural improvement."
```

**Note:** `prompt_review_synthesizer.py` already handles extraction via `extract_verdict_block` after Phase 1 changes. No synthesizer changes needed for this.

**Commit:** `feat: upgrade prompt workflow reviewers to severity-structured verdict format`

---

### 8C: Optional plan review bypass for pre-validated plans

**Source:** Efficiency P5-C

**Problem:** Callers with pre-written, externally validated plans still run a full Sonnet structured-output call to review a plan they already validated. Adds latency with no quality improvement.

#### `state.py` — add to `ParentState`

```python
class ParentState(TypedDict):
    task: str
    current_plan: str
    current_code: str
    workspace_path: str
    e2e_verdict: str
    e2e_report: str
    e2e_cycle: int
    skip_plan_review: bool  # True = bypass plan_review, go straight to build_review
```

#### `plan_build_review.py` — conditional routing on START

```python
def _route_entry(state: ParentState) -> str:
    """Skip plan review when caller has a pre-validated plan."""
    if state.get("skip_plan_review"):
        return "build_review"
    return "plan_review"


def build_plan_build_review_graph() -> StateGraph:
    graph = StateGraph(ParentState)
    graph.add_node("plan_review", _call_plan_review)
    graph.add_node("build_review", _call_build_review)
    graph.add_node("e2e_test", e2e_test)

    # Replace unconditional START -> plan_review with conditional routing
    graph.add_conditional_edges(
        START,
        _route_entry,
        {"plan_review": "plan_review", "build_review": "build_review"},
    )
    graph.add_edge("plan_review", "build_review")
    graph.add_edge("build_review", "e2e_test")
    graph.add_conditional_edges(
        "e2e_test",
        _route_after_e2e,
        {END: END, "build_review": "build_review"},
    )
    return graph
```

**Run scripts that should set `skip_plan_review=True`:**
- `run_test_audit_A.py`, `run_test_audit_B.py`, `run_test_audit_C.py` — externally audited plans
- `run_companies_audit.py` — plan loaded from file
- `run_sync_opt_phase1.py`, `run_sync_opt_phase2.py`, `run_sync_opt_phase3.py` — after 8A separates task from plan

**Default:** `False` — existing scripts that don't pass the field are unaffected.

**Tests:** `tests/test_plan_build_review.py` — add:
- `test_skip_plan_review_routes_start_to_build_review`
- `test_no_skip_routes_start_to_plan_review`

**Commit:** `feat: add skip_plan_review flag to bypass plan review for pre-validated plans`

---

## Phase 9: Architecture Improvements

*Depends on Phase 7 (checkpointing enables subgraph streaming). Order: 9A -> 9B -> 9C.*

---

### 9A: Add `discover_architecture` to `plan_build_review` workflow

**Source:** Superpowers Task 12

**Problem:** The planner and coder in `plan_build_review` operate without any knowledge of existing workspace architecture. Produces plans that miss conventions.

#### `state.py` — add `agent_architecture` to `ParentState`

```python
class ParentState(TypedDict):
    task: str
    current_plan: str
    current_code: str
    workspace_path: str
    agent_architecture: str  # compressed workspace architecture summary
    e2e_verdict: str
    e2e_report: str
    e2e_cycle: int
    skip_plan_review: bool
```

#### `discover_architecture.py` — generalize state type

```python
from typing import Any

@validate_node(
    pre={"workspace_path": is_path},
    post={"agent_architecture": non_empty},
)
def discover_architecture(state: Any) -> dict:  # accepts both ParentState and PromptWorkflowState
    """Scan the workspace and produce a compressed architecture summary."""
    ...
```

#### `plan_build_review.py` — add discover node

```python
from langgraph_agents.nodes.discover_architecture import discover_architecture

def _call_plan_review(state: ParentState) -> dict:
    """Wrapper: enriches task with architecture context."""
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

# Update routing — integrate with skip_plan_review from 8C:
def _route_entry(state: ParentState) -> str:
    if state.get("skip_plan_review"):
        return "build_review"
    return "discover_architecture"

graph.add_conditional_edges(
    START,
    _route_entry,
    {"discover_architecture": "discover_architecture", "build_review": "build_review"},
)
graph.add_edge("discover_architecture", "plan_review")
graph.add_edge("plan_review", "build_review")
graph.add_edge("build_review", "e2e_test")
graph.add_conditional_edges("e2e_test", _route_after_e2e, {END: END, "build_review": "build_review"})
```

**Tests:** `tests/test_plan_build_review.py` — add:
- `test_graph_has_discover_architecture_node`
- `test_discover_runs_before_plan_review`

**Commit:** `feat: add discover_architecture node to plan_build_review workflow`

---

### 9B: Async streaming runner

**Source:** Superpowers Task 13

**Problem:** All workflows use blocking `.invoke()`. For 2-hour runs, the caller gets zero feedback — impossible to distinguish "running" from "hung."

**Create:** `src/langgraph_agents/graph_runner.py`

```python
"""Streaming and synchronous runners for LangGraph workflows.

Provides:
- stream_graph: async generator that yields (node_name, state_update) pairs
  with console progress output.
- run_graph: thin synchronous wrapper with consistent thread_id config handling.
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
    """Async generator that streams node-level updates from a graph."""
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

    Prefer over app.invoke() for long-running workflows — provides
    node-level progress visibility while remaining synchronous.
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

**Tests:** `tests/test_graph_runner.py`

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock

from langgraph_agents.graph_runner import stream_graph, run_graph


async def async_generator(items):
    for item in items:
        yield item


async def collect_stream(app, inputs, config):
    results = []
    async for node_name, update in stream_graph(app, inputs, config):
        results.append((node_name, update))
    return results


class TestStreamGraph:
    def test_stream_graph_yields_node_updates(self):
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
        mock_app = MagicMock()
        mock_app.invoke = MagicMock(return_value={"result": "done"})
        result = run_graph(mock_app, {"task": "x"}, {"configurable": {"thread_id": "t1"}})
        assert result == {"result": "done"}
        mock_app.invoke.assert_called_once()
```

**Commit:** `feat: add streaming graph runner with node-level progress output`

---

### 9C: Native subgraph composition (prototype — highest risk)

**Source:** Superpowers Task 14

**Problem:** Wrapper nodes that call `app.invoke()` inside a node function are opaque to LangGraph's orchestration. Streaming with `subgraphs=True` doesn't work; checkpointing doesn't extend into subgraph boundaries.

**Scope:** `_call_plan_review` in `plan_build_review.py` only. `_call_build_review` is more complex and is a documented follow-up.

**Design:** When a compiled subgraph is added via `graph.add_node("plan_review", plan_review_app)`, LangGraph:
1. Passes matching keys from parent -> subgraph state
2. Merges matching keys from subgraph output -> parent state
3. Non-shared keys stay isolated

`ParentState` and `PlanReviewState` share: `task`, `current_plan`.
Non-shared in `PlanReviewState`: `plan_feedback`, `plan_verdict`, `plan_cycle` — stay isolated.

#### `state.py` — add `agent_architecture` to `PlanReviewState`

```python
class PlanReviewState(TypedDict):
    task: str
    current_plan: str
    agent_architecture: str   # shared key with ParentState — flows down automatically
    plan_feedback: str
    plan_verdict: str
    plan_cycle: int
```

#### `plan_build_review.py` — replace wrapper with native subgraph

```python
# REMOVE: _call_plan_review function entirely
# REMOVE: PlanReviewState import (no longer needed in this file)

from langgraph_agents.graphs.plan_review import plan_review_app

# In build_plan_build_review_graph():
graph.add_node("plan_review", plan_review_app)  # native subgraph
```

#### `planner.py` — use `agent_architecture` when available

```python
if state.get("agent_architecture"):
    parts.append(f"## Workspace Architecture\n{state['agent_architecture']}")
```

**Risk:** Highest-complexity change. Do last with clean git history for independent revert.

**Test:** `tests/test_plan_build_review.py` — add:

```python
def test_plan_review_visible_in_subgraph_stream():
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph_agents.graphs.plan_build_review import build_plan_build_review_graph

    graph = build_plan_build_review_graph()
    compiled = graph.compile(checkpointer=InMemorySaver())
    graph_data = compiled.get_graph(xray=True)
    all_node_names = {n for n in graph_data.nodes.keys()}
    assert "plan_review" in all_node_names or "planner" in all_node_names
```

**Commit:** `refactor: replace _call_plan_review wrapper with native subgraph composition`

---

## Verification

After each phase:
```
uv run pytest tests/ -v --tb=short
```

Final full-suite checkpoint after all phases:
```
uv run pytest tests/ -v --tb=short
```

Expected:
```
tests/test_build_review.py         PASSED
tests/test_config.py               PASSED
tests/test_e2e_tester.py           PASSED
tests/test_graph_runner.py         PASSED
tests/test_models.py               PASSED
tests/test_node_contract.py        PASSED
tests/test_plan_build_review.py    PASSED
tests/test_plan_review.py          PASSED
tests/test_prompt_build_review.py  PASSED
tests/test_prompt_workflow.py      PASSED
```

No `test_orchestrator.py` (deleted in Phase 2).

---

## Traceability: All Items From Both Plans

| Combined | Superpowers Source | Efficiency Source | Status |
|----------|-------------------|-------------------|--------|
| 1A | Task 1 (C2-verdict) | P1-A (H4, H5) | Merged — Efficiency approach |
| 1B | Task 2 (C2-allowed) | P1-F (L2) | Superpowers — user confirmed |
| 1C | Task 3 (H1) | — | Superpowers only |
| 1D | — | P1-C (C2) | Efficiency only |
| 1E | — | P1-B (H1) partial | Efficiency — budget deferred to 3A |
| 2A | Task 4 (M7) | — | Superpowers only |
| 2B | — | P1-E (L1) | Efficiency only |
| 3A | Task 5 (M1) | P1-B (H1, H2) | Merged — Superpowers subsumes P1-B |
| 4A | Task 6 (H4) | — | Superpowers only |
| 4B | — | P1-A (H5) partial | Efficiency — trace suppression |
| 5A | — | P3-A (M1-pt1) | Efficiency only |
| 5B | — | P5-B (M1-pt3) | Efficiency only |
| 6A | Task 7 (M3) | P4-A (M1-pt2) | Merged — both plans |
| 6B | Task 9 (M5) | P1-D (M4) | Merged — both plans |
| 6C | Task 8 (M2) | — | Superpowers only |
| 6D | — | P5-D (M3) | Efficiency only |
| 7A | Task 10 (H3) | — | Superpowers only |
| 7B | Task 11 (C1) | — | Superpowers only |
| 8A | — | P2-A (C1) | Efficiency only |
| 8B | — | P5-A (H3) | Efficiency only |
| 8C | — | P5-C (M2) | Efficiency only |
| 9A | Task 12 (M4) | — | Superpowers only |
| 9B | Task 13 (M6) | — | Superpowers only |
| 9C | Task 14 (H2) | — | Superpowers only |
