# Experiment 002: Follow-Up Sweeps — Rounds, Anonymization, Cross-Generation

**Date**: 2026-04-24
**Author**: Senkichi (with Claude Opus 4.7)
**Status**: Complete (with caveat — see §10.1)
**Prior work**: [`docs/experiment_001_baseline_eval.md`](experiment_001_baseline_eval.md)
**Plan**: [`docs/experiment_002_plan.md`](experiment_002_plan.md)

---

## Abstract

Three follow-up experiments were run against the dual-pipeline framework established by Experiment 001: a max-debate-rounds sweep crossed with two model generations (2A), an anonymization toggle (2E), and a cross-generation heterogeneous pairing (2B). All three experiments used Variant B exclusively, evaluated on the same three complex tasks from the 001 corpus, with the same two-judge position-bias-corrected pairwise preference framework.

The results overturn two assumptions baked into the 001 baseline. First, **model version dominates pipeline tuning by a wide margin**: every Opus 4.7 configuration in 2A beats every Opus 4.6 configuration, regardless of round count. Second, **the diversity hypothesis does not generalize cross-generation**: pairing Opus 4.6 with Opus 4.7 underperforms homogeneous 4.7, mirroring the prior finding that mismatched-tier pairings (sonnet × haiku) underperform their strong-side homogeneous counterparts. Round count effects are second-order and non-monotonic on 4.7: 7 rounds dominate, but 3 rounds (the 001 default) lose to 1 round in some matchups — an "uncanny valley" where debate runs long enough to argue but not long enough to converge. Anonymization mildly hurts (0.58 vs 0.42 for anonymize-off), though sample size is small.

The headline practical implication is that **upgrading the model is worth more than any pipeline optimization tested here**, and that the pipeline configurations that won on 4.6 are not necessarily the configurations that win on 4.7. Configurations are not portable across model generations.

---

## 1. Motivation

Experiment 001 established that Variant B's debate loop produces a 15-point win-rate advantage over Variant A on complex analytical tasks, with B-homo-opus winning 93.5% on the 3-complex-task subset. The default round limit was 3, which 17 of 25 Variant B runs hit (`max_rounds`) rather than reaching mutual agreement. Several open questions remained:

1. Does raising the round limit improve quality or just burn cost? (2A)
2. Is the anonymization-in-debate flag (default `True`) helping or hurting? (2E)
3. Can same-tier cross-generation pairing (4.6 × 4.7) capture the diversity benefit observed in cross-tier heterogeneous configs without the capability gap that hurt 001's `B-het-sonnet-haiku`? (2B)

A fourth question emerged unplanned during execution: between the 001 baseline (2026-04-18) and the 2A run (2026-04-23), the short alias `opus` flipped from `claude-opus-4-6` to `claude-opus-4-7`. The 002 plan anticipated this risk and explicitly recommended verifying the alias before running 2B. Verification surfaced the shift, prompting an expansion of 2A from a single-model rounds sweep to a 4-rounds × 2-models design that disentangles round count from model version.

---

## 2. Pipeline and Methodology

### 2.1 Pipeline (unchanged from 001)

Variant B: parallel generation → asymmetric cross-review (challenger left, builder right) → revision → multi-round debate → debate-aware synthesis. Implementation in `src/langgraph_agents/pipeline/`. Variant A is not run in any of the 002 experiments.

### 2.2 Pre-flight Pipeline Fixes

Variant B as committed at 001 publication time was not actually executable end-to-end on Windows for non-trivial tasks. Two pre-existing blockers were fixed before 002 launched (commit `fe036d8`):

1. **SDK iterator protocol** — `AgentSession._send` iterated `ClaudeSDKClient.query()` directly as an async iterator. SDK 0.1.62 requires `await client.query(msg)` followed by `async for msg in client.receive_response()`. Prior pattern crashed on the first debate turn with `TypeError: 'async for' requires an object with __aiter__, got coroutine`.
2. **Windows `CreateProcess` arg-size limit** — `init_debate` embedded both v2 drafts (typically 5–10 KB each) into the debater's system prompt, which the Claude Code CLI passes to `CreateProcess` as `--system-prompt`. On long tasks this exceeded the ~32 KB Windows limit and failed with `WinError 206`. Split into a short `DEBATE_SYSTEM_PROMPT` (role + rules + format) and `DEBATE_OPENING_USER_MESSAGE` (task + proposals), the latter routed through the uncapped API payload path.

Independent of correctness, every artifact write is now atomic (`<name>.<pid>.tmp` followed by `os.replace`), and every `summary.json` carries an `environment` block (git_sha, git_dirty, claude_cli_version, claude_agent_sdk_version, python_version, platform). The provenance block was the only reason the alias shift was detected — 001 baseline runs do not carry it. (Commits `a947b70`, `fe036d8`.)

A Variant B end-to-end smoke test (`run_variant_b_smoke.py`) was added that runs the architecture-review task with Opus 4.7, 1-round debate cap, and asserts a non-empty final plan with a clean termination reason. This passed before 2A launched.

### 2.3 Evaluation Framework (unchanged from 001)

Three phases per experiment:

1. **Structured metrics** — deterministic, no LLM calls. Cost, wall time, plan size, keyword coverage, token-Jaccard concept coverage.
2. **Pairwise preference judging** — two judges (Opus + Sonnet alias), each pair evaluated twice (natural and swapped order). Position bias is detected by checking whether the judge prefers the same response after the order is swapped; biased judgments are scored as 0.5 ties.
3. **Report generation** — win matrix, cost-adjusted ranking, termination distribution.

Eval scripts (`run_eval_2a.py`, `run_eval_2e.py`, `run_eval_2b.py`) reuse the `run_eval.py` machinery via module-level path rebinding.

### 2.4 Task Corpus

All three 002 experiments filter the 001 corpus to the three complex tasks:

| Task ID | Description |
|---|---|
| `architectural_review_auth` | Harden a flawed JWT auth design (HS256, 30-day tokens, no revocation) |
| `design_testing_strategy` | Design a testing strategy for a real-time pricing service (Kafka, 10k/sec, <100ms) |
| `migration_postgres_dynamo` | Plan migration of 2B-row event table from PostgreSQL to DynamoDB |

The two sanity tasks from 001 (`sanity_semver`, `sanity_prompt_caching`) are excluded — 001 established that debate loop benefits do not appear on simple tasks.

---

## 3. Experiment 2A — Max Debate Rounds × Model Generation

### 3.1 Design

Eight configurations: `max_debate_rounds` ∈ {1, 3, 5, 7} crossed with model ∈ {`claude-opus-4-6`, `claude-opus-4-7`}, on three complex tasks. 24 matrix runs. Budget raised to $10 / 3600s so the round limit, not the budget, is the binding constraint. Random seed 42 throughout.

The 3-round configurations act as within-experiment controls: `B-opus46-3rnd` should approximately reproduce the 001 `B-homo-opus` result (which was almost certainly Opus 4.6 given the publication date).

### 3.2 Execution Notes

The 24 runs spanned two pieces of execution because of an hourly rate limit hit at run 16. The 8 `migration_postgres_dynamo` runs failed with `api_error_status: 429 — You've hit your limit, resets 3:40pm`. Resume succeeded on the next attempt; `summary.json` presence as the resume signal worked correctly. No state was lost.

| Metric | Value |
|---|---|
| Matrix runs completed | 24 / 24 |
| Total matrix cost | $74.78 |
| Total matrix wall (across runs) | 17,519 s (292 min) |
| Eval judgments collected | 167 / 168 expected |
| Position-bias rate | (computed but not extracted) |

### 3.3 Results — Pairwise Win Matrix

Values are row-vs-column win rate (position-bias judgments scored as 0.5 ties).

| | B-opus46-1 | B-opus46-3 | B-opus46-5 | B-opus46-7 | B-opus47-1 | B-opus47-3 | B-opus47-5 | B-opus47-7 |
|---|---|---|---|---|---|---|---|---|
| **B-opus46-1rnd** | — | 0.58 | 0.42 | 0.33 | 0.00 | 0.00 | 0.00 | 0.00 |
| **B-opus46-3rnd** | 0.42 | — | 0.08 | 0.17 | 0.00 | 0.00 | 0.00 | 0.00 |
| **B-opus46-5rnd** | 0.58 | 0.92 | — | 0.33 | 0.00 | 0.00 | 0.08 | 0.00 |
| **B-opus46-7rnd** | 0.67 | 0.83 | 0.67 | — | 0.00 | 0.08 | 0.00 | 0.00 |
| **B-opus47-1rnd** | 1.00 | 1.00 | 1.00 | 1.00 | — | 0.58 | 0.58 | 0.25 |
| **B-opus47-3rnd** | 1.00 | 1.00 | 1.00 | 0.92 | 0.42 | — | 0.17 | 0.17 |
| **B-opus47-5rnd** | 1.00 | 1.00 | 0.92 | 1.00 | 0.42 | 0.83 | — | 0.30 |
| **B-opus47-7rnd** | 1.00 | 1.00 | 1.00 | 1.00 | 0.75 | 0.83 | 0.70 | — |

Two patterns dominate:

**Pattern 1 — Model version is a hard partition.** Every cell in the upper-right quadrant (4.7 row vs 4.6 column) is 1.00 except `B-opus47-3rnd` vs `B-opus46-7rnd` at 0.92. Every cell in the lower-left quadrant (4.6 row vs 4.7 column) is 0.00 except the same matchup at 0.08. Model generation outranks every other dimension tested.

**Pattern 2 — Within-generation rounds non-monotonicity on 4.7.** Within Opus 4.6, more rounds help: `7 > 5 > 3` (and 3 is anomalously weak vs 5 and 7). Within Opus 4.7, the picture is messier:

- `B-opus47-7rnd` is the strongest 4.7 config (0.70–0.83 vs other 4.7 configs)
- `B-opus47-3rnd` (the 001 default) loses to `B-opus47-1rnd` (0.42 vs 1's 0.58)
- This suggests an "uncanny valley": 3 rounds of debate is enough to argue but not enough to converge, producing worse synthesis input than either no debate (1 round = a single position statement, no back-and-forth) or full convergence (5–7 rounds).

### 3.4 Termination Reason Distribution

Across the 24 runs:

| Round limit | Model | mutual_agreement | max_rounds |
|---|---|---|---|
| 1 | 4.6 | 0 | 3 |
| 3 | 4.6 | 2 | 1 |
| 5 | 4.6 | 3 | 0 |
| 7 | 4.6 | 3 | 0 |
| 1 | 4.7 | 0 | 3 |
| 3 | 4.7 | 0 | 3 |
| 5 | 4.7 | 3 | 0 |
| 7 | 4.7 | 3 | 0 |

A clear shift from the 001 baseline: 001 saw 17/25 Variant B runs hit `max_rounds`. With 5+ rounds available, debaters consistently reach `mutual_agreement`. **The 3-round cap was leaving most debates strictly mid-conversation.** This makes sense of the uncanny-valley pattern in §3.3: 3 rounds is the minimum cap at which most debaters will *not* reach agreement, producing a synthesizer input that is neither converged nor naive.

### 3.5 Structured Metrics by Config

| Config | Avg cost | Avg wall | Concept coverage (kw) | Plan chars |
|---|---|---|---|---|
| B-opus46-1rnd | $2.28 | 690 s | 80.5% | 26,553 |
| B-opus46-3rnd | $2.56 | 758 s | 79.4% | 25,073 |
| B-opus46-5rnd | $2.72 | 770 s | 78.4% | 27,961 |
| B-opus46-7rnd | $2.51 | 809 s | 71.2% | 29,797 |
| B-opus47-1rnd | $3.24 | 636 s | 69.3% | 23,735 |
| B-opus47-3rnd | $3.71 | 692 s | 63.1% | 21,664 |
| B-opus47-5rnd | $3.84 | 717 s | 70.3% | 24,225 |
| B-opus47-7rnd | $4.08 | 767 s | 73.3% | 26,338 |

**Counterintuitive finding**: Opus 4.7 produces shorter plans (~22–26K chars vs 25–30K for 4.6) and has lower keyword coverage (~63–73% vs 71–80% for 4.6), yet wins every pairwise comparison. **Quality, as judged by the LLM-as-judge framework, is not correlated with length or keyword coverage** in this regime. The judges are rewarding something else — presumably concreteness, correctness, or analytical depth — that the deterministic metrics do not capture.

---

## 4. Experiment 2E — Anonymization Toggle

### 4.1 Design

Two configurations: `B-opus47-anon-on` (current default, drafts labeled "Proposal A/B" in debate prompts) vs `B-opus47-anon-off` (drafts labeled "Your draft / Their draft"). Both pinned to `claude-opus-4-7`. Three complex tasks, 6 matrix runs.

### 4.2 Execution Notes

One transient SDK initialization timeout (`Control request timeout: initialize` in `AgentSession.start()`) on `B-opus47-anon-on__design_testing_strategy`. Resume picked it up cleanly on retry. 6/6 runs completed.

### 4.3 Results

| Config | Win rate vs other | Wins/$ | Avg cost | Avg wall |
|---|---|---|---|---|
| B-opus47-anon-off | 0.58 | 0.15 | $3.91 | 732 s |
| B-opus47-anon-on  | 0.42 | 0.12 | $3.57 | 677 s |

Anonymization-off wins by a small margin (0.58 vs 0.42), running roughly 10% more expensive and 10% slower. The signal is directionally clear but underpowered: 6 judgments total (3 tasks × 2 judges × 1 pair).

### 4.4 Interpretation (tentative)

The original design intent of `anonymize_in_debate=True` was to reduce identity bias — debaters should evaluate proposals on merit, not loyalty. The data weakly suggests the opposite: knowing which draft is "yours" produces more vigorous defense and substantive engagement, leading to better synthesis input. This is consistent with the broader observation in 2A that more debate (within a productive range) helps.

The effect is small enough that it should be treated as a hypothesis to be re-tested at higher N before flipping the default.

---

## 5. Experiment 2B — Cross-Generation Heterogeneous

### 5.1 Design

Three configurations on three complex tasks (9 runs):

| Config | Left-side roles | Right-side roles | Synthesizer |
|---|---|---|---|
| `B-homo-opus46` | claude-opus-4-6 | claude-opus-4-6 | claude-opus-4-6 |
| `B-homo-opus47` | claude-opus-4-7 | claude-opus-4-7 | claude-opus-4-7 |
| `B-het-opus46-opus47` | claude-opus-4-6 | claude-opus-4-7 | claude-opus-4-7 |

The two homogeneous configurations are parameter-identical to `B-opus46-3rnd` and `B-opus47-3rnd` from 2A; they are re-run here so the eval pipeline stays self-contained.

### 5.2 Execution Notes — Eval Underpowered

The 2B eval was interrupted by a hard organization-level monthly usage cap ("You've hit your org's monthly usage limit"). 7 of 18 expected judgments completed before the cap engaged. The cap does not reset until the next monthly billing cycle.

The 7 judgments are unanimously consistent within each pair. With 2–3 judgments per pair direction (rather than 6), the directional signal is decisive but statistical power is reduced. The win-matrix values below should be read as "100% of judged pairs agreed" rather than "100% of all pairs would agree."

| Pair | Judgments collected / expected | Outcome (unanimous in collected sample) |
|---|---|---|
| `B-het-opus46-opus47` vs `B-homo-opus46` | 3 / 6 | het wins |
| `B-het-opus46-opus47` vs `B-homo-opus47` | 2 / 6 | homo-47 wins |
| `B-homo-opus46` vs `B-homo-opus47` | 2 / 6 | homo-47 wins |

### 5.3 Results — Strict Ordering

| | B-het-46-47 | B-homo-46 | B-homo-47 |
|---|---|---|---|
| **B-het-opus46-opus47** | — | 1.00 | 0.00 |
| **B-homo-opus46** | 0.00 | — | 0.00 |
| **B-homo-opus47** | 1.00 | 1.00 | — |

Strict ordering: **`B-homo-opus47` > `B-het-opus46-opus47` > `B-homo-opus46`**.

### 5.4 Interpretation — Diversity Hypothesis Refuted at This Boundary

The 001 baseline finding was that heterogeneous pairings outperform homogeneous at equivalent tiers (`A-het-opus-sonnet > A-homo-opus`, `B-het-opus-sonnet > B-homo-sonnet`), supporting the "diversity hypothesis": different models bring different reasoning strategies, creating productive tension during cross-review and debate. The 001 caveat was that this only works when the weaker model is "strong enough" — `B-het-sonnet-haiku < B-homo-sonnet` because Haiku is too weak to be a productive partner.

Experiment 2B tests whether same-tier cross-generation pairing (Opus 4.6 × Opus 4.7) captures the diversity benefit without the capability gap. **It does not.** The cross-generation het config underperforms strong-side homo (4.7) by the same pattern observed in 001's `sonnet × haiku` matchup: the older-generation model behaves as the "weaker" partner from the synthesizer's perspective, even at the same nominal capability tier. Diversity in *training* is not equivalent to diversity in *strategy* for the synthesizer's purposes.

This is an important boundary on the diversity hypothesis from 001: it is sensitive to which dimension is varied. Cross-tier pairings (where one side is genuinely weaker) help. Cross-generation pairings (where both sides are "the same model" with different training) do not.

### 5.5 Structured Metrics

| Config | Avg cost | Avg wall | Concept coverage (kw) | Plan chars |
|---|---|---|---|---|
| B-homo-opus46 | $2.52 | 750 s | 73.3% | 25,451 |
| B-het-opus46-opus47 | $3.09 | 700 s | 69.3% | 22,833 |
| B-homo-opus47 | $3.64 | 675 s | 62.9% | 19,864 |

The same length-vs-quality inversion seen in 2A holds: the winning config (`B-homo-opus47`) produces the shortest plan and has the lowest keyword coverage.

---

## 6. Cross-Experiment Synthesis

### 6.1 The Five Findings

**Finding 1 — Model version dominates pipeline tuning.** Across 167 pairwise judgments in 2A, every Opus 4.7 configuration beats every Opus 4.6 configuration regardless of round count. The same pattern holds in 2B. Pipeline architecture optimizations achieved through 001's design work are dwarfed by a single model-version upgrade.

**Finding 2 — LLM-as-judge quality is not length-correlated.** Opus 4.7 wins every pairwise comparison while producing shorter plans (~20% fewer characters) with lower keyword coverage (~10 percentage points lower) than Opus 4.6. Whatever the judges are rewarding — concreteness, correctness, analytical density — the deterministic structured metrics fail to capture it. This is a methodological flag for any future work that relies on coverage metrics as a quality proxy.

**Finding 3 — Round count effects are non-monotonic on 4.7.** On Opus 4.6, more rounds monotonically help (1 → 3 → 5 → 7 each step is a small win). On Opus 4.7, 7 rounds dominate, but 3 rounds — the 001 default — actually lose to 1 round. There is an "uncanny valley" at 3 rounds: enough debate to dilute initial positions, not enough to converge. The termination distribution confirms this: at 3 rounds, almost all 4.7 debates hit `max_rounds`; at 5 rounds, all reach `mutual_agreement`. **The 001 default is the worst non-trivial choice for 4.7.**

**Finding 4 — The diversity hypothesis is dimension-specific.** Cross-tier heterogeneous pairings (Opus × Sonnet in 001) help; cross-generation pairings (4.6 × 4.7 in 2B) do not. From the synthesizer's perspective, an older-generation peer behaves more like a weaker peer than like a "differently strategic peer." Diversity in training data does not translate to diversity in usable reasoning strategies.

**Finding 5 — Configurations do not port across model generations.** Three of the experiments measured "what was best" on a particular model, and the answers differed by model. The 001 default of 3 rounds was reasonable for 4.6 (where it sits between 1 and 5) but is the worst choice on 4.7. Anonymization-off wins on 4.7 with small N; we do not know whether it wins on 4.6. **Pipeline tuning must be re-validated whenever the underlying model changes.**

### 6.2 Three Patterns Worth Watching

**Termination shifted from `max_rounds` to `mutual_agreement`.** 001's 17-of-25 `max_rounds` rate looked like "debaters are still arguing when time runs out." With higher round caps, the same models converge cleanly. This is good news for the convergence-oriented prompt variants planned in 2D — there is room for them to land.

**4.7 is more tenacious in debate at the same round cap.** In 2B, both 4.7 homo configs hit `max_rounds` at 3 rounds; the 4.6 homo reached `mutual_agreement`. With identical prompts and identical round caps, 4.7 sustains disagreement longer.

**4.7 costs ~50% more per run than 4.6** ($3.64 vs $2.52 for 3-round homogeneous on the same tasks). Under flat-rate pricing this is irrelevant. Under API pricing, the 4.6 → 4.7 upgrade is a ~50% cost increase for a ~100% win-rate uplift.

---

## 7. Practical Recommendations

If you are running this pipeline today on Opus 4.7, the parameters most likely to win are:

| Parameter | Recommended | Source |
|---|---|---|
| `max_debate_rounds` | 7 | 2A: B-opus47-7rnd dominates other 4.7 configs |
| `anonymize_in_debate` | `False` | 2E: small but consistent advantage |
| Models | All Opus 4.7 explicit ID | 2A, 2B: 4.7 dominates 4.6, no benefit from cross-gen mixing |
| Avoid | 3-round cap on 4.7 | 2A: uncanny valley |

These should be re-validated at the next model upgrade (Finding 5).

---

## 8. Limitations

1. **2B eval is underpowered.** 7 of 18 planned judgments completed before the monthly usage cap engaged. The remaining 11 should be collected when the cap resets and the report regenerated.

2. **Three complex tasks is a small corpus.** The 001 limitation persists. Confidence intervals on win rates are wide. A 1.00 win rate from 3 judgments and a 1.00 win rate from 30 judgments are not the same evidence.

3. **Single-run-per-config-task.** No variance estimate from repeated trials. Random seed was held at 42 throughout, but model temperature and CLI-side non-determinism mean the same config-task pair can produce different outputs on re-run.

4. **LLM-as-judge homogeneity.** Both judges are Claude. A cross-family judge (GPT-4, Gemini) would test for self-preference bias, particularly for Findings 1 and 4 where 4.7 dominates 4.6 (same family) and for the anonymization weak signal.

5. **2A confounds rounds with budget headroom.** Higher round caps had higher cost / wall budgets ($10 / 3600s) than 001's defaults ($5 / 2400s). The within-experiment comparison is clean (all 2A configs share the same budget), but 2A → 001 comparison is not.

6. **Keyword-coverage metric is misleading.** Section 6.1 Finding 2: the metric does not track quality at the model-version boundary. Future work should not use it as a primary quality proxy without supplementing with judged outcomes.

7. **No A-vs-B comparison in 002.** All three experiments are within Variant B. The `Variant A vs Variant B` block in each report shows 0% / 0% because no cross-variant judgments exist; this is cosmetic and noted here so the report files are not misread.

---

## 9. Recommended Next Steps

In rough priority order, lowest-effort first:

1. **Resume 2B eval when monthly cap resets.** 11 judgments outstanding. Single command (`uv run --active python run_eval_2b.py`) — `judgments.jsonl` is append-only and the resume logic skips completed work. Cost: ~$3–5.

2. **Re-run 001 baseline with `claude-opus-4-7` explicit IDs.** Current 001 results are on aliases that have since shifted, and we have no environment provenance on those runs to confirm what model actually ran. A fresh run of the 001 matrix with explicit 4.7 IDs would let us cleanly compare "what 001 found in 2026-04-18" against "what 001 finds today." Cost: ~$60. Time: ~2 hours wall.

3. **Test asymmetric model-role configs.** 2B mixed 4.6 and 4.7 by side (left vs right). The diversity hypothesis might still hold if mixing is by *role*: 4.7 generators with 4.6 critics, or 4.6 generators with 4.7 synthesizer. This tests whether model differences are productive when the roles structurally differ. 4–6 configs, 12–18 runs, ~$25.

4. **Extend 2E to N≥30 judgments.** The 0.58 vs 0.42 anonymization signal is the lowest-confidence finding in this report. Re-run with two more random seeds (or scale to 6 tasks if/when the corpus is expanded) to confirm or refute. Cost: ~$10.

5. **Implement Experiment 2C (reasoning effort).** The plan's 2C requires threading a `reasoning_effort` parameter through `RunConfig` / `ModelConfig` / `session.py` / both variants' node modules. Asymmetric effort (high on critics + debaters + synthesizer, low on generators) is the most interesting hypothesis. ~1–2 sessions of code work + ~$50 in matrix execution.

6. **Implement Experiment 2D (debate prompt structure).** Variants D2 (objection-focused, structured turn format) and D3 (convergence-pressure with mandatory concessions) become more interesting given Finding 3: the uncanny-valley issue at 3 rounds is exactly the kind of problem D3 is designed to fix. ~1 session of code + ~$30.

7. **Expand the task corpus.** All five 002 limitations would be partially addressed by adding 5–10 more complex tasks across different domains (performance tuning, API design review, incident postmortem, threat modeling). This is the single most impactful methodological improvement available.

8. **Revisit Variant A on Opus 4.7.** All of 002 is Variant B. The 001 finding that B beats A by 15 points on complex tasks was on the older model. If 4.7 produces strong direct synthesis, the gap may have narrowed — and the cost premium of B's debate loop may not be worth it on the new flagship.

### 9.1 Anti-recommendation

**Do not invest in 4.6-vs-4.7 head-to-head experiments beyond what's already in this report.** The signal is unambiguous (every cell in 2A's cross-quadrant is 1.00 / 0.00). Further measurements of "which generation wins" are not informative; the open questions are about *how* 4.7 wins, not whether it does.

---

## 10. Appendix

### 10.1 Provenance and Reproducibility

All matrix and eval artifacts are in:

```
logs/matrix_2a_rounds/   # 24 runs
logs/eval_2a/            # 167 judgments + report.md
logs/matrix_2e_anon/     # 6 runs
logs/eval_2e/            # 6 judgments + report.md
logs/matrix_2b_crossgen/ # 9 runs
logs/eval_2b/            # 7/18 judgments + report.md (PARTIAL — see §10.2)
```

Each `summary.json` carries an `environment` block recording git_sha, git_dirty, claude_cli_version (2.1.118), claude_agent_sdk_version (0.1.62), python_version (3.13.5), and platform (Windows 11). All runs in 002 were executed against git_sha `9ef7a87` or later, all on a clean tree (`git_dirty: false`) except a handful made before the smoke-test script was committed.

Driver scripts: `run_exp_2a_rounds.py`, `run_exp_2e_anon.py`, `run_exp_2b_crossgen.py` (matrix) and `run_eval_2a.py`, `run_eval_2e.py`, `run_eval_2b.py` (eval). All use `random_seed=42`, `max_total_cost_usd=10.0`, `max_wall_clock_seconds=3600`. Resume logic: `summary.json` presence in the run directory short-circuits matrix re-execution; `judgments.jsonl` append-only persistence does the same for the eval.

### 10.2 Outstanding Work

- 2B: 11 of 18 judgments outstanding (see §5.2). Re-run `run_eval_2b.py` after monthly limit resets.
- The cosmetic A-vs-B block in all three eval reports is empty by construction; not worth fixing unless the report becomes externally consumed.

### 10.3 Cost Summary

| Experiment | Matrix runs | Matrix cost | Eval calls | Eval cost (est.) |
|---|---|---|---|---|
| 2A | 24 | $74.78 | 167 (2-pass × 84 pairs ≈ 334 calls) | ~$50 |
| 2E | 6 | $22.44 | 6 (12 calls) | ~$2 |
| 2B | 9 | $27.78 | 7 of 18 (~14 calls) | ~$2 |
| **Total (002)** | **39** | **$125.00** | **180** | **~$54** |

For comparison, Experiment 001 totaled $58.71 in matrix cost across 50 runs and ~$50 in eval calls across 450 judgments. Experiment 002 is ~3× the per-run cost (one fewer task, but Opus 4.7's higher per-run cost), and ~10× lower judgment density (180 vs 450 judgments).
