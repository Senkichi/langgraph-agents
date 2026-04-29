# Experiment 003 Plan: Stress-Tested Follow-Ups to Experiment 002

**Date**: 2026-04-26
**Status**: Planned (pending review)
**Prior work**: [`docs/experiment_002_results.md`](experiment_002_results.md), [`docs/experiment_001_baseline_eval.md`](experiment_001_baseline_eval.md)
**Author**: Senkichi (with Claude Opus 4.7, in Zero-Trust Architect mode)

---

## 0. Why this plan does not just execute §9 of 002

The 002 results document closes with seven recommended next steps and one anti-recommendation. Adopting that list verbatim would be an act of faith in the document's framing. This plan does not do that. Each recommendation is examined against three questions:

1. **What is the recommendation's actual intent** — the question the experimenter wants answered, distinct from the literal procedure?
2. **Will the proposed procedure answer that question?** Or does it under-power, conflate variables, or duplicate another recommendation?
3. **Is there a cheaper, sharper, or more decisive way to satisfy the intent?**

The result is a re-prioritised plan where the order, scope, and in some cases the existence of phases differ from §9. Items the original §9 omitted — most importantly judge self-preference bias on Finding 1, and a feasibility gate for the SDK changes Rec 4 silently assumes — are added as Phase 0 gates.

Two systemic concerns drive the reordering:

- **Confound risk on the headline result.** Findings 1, 4, and 5 all rest on a 4.7-dominates-4.6 signal where both judges are Claude. The 002 limitations section flags this as a known threat (§8.3), then the recommendations section does not act on it. If self-preference bias is real, the 4.7-vs-4.6 cross-quadrant is inflated and every downstream conclusion shifts. This must be tested before more matrix runs are bought.
- **Statistical floor.** Three complex tasks × small judgment counts produces wide confidence intervals on every win-rate. The recommendations bury "expand corpus" at position 6. This plan moves it to position 1: every other phase pays the same statistical cost until it is fixed.

---

## 1. Stress-test of §9 recommendations

| # | §9 Recommendation | Intent | Stress-test verdict | Disposition in this plan |
|---|---|---|---|---|
| 1 | Re-run 001 baseline with explicit 4.7 IDs | Confirm 001's pipeline-architecture findings (B>A by 15pts, diversity helps) hold on 4.7 | Heavy overlap with Rec 7. The 001 matrix had 5 configs (`A-homo-opus`, `B-homo-opus`, `A-het-opus-sonnet`, `B-het-opus-sonnet`, `B-het-sonnet-haiku`). Re-running all five is wasteful — the *interesting* questions are A-vs-B on 4.7 and whether cross-tier diversity (Opus×Sonnet) still helps on 4.7. | **Merged with Rec 7 into Phase 2.1.** Trim to four configs, drop sanity tasks, target the two open questions. |
| 2 | Asymmetric model-role configs | Distinguish "diversity by side" (refuted in 2B) from "diversity by role" — does generator/critic/synth role asymmetry capture diversity benefit? | Combinatorial space is large (3 roles × 2 model choices = 8 cells, plus debater split, plus per-side variations). 4–6 configs without theoretical narrowing is a fishing expedition. | **Phase 3.1, narrowed.** Pick three motivated configs, not a sweep. Strongest hypothesis is "concentrate the strong model where reasoning depth matters most" (critic + synth = 4.7, generators = 4.6). |
| 3 | Extend 2E to N≥30 judgments | Confirm/refute weak anonymization-off signal | Power analysis: detecting a 0.58 vs 0.42 effect on a binomial with α=0.05, β=0.20 needs **~150 paired judgments**, not 30. N=30 confirms only large effects (~0.70 vs 0.30). At measured effect size, 30 is still under-powered. | **Phase 3.3, gated on Phase 0.3.** Either commit to N≈150 or drop the question. Do not run a half-measure that produces another inconclusive result. |
| 4 | Implement Experiment 2C (reasoning effort) | Test whether reasoning-effort parameter improves quality / cost trade | **Hidden assumption: this parameter exists in the SDK path the pipeline uses.** A grep of `src/langgraph_agents/pipeline/` finds no `reasoning_effort` field anywhere in `config.py`, `session.py`, or the CLI argument builder. Whether the Claude Code subscription path even exposes it is unverified. The recommendation budgets "1–2 sessions of code work" without confirming it is possible. | **Phase 0.2 feasibility spike**, then **Phase 3.2** if green. Spike is cheap; building the matrix on a non-existent knob is not. |
| 5 | Implement 2D (debate prompt structure) | Address the 3-round "uncanny valley" — make 3 rounds reach mutual agreement, recovering cost/time at no quality loss | **Question what is being optimised.** On 4.7, 7 rounds already wins, costs only ~10% more than 3 rounds, takes ~10% more wall time. The optimisation target needs to be explicit: "match 7-round quality at lower cost" is the only honest framing. If that delta is the prize, it is small. | **Phase 2.2, with explicit success bar.** Only worth building if the 7-rnd-vs-3-rnd cost gap is quantified up-front and the prompt-restructure target beats it. Otherwise: just use 7 rounds and move on. |
| 6 | Expand task corpus | Address the most-cited limitation across both 001 and 002 | The recommendation itself says this is "the single most impactful methodological improvement available." It is then ranked sixth. **The ranking is wrong.** Every finding in 002 has a confidence interval that this work would tighten. | **Promoted to Phase 1.1 — the first thing built.** |
| 7 | Revisit Variant A on Opus 4.7 | Test if the 15-pt B>A gap holds on 4.7 | Same intent as Rec 1. | **Merged into Phase 2.1.** |
| §9.1 | Anti-rec: do not invest in 4.6-vs-4.7 head-to-head | The cross-quadrant is unanimous; further measurement is uninformative | Agreed *if* the judges are unbiased. Cross-quadrant unanimity given homogeneous Claude judges is exactly what self-preference bias would produce. The anti-rec is correct conditional on Phase 0.1 finding no bias; otherwise it is the wrong call. | **Conditionally accepted.** Phase 0.1 must clear the bias hypothesis first. |

### Gaps the §9 list missed

- **Judge self-preference bias** (limitation §8.3, never operationalised). This is the single biggest threat to the headline result.
- **Reasoning-effort SDK feasibility** — assumed not verified.
- **Statistical power floor** for the anonymization re-run — N=30 is not enough, the recommendation is technically correct (extend 2E) but functionally ineffective.
- **Disposition of the keyword-coverage metric** (Finding 2). The metric does not track quality. Either drop it from future reports, or add a metric that does. The recommendations are silent.

---

## 2. Reordered phase plan

```
Phase 0 — Gates (cheap, must clear before spending matrix budget)
   0.1  Judge self-preference bias sanity check        $8 real,        1 hr      (GPT-4o)
   0.2  reasoning_effort SDK feasibility spike         $0,             30 min
   0.3  2E sample-size & feasibility analysis          $0,             30 min

Phase 1 — Methodological foundation (one-time, downstream-multiplying)
   1.1  Corpus expansion: +6 tasks → final corpus = 9  $0,             2–3 hrs
   1.2  Quality metric replacement / supplement        $0,             1–2 hrs

Phase 2 — Architectural questions on 4.7
   2.1  A-vs-B + cross-tier diversity on 4.7           $0 real,        4–5 hrs   ($82 imputed matrix + $36 imputed eval)
   2.2  2D debate prompt restructure (cost/quality)    $0 real,        3–4 hrs   ($126 imputed matrix + $36 imputed eval)

Phase 3 — Conditional / second-order
   3.1  Asymmetric role configs (narrowed)             $0 real,        2.5 hrs   ($95 imputed matrix + $20 imputed eval)
   3.2  2C reasoning_effort (gated on 0.2)             $0 real,        1 day     (~$60 imputed if green)
   3.3  2E re-run at adequate N (gated on 0.3)         $0 real,        1.5 hrs   (~$30 imputed)

Real-cash total (all phases, judge stays Claude-only):                $8
Real-cash total (Phase 0.1 finds bias → permanent third judge):       $40–60
```

---

## 3. Phase 0 — Gates

### 3.1 Phase 0.1 — Judge self-preference bias sanity check

**Question.** Do the Claude judges (Opus + Sonnet aliases) prefer Claude-family responses over equally-strong non-Claude responses, at a rate that would inflate the 4.7-vs-4.6 win quadrant?

**Design.** Take ~6 already-judged 4.7-vs-4.6 pairs from `logs/eval_2a/judgments.jsonl`. Re-judge with a single non-Claude judge (GPT-4-class or Gemini-Pro-class via API). Compare:

- Cross-quadrant cells (4.7 row vs 4.6 column) under Claude judges: 1.00 / 0.00
- Same cells under the cross-family judge: ?

If the cross-family judge also produces 0.92+ in favour of 4.7, Finding 1 is robust and §9.1 stands. If the cross-family judge produces 0.60–0.75, the effect is real but inflated; downstream phases must keep this quantified inflation factor in mind. If the cross-family judge produces ≤0.55, the headline result of 002 is largely artifactual and Phase 2 design changes accordingly.

**Implementation.**
- New script `run_eval_judge_sanity.py` — reads `logs/eval_2a/judgments.jsonl`, samples 6 pairs (1 per task × 2 cross-quadrant configs), submits to chosen non-Claude API, writes `logs/eval_judge_sanity/results.json`.
- Choice of cross-family judge: **GPT-4o via OpenAI API** (locked decision). Reuse the position-bias correction (judge twice, swap order, count biased preferences as 0.5).
- One-time script — does not need to integrate with `run_eval.py`'s machinery.

**Cost.** ~12 cross-family judgment calls × ~$0.50 ≈ $6–8.
**Wall.** ~1 hour including write-up.
**Code touch.** New file only; no pipeline changes.

**Decision rule.**
- Robust (cross-family ≥0.85 in favour of 4.7): **proceed with §9.1's anti-recommendation.**
- Inflated (0.60–0.85): **proceed but record the deflation factor**; revise win-rate framing in future reports.
- Refuted (≤0.55): **STOP.** Convene to redesign Phase 2; the foundational claim of 002 is challenged.

### 3.2 Phase 0.2 — `reasoning_effort` SDK feasibility spike

**Question.** Does the path the pipeline uses (Claude Code CLI for Variant A's `single_query`, `claude-agent-sdk` for Variant B's `AgentSession`) expose a knob that controls extended-thinking depth on Opus 4.7?

**Procedure.**
1. Inspect `claude-agent-sdk==0.1.62` (already a dependency) for any thinking-mode / reasoning-effort parameter on `ClaudeSDKClient` or its query/options surface. Check release notes for 0.1.62 + later.
2. Inspect `claude` CLI (2.1.118, currently used) flags via `claude --help` for an extended-thinking / reasoning-budget flag.
3. If neither path exposes it, confirm via Anthropic SDK direct (`anthropic.Anthropic.messages.create(thinking=...)`) what the official knob is and whether it would require swapping `single_query` and `AgentSession` to a different transport.

**Output.** A 1-page memo at `docs/spike_reasoning_effort.md` with:
- Verdict: **available / available-with-rewrite / not-available**.
- If available: exact parameter name, valid values, default, and 5 lines of code showing where it threads through `RunConfig` → `ModelConfig` → CLI args / SDK options.
- If available-with-rewrite: the scope of the rewrite (lines of code, surfaces touched).

**Cost.** $0 (reading / smoke calls).
**Wall.** 30 minutes.

**Decision rule.**
- Available: **green-light Phase 3.2** as scoped.
- Rewrite: **defer Phase 3.2** until a transport-rewrite phase is independently justified.
- Not available: **drop Phase 3.2.** Find an alternative quality knob (e.g. system-prompt-injected "think step by step" — separate, smaller experiment).

### 3.3 Phase 0.3 — 2E re-run sample-size analysis

**Question.** What N is required to reject the null at the measured effect size?

**Procedure.** Closed-form binomial power calculation. Inputs: observed effect 0.58 vs 0.42, α=0.05, β=0.20. Outputs N per arm and total judgment count required.

Then translate to runs: at 2 judges × 2 orders × 1 pair-per-task, N total judgments per task = 4. To reach the required N, multiply tasks. With the Phase 1.1 expanded corpus (8–12 tasks), is the required N feasible inside a $30 budget?

**Output.** A 5-line note in `docs/experiment_003_plan.md` (this file, addended) recording N required, $/run baseline, and feasibility verdict.

**Decision rule.**
- Required N achievable in ≤ $30: **green-light Phase 3.3.**
- Required N too costly: **drop Phase 3.3.** Anonymization stays at the current default; weak signal is acknowledged but not chased.

---

## 4. Phase 1 — Methodological foundation

### 4.1 Phase 1.1 — Corpus expansion

**Why this is first.** Every win-rate in this report has a confidence interval determined by N. With three tasks, even a 1.00 win-rate is ~3 successes in 3 trials — the 95% CI is ~[0.29, 1.00]. Expanding to 10 tasks tightens that to ~[0.69, 1.00] for the same observed rate. **No experiment after this point should be run on the 3-task corpus.**

**Target (locked).** Add **6 new complex tasks** for a final corpus of **9 tasks** (3 existing + 6 new). The locked domain list:

1. **Performance tuning of a hot-path service** (existing system, profiler output given)
2. **API design review** (RESTful service spec, breaking-change risk)
3. **Incident postmortem authoring** (timeline + root cause + action items)
4. **Database schema migration with downtime constraints** (different from the existing PG→Dynamo task — adds rollback / data-validation dimensions)
5. **Caching / consistency design** (write-through vs write-behind in a constrained env)
6. **Refactoring strategy for a legacy module** (named smells, must preserve behaviour)

Domains *not* selected (and why): threat modelling overlapped with the existing `architectural_review_auth`; distributed-systems failure analysis overlapped with incident postmortem on reasoning-about-failure shape; ML system design opens a domain not represented elsewhere in the pipeline's expected production usage.

Diversity check across the locked 6: input format (existing-design vs greenfield) is balanced 4-vs-2 (existing ≫ greenfield, matching production reality); expected-output shape varies (analytical critique, narrative postmortem, structured migration plan, trade-off analysis, refactoring roadmap); 4 of 6 admit a frontier of acceptable trade-offs rather than a single best answer.

**Implementation.** Each task is a `*.md` file in `src/langgraph_agents/eval/corpus/` matching the format already parsed by `corpus.py`:

```
# Task: <name>

<task body shown to the pipeline>

## Expected response shape (for eval reference only, not shown to pipeline)
- Length: short | medium | long
- Key concepts: <comma-separated>
- Failure modes:
  - ...
```

Author tasks by hand (do not use the pipeline to author them — that contaminates the corpus).

**Quality gate.** Each new task must:
- Be answerable in ~25 KB plan or less (otherwise it stresses the synthesizer)
- Have ≥6 distinct correct concepts that a strong response should cover
- Have ≥3 plausible failure modes a weak response would commit
- Pass a smoke run on Variant A + 4.7 single-config without error

**No matrix cost** — corpus authoring only. Smoke runs use ~$5–10.

**Wall.** 2–3 hours of human authoring.

### 4.2 Phase 1.2 — Quality-metric replacement

**Why.** Finding 2 says the keyword-coverage metric does not track quality. The 002 recommendations leave this metric in place. It will continue to mislead in every future report.

**Action (small, decisive).**
1. Mark the existing concept-coverage / keyword-coverage column in `eval/metrics.py` as `coverage_legacy`. Keep computing it (cheap), but do not surface it as a quality proxy in reports.
2. Add a new structured metric: **failure-mode hit rate.** Each task's `Failure modes` section lists antipatterns the pipeline should avoid; a simple substring / phrase check against the final plan flags whether each was committed. Lower is better. This is bounded in the same way concept coverage is, but inverted: it directly measures plan badness rather than plan thoroughness.
3. Add an **independence flag** to each metric in the reports: "judged-independent" (positively correlates with judged win-rate over historical data) vs "decorative". Keep coverage as decorative until proven otherwise.

**Implementation scope.** Touches `eval/metrics.py` (~30–60 LOC) and `eval/report.py` (column header changes). No matrix re-run needed; can be backfilled across `logs/eval_*` artifacts on demand.

**Wall.** 1–2 hours.

---

## 5. Phase 2 — Architectural questions on 4.7

### 5.1 Phase 2.1 — A-vs-B + cross-tier diversity on 4.7 (combines §9 Recs 1 and 7)

**Question 1.** Does B beat A on 4.7 by anything close to the 15-point margin observed on 4.6? Or has 4.7's stronger direct synthesis closed the gap?

**Question 2.** Does the cross-tier diversity benefit (`B-het-opus-sonnet > B-homo-sonnet` in 001) persist on 4.7-class models? Or does it disappear with a stronger Opus generation, the way cross-generation diversity disappeared in 2B?

**Configs.**

| ID | Variant | Models | Notes |
|---|---|---|---|
| `A-homo-opus47` | A | all 4.7 | Direct-synthesis baseline |
| `B-homo-opus47` | B | all 4.7 | Re-uses 2A's `B-opus47-7rnd` setting (7 rounds — best 4.7 setting) |
| `A-het-opus47-sonnet46` | A | left=4.7, right=Sonnet-4.6 | Cross-tier on 4.7-flagship |
| `B-het-opus47-sonnet46` | B | left=4.7, right=Sonnet-4.6, synth=4.7, 7 rounds | Cross-tier in B |

Use the **expanded corpus** from Phase 1.1 (8–12 complex tasks). All configs at `max_debate_rounds=7`, `random_seed=42`, $10 / 3600s budgets.

**Driver.** New file `run_exp_3_1.py`, copy-and-modify of `run_exp_2b_crossgen.py`, output to `logs/matrix_3_1_4_7_arch/`, eval to `logs/eval_3_1/`.

**What the result decides.**
- B beats A by ≥10 pts: B's debate loop is still worth its cost on 4.7 — pipeline architecture findings from 001 carry forward.
- B beats A by <5 pts: the architecture has been mooted by the model. Recommend Variant A as default for 4.7-and-later, retire B from production unless the residual quality is worth the cost.
- Cross-tier het beats homo on 4.7: diversity hypothesis is alive on the strong side; recommend cross-tier as production default.
- Cross-tier het loses on 4.7 the way cross-generation lost in 2B: 4.7 is too far ahead of any current weaker partner; recommend homo-4.7 as default.

**Cost.** 4 configs × 8 tasks (low estimate) = 32 runs × ~$3.70 average = ~$118 matrix; 4 configs × 12 tasks × ~$3.70 = ~$178 matrix. Eval: ~50 pairs × 4 calls = $30. **Estimated total ~$130–$210.** This is more than the §9 estimate ($60) — the §9 estimate did not include corpus expansion or cross-tier on 4.7. The trade-off is honest: the bigger corpus is what makes the result trustworthy.

If budget is constrained, fall back to 8 tasks and the four configs above; do not shrink the configs.

**Wall.** ~3–4 hours matrix at parallel=3, ~1 hour eval.

### 5.2 Phase 2.2 — 2D debate prompt restructure (cost/quality on 7-rnd target)

**Honest framing.** The §9 recommendation pitches 2D as fixing the uncanny valley. The data already gives a fix: use 7 rounds. **2D is only worth running if the goal is recovering the ~10% cost/time of 7 rounds while keeping its quality** — not if the goal is "make 3 rounds usable." This phase is greenlit only if that target is the explicit objective.

**Configs.**

| ID | Prompt variant | Rounds | Notes |
|---|---|---|---|
| `B-D1-7rnd` | Current default ("you are debating two drafts; defend yours, attack theirs") | 7 | Control — matches Phase 2.1's `B-homo-opus47` |
| `B-D2-3rnd` | Objection-focused: each turn must list 1 concrete objection + 1 concrete amendment to the opponent's draft | 3 | Tests whether structure forces convergence at low round count |
| `B-D3-3rnd` | Convergence-pressure: turn N must explicitly list which of the opponent's claims it concedes | 3 | Forced concession schedule |
| `B-D2-7rnd` | Objection-focused | 7 | Discriminates "structure helps" from "structure helps at low rounds" |

**Implementation.** Prompt strings live in `src/langgraph_agents/pipeline/prompts.py`. New constants `DEBATE_OBJECTION_PROMPT` and `DEBATE_CONVERGENCE_PROMPT`. Add a `debate_prompt_variant: Literal["default","D2","D3"]` to `RunConfig` (the only knob that needs adding). Variant B's debate node already takes the prompt from `prompts.py`; switch the lookup based on the new field.

**Touch.** `pipeline/config.py` (+1 field), `pipeline/prompts.py` (+2 constants), `pipeline/variant_b/nodes.py` (~10 LOC dispatch). Estimated 1 session of code.

**Cost.** 4 configs × 8 tasks × $3.70 = $118 matrix; eval ~$15. **Estimated $130 total.** Higher than §9's $30 estimate — the §9 estimate dropped corpus expansion and config count.

**Decision rule.** Run only if Phase 2.1's `B-homo-opus47` win rate ≥0.55 vs `A-homo-opus47` (i.e., B is still the production default). If A is the production default after Phase 2.1, debate-prompt restructure has no audience and this phase is dropped.

---

## 6. Phase 3 — Conditional / second-order

### 6.1 Phase 3.1 — Asymmetric role configs (narrowed)

**Hypothesis (single, motivated).** The strong model is best deployed where reasoning depth dominates, and a weaker partner is acceptable where breadth/parallelism dominates. Concretely: **critic + synthesizer should be 4.7; generators can be 4.6 or smaller and the result will not measurably degrade.**

If true: this is the cost-efficiency story for 4.7 — get most of 4.7's quality at materially lower cost than `B-homo-opus47`.

**Configs (three only).**

| ID | gen_left | gen_right | crit_left | crit_right | rev_left | rev_right | synth | dbt_left | dbt_right |
|---|---|---|---|---|---|---|---|---|---|
| `B-homo-opus47` | 4.7 | 4.7 | 4.7 | 4.7 | 4.7 | 4.7 | 4.7 | 4.7 | 4.7 |
| `B-roleasym-strongcore` | 4.6 | 4.6 | 4.7 | 4.7 | 4.7 | 4.7 | 4.7 | 4.7 | 4.7 |
| `B-roleasym-weakcore` | 4.7 | 4.7 | 4.6 | 4.6 | 4.6 | 4.6 | 4.6 | 4.6 | 4.6 |

The third (mirror) config is the falsifier: if the role-asymmetry hypothesis is right, `B-roleasym-strongcore` should approach `B-homo-opus47` while `B-roleasym-weakcore` should look like `B-homo-opus46`. If both asymmetric configs underperform homo-47 by similar amounts, the role-asymmetry hypothesis is wrong and the model has to be 4.7 throughout.

**Implementation.** Driver `run_exp_3_3_role.py`, no code changes (use direct `ModelConfig` construction). 3 configs × 8 tasks = 24 runs × ~$3.50 = ~$84 matrix; eval ~$15.

**Wall.** ~2 hrs matrix, 30 min eval.

### 6.2 Phase 3.2 — `reasoning_effort` (gated on Phase 0.2)

Run only if 0.2 returns "available". Design and config matrix authored after 0.2's memo is in place — do not pre-commit to a design that may be infeasible.

**Skeleton (subject to 0.2 outcome).** Sweep effort `low / medium / high` × Variant B 4.7 7-rnd, on the expanded corpus. Asymmetric variant (high on critics + synth, low on generators) is the second-order config, run only if the homogeneous sweep shows non-trivial variation across effort levels.

**Estimated cost (if 0.2 green).** ~$50 matrix + $15 eval. ~1 day code + matrix.

### 6.3 Phase 3.3 — 2E re-run at adequate N (gated on Phase 0.3)

Run only if 0.3 returns "feasible at ≤$30". Design: re-run the 2E pair on the expanded corpus across two random seeds (for variance), and aggregate. Goal: drive total judgment count to the figure 0.3 calls for.

---

## 7. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Phase 0.1 finds Claude judges biased toward 4.7 | Medium | High — invalidates 002's headline | Phases 2 and 3 use cross-family judge as the tie-breaker on close calls; reports include both judge outputs; the deflation factor is published |
| Phase 0.2 finds reasoning_effort unavailable | Medium | Medium — drops Phase 3.2 only | Substitute experiment: in-context "think step by step" injection, smaller scope |
| Corpus expansion (1.1) takes longer than 3 hours | High | Low — schedule slips one day | Accept the slip. Do not skimp on task quality to hit a budget |
| Phase 2.1 finds A ≈ B on 4.7 | Medium | High in a good way — major finding, simplifies stack | Plan Phase 2.2 as conditional already (above) |
| Alias drift between phase 0/1 and phase 2/3 | Low (we have provenance now) | Low — caught by `environment` block | Re-verify alias resolution at the start of each phase |
| Org monthly usage cap re-hits, as in 2B | Medium | Low — eval is resumable | Already mitigated by `judgments.jsonl` append-only persistence; budget timing of large phases (2.1) early in the billing window |
| Cross-family judge API outage | Low | Medium for Phase 0.1 only | Phase 0.1 is the only phase depending on a non-Anthropic API; have a manual fallback (read pairs in person, score 6 by hand) |

---

## 8. Success criteria

This experiment is a success when each of the following can be answered with a citation to a specific artifact in `logs/`:

1. **Is Finding 1 robust to judge family?** (Phase 0.1)
2. **Does B>A still hold on 4.7 with the expanded corpus?** (Phase 2.1)
3. **Does cross-tier diversity persist on 4.7-class flagship?** (Phase 2.1)
4. **Can role-asymmetry recover most of homo-4.7's quality at lower cost?** (Phase 3.1)

These four answers reshape the production-deployment recommendation. The remaining phases (2.2, 3.2, 3.3) are second-order and worth running only if their gates clear.

---

## 9. What this plan does *not* do

- **Does not** retreat from 002's findings; it stress-tests them and adds the missing controls.
- **Does not** add Variant C / new pipeline architectures. The architectural exploration belongs in a later experiment series; Experiment 003 is a robustness pass on 002's claims plus the most decisive new questions.
- **Does not** pursue the §9 anti-recommendation territory (more 4.6-vs-4.7 head-to-heads). That stands.
- **Does not** authorise running anything before Phase 0 is complete. The gates exist to prevent the costliest phases from running on falsified premises.

---

## 10. Cost / wall summary

**Important framing note.** The dollar figures in 002 (and below) are the Claude Code CLI's `total_cost_usd` field — an *estimate of equivalent API spend*, not real cash on a Claude Code subscription. 002 §6.2 explicitly says *"Under flat-rate pricing this is irrelevant."* On subscription, the only real-money line in this plan is **Phase 0.1's GPT-4o calls (~$8)**; everything else is $0 marginal. The "imputed" column below is what the CLI's accounting will report — useful for relative comparison across phases, not a bill.

Per-run imputed costs are anchored on 002 §10.3 actuals: 4.7 Variant B at 7 rounds ≈ $4/run, 4.7 Variant B at 3 rounds ≈ $3.70/run, Variant A on 4.7 ≈ ~$1/run (no debate loop). Eval calls ≈ $0.30/judgment.

Updated for the locked corpus size of **9 tasks** (3 existing + 6 new). Eval calls per phase: pairs(C-choose-2 of configs) × 9 tasks × 2 judgments per pair = judgments. Imputed at $0.30/judgment.

| Phase | Code work | Matrix imputed | Eval imputed | Real cash | Wall |
|---|---|---|---|---|---|
| 0.1 | 1–2 hrs | $0 | $8 | **$8** (OpenAI) | 1 hr |
| 0.2 | 30 min | $0 | $0 | $0 | 30 min |
| 0.3 | 30 min | $0 | $0 | $0 | 30 min |
| 1.1 | 2–3 hrs authoring | ~$5 (smokes) | $0 | $0 | 2–3 hrs |
| 1.2 | 1–2 hrs | $0 | $0 | $0 | — |
| 2.1 (4 configs × 9 tasks; 2× A + 2× B) | 30 min | ~$82 | ~$36 | $0 | 4–5 hrs |
| 2.2 (4 B-configs × 9 tasks) | 1 session | ~$126 | ~$36 | $0 | 3–4 hrs |
| 3.1 (3 B-configs × 9 tasks) | 30 min | ~$95 | ~$20 | $0 | 2.5 hrs |
| 3.2 (cond.) | 1–2 sessions | ~$60 | ~$15 | $0 | 1 day total |
| 3.3 (cond.) | 30 min | ~$30 | — | $0 | 1.5 hrs |
| **Total all phases** | **~6–8 sessions** | **~$398 imputed** | **~$115 imputed** | **~$8 real** | **~2 work-days** |
| **Total Phase 0–2 only** | **~3 sessions** | **~$213 imputed** | **~$80 imputed** | **~$8 real** | **~1.5 work-days** |

**Locked judge-fixture policy: permanent-if-biased.** Phase 0.1 uses GPT-4o as a one-shot sanity check ($8). If Phase 0.1 returns "robust" (cross-family judge agrees with Claude judges), GPT-4o stays one-shot — total real cash is **$8**. If Phase 0.1 returns "inflated" or "refuted", GPT-4o is upgraded to a permanent third judge across Phases 2–3, adding **~$30–50 real cash** (estimated 100–170 cross-family judgments at $0.30 each). Total worst case: **~$58 real cash**.

### 10.1 Addendum (2026-04-29) — Phase 1.1 smoke-derived cost anchor

The Phase 1.1 smoke (Variant A + Opus 4.7, all 6 new complex tasks; logs in `logs/smoke_phase_1_1/`) produced two natural-completion runs and four budget-or-wall-capped runs. The two natural completions cost **$2.18 and $2.70** (mean **$2.44/run**). The cost-capped runs sat at **$2.43–$2.95** with the cap binding before synthesis finished, so true natural-completion cost is at or above $2.44 — the per-run figure originally cited in §10 (anchored on 002 §10.3) is **2.4× too low** for current 4.7 behaviour on the expanded corpus.

**Revised Phase 2.1 imputed estimate** (4 configs × 9 tasks = 36 runs):

| | §10 original | Smoke-revised |
|---|---|---|
| 2× Variant A × 9 = 18 runs | ~$18 (@$1) | **~$45 (@$2.50)** |
| 2× Variant B × 9 = 18 runs | ~$72 (@$4) | **~$90+** (B-on-4.7 estimate likely also low; defer until Phase 2.1 first-config smoke confirms) |
| **Phase 2.1 imputed total** | **~$82** | **~$135+** |

Real cash unchanged ($0 on subscription). The substantive consequence is org-cap timing: the Phase 1.1 smoke alone consumed enough capacity to trip the daily cap, so Phase 2.1 needs to land early in a billing window with no other heavy phases competing. Re-affirms the §7 risk-register mitigation but with sharper numbers.

**Cost-cap policy revised: removed.** Per-run `max_total_cost_usd` overrides are dropped from `run_smoke_phase_1_1.py` and should be dropped from Phase 2.1 drivers. Rationale: real cash is $0; cost caps only truncate runs before synthesis finishes, producing artificially-clipped final plans that bias eval against the pipeline. The pipeline's wall cap remains the runaway-protection mechanism. **Recommended wall cap for Phase 2.1: 1200s** (the longest natural-completion smoke run was 829s; 1200s gives ~45% headroom and stays well clear of the 1800s default).

**Phase 1.1 §4.1 verdict: cleared.** All 6 new tasks parse cleanly, execute end-to-end on Variant A + 4.7, and produce final plans of 19,752–37,994 chars. Concept-leak rates on new rubrics are 0–18%, at or below the existing-corpus baseline of 31–44%.

---

## 11. Locked decisions

The four scoping decisions raised by an earlier draft of this plan have been settled (2026-04-26):

| # | Decision | Locked answer | Rationale captured |
|---|---|---|---|
| 1 | Cross-family judge for Phase 0.1 | **GPT-4o** (single judge) | Cheapest robust option; falls back to adding Gemini-Pro only if Phase 0.1's first pass returns ambiguous (cross-family judge between 0.55 and 0.85). |
| 2 | Corpus expansion domains | **6 new tasks → final corpus = 9** (Performance tuning, Incident postmortem, API design review, DB migration with downtime, Caching/consistency, Refactoring strategy) | Diversity across input format and expected-output shape; production-relevant; non-overlapping with the 3 existing complex tasks. Threat-modelling, distributed-failure analysis, ML system design dropped (overlap or out-of-scope). |
| 3 | Scope and budget | **Full plan, all phases conditional on their gates** | Real cash is $8 baseline regardless of scope (subscription absorbs imputed costs); the budget question collapses once that's understood. Phases 3.1/3.2/3.3 each gated on Phase 0/2 outcomes — they only run if the gate clears. |
| 4 | Non-Anthropic judge as permanent fixture | **Permanent-if-biased** | Cross-family judge stays one-shot if Phase 0.1 returns "robust"; promotes to permanent third judge across Phases 2–3 if Phase 0.1 returns "inflated" or "refuted". Conditional commitment minimises real-cash spend on the optimistic path while ensuring bias-corrected results on the pessimistic path. |

Total real cash: **$8** (optimistic) to **~$58** (Phase 0.1 finds bias → permanent third judge across all remaining phases).

Plan is now ready for execution. First action is **Phase 0.1** (judge bias sanity check); Phases 0.2 and 0.3 can run in parallel since they require no LLM calls.
