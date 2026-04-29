# Experiment 003 Phase 0.1 — Judge Self-Preference Bias Sanity Check (Results)

**Date**: 2026-04-29
**Status**: Complete
**Plan**: [`experiment_003_plan.md`](experiment_003_plan.md) §3.1
**Artifacts**: [`logs/eval_judge_sanity/results.json`](../logs/eval_judge_sanity/results.json), [`run_eval_judge_sanity.py`](../run_eval_judge_sanity.py)

---

## TL;DR

**Verdict: INFLATED.** Cross-family judge agrees with the Claude judges on 4 of 6 cells (1 disagreement, 1 position-bias collapse). The 4.7-over-4.6 finding from experiment 002 is **real but its magnitude is overstated** — Claude judges showed 1.00 unanimity, the cross-family judge shows 0.75. Per the plan's locked decision policy, the cross-family judge is promoted to permanent third judge across Phases 2–3.

| | Claude judges (opus + sonnet) | Cross-family judge (DeepSeek V4 Pro) |
|---|---:|---:|
| Cells | 6 | 6 |
| 4.7 wins | 6 (1.00) | 4 |
| 4.6 wins | 0 | 1 |
| Tie / position bias | 0 | 1 |
| Win rate for 4.7 (ties = 0.5) | **1.00** | **0.75** |

---

## Method

Six cross-quadrant cells from [`logs/eval_2a/judgments.jsonl`](../logs/eval_2a/judgments.jsonl), round-matched so the only varying axis is model generation:

- 3 tasks × 2 config-pairs: `(B-opus46-3rnd, B-opus47-3rnd)` and `(B-opus46-7rnd, B-opus47-7rnd)`
- Each cell judged twice (natural + swapped order) for position-bias correction
- Same `JUDGE_PAIRWISE_PROMPT` and `parse_judgement` parsing as the production eval — every variable held constant except judge identity

Cross-family judge: **DeepSeek V4 Pro** (substituted for the plan's GPT-4o; same OpenAI-compatible API surface, ~6× cheaper, no implication for the bias signal). Used DeepSeek's default thinking mode with `max_tokens=8000` to give the model adequate budget for both reasoning + output.

## Results — cell by cell

| # | Task | Rounds | DeepSeek | Claude | Agree? |
|---|---|---|---|---|---|
| 1 | architectural_review_auth | 3 | B (4.7) high conf | B | ✓ |
| 2 | design_testing_strategy | 3 | A (4.6) medium conf | B | ✗ disagree |
| 3 | migration_postgres_dynamo | 3 | tie (position bias) | B | ✗ |
| 4 | architectural_review_auth | 7 | B (4.7) high conf | B | ✓ |
| 5 | design_testing_strategy | 7 | B (4.7) high conf | B | ✓ |
| 6 | migration_postgres_dynamo | 7 | B (4.7) medium conf | B | ✓ |

### The substantive disagreement (cell 2)

DeepSeek picked the 4.6 response over the 4.7 response on `design_testing_strategy` at 3 rounds, **consistently in both orderings** (no position bias). The reasoning was substantive:

> Response X provides more concrete code examples, specific tool configurations, and detailed fault-injection scenarios, making it more directly actionable. … While Y's determinism contract and expected-divergence manifest are strong architectural concepts, X's concrete [code examples] make it more useful in practice.

This is a legitimate evaluative axis: DeepSeek values concrete code over architectural concepts, where the Claude judges may have weighted those criteria differently. It is **not** evidence of judge confusion — it is exactly the cross-family disagreement the bias check was designed to surface.

### Position bias (cell 3)

`migration_postgres_dynamo` at 3 rounds: DeepSeek picked the **first-presented** response in both orderings (X-then-X), regardless of which side was 4.6 vs 4.7. Both reasonings emphasised "more concrete" / "more rigorous" — i.e. the model anchored on whatever was on the left. One cell out of six (~17%) is a small sample but worth tracking; Claude judges' cross-quadrant position-bias rate in 2A was much lower.

### Where the disagreement concentrated

Of the **3 cells at 3 rounds**: 1 agree, 1 substantive disagreement, 1 position-bias.
Of the **3 cells at 7 rounds**: 3/3 agreement.

The 7-round configs all agreed with Claude. The 3-round configs are where the cross-family judge is unsure. This is consistent with experiment 002's Finding 4 ("3-round uncanny valley on 4.7"): at 3 rounds the responses are closer in quality and the judge has less signal. By 7 rounds the 4.7 responses pull ahead clearly enough that any reasonable judge sees it.

---

## Decision rule (per plan §3.1)

| Range | Verdict | Action |
|---|---|---|
| ≥0.85 | robust | §9.1 anti-rec stands; one-shot judge sufficient |
| **0.55–0.85** | **inflated** | **proceed; record deflation factor; promote cross-family judge to permanent fixture** |
| ≤0.55 | refuted | STOP, redesign |

We are at **0.75** — solidly in the "inflated" band.

---

## Consequences

### 1. Promote DeepSeek V4 Pro to permanent third judge for Phases 2–3

Per the locked judge-fixture policy in plan §11. Adds DeepSeek as a third judge alongside Claude opus + sonnet. Practically: extend `judge_multi` callers and the matrix eval drivers to include DeepSeek as a model id, and route DeepSeek through the OpenAI-compatible client path established in `run_eval_judge_sanity.py`.

**Cost impact.** Plan §10 budgeted $30–50 real cash for the permanent-judge scenario at GPT-4o pricing. With DeepSeek V4 Pro at the current promotional rate, ~150–200 cross-family judgments cost **≈$8–11**. Total real-cash budget for experiment 003 stays comfortably under the worst-case $58 figure.

### 2. Record deflation factor in future reports

Future cross-quadrant or cross-family win rates must be reported with both the Claude-only number and the cross-family number. The deflation factor on this sample is approximately **25%** (Claude: 1.00; cross-family: 0.75). This is not promoted to a universal correction — it is the sample value on six cells; the next phases will refine it with more data.

### 3. Refine framing of Finding 1 in 002

The 002 writeup says "4.7 wins every cross-quadrant cell unanimously." That phrasing is technically correct but misleading; the post-Phase-0.1 framing should be:

> 4.7 wins every cross-quadrant cell unanimously **as judged by Claude opus and Claude sonnet**. A cross-family judge (DeepSeek V4 Pro) prefers 4.7 in 4 of 6 round-matched cells; in 1 cell it prefers 4.6 on the substantive grounds of code-example concreteness, and in 1 cell it shows position bias. The 4.7-over-4.6 finding is real, but its magnitude is partly inflated by judge-family agreement.

### 4. §9.1 anti-recommendation does NOT stand unconditionally

The plan said: "anti-rec stands if Phase 0.1 finds no bias; conditionally accepted." Phase 0.1 found bias (inflation). So the original 002 anti-recommendation against further 4.6-vs-4.7 head-to-heads is **softened**: 4.6-vs-4.7 head-to-heads are still not the highest-value experiments to run, but the cross-family judge data they would generate has marginal value beyond what the within-family unanimity establishes. Phases 2.1, 2.2, 3.1 should opportunistically include cross-family judgment on the cells they generate; they should not specifically target more 4.6-vs-4.7 cells.

---

## Cost actuals

12 DeepSeek V4 Pro chat-completion calls. The first run (max_tokens=600) burned the entire completion budget on internal reasoning and emitted empty content, producing 12 unparseable verdicts; that was a $0.10 false start. The fixed run (max_tokens=8000, the actual data above) was another ~$0.15. **Total real cash spent: ~$0.25**, against a planned $8 ceiling.

The empty-content failure is a useful gotcha: any thinking-mode model called via the chat-completions surface needs a generous output budget because reasoning tokens are billed against the same `max_tokens` cap as visible content.

---

## Open follow-ups

- Wire DeepSeek into `judge_multi` and the matrix eval drivers so Phase 2.1 onward emit three-judge results without script-level hacking.
- Track DeepSeek's position-bias rate across the larger Phase 2 corpus. One cell (17% on this tiny sample) is not yet a stable estimate, but if it stays elevated relative to the Claude judges' rate, it becomes a confounder we need to call out.
- Decide whether to formalise the "deflation factor" reporting in the eval report markdown templates, or leave it as narrative caveat. Defer until after Phase 2.1 produces a larger sample.
