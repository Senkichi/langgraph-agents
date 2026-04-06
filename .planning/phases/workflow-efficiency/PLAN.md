# Workflow Efficiency Implementation Plan

**Source:** Audit of all graph nodes, state schemas, run scripts, and orchestration
logic including `.planning/RESEARCH-feedback-passing.md` (2026-04-03).

**Phasing rationale:** Phase 1 contains zero-dependency changes. Each subsequent phase
only depends on what came before. Phases 1–2 can ship independently; they improve safety
and correctness immediately with no state schema changes.

---

## Phase 1: Quick Wins (no state schema changes)

All changes in this phase are 1–10 lines, reversible, and independently testable.

---

### P1-A: Shared `parse_verdict` utility + VERDICT detection hardening

**Problem (H4):** `review_synthesizer.py:43` and `prompt_review_synthesizer.py:22`
both use exact string containment `"VERDICT:REVISE" in text`. A space (`"VERDICT: REVISE"`)
or different casing causes a false APPROVE. `e2e_tester.py:_parse_verdict` already handles
this correctly with `.strip().upper()` — three files use three different strategies.

**Also (H5):** `_extract_verdict_block` is defined only in `review_synthesizer.py` but
is needed in `prompt_review_synthesizer.py`. Moving it to `node_contract.py` makes it
a shared utility.

**Files changed:** `src/langgraph_agents/node_contract.py`, `src/langgraph_agents/nodes/review_synthesizer.py`,
`src/langgraph_agents/nodes/prompt_review_synthesizer.py`, `src/langgraph_agents/nodes/e2e_tester.py`

#### `node_contract.py` — add two shared utilities after the existing validators

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

#### `review_synthesizer.py` — replace local `_extract_verdict_block` and detection

```python
# Remove the local _extract_verdict_block definition.
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

#### `prompt_review_synthesizer.py` — fix VERDICT detection + suppress APPROVE traces (H5)

**Additional problem:** The prompt synthesizer currently includes APPROVE feedback verbatim
(with full tool-use traces) in `build_feedback`, while the code synthesizer correctly
suppresses APPROVE feedback entirely. The prompt engineer receives unnecessary context.

```python
# Add to imports:
from langgraph_agents.node_contract import extract_verdict_block, parse_verdict

# Replace synthesize_prompt_reviews() body:
def synthesize_prompt_reviews(state: PromptBuildState) -> dict:
    behavioral = state.get("behavioral_feedback", "")
    architectural = state.get("architectural_feedback", "")

    behavioral_revise = parse_verdict(behavioral, "APPROVE", "REVISE") == "REVISE"
    architectural_revise = parse_verdict(architectural, "APPROVE", "REVISE") == "REVISE"

    verdict = "REVISE" if (behavioral_revise or architectural_revise) else "APPROVE"

    parts: list[str] = []
    if behavioral_revise:
        parts.append(f"## Behavioral Review\n{extract_verdict_block(behavioral)}")
    if architectural_revise:
        parts.append(f"## Architectural Review\n{extract_verdict_block(architectural)}")

    feedback = "\n\n".join(parts) if parts else "Both reviewers approved."

    return {"build_verdict": verdict, "build_feedback": feedback}
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
# (Fallback for unrecognized values remains "REVISE" from parse_verdict's default)
```

**Tests to update:** `tests/test_node_contract.py` — add tests for `parse_verdict` and
`extract_verdict_block`. `tests/test_build_review.py` — existing synthesizer tests pass
unchanged since behavior is equivalent (exact format still works; the fix adds robustness).

---

### P1-B: Macro reviewer timeout parity + budget caps

**Problem (H1, H2):** `macro_reviewer.py` omits `timeout=`, defaulting to 1800s vs
`micro_reviewer.py`'s explicit 3600s. Both reviewers run in parallel with no `max_budget_usd`.
With `MAX_BUILD_CYCLES=4` and 2 parallel reviewers, up to 8 uncapped agent calls per build.

**Files changed:** `src/langgraph_agents/nodes/micro_reviewer.py`,
`src/langgraph_agents/nodes/macro_reviewer.py`

#### `micro_reviewer.py:60-68` — add budget cap

```python
response = invoke_agent(
    content,
    system_prompt=SYSTEM_PROMPT,
    cwd=workspace,
    allowed_tools=REVIEW_TOOLS,
    model="sonnet",
    max_budget_usd=1.5,   # add this line
    timeout=3600,
)
```

#### `macro_reviewer.py:60-68` — add timeout + budget cap

```python
response = invoke_agent(
    content,
    system_prompt=SYSTEM_PROMPT,
    cwd=workspace,
    allowed_tools=REVIEW_TOOLS,
    model="sonnet",
    max_budget_usd=1.5,   # add this line
    timeout=3600,          # add this line (parity with micro_reviewer)
)
```

**No tests required** — these are behavioral guards, not logic changes.

---

### P1-C: `git diff` captures committed changes

**Problem (C2):** `dev_tools.py:run_git_diff` calls `git diff HEAD`. If the coder commits
its work, `git diff HEAD` returns empty. The fallback `git diff` (no args, unstaged vs
staging) is always a subset and also empty after a clean commit. Result:
`code_diff = "(no changes detected)"` — reviewers receive an empty diff and issue
quality verdicts against nothing. The `non_empty` validator passes on the sentinel
string so no error is raised.

The fallback comment "showing all untracked files" is also wrong — `git diff` does
not show untracked files.

**Files changed:** `src/langgraph_agents/tools/dev_tools.py`

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

**Note:** `git show --patch --format= HEAD` outputs the diff of the most recent commit
without the commit header, identical in format to `git diff HEAD` output. This is
intentional — downstream consumers (reviewers, e2e) do not need to distinguish between
committed vs uncommitted diffs.

**Verify:** `tests/test_build_review.py` — no change needed. Consider adding a unit
test for `run_git_diff` with a tmp git repo fixture.

---

### P1-D: `_suggest_test_commands` covers non-Python changes

**Problem (M4):** `e2e_tester.py:_suggest_test_commands` only maps Python source files
to pytest commands. SQL migration files, YAML configs, and Jinja2 templates are silently
ignored — the e2e agent gets no guidance on how to test them.

**File changed:** `src/langgraph_agents/nodes/e2e_tester.py`

```python
def _suggest_test_commands(changed_files: list[str]) -> str:
    """Map changed source files to likely test commands.

    Returns a markdown section with suggested pytest commands and a list of
    changed non-Python files that may have associated tests. Returns empty
    string if no source files were changed.
    """
    test_targets: list[str] = []
    non_python_changed: list[str] = []

    for f in changed_files:
        if not f.endswith(".py"):
            non_python_changed.append(f)
            continue
        if "/test_" in f or f.startswith("test_"):
            continue
        basename = f.rsplit("/", 1)[-1].removesuffix(".py")
        test_targets.append(basename)

    section_parts: list[str] = []

    if test_targets:
        commands = [
            f"- `uv run pytest tests/ -k '{name}' -x --tb=short`"
            for name in sorted(set(test_targets))[:5]
        ]
        section_parts.append("## Suggested Test Commands\n" + "\n".join(commands))

    if non_python_changed:
        file_list = "\n".join(f"- `{f}`" for f in sorted(non_python_changed)[:10])
        section_parts.append(
            "## Changed Non-Python Files (locate tests manually)\n"
            + file_list
        )

    return "\n\n".join(section_parts)
```

---

### P1-E: Remove dead LangChain tool code

**Problem (L1):** `tools/dev_tools.py` defines `make_dev_tools()` and `make_review_tools()`
that create LangChain `@tool` callables. The current architecture routes all agent calls
through `invoke_agent` → `claude` CLI subprocess. These functions are never called.
They create architectural confusion about what tool access model is actually in use.

**File changed:** `src/langgraph_agents/tools/dev_tools.py`

Delete: all imports used only by dead code (`glob as globlib`, `os`, `subprocess` for
tool functions, `from langchain_core.tools import tool`), `make_dev_tools()`,
`make_review_tools()`. Keep only `run_git_diff()` and its imports.

The resulting file:

```python
"""Utilities for interacting with git in a workspace directory."""

import subprocess


def run_git_diff(workspace_path: str) -> str:
    # ... (updated implementation from P1-C)
```

**Check:** `grep -r "make_dev_tools\|make_review_tools" src/ tests/` — confirm no callers.

---

### P1-F: Harden `invoke_structured` tool-disable mechanism

**Problem (L2):** `claude_cli.py:135` passes `allowed_tools=[""]` to disable tools.
`[""]` produces `--allowed-tools ""` on the command line. Whether the CLI interprets
an empty string as "no tools" is undocumented behavior.

**File changed:** `src/langgraph_agents/claude_cli.py`

Add a module-level constant and document the intent:

```python
# Passing a single empty string to --allowed-tools disables all tool access.
# This is the documented mechanism for pure-reasoning invocations in claude CLI.
_ALLOWED_TOOLS_NONE: list[str] = [""]
```

In `invoke_structured`:
```python
raw = invoke(
    prompt,
    system_prompt=system_prompt,
    cwd=cwd,
    model=model,
    allowed_tools=_ALLOWED_TOOLS_NONE,
    max_budget_usd=max_budget_usd,
    json_schema=schema,
)
```

**Note:** If the claude CLI adds a formal `--no-tools` flag in a future version, replace
`_ALLOWED_TOOLS_NONE` usage with that flag in a single location.

---

## Phase 2: Run Script Fixes (no graph changes)

### P2-A: Separate task summary from plan text in sync optimization runners

**Problem (C1):** `run_sync_opt_phase1.py:133`, `run_sync_opt_phase2.py:133`,
`run_sync_opt_phase3.py:120` all set `current_plan=TASK` where `TASK` is a 3,000+
character combined task+plan document. This causes:

1. The coder to receive `## Task\n<3000-char plan>\n\n## Approved Plan\n<same 3000-char plan>` —
   the full plan content duplicated twice in every coder call.
2. The plan reviewer to evaluate a task description as an implementation plan —
   the wrong semantic. The reviewer evaluates structural completeness of a plan
   (phases, dependencies, edge cases) but the TASK field is a task description.

**Files changed:** `run_sync_opt_phase1.py`, `run_sync_opt_phase2.py`, `run_sync_opt_phase3.py`

Pattern for each file: extract a short `TASK_SUMMARY` (2–4 sentences: what it does,
why, key constraints) and use the existing `TASK` as `current_plan`.

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

**Note:** The run_test_audit_A/B/C scripts already have separate TASK and PLAN variables
correctly — no changes needed there.

---

## Phase 3: State Schema Extensions

### P3-A: `resolved_issues` in `BuildReviewState` — regression contract

**Problem (M1-pt1):** The coder has no mechanism to know which issues were fixed in a
prior build cycle. It can re-introduce a regression and reviewers can re-raise issues
already addressed. The research document (section 2, section 7) identifies
`resolved_issues: list[str]` as the highest-value, lowest-risk addition.

**Files changed:** `src/langgraph_agents/state.py`,
`src/langgraph_agents/graphs/plan_build_review.py`,
`src/langgraph_agents/nodes/review_synthesizer.py`,
`src/langgraph_agents/nodes/coder.py`

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
    resolved_issues: list[str]   # add: confirmed-fixed CRITICAL/MAJOR issues, injected as DO NOT REINTRODUCE
```

#### `plan_build_review.py:_call_build_review` — initialize the field

```python
subgraph_input: BuildReviewState = {
    ...
    "e2e_feedback": e2e_feedback,
    "resolved_issues": [],       # add: starts empty; synthesizer accumulates across cycles
}
```

#### `review_synthesizer.py` — extract and accumulate resolved issues

Add a helper and update `synthesize_reviews`:

```python
def _extract_critical_major_issues(feedback_block: str) -> list[str]:
    """Extract file:line issue descriptions from CRITICAL and MAJOR sections.

    Operates on the verdict block (post-_extract_verdict_block), not raw feedback.
    Returns each issue line stripped of the leading "- ".
    """
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
    micro = state.get("micro_feedback", "")
    macro = state.get("macro_feedback", "")

    micro_revise = parse_verdict(micro, "APPROVE", "REVISE") == "REVISE"
    macro_revise = parse_verdict(macro, "APPROVE", "REVISE") == "REVISE"

    verdict = "REVISE" if (micro_revise or macro_revise) else "APPROVE"

    parts: list[str] = []
    if micro_revise:
        parts.append(f"## Micro Review\n{extract_verdict_block(micro)}")
    if macro_revise:
        parts.append(f"## Macro Review\n{extract_verdict_block(macro)}")

    feedback = "\n\n".join(parts) if parts else "Both reviewers approved."

    # Accumulate resolved issues: when verdict is APPROVE and there was prior REVISE
    # feedback, those CRITICAL/MAJOR issues are now confirmed fixed.
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

#### `coder.py:_build_coder_context` — inject resolved issues as DO NOT REINTRODUCE

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

**Ordering rationale:** "Do Not Reintroduce" appears before e2e feedback and build feedback
because it is a hard constraint, not a new issue. The coder reads it first, then processes
new issues in priority order.

**Tests:** Add to `tests/test_build_review.py`:
- `test_synthesizer_accumulates_resolved_issues_on_approve` — prior REVISE → APPROVE flip
  populates `resolved_issues` with extracted CRITICAL/MAJOR items.
- `test_synthesizer_does_not_populate_resolved_on_revise` — REVISE verdict does not add to
  `resolved_issues`.
- `test_synthesizer_preserves_existing_resolved_issues` — existing `resolved_issues` list
  is preserved across REVISE cycles.

---

## Phase 4: E2E Improvement

### P4-A: Inject prior PROPOSED FIXES on e2e re-entry

**Problem (M1-pt2):** `e2e_tester.py` deliberately excludes prior `e2e_report` to
avoid anchoring bias (correct). But the research document (section 5) identifies that
this creates a re-raise risk on cycle 2+: the e2e agent re-discovers issues already
addressed in the coder's fix cycle. The lightweight mitigation is to inject only the
PROPOSED FIXES section (not the full report) as a "verify these were addressed" checklist.

**File changed:** `src/langgraph_agents/nodes/e2e_tester.py`

```python
def _extract_proposed_fixes(e2e_report: str) -> str:
    """Extract the PROPOSED FIXES section from a prior e2e report.

    Returns the section content (without the header line), or empty string
    if the section is absent or empty.
    """
    lines = e2e_report.splitlines()
    result: list[str] = []
    in_section = False
    for line in lines:
        if line.startswith("PROPOSED FIXES:"):
            in_section = True
            # Include content on the same line after the header
            rest = line.split(":", 1)[1].strip()
            if rest:
                result.append(rest)
        elif in_section and line.startswith("VERDICT:"):
            break
        elif in_section:
            result.append(line)
    return "\n".join(result).strip()


def _build_e2e_context(state: ParentState) -> str:
    parts = [
        f"## Task\n{state['task']}",
        f"## Approved Plan\n{state['current_plan']}",
    ]
    code_diff = state.get("current_code", "")
    if code_diff:
        parts.append(f"## Code Changes\n```diff\n{code_diff}\n```")
        test_cmds = _suggest_test_commands(_extract_changed_files(code_diff))
        if test_cmds:
            parts.append(test_cmds)

    # On re-entry: inject prior PROPOSED FIXES as a verification checklist.
    # Intentionally does NOT include the full prior e2e_report (anti-anchoring).
    if state.get("e2e_cycle", 0) > 0 and state.get("e2e_report"):
        proposed_fixes = _extract_proposed_fixes(state["e2e_report"])
        if proposed_fixes:
            parts.append(
                "## Prior E2E Findings — Verify These Were Addressed\n"
                "Check whether the current diff addresses each item below. "
                "Do NOT re-raise an item if the diff already resolves it.\n\n"
                + proposed_fixes
            )

    parts.append(
        "Validate that the code achieves the intent described above. "
        "Run the suggested test commands (or targeted equivalents), examine "
        "the outputs, and assess quality — not just correctness."
    )
    return "\n\n".join(parts)
```

**Tests:** Add to `tests/test_e2e_tester.py` (or create it):
- `test_extract_proposed_fixes_returns_section_content` — verify extraction from a
  full e2e report with PROPOSED FIXES section.
- `test_extract_proposed_fixes_returns_empty_when_absent` — no PROPOSED FIXES section.
- `test_build_e2e_context_includes_prior_fixes_on_reentry` — `e2e_cycle=1` + `e2e_report`
  with PROPOSED FIXES → context includes the checklist section.
- `test_build_e2e_context_omits_prior_fixes_on_first_cycle` — `e2e_cycle=0` → no checklist.

---

## Phase 5: Higher-Effort Improvements

These changes are correct and valuable but require more careful implementation or have
broader surface area. Implement after Phase 1–4 are stable.

---

### P5-A: Prompt workflow reviewer verdict format upgrade

**Problem (H3):** `behavioral_reviewer.py` and `architectural_reviewer.py` use the old
flat verdict format (`ISSUES:<comma-separated>`). The code reviewers (micro/macro) use
the structured severity format (`CRITICAL: / MAJOR: / MINOR:` with file:line and ACTION).
The prompt engineer receives weaker, less actionable feedback than the code engineer.

**Files changed:** `src/langgraph_agents/nodes/behavioral_reviewer.py`,
`src/langgraph_agents/nodes/architectural_reviewer.py`

In both files, replace the verdict format instructions at the end of SYSTEM_PROMPT:

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
"CRITICAL = isolation boundary violation, contract break, or dependency inconsistency.\n"
"MAJOR = wrong abstraction layer, incomplete downstream update, duplication risk.\n"
"MINOR = naming consistency, minor structural improvement."
```

**Note:** `prompt_review_synthesizer.py` already handles extraction via `extract_verdict_block`
after Phase 1 changes — it will naturally extract the structured block including severity
sections. No synthesizer changes needed.

---

### P5-B: `persistent_rules` accumulation across build cycles

**Problem (M1-pt3 from research doc):** Lessons learned in cycle 1 (e.g., "always use
context managers for DB connections") are lost in cycle 2 when `build_feedback` is
overwritten. The research proposes `persistent_rules: str` — compressed, deduplicated
1-sentence rules from resolved CRITICALs, injected into the coder prompt as permanent
constraints.

**Implementation approach:** Pure Python derivation (no additional LLM call) to preserve
the deterministic synthesizer property.

**Files changed:** `src/langgraph_agents/state.py`,
`src/langgraph_agents/graphs/plan_build_review.py`,
`src/langgraph_agents/nodes/review_synthesizer.py`,
`src/langgraph_agents/nodes/coder.py`

#### `state.py` — add to `BuildReviewState`

```python
persistent_rules: str  # LLM-digestible constraint list derived from resolved CRITICALs; bounded at 5 rules
```

#### `review_synthesizer.py` — derive rules from resolved CRITICAL issues

```python
_MAX_PERSISTENT_RULES = 5

def _derive_rule(issue_line: str) -> str:
    """Convert a resolved CRITICAL issue line to a brief constraint rule.

    Input:  "foo.py:42 — bare except swallows all errors — ACTION: catch specific types"
    Output: "Always catch specific exception types, never bare except."
    The ACTION field is the most actionable part; re-phrase it as a positive constraint.
    """
    if " — ACTION: " in issue_line:
        action = issue_line.split(" — ACTION: ", 1)[1].strip()
        # Capitalize and ensure sentence ends with period
        rule = action[0].upper() + action[1:]
        return rule if rule.endswith(".") else rule + "."
    # Fallback: use full issue description
    return issue_line.strip()


def synthesize_reviews(state: BuildReviewState) -> dict:
    # ... existing logic ...

    # Derive persistent rules from newly resolved CRITICAL issues (not MAJOR/MINOR —
    # only CRITICAL issues represent patterns worth hardening as permanent rules).
    existing_rules_text = state.get("persistent_rules", "").strip()
    existing_rules = [r for r in existing_rules_text.splitlines() if r.strip()]

    new_critical: list[str] = []
    if verdict == "APPROVE" and state.get("build_feedback"):
        # Extract CRITICAL only (not MAJOR) for rule derivation
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

#### `coder.py:_build_coder_context` — inject persistent rules as hard constraints

```python
if state.get("persistent_rules"):
    parts.append(
        "## Engineering Constraints (learned from prior cycles — treat as hard rules)\n"
        + state["persistent_rules"]
    )
```

Insert this after the task/plan block and before DO NOT REINTRODUCE.

#### `plan_build_review.py:_call_build_review` — initialize

```python
subgraph_input: BuildReviewState = {
    ...
    "resolved_issues": [],
    "persistent_rules": "",    # add
}
```

---

### P5-C: Optional plan review bypass for pre-validated plans

**Problem (M2):** When callers pass a pre-written plan, the `plan_review_app` runs a
full Sonnet structured-output call to review a plan the caller already validated externally.
For high-confidence plans, this adds latency with no quality improvement.

**Files changed:** `src/langgraph_agents/state.py`,
`src/langgraph_agents/graphs/plan_build_review.py`

#### `state.py` — add optional flag to `ParentState`

```python
class ParentState(TypedDict):
    task: str
    current_plan: str
    current_code: str
    workspace_path: str
    e2e_verdict: str
    e2e_report: str
    e2e_cycle: int
    skip_plan_review: bool  # add: True = bypass plan_review, go straight to build_review
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

    # Replace unconditional START → plan_review edge with conditional routing
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
- `run_test_audit_A.py`, `run_test_audit_B.py`, `run_test_audit_C.py` — all pass
  externally audited plans.
- `run_companies_audit.py` — plan loaded from file, externally authored.
- `run_sync_opt_phase1.py`, `run_sync_opt_phase2.py`, `run_sync_opt_phase3.py` — after
  Phase 2 separates task from plan, the plan is still the full TASK document (authored
  externally). Set `skip_plan_review=True`.

**Default:** `False` — existing scripts that do not pass the field are unaffected.

**Tests to add:** `tests/test_plan_build_review.py`:
- `test_skip_plan_review_routes_start_to_build_review`
- `test_no_skip_routes_start_to_plan_review`

---

### P5-D: Truncate plan context in code reviewers (large plan optimization)

**Problem (M3):** `micro_reviewer.py:53` and `macro_reviewer.py:54` inject the full
`current_plan` string. For large plans (Chunks A/B/C: 5,000–8,000 chars), this adds
token overhead before the diff. Reviewers already have `Read`/`Glob` workspace access.

**Design constraint:** Reviewers DO need to verify plan alignment. A complete plan truncation
would hurt macro review quality. The mitigation: truncate the plan in the reviewer context
but note the workspace path where the agent can read the full plan if it was written there.
For plans not stored in the workspace, use a 1,500-char summary truncation.

**Files changed:** `src/langgraph_agents/nodes/micro_reviewer.py`,
`src/langgraph_agents/nodes/macro_reviewer.py`

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

**Risk note:** Only apply this after verifying that reviewers are not silently missing
plan alignment issues due to truncation. Monitor macro reviewer REVISE rates — a drop
may indicate it's missing plan details.

---

## Verification Checklist

For each phase, run before merging:

```
uv run pytest tests/ -v --tb=short
```

Phase-specific tests to add:

| Phase | Test file | New test(s) |
|-------|-----------|-------------|
| P1-A | test_node_contract.py | parse_verdict: space, lowercase, no-match fallback; extract_verdict_block strips traces |
| P1-A | test_build_review.py | Existing synthesizer tests pass unchanged |
| P1-C | test_build_review.py | run_git_diff with committed changes (tmp git repo fixture) |
| P3-A | test_build_review.py | resolved_issues: accumulate on approve, preserve on revise, empty init |
| P4-A | test_e2e_tester.py | extract_proposed_fixes; context includes checklist on re-entry |
| P5-C | test_plan_build_review.py | skip_plan_review routing |

---

## Change Summary Table

| ID | File | Change | Lines |
|----|------|--------|-------|
| P1-A | node_contract.py | Add `parse_verdict`, `extract_verdict_block` | +20 |
| P1-A | review_synthesizer.py | Use shared utilities, remove local `_extract_verdict_block` | -10/+5 |
| P1-A | prompt_review_synthesizer.py | Use shared utilities, suppress APPROVE traces | -15/+10 |
| P1-A | e2e_tester.py | Use `parse_verdict` from node_contract | -8/+3 |
| P1-B | micro_reviewer.py | Add `max_budget_usd=1.5` | +1 |
| P1-B | macro_reviewer.py | Add `max_budget_usd=1.5, timeout=3600` | +2 |
| P1-C | dev_tools.py | Rewrite `run_git_diff` with commit fallback | +15/-10 |
| P1-D | e2e_tester.py | Extend `_suggest_test_commands` for non-Python files | +12/-5 |
| P1-E | dev_tools.py | Delete `make_dev_tools`, `make_review_tools`, unused imports | -65 |
| P1-F | claude_cli.py | Add `_ALLOWED_TOOLS_NONE` constant | +3 |
| P2-A | run_sync_opt_phase1/2/3.py | Add `TASK_SUMMARY`, use as `task=` | +5 each |
| P3-A | state.py | Add `resolved_issues: list[str]` to BuildReviewState | +1 |
| P3-A | plan_build_review.py | Initialize `resolved_issues: []` in subgraph input | +1 |
| P3-A | review_synthesizer.py | Add `_extract_critical_major_issues`, accumulate resolved | +25 |
| P3-A | coder.py | Inject `resolved_issues` as DO NOT REINTRODUCE section | +8 |
| P4-A | e2e_tester.py | Add `_extract_proposed_fixes`, inject on re-entry | +25 |
| P5-A | behavioral_reviewer.py | Replace verdict format with severity-structured format | +10/-4 |
| P5-A | architectural_reviewer.py | Replace verdict format with severity-structured format | +10/-4 |
| P5-B | state.py | Add `persistent_rules: str` to BuildReviewState | +1 |
| P5-B | review_synthesizer.py | Add `_derive_rule`, `_MAX_PERSISTENT_RULES`, accumulate rules | +35 |
| P5-B | coder.py | Inject `persistent_rules` as Engineering Constraints | +6 |
| P5-B | plan_build_review.py | Initialize `persistent_rules: ""` | +1 |
| P5-C | state.py | Add `skip_plan_review: bool` to ParentState | +1 |
| P5-C | plan_build_review.py | Add `_route_entry`, replace START edge with conditional | +12 |
| P5-D | micro_reviewer.py | Add `_truncate_plan_for_reviewer`, apply to plan context | +8 |
| P5-D | macro_reviewer.py | Apply same truncation | +3 |
