# Research: Feedback Passing in Multi-Agent LLM Plan→Build→Review→Revise Loops

**Researched:** 2026-04-03
**Domain:** Multi-agent LLM orchestration — feedback structure, accumulation, and consumption
**Confidence:** HIGH (core patterns), MEDIUM (specific schema details)

---

## Summary

Feedback passing between stages in multi-agent LLM loops is one of the highest-leverage
design decisions in the system. Bad feedback structure causes agent drift, regression
bugs, and unbounded context growth within 2–3 cycles. Good structure keeps feedback
deterministic, bounded, and action-forcing.

The state of the art (2024–2025) has converged on four principles: (1) structured
prose beats JSON for LLM consumers, (2) feedback should be replaced-not-accumulated
per cycle with only a compressed "persistent lessons" layer surviving across cycles,
(3) the receiving agent's prompt must explicitly separate "new issues this cycle" from
"unresolved issues from prior cycles", and (4) test failure feedback must include
not only what failed but what was previously passing, so the agent can detect
self-inflicted regressions.

This codebase already implements several of these patterns correctly — notably
the replace-not-accumulate pattern in `BuildReviewState` (`micro_feedback`,
`macro_feedback`, `build_feedback` are overwritten each cycle) and the
e2e-feedback-first prompt ordering in `_build_coder_context`. The open gaps are:
no persistent "lessons" layer across cycles, no structured severity tiers in
reviewer output, and no regression-protection in the e2e feedback format.

**Primary recommendation:** Add a categorical severity header to reviewer verdicts
(`CRITICAL / MAJOR / MINOR`), add a `resolved_issues` carry-forward field to
`BuildReviewState`, and inject a "DO NOT RE-BREAK" list into the coder prompt after
any cycle where e2e_feedback was present.

---

## 1. Feedback Summarization

### What the research says

The dominant industry pattern (AutoGen, LangGraph reflection examples, SWE-agent) is
**structured prose with mandatory fields**, not free-form paragraphs and not raw JSON.
The key finding: LLMs consume prose better than JSON for reasoning tasks, but prose
without structure leads to omissions and priority inversion.

The winning format is a set of **labeled sections** where the LLM must populate each
one, which forces evidence gathering before conclusion. Meta's "semi-formal reasoning"
research (2025) demonstrated up to 93% accuracy improvement on code verification by
forcing the model to explicitly state premises, trace execution paths, and derive a
formal conclusion — vs. allowing it to jump to verdicts. This maps directly to
structured feedback templates.

### Recommended feedback template (reviewer → coder)

```
VERDICT:<APPROVE|REVISE>
REASONING:<1–3 sentences: why this verdict>

CRITICAL:
- <file>:<line> — <issue> — ACTION: <specific fix>
- ...

MAJOR:
- <file>:<line> — <issue> — ACTION: <specific fix>
- ...

MINOR:
- <suggestion, not a blocker>
- ...

EVIDENCE:
<concrete output sample, test result, or diff excerpt supporting the findings above>
```

**Why this over JSON:**
- LLM writing JSON for another LLM to read adds unnecessary parse overhead
- Prose sections allow the reviewer to express nuance the schema doesn't anticipate
- Labeled sections force completeness — the reviewer can't skip EVIDENCE
- The receiving coder agent processes it with a simple section-split, not a JSON parser

**Why structured over free prose:**
- Free prose is underdetermined — reviewers mix critical and trivial in the same
  paragraph, causing the coder to weight them equally
- Without an EVIDENCE section, reviewers make assertions without grounding; the coder
  has no way to verify the claim is valid before spending time on it

### Context bloat prevention

The single most effective intervention is **replace-not-accumulate**: each feedback
field (`micro_feedback`, `macro_feedback`, `build_feedback`) is overwritten, not
appended. Your codebase already does this correctly in `review_synthesizer.py` and
the state schema.

The second intervention is **compressing prior-cycle issues into a "lessons" field**
rather than re-passing full prior feedback. See Section 2.

---

## 2. Feedback Accumulation Patterns

### Replace vs. accumulate: the evidence

Research on the Reflexion framework (Shinn et al., 2023) and follow-on work shows:
- Full history accumulation (passing all prior feedback): adds 20–40% to prompt length
  per cycle with diminishing returns after cycle 2; performance degrades at cycle 3+
- Rolling window (last N cycles): maintains performance but risks losing a lesson
  learned in cycle 1 that becomes relevant again in cycle 3
- **Selective reflection (recommended)**: replace the current-cycle feedback fields
  with fresh output, but maintain a separate `lessons_learned` field that accumulates
  a compressed, deduplicated list of *rules* derived from prior failures

Multi-Agent Reflexion (MAR, 2024) found the best results with a judge model that
synthesizes multiple critiques into "unified reflections" — exactly what your
`review_synthesizer.py` does, but the synthesizer should also emit a lesson when a
`REVISE` verdict is issued.

### Recommended accumulation architecture

```
Per-cycle fields (REPLACED each cycle):
  micro_feedback: str       — latest micro review full output
  macro_feedback: str       — latest macro review full output
  build_feedback: str       — synthesized current-cycle feedback
  e2e_feedback: str         — latest e2e findings

Persistent-across-cycles field (APPENDED, bounded):
  resolved_issues: list[str]  — issues that were CRITICAL/MAJOR and are now fixed
                                 (extracted by synthesizer when verdict flips to APPROVE)
  persistent_rules: str       — compressed lessons from prior REVISE cycles
                                 (LLM-generated 1-sentence rules, max 5)
```

The `resolved_issues` list serves double duty: it gives the coder a "do not re-break
this" contract, and it gives reviewers context so they don't re-flag already-fixed
issues.

**Concrete example of `persistent_rules` content (cycle 2 lesson):**
```
- Do not use bare `except:` — always catch specific exception types
- The Database class must close its connection in a context manager, not __del__
- All file writes must be atomic (write to tmp + os.replace)
```

These are more durable and token-efficient than re-passing the full cycle-1 feedback.

### What AutoGen does (and why it's worse for this use case)

AutoGen's conversational model passes the full message history each turn. This works
for short exchanges but creates unbounded context growth in multi-cycle code revision.
The hard lesson from AutoGen deployments: always set `max_turns` and build explicit
convergence criteria. Your MAX_PLAN_CYCLES / build_cycle guards are the right
equivalent.

---

## 3. Structured Feedback Schemas

### Field analysis: what actually matters for a coder agent

From the empirical study (Rethinking Code Review Workflows, arXiv 2505.16339) and
SWE-agent's interface design work:

| Field | Required? | Notes |
|-------|-----------|-------|
| Severity tier | Yes | CRITICAL/MAJOR/MINOR prevents treating nit as blocker |
| File path | Yes | Without it, the coder has to guess which file |
| Line number | Yes for bugs | Approximate is fine; "around line 40" is sufficient |
| Issue description | Yes | Should state *what's wrong*, not *what to change* |
| ACTION | Yes | Required — the coder should not have to infer the fix |
| Evidence | Yes (when REVISE) | Concrete output/test/diff excerpt; prevents false positives |
| Category | Useful | bug / architecture / test-coverage / style; helps coder triage |
| Cycle number | No | Tracked in state, not needed in feedback body |

### What your current schema is missing

Your current format:
```
VERDICT:REVISE
REASONING:<...>
ISSUES:<comma-separated list>
SUGGESTIONS:<comma-separated list>
```

Problems:
1. No severity — ISSUES mixes blockers and nits in a flat list
2. No file/line attribution — coder must grep to find the location
3. No ACTION field — "issue X" vs "do Y to fix issue X"
4. ISSUES as comma-separated means multi-clause issues get truncated or mangled

The recommended template in Section 1 directly addresses all four gaps.

### Schema for e2e feedback specifically

E2e feedback has different semantics: it's about intent gaps, not code quality.
Your existing `e2e_tester.py` already uses the right format:
```
INTENT GAPS: <what was supposed to happen vs what actually happened>
EVIDENCE: <concrete output samples, test results>
ROOT CAUSE: <why the implementation falls short>
PROPOSED FIXES: <specific, actionable changes>
```

This is well-designed. The one addition recommended: a `FIXED_IN_PRIOR_CYCLE` section
for cycles 2+, populated by the coder's response summary (or the diff), so the e2e
agent can confirm the fix was applied and not re-raise the same issue.

---

## 4. Prompt Engineering for Feedback Consumption

### Receiving agent structure

The coder agent's prompt (your `_build_coder_context`) has the right priority order:
e2e feedback first (intent), then build feedback (quality). This is correct.
What can be improved:

**Pattern 1: Explicit consumption instructions**
Instead of "address every point", use role-scoped instructions:
```
For each CRITICAL issue: fix it before proceeding.
For each MAJOR issue: fix it unless there is a strong architectural reason not to.
For each MINOR issue: address at your discretion.
Do NOT revisit items listed in RESOLVED ISSUES.
```

**Pattern 2: Diff-aware feedback injection**
The receiving agent benefits from knowing what changed in the current cycle.
Your `_build_coder_context` already injects `code_diff` when `build_feedback` is
present. The enhancement: also inject a `changed_files` summary at the top level so
the agent knows its scope. The SWE-agent research found that presenting post-action
results in "deterministic, highly formatted views (code windows with line numbers and
omissions)" significantly improves correction accuracy.

**Pattern 3: Separate "new issues" from "unresolved prior issues"**
If `build_cycle > 1`, restructure the feedback block:
```
## Reviewer Feedback — Unresolved from Prior Cycles (MUST fix)
{issues that were present in cycle N-1 and not yet resolved}

## Reviewer Feedback — New Issues This Cycle
{issues appearing for the first time}

## Resolved Issues — Do NOT Reintroduce
{items confirmed fixed in a prior cycle}
```

This is the "diff-aware feedback" pattern: the agent knows whether an issue is new
(fresh analysis needed) or persistent (prior fix attempt failed, try a different
approach). Your current system doesn't distinguish these — it re-emits the full merged
feedback, which looks identical whether an issue is new or a stubborn repeat.

**Pattern 4: Evidence-first in system prompt**
Meta's semi-formal reasoning research: the reviewer template should require evidence
*before* the verdict, not after. This forces the model to gather proof before
concluding, which prevents fabricated issues. Your e2e_tester already does this
(INTENT GAPS + EVIDENCE before VERDICT). Apply the same pattern to micro/macro
reviewers.

### Avoiding the prompt-bloat spiral

Concrete rules for the system prompt (not the user turn):
- System prompt should describe behavior and format, not carry feedback content
- Never put prior-cycle feedback in the system prompt — it becomes invisible to the
  model's instruction-following attention and grows unboundedly
- Keep the system prompt stable across cycles; only the user turn changes

---

## 5. E2E / Integration Test Feedback

### The regression problem

The core failure mode: coder fixes issue A in cycle 2, then e2e re-runs in cycle 3
and reports issue A again because the e2e agent evaluates from scratch
(correctly — your `_build_e2e_context` deliberately excludes prior e2e_report to
prevent anchoring). But this creates a re-raise risk when the agent doesn't notice
the current diff already addressed the issue.

Your comment in `e2e_tester.py` ("Deliberately excludes any prior e2e_report to
avoid anchoring bias") is the right trade-off, but it can be made safe with a
lightweight addendum:

```python
if state.get("e2e_cycle", 0) > 0 and state.get("current_code"):
    parts.append(
        "## Previously Reported Issues (do NOT re-raise if the diff addresses them)\n"
        + _extract_resolved_e2e_issues(state)
    )
```

where `_extract_resolved_e2e_issues` extracts the PROPOSED FIXES section from the
prior e2e_report and formats them as a checklist the agent can verify against the
diff.

### Preventing re-breaking fixed issues

The SWE-bench PASS_TO_PASS / FAIL_TO_PASS distinction maps to:
- FAIL_TO_PASS: the new code fixes the reported issue (what you want)
- PASS_TO_PASS: the fix doesn't break tests that were already passing (what you need
  to explicitly check)

Concrete implementation: after each e2e REVISE cycle, inject into the next coder
prompt a `## Do Not Regress` section listing the specific tests/behaviors that the
e2e confirmed as passing in the prior cycle:

```
## Do Not Regress (these passed in the prior e2e run — keep them passing)
- test_insert_and_check_seen: SQLite insert/dedup works
- test_loads_valid_config: config parsing handles valid YAML
- HTTP server returns 200 for /feeds/name.xml
```

This is derived from the EVIDENCE section of the prior e2e_report, not from re-running
tests. It's lightweight (no re-execution) but gives the coder an explicit contract.

### Test failure format

Best practice from Trae Agent and SWE-agent research: test failure feedback should
be **structured and bounded**:

```
## Test Failures

### test_name (FAILING)
Command: uv run pytest tests/test_foo.py::test_name -x --tb=short
Exit code: 1
Error summary: AssertionError: expected 3 items, got 0
Relevant stack frame:
  tests/test_foo.py:42 in test_name
    assert len(result) == 3
Root cause hypothesis: enrich_url mock not patched in this test scope

### test_other (ALSO FAILING — likely same root cause)
...
```

Key rules:
- Include the exact command to reproduce (agent can re-run to verify fix)
- Truncate stack traces to the deepest relevant frame + the assertion line; full
  traces are noise
- Group tests with the same root cause — don't list 12 individually failing tests
  that all have the same underlying cause
- Add "likely same root cause" attribution so the agent doesn't over-fix

---

## 6. Current Codebase Assessment vs. Best Practices

| Practice | Status | Gap |
|----------|--------|-----|
| Replace-not-accumulate per cycle | Implemented | None |
| Structured verdict format with labeled sections | Partial | Missing severity tiers, file/line |
| E2e feedback excluded from reviewer context | Implemented | None |
| E2e excludes prior report (anti-anchor) | Implemented | Adds re-raise risk, fixable |
| Coder receives e2e feedback before build feedback | Implemented | None |
| Persistent lessons across cycles | Not implemented | No `persistent_rules` or `resolved_issues` |
| "New vs. unresolved" feedback distinction | Not implemented | All feedback looks same in cycle 2+ |
| Regression contract ("do not reintroduce") | Not implemented | Coder has no list of confirmed-passing items |
| Severity tiers in reviewer output | Not implemented | ISSUES is a flat, unordered list |
| Evidence required before verdict | Partial | E2e has it; micro/macro do not |

---

## 7. Recommended Changes (Priority Order)

### High value, low risk

**1. Add severity tiers to reviewer system prompts.**
Change `ISSUES:<comma-separated>` to the structured template in Section 1.
This is a system prompt change only — no state schema changes required.

**2. Add `resolved_issues: list[str]` to `BuildReviewState`.**
The synthesizer extracts CRITICAL/MAJOR issues that are confirmed resolved
(prior cycle was REVISE, current cycle the specific issue is absent from reviewer
output). These are injected into the coder prompt as "DO NOT REINTRODUCE".

**3. Add "previously reported / now addressed" check to e2e context builder.**
When `e2e_cycle > 0`, inject a compact list of the prior cycle's PROPOSED FIXES
so the e2e agent can verify them against the diff rather than re-discovering
them from scratch.

### Medium value, higher effort

**4. Add `persistent_rules: str` to `BuildReviewState`.**
Synthesizer generates a 1-sentence rule per resolved CRITICAL issue, capped at 5.
These survive across all cycles and are injected as constraints at the top of the
coder prompt.

**5. Distinguish "new" vs "unresolved" issues in the synthesized feedback.**
When `build_cycle > 1`, compare current micro/macro output against prior
`build_feedback` to categorize issues. Requires a lightweight comparison step
in the synthesizer (string matching on issue text is sufficient; no LLM needed).

---

## Sources

### Primary (HIGH confidence)
- LangChain Reflection Agents blog — `MessageGraph` accumulation pattern, full
  conversation history with bounded turn count
  https://blog.langchain.com/reflection-agents/
- Reflexion paper (Shinn et al., arXiv 2303.11366) — verbal reinforcement learning,
  episodic memory with compressed reflections
  https://arxiv.org/abs/2303.11366
- SWE-agent paper (arXiv 2405.15793) — structured tool output format, FAIL_TO_PASS /
  PASS_TO_PASS test classification, context window management
  https://arxiv.org/pdf/2405.15793
- Context Engineering in LLM-Based Agents (Tan Ruan, Medium) — summarization,
  pruning, sliding window, Reflexion memory synthesis
  https://jtanruan.medium.com/context-engineering-in-llm-based-agents-d670d6b439bc

### Secondary (MEDIUM confidence)
- Meta semi-formal reasoning for code review (VentureBeat/InfoWorld, 2025) —
  structured evidence-before-verdict format, 93% accuracy result
  https://www.infoworld.com/article/4153054/meta-shows-structured-prompts-can-make-llms-more-reliable-for-code-review.html
- LoopJar Agent Orchestration Feedback Loop blog — hub-and-spoke topology,
  iteration caps, test-driven development pattern
  https://loopjar.ai/blog/agent-orchestration-feedback-loop
- Rethinking Code Review Workflows with LLM Assistance (arXiv 2505.16339) —
  empirical study on field importance: file, line, severity, actionability
  https://arxiv.org/html/2505.16339v1
- MAR: Multi-Agent Reflexion (arXiv 2512.20845) — judge model synthesizes
  multi-perspective critiques into unified reflection
  https://arxiv.org/html/2512.20845
- Trae Agent (arXiv 2507.23370) — regression test suite on candidate patches,
  hierarchical pruning strategy
  https://arxiv.org/html/2507.23370v1
- DSPy Assertions paper (arXiv 2312.13382) — backtracking feedback format,
  assertion vs. suggestion semantics
  https://arxiv.org/abs/2312.13382

### Tertiary (LOW confidence)
- AutoGen paper (arXiv 2308.08155) — conversational feedback model; treat as
  baseline to avoid, not recommended pattern for code revision loops
  https://arxiv.org/abs/2308.08155

---

## Confidence Assessment

| Area | Level | Reason |
|------|-------|--------|
| Replace-not-accumulate pattern | HIGH | Multiple independent sources + your codebase already uses it |
| Structured prose over JSON | HIGH | Verified in Meta research + Reflexion paper + SWE-agent |
| Severity tiers as key missing field | HIGH | Empirical study + production observation |
| Evidence-before-verdict ordering | HIGH | Meta semi-formal reasoning + your e2e tester already applies it |
| Persistent lessons layer design | MEDIUM | Pattern from Reflexion / MAR; specific field schema is an inference |
| New vs. unresolved issue distinction | MEDIUM | Logically sound, limited direct prior art found |
| Regression "do not re-break" contract | MEDIUM | SWE-bench evaluation criteria; application to prompt injection is inference |

**Research date:** 2026-04-03
**Valid until:** 2026-07-03 (stable domain, 90-day window reasonable)
