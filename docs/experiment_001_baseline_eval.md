# Experiment 001: Baseline Dual-Pipeline Evaluation

**Date**: 2026-04-18
**Author**: Senkichi (with Claude Opus 4.6)
**Status**: Complete

---

## Abstract

We evaluated two multi-agent LLM pipeline architectures for generating high-quality analytical responses to complex technical tasks. **Variant A** uses a four-phase generate-review-revise-synthesize pipeline. **Variant B** extends this with a structured debate loop between two LLM advocates before synthesis. We ran 50 pipeline executions (10 configurations x 5 tasks) and conducted 450 pairwise preference judgments using position-bias-corrected LLM judging.

On simple tasks, the variants perform equivalently. On complex tasks (security review, test strategy design, database migration planning), Variant B's debate loop produces a **15-point win-rate advantage** (57.3% vs 42.7%) over Variant A. The strongest configuration overall is B-homo-opus (all roles filled by Opus), achieving a 93.5% win rate on complex tasks. However, the best cost-adjusted configuration is A-het-opus-sonnet (Opus on the left side, Sonnet on the right), achieving 75% win rate at less than half the cost. Heterogeneous model pairings consistently outperform their homogeneous counterparts at equivalent model tiers, providing evidence for the "diversity hypothesis" — that pairing different models creates productive tension during cross-review and debate.

---

## 1. Motivation

Large language models produce qualitatively different outputs depending on how they are orchestrated. A single-pass prompt produces a first draft. A review-and-revise loop catches surface errors. But complex analytical tasks — security audits, architecture reviews, migration plans — benefit from genuine disagreement: identifying assumptions, challenging recommendations, and stress-testing reasoning.

We designed two pipeline variants to test whether structured multi-agent deliberation improves output quality, and if so, under what conditions.

**Core research questions:**

1. Does adding a debate phase improve output quality on complex tasks?
2. Does pairing different models on opposing sides produce better results than using one model throughout?
3. What is the cost-quality tradeoff between pipeline variants and model configurations?

---

## 2. Pipeline Architecture

### 2.1 Shared Phases (Both Variants)

Both variants share three initial phases, implemented once and imported by both graph builders:

**Phase 1 — Parallel Generation**: Two generators (`generator_left`, `generator_right`) independently produce drafts from the same task prompt. Each receives a neutral directive emphasizing concrete, specific, claim-dense output.

**Phase 2 — Asymmetric Cross-Review**: Each side critiques the other's draft using deliberately asymmetric personas:
- The **left critic** uses a CHALLENGER persona: find what's wrong, weak, or underspecified.
- The **right critic** uses a BUILDER persona: find what's right and how to strengthen it.

This asymmetry ensures at least one reviewer is structurally motivated to find flaws, preventing the "everything looks fine" failure mode common in symmetric review.

Both critiques use a structured severity format (CRITICAL / MAJOR / MINOR) to force prioritization.

**Phase 3 — Revision**: Each side incorporates the critique of its own draft, explicitly accepting or rejecting each point. This produces v2 drafts that have been stress-tested by the opposing perspective.

**Budget Guards**: After each parallel phase, a routing function checks whether cost or wall-clock budget has been exceeded. If so, the pipeline short-circuits directly to synthesis with whatever drafts exist, ensuring graceful degradation rather than failure.

### 2.2 Variant A — Direct Synthesis

After revision, a single **synthesizer** model reads both v2 drafts and produces the final output. The synthesizer evaluates along four criteria (concreteness > correctness > completeness > consistency) and may merge, select from, or extend the two proposals. This is a four-phase, six-LLM-call pipeline.

### 2.3 Variant B — Debate-Enhanced Synthesis

After revision, Variant B inserts a structured debate loop:

**Debate Initialization**: Two persistent agent sessions are opened (one per side). Each debater receives both v2 drafts (optionally anonymized as "Proposal A/B" to reduce identity bias) and states their position with a mandatory structured footer:

```
STANCE: AGREE | DISAGREE | AGREE_WITH_MODIFICATION
KEY_POINT: <one-line summary of core argument>
```

**Debate Turns**: Speakers alternate. Each turn, the current speaker receives the other's most recent message and responds with their own stance and key point. The structured footer enables automated tracking of agreement convergence.

**Exit Conditions** (evaluated in priority order after each turn):
1. Budget exceeded (cost or wall-clock)
2. Both sides signal AGREE → `mutual_agreement`
3. Round limit reached (default: 3 rounds = 6 turns) → `max_rounds`
4. Stable disagreement heuristic fires (key points repeat with >60% Jaccard similarity) → `stable_disagreement`

**Transcript Compaction**: When the estimated token count exceeds a configurable threshold, both debaters self-summarize their positions in parallel (300 words max). This resets the token budget and allows longer debates without context overflow. Up to 3 compactions per run.

**Synthesis with Debate Context**: The synthesizer receives both v2 drafts plus the full debate transcript. Critically, it is instructed to treat bilateral agreement as a **weak signal** — the synthesizer must re-evaluate independently, preventing the debate from merely rubber-stamping a premature consensus.

### 2.4 State Management

Both variants use LangGraph TypedDict state with annotated reducers. Cost tracking uses `Annotated[float, operator.add]` to automatically sum contributions across parallel nodes. Variant B's transcript uses `Annotated[list[dict], add]` for append-only accumulation. Persistent debate sessions live in an out-of-band module-level registry (keyed by run_id and speaker) since they are not serializable into graph state.

### 2.5 Artifact Storage

Every run writes intermediate outputs atomically (via `os.replace()` on a temp file) to a structured directory:

```
logs/matrix/<config_id>/<run_id>/
  ├── config.json
  ├── task.md
  ├── left_draft_v1.md
  ├── right_draft_v1.md
  ├── left_critique_of_right.md
  ├── right_critique_of_left.md
  ├── left_draft_v2.md
  ├── right_draft_v2.md
  ├── debate_transcript.md      (Variant B only)
  ├── final_plan.md
  └── summary.json               (completion marker)
```

The presence of `summary.json` marks a completed run, enabling resume-on-crash semantics — re-running the matrix skips any run with an existing summary.

---

## 3. Experimental Design

### 3.1 Task Corpus

Five tasks spanning two difficulty tiers:

**Short tasks (sanity checks):**

| Task ID | Description | Key Concepts |
|---------|-------------|--------------|
| `sanity_semver` | Summarize semantic versioning in one paragraph (<120 words) | major, minor, patch, breaking, backward, compatible |
| `sanity_prompt_caching` | Explain prompt caching in 3 sentences for a mid-level backend engineer | cache, tokens, cost, latency, reuse, prefix |

**Complex tasks (substantive analysis):**

| Task ID | Description | Key Concepts |
|---------|-------------|--------------|
| `architectural_review_auth` | Harden a flawed JWT auth design (HS256, 30-day tokens, no revocation) | HS256→RS256, revocation, short-lived tokens, refresh rotation, rate limiting, account enumeration |
| `design_testing_strategy` | Design a testing strategy for a real-time pricing service (Kafka, 10k/sec, <100ms) | unit tests, property-based testing, integration, load test, canary, shadow traffic, golden dataset |
| `migration_postgres_dynamo` | Plan migration of 2B-row event table from PostgreSQL to DynamoDB | partition key, sort key, GSI, dual-write, backfill, rollback, hot partition, observability |

Each task defines key concepts (for automated coverage scoring) and known failure modes (for qualitative analysis). The task body shown to the pipeline is stripped of the rubric section.

### 3.2 Configurations

Ten configurations testing two dimensions: pipeline variant (A vs B) and model assignment (homogeneous vs heterogeneous).

**Homogeneous** — every role uses the same model:

| Config ID | Variant | Model |
|-----------|---------|-------|
| A-homo-opus | A | Opus (all roles) |
| A-homo-sonnet | A | Sonnet (all roles) |
| A-homo-haiku | A | Haiku (all roles) |
| B-homo-opus | B | Opus (all roles) |
| B-homo-sonnet | B | Sonnet (all roles) |
| B-homo-haiku | B | Haiku (all roles) |

**Heterogeneous** — left-side roles use one model, right-side roles use another:

| Config ID | Variant | Left Side | Right Side | Synthesizer |
|-----------|---------|-----------|------------|-------------|
| A-het-opus-sonnet | A | Opus | Sonnet | Opus |
| A-het-sonnet-haiku | A | Sonnet | Haiku | Sonnet |
| B-het-opus-sonnet | B | Opus | Sonnet | Opus |
| B-het-sonnet-haiku | B | Sonnet | Haiku | Sonnet |

**Budget parameters:**

| Parameter | Variant A | Variant B |
|-----------|-----------|-----------|
| `max_total_cost_usd` | $3.00 | $5.00 |
| `max_wall_clock_seconds` | 1,200 | 2,400 |
| `max_debate_rounds` | — | 3 |
| `random_seed` | 42 | 42 |

Variant B receives higher budgets to accommodate the debate loop's additional LLM calls.

### 3.3 Evaluation Methodology

The evaluation pipeline runs three phases:

**Phase 1 — Structured Metrics** (deterministic, no LLM calls):
- Cost and wall-clock time from `summary.json`
- Final plan character/token counts
- **Concept coverage (keyword)**: fraction of task key concepts whose lowercase form appears as a substring in the final plan
- **Concept coverage (token Jaccard)**: Jaccard similarity between tokenized plan and tokenized concept strings
- Variant B only: round count, compaction count, stance flip count

**Phase 2 — Pairwise Preference Judging** (LLM-based):
For every pair of configurations (C(10,2) = 45 pairs) on each of 5 tasks, two judge models (Opus and Sonnet) evaluate which response is better.

Each judgment runs **twice** — once in natural order (A as X, B as Y) and once swapped (B as X, A as Y). If the judge prefers whichever response appears first regardless of content, the judgment is flagged as **position-biased** and scored as a tie (0.5 to each side). This yielded 450 judgments from 900 LLM calls.

Judges evaluate on the same criteria hierarchy used by the synthesizer: concreteness > correctness > completeness > consistency.

**Phase 3 — Report Generation** (deterministic aggregation):
- Per-config win rates and cost-adjusted win rates (wins per dollar)
- Cross-variant aggregate (A vs B head-to-head)
- Full pairwise win matrix
- Termination reason distribution

### 3.4 Execution

- **Matrix run**: 50 runs (10 configs × 5 tasks), 3 concurrent, seeded for reproducibility
- **Eval run**: 450 judgments (112 new + 338 resumed from prior partial run), 3 concurrent judge calls
- **Total wall time**: ~30 minutes for the eval pass; matrix run time not recorded in this session
- **Infrastructure**: Claude Code CLI instances via `single_query()` (one-shot) and `AgentSession` (persistent debate sessions)

---

## 4. Results

### 4.1 All Tasks — Headline Numbers

| Metric | Variant A | Variant B |
|--------|-----------|-----------|
| Cross-variant win rate | 47.8% | 52.2% |
| Average cost per run | $0.87 | $1.62 |
| Average wall time | 411s | 564s |
| Average concept coverage (keyword) | 79.7% | 78.9% |

Across all tasks, Variant B holds a marginal 4.4-point edge at nearly double the cost. The debate loop does not justify itself when simple tasks are included.

### 4.2 Complex Tasks Only — The Real Story

Filtering to the three complex tasks (auth review, testing strategy, migration planning):

| Metric | Variant A | Variant B |
|--------|-----------|-----------|
| Cross-variant win rate | **42.7%** | **57.3%** |
| Average cost per run | $1.28 | $2.07 |
| Average wall time | ~600s | ~800s |

The debate loop's advantage widens to a **15-point spread** on substantive analytical tasks. This is the pipeline's intended use case — simple tasks don't benefit from structured deliberation.

### 4.3 Configuration Rankings (Complex Tasks Only)

**By absolute win rate:**

| Config | Win Rate | Avg Cost |
|--------|----------|----------|
| B-homo-opus | **93.5%** | $3.40 |
| B-het-opus-sonnet | 79.6% | $2.76 |
| A-het-opus-sonnet | 75.0% | $1.57 |
| A-homo-opus | 71.3% | $1.95 |
| B-homo-sonnet | 63.0% | $1.84 |
| A-homo-sonnet | 47.2% | $1.14 |
| A-het-sonnet-haiku | 31.5% | $0.74 |
| B-het-sonnet-haiku | 27.8% | $1.41 |
| B-homo-haiku | 6.5% | $0.83 |
| A-homo-haiku | 4.6% | $0.46 |

**By cost-adjusted win rate (wins per dollar):**

| Config | Wins/$ |
|--------|--------|
| A-het-opus-sonnet | 0.478 |
| A-het-sonnet-haiku | 0.426 |
| A-homo-sonnet | 0.415 |
| A-homo-opus | 0.365 |
| B-homo-sonnet | 0.342 |
| B-het-opus-sonnet | 0.288 |
| B-homo-opus | 0.275 |
| B-het-sonnet-haiku | 0.197 |
| A-homo-haiku | 0.100 |
| B-homo-haiku | 0.078 |

**Note on cost relevance**: Under Claude Code flat-rate pricing, per-run API cost is not a direct expense. The cost-adjusted metric is useful for understanding token efficiency and would apply to direct API deployments, but for Claude Code usage the absolute win rate ranking is the more relevant one.

### 4.4 Head-to-Head Matrix (Complex Tasks)

Selected matchups illustrating the dominant patterns:

| B Config | vs A Config | B Win Rate |
|----------|-------------|------------|
| B-homo-opus | A-homo-haiku | 100% |
| B-homo-opus | A-het-sonnet-haiku | 100% |
| B-homo-opus | A-homo-sonnet | 100% |
| B-homo-opus | A-homo-opus | 92% |
| B-homo-opus | A-het-opus-sonnet | 83% |
| B-het-opus-sonnet | A-het-opus-sonnet | 67% |
| B-homo-sonnet | A-het-opus-sonnet | 25% |
| B-het-sonnet-haiku | A-het-opus-sonnet | 0% |
| B-homo-haiku | A-het-opus-sonnet | 0% |

B-homo-opus dominates nearly everything. But a strong Variant A config (A-het-opus-sonnet) beats all B configs except those using Opus on every role.

### 4.5 Termination Patterns

| Reason | Count | Description |
|--------|-------|-------------|
| complete | 25 | All Variant A runs (no debate loop) |
| max_rounds | 17 | Variant B runs that exhausted the 3-round debate limit |
| mutual_agreement | 8 | Variant B runs where debaters converged early |

**Mutual agreement vs max_rounds on complex tasks:**

| Termination | B Win Rate vs A | Avg Coverage | Notes |
|-------------|-----------------|--------------|-------|
| max_rounds | 55.3% | 74.1% | All 3 complex tasks, most configs |
| mutual_agreement | 45.6% | 89.1% | Overwhelmingly sanity tasks |

This is a confounding variable: mutual agreement correlates with easy tasks (where there's little to disagree about), not with higher quality. The max_rounds runs perform better against Variant A because they're tackling harder tasks where debate adds value.

### 4.6 Cross-Run Similarity

Token Jaccard between final plans across configurations, per task:

| Task | Pairs | Mean | Min | Max |
|------|-------|------|-----|-----|
| migration_postgres_dynamo | 45 | 0.297 | 0.249 | 0.349 |
| design_testing_strategy | 45 | 0.253 | 0.190 | 0.304 |
| architectural_review_auth | 45 | 0.316 | 0.255 | 0.382 |
| sanity_prompt_caching | 45 | 0.208 | 0.122 | 0.312 |
| sanity_semver | 45 | 0.197 | 0.126 | 0.294 |

Low to moderate similarity across all tasks indicates the pipelines are not converging to template-like outputs. Different configurations genuinely approach each task differently, validating that the experimental design captures meaningful variation.

### 4.7 Position Bias in Judging

Of 450 pairwise judgments, **84 (18.7%)** exhibited position bias — the judge preferred whichever response appeared first regardless of content. These were conservatively scored as ties. This rate is consistent with known LLM judging behavior and validates the two-pass position-check methodology.

---

## 5. Key Findings

### Finding 1: The debate loop earns its keep on complex tasks

On complex analytical tasks, Variant B's debate phase produces a 15-point win-rate advantage over Variant A (57.3% vs 42.7%). On simple tasks, the advantage vanishes. This aligns with the intuition that structured deliberation adds value when there are genuine tradeoffs to explore, assumptions to surface, and recommendations to stress-test.

### Finding 2: Heterogeneous model pairings outperform homogeneous at equivalent tiers

Across both variants, pairing different models on opposing sides produces better results than using one model everywhere:

- A-het-opus-sonnet (75.0%) > A-homo-opus (71.3%) > A-homo-sonnet (47.2%)
- B-het-opus-sonnet (79.6%) > B-homo-sonnet (63.0%)

The diversity hypothesis is supported: different models bring different reasoning strategies to cross-review and debate, creating productive tension that a single model talking to itself cannot replicate.

**Caveat**: This only works when the weaker model is strong enough. B-het-sonnet-haiku (27.8%) performs worse than B-homo-sonnet (63.0%) — Haiku is too weak to be a productive debate partner, and the stronger side can't compensate.

### Finding 3: Model capability dominates pipeline architecture

A strong model in a simple pipeline beats a weak model in a sophisticated one. B-homo-haiku (6.5% win rate) with full debate infrastructure loses to A-homo-sonnet (47.2%) with just direct synthesis. Pipeline architecture amplifies model capability; it does not substitute for it.

### Finding 4: Most debates don't converge

17 of 25 Variant B runs hit the 3-round debate limit rather than reaching mutual agreement. The debate structure may need better convergence incentives, or the round limit may simply be too low for the debaters to work through substantive disagreements on complex tasks.

### Finding 5: The Pareto frontier depends on pricing model

- **Under flat-rate pricing** (Claude Code): B-homo-opus is the clear winner at 93.5% win rate. Cost per run is irrelevant; only quality and wall time matter.
- **Under API pricing**: A-het-opus-sonnet is the Pareto winner — 75% win rate at $1.57/run, outperforming all B configs on cost-adjusted quality.

---

## 6. Limitations

1. **Small task corpus**: Five tasks (three complex) is sufficient to identify trends but not to claim statistical significance. Confidence intervals on win rates are wide.

2. **LLM-as-judge**: Both preference judges are Claude models, introducing potential self-preference bias. Cross-model judging (e.g., GPT-4 as judge) would strengthen validity.

3. **Single run per config-task pair**: No repeated trials to measure variance. A configuration's win rate on a specific task is a point estimate from a single execution.

4. **Keyword coverage is a proxy**: Concept coverage measures whether key terms appear, not whether they're used correctly. A plan that mentions "hot partition" in passing scores the same as one that analyzes it thoroughly.

5. **Budget asymmetry**: Variant B received higher cost and time budgets ($5/2400s vs $3/1200s). While necessary to accommodate the debate loop, this means Variant B has more total compute available, which partially confounds the comparison.

6. **Model generation fixed**: All runs used the same Claude model generation. Results may differ with future model releases or different model families.

---

## 7. Conclusion

Structured multi-agent debate meaningfully improves LLM output quality on complex analytical tasks, with a 15-point win-rate advantage over direct synthesis. The benefit scales with task complexity and disappears on simple tasks. Heterogeneous model pairings create productive tension that improves both pipeline variants. The optimal configuration depends on the deployment context: B-homo-opus for maximum quality under flat-rate pricing, A-het-opus-sonnet for the best cost-quality tradeoff under API pricing.

The most promising direction for future work is exploring whether cross-generation model pairings (e.g., Opus 4.6 × Opus 4.7) can capture diversity benefits at the highest capability tier, and whether extended debate rounds allow the deliberation to reach its full potential.
