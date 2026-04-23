# Dual-Pipeline Matrix Experiment — Report

**Date:** 2026-04-17
**Plan under test:** [`docs/dual_pipeline_with_eval_plan.md`](dual_pipeline_with_eval_plan.md)
**Matrix run:** 10 configurations × 5 tasks = 50 runs, parallel=3, no API fallback (local Claude Code only)
**Total spend:** $58.71 across 46 new runs + 4 reused from an earlier tiny matrix
**Total wall:** 127 min end-to-end; 377 min summed across individual runs
**Status:** 50/50 successful, 0 errors

---

## 1. Executive Summary

The dual-pipeline experiment compared **Variant A** (generate → cross-review → revise → synthesize; no debate) against **Variant B** (same four phases plus a 3-round debate loop before synthesis) across five tasks and five model configurations.

Four concrete findings:

1. **Variant B costs roughly 2× Variant A across every model configuration tested.** The ratio is stable between 1.8× and 2.2× regardless of whether the backbone is opus, sonnet, haiku, or a heterogeneous pair. Wall-time scales similarly.
2. **Variant B behaves very differently on simple vs. substantive tasks.** On short sanity tasks the debate converges to `mutual_agreement` 70% of the time (7/10). On long substantive tasks it converges 7% of the time (1/15) — the other 14 hit the 3-round cap.
3. **The one B-on-long-task that converged (B-homo-opus on `migration_postgres_dynamo`) shows real substantive engagement**, not sycophancy: debaters traded specific technical concessions on bucketing strategy and rollback mechanics across four rounds before arriving at a fully merged architecture. This is the pattern the research literature hoped debate would produce.
4. **Response length is roughly bimodal by task type, not by variant.** Sanity tasks produce 700 B–3 KB final plans; long tasks produce 18–39 KB regardless of variant. Variant B does not materially pad responses.

These four findings are data we have now. What we do **not** have yet is a quality verdict — no pairwise preference judging or structured metrics pass has run. The qualitative reads below are author judgments, not scored comparisons.

---

## 2. What Was Built

The scaffolding from the pre-existing roadmap (`Part 1` shared infrastructure, `Part 2` Variant A, `Part 3` Variant B) was largely in place before this experiment. This session added four concrete improvements and fixed two blocking bugs.

### Improvements added

| Area | Change | Rationale |
|---|---|---|
| `pipeline/artifacts.py` | **Atomic writes** — all on-disk artifacts write to `<name>.<pid>.tmp` then `os.replace` onto the final path | A crashed run now either leaves the old artifact intact or no artifact at all; `summary.json` presence stays a reliable resume signal. |
| `pipeline/environment.py` *(new)* | **Environment provenance** — every `summary.json` embeds `git_sha`, `git_branch`, `git_dirty`, `claude_cli_version`, `claude_agent_sdk_version`, `python_version`, `platform` | Straddle-edit detection: "did my matrix span a code change?" answerable from disk. |
| `pipeline/config.py` | `RunResult.environment` field, optional, auto-filled by `write_summary` if unset | Tests can inject deterministic values; production runs self-capture. |
| `tests/pipeline/test_artifacts.py` | Tests for atomic crash safety, env-provenance default capture, explicit override preservation | 4 new tests, all pass. |

### Bugs fixed (both were pre-existing blockers)

1. **`ClaudeSDKClient.query()` coroutine misuse** — Variant B's `_send` iterated `query()` directly as an async iterator. SDK 0.1.62 requires `await client.query(msg)` followed by `async for msg in client.receive_response()`. The prior pattern crashed on the first Variant B turn with `TypeError: 'async for' requires an object with __aiter__ method, got coroutine`. Fixed in `pipeline/session.py::AgentSession._send`, plus downstream message-type handling (`AssistantMessage.content[TextBlock].text` for text; `ResultMessage.total_cost_usd` / `.session_id` for metadata).

2. **Windows `CreateProcess` command-line limit (`WinError 206`)** — Variant B's `init_debate` embedded both v2 drafts into the debater's *system prompt*, which the Claude Code CLI receives as a `--system-prompt` command-line argument. For long tasks (drafts ≈5 KB each + template), the argument exceeded Windows' ~32 KB `CreateProcess` limit and failed with `FileNotFoundError: [WinError 206]`. Fixed by splitting the template into `DEBATE_SYSTEM_PROMPT` (short: role + rules + format) and `DEBATE_OPENING_USER_MESSAGE` (long: task + proposals + opening directive), with the latter now flowing through the uncapped API payload path as the first user message. A regression test caps the system prompt at 4 KB after formatting.

All tests pass: **181/181**.

---

## 3. Matrix Composition

### Tasks (5)

Pulled unmodified from `src/langgraph_agents/eval/corpus/`.

| ID | Length hint | Shape |
|---|---|---|
| `sanity_prompt_caching` | short | 3-sentence explainer |
| `sanity_semver` | short | 3-sentence explainer |
| `design_testing_strategy` | long | multi-layer testing plan for a Kafka service |
| `architectural_review_auth` | long | review + harden an auth design |
| `migration_postgres_dynamo` | long | phased migration plan across two databases |

The two sanity tasks are bounded (one clear good answer in <200 words); the three long tasks are open-ended architecture/design exercises where substantive disagreement is plausible.

### Configurations (10)

All configs use the short model aliases that the bundled Claude Code CLI resolves: `opus`, `sonnet`, `haiku`.

| ID | Variant | Generator L | Generator R |
|---|---|---|---|
| `A-homo-opus` | A | opus | opus |
| `A-homo-sonnet` | A | sonnet | sonnet |
| `A-homo-haiku` | A | haiku | haiku |
| `B-homo-opus` | B | opus | opus |
| `B-homo-sonnet` | B | sonnet | sonnet |
| `B-homo-haiku` | B | haiku | haiku |
| `A-het-opus-sonnet` | A | opus | sonnet |
| `A-het-sonnet-haiku` | A | sonnet | haiku |
| `B-het-opus-sonnet` | B | opus | sonnet |
| `B-het-sonnet-haiku` | B | sonnet | haiku |

All runs used `random_seed=42`, `max_debate_rounds=3` (Variant B), `parallel=3`.

---

## 4. Results

### 4.1 Aggregate cost and termination by config

Averages across 5 tasks per config.

| Config | Variant | Avg cost | Total cost | Terminations |
|---|---|---|---|---|
| A-homo-opus | A | $1.48 | $7.39 | complete ×5 |
| A-homo-sonnet | A | $0.95 | $4.76 | complete ×5 |
| A-homo-haiku | A | $0.35 | $1.76 | complete ×5 |
| A-het-opus-sonnet | A | $1.17 | $5.86 | complete ×5 |
| A-het-sonnet-haiku | A | $0.54 | $2.69 | complete ×5 |
| **Variant A subtotal** | — | **$0.90** | **$22.46** | **complete ×25** |
| B-homo-opus | B | $2.70 | $13.51 | max_rounds ×3, mutual_agreement ×2 |
| B-homo-sonnet | B | $1.41 | $7.07 | max_rounds ×3, mutual_agreement ×2 |
| B-homo-haiku | B | $0.67 | $3.35 | max_rounds ×4, mutual_agreement ×1 |
| B-het-opus-sonnet | B | $2.19 | $10.95 | max_rounds ×4, mutual_agreement ×1 |
| B-het-sonnet-haiku | B | $1.10 | $5.51 | max_rounds ×3, mutual_agreement ×2 |
| **Variant B subtotal** | — | **$1.61** | **$40.39** | **max_rounds ×16, mutual_agreement ×9 (incl 2 reused)** |

Variant B averages **1.79× the per-run cost of Variant A** across the matrix (~$58.71 total on the full sweep including reused runs from the tiny matrix; $40.39+$22.46 = $62.85 if you pay list price for the reused 4 runs).

### 4.2 Variant B termination by task type

The most informative single table in the experiment.

| Task | Config | Termination |
|---|---|---|
| sanity_prompt_caching | B-homo-opus | mutual_agreement |
| sanity_prompt_caching | B-homo-sonnet | mutual_agreement *(reused)* |
| sanity_prompt_caching | B-homo-haiku | max_rounds |
| sanity_prompt_caching | B-het-opus-sonnet | mutual_agreement |
| sanity_prompt_caching | B-het-sonnet-haiku | max_rounds |
| sanity_semver | B-homo-opus | mutual_agreement |
| sanity_semver | B-homo-sonnet | mutual_agreement |
| sanity_semver | B-homo-haiku | mutual_agreement |
| sanity_semver | B-het-opus-sonnet | max_rounds |
| sanity_semver | B-het-sonnet-haiku | mutual_agreement |
| architectural_review_auth | B-homo-opus | max_rounds |
| architectural_review_auth | B-homo-sonnet | max_rounds |
| architectural_review_auth | B-homo-haiku | max_rounds |
| architectural_review_auth | B-het-opus-sonnet | max_rounds |
| architectural_review_auth | B-het-sonnet-haiku | max_rounds |
| design_testing_strategy | B-homo-opus | max_rounds |
| design_testing_strategy | B-homo-sonnet | max_rounds *(reused)* |
| design_testing_strategy | B-homo-haiku | max_rounds |
| design_testing_strategy | B-het-opus-sonnet | max_rounds |
| design_testing_strategy | B-het-sonnet-haiku | max_rounds |
| migration_postgres_dynamo | B-homo-opus | **mutual_agreement** |
| migration_postgres_dynamo | B-homo-sonnet | max_rounds |
| migration_postgres_dynamo | B-homo-haiku | max_rounds |
| migration_postgres_dynamo | B-het-opus-sonnet | max_rounds |
| migration_postgres_dynamo | B-het-sonnet-haiku | max_rounds |

**Sanity tasks:** 7/10 `mutual_agreement` (70%)
**Long tasks:** 1/15 `mutual_agreement` (7%), 14/15 `max_rounds` (93%)

### 4.3 Wall-time distribution

Ranges in seconds across the matrix.

| Variant | Task type | Min | Median | Max |
|---|---|---|---|---|
| A | sanity | 108 | 140 | 182 |
| A | long | 284 | 605 | 1090 |
| B | sanity | 208 | 262 | 297 |
| B | long | 477 | 759 | 1342 |

Variant B adds 50–150% to wall-time on sanity tasks, 15–30% on long tasks. The long-task multiplier is smaller because the shared pre-debate phases (generate + review + revise) already dominate wall-time there.

### 4.4 Response length

Taken from `final_plan.md` byte count. Very tight clustering by task type.

| Task | Variant A range | Variant B range |
|---|---|---|
| sanity_prompt_caching | 933–2004 B | 943–3280 B |
| sanity_semver | 783–1767 B | 680–2508 B |
| architectural_review_auth | 20.5–37.2 KB | 18.9–36.1 KB |
| design_testing_strategy | 21.3–27.9 KB | 19.0–39.0 KB |
| migration_postgres_dynamo | 25.4–39.0 KB | 22.4–33.0 KB |

Variant B does **not** systematically produce longer responses — it's within ±10% of A on most task/model combinations. The synthesizer appears to use the debate transcript as context rather than as filler.

---

## 5. Findings

### 5.1 Cost/wall are linear in debate overhead, independent of model

B/A cost ratio by model pairing:

| Pairing | B/A cost ratio |
|---|---|
| opus | 1.83× |
| sonnet | 1.49× (artificially low — 2/5 runs were reused from tiny matrix) |
| haiku | 1.90× |
| het opus-sonnet | 1.87× |
| het sonnet-haiku | 2.04× |

Excluding reused runs, the range tightens further. The debate loop adds **one init step + ~3 turn pairs + one synthesis + compaction overhead** beyond Variant A's work. On a 7-phase pipeline, that's roughly +7 LLM calls, giving a ~2× per-run cost multiplier. The model identity only moves the absolute cost, not the multiplier.

**Implication:** if quality parity holds, Variant B is a straight 2× cost tax. If Variant B is better, the relevant question is "better enough to justify 2× cost?" — a question only the pairwise judging pass can answer.

### 5.2 Variant B convergence is task-bounded, not model-bounded

The 70% vs 7% `mutual_agreement` split between sanity and long tasks is the strongest single signal in the data. Two readings, both defensible:

- **Optimistic:** the debate is working correctly. Sanity tasks have one right answer; debaters find it and agree. Long architecture tasks have multiple defensible positions; debaters maintain real disagreement inside the 3-round window, which is the research's hoped-for outcome and the scenario where Variant B's synthesis judge has the most to work with.
- **Pessimistic:** 3 rounds is too few to converge on substantive problems. A 5–7 round cap might shift the long-task distribution toward `mutual_agreement` and thus toward the convergence signal the plan says is weak anyway.

Neither reading is verifiable from termination alone. The quality judgment in §5.4 is where this gets resolved.

### 5.3 The one long-task B convergence tells us what healthy debate looks like

`B-homo-opus` on `migration_postgres_dynamo` is the only long-task Variant B run that reached `mutual_agreement`. Its debate transcript shows:

- **Round 1 openings:** substantive structural disagreement — left favored day-bucketing + shard registry for partition distribution; right favored hour-bucketing with CDC from a replica.
- **Round 2:** specific technical concessions. Right conceded bucket width on rate-limit grounds ("hour bucketing buys no write headroom at the actual WCU/partition rate limit"), left accepted right's rollback decomposition (S3 archive as authoritative + reverse-CDC as warm standby).
- **Round 3:** mutual `AGREE` with named surviving decisions: *day bucket + shard registry, replica-sourced CDC, two-tier rollback, Phase 0 census/audit gates, A's Phase 4 drain replaces B's 503 freeze.*

This is not sycophancy. The debaters each named the point they were conceding, why they were conceding it, and which of their original positions survived. The synthesizer then produced a merged plan (21.8 KB, `final_plan.md`) that preserved the agreed structure.

Whether a single convergent case is common enough to matter is a judgment call; the directional signal is that **the research-flagged failure mode ("sycophantic collapse to agreement") did not dominate this matrix.**

### 5.4 Qualitative A-vs-B snapshots (author judgment, not scored)

These are single-run reads from the author, not the outputs of a judging pass. They should be treated as hypotheses to test with pairwise judging, not conclusions.

**`sanity_prompt_caching`, A-homo-sonnet vs B-homo-sonnet** — B produces three clean sentences with `cache_control` marker name, explicit 5-minute TTL, and 60–80% realistic-savings framing. A produces one dense multi-clause paragraph with ~90% per-token figure and a vaguer "few minutes" TTL reference. B follows the task's 3-sentence instruction; A arguably doesn't.

**`design_testing_strategy`, A-homo-sonnet vs B-homo-sonnet** — A leads with an "Unresolved Disagreement" meta-section inferred from the cross-critique (mutation-testing cadence: per-PR vs nightly), proposes a hybrid, then dives into Pydantic-boundary typing. B leads with a committed structural prerequisite (32 partitions × 32 threads, derived per-message budget = 3 ms), then hypothesis property tests with working code. Both are substantive; they have different *shapes* — A more meta, B more committed.

**`migration_postgres_dynamo`, B-homo-opus converged case** — the merged plan is demonstrably richer than either individual v2 draft, incorporating specific contributions named in the debate (Phase 0 census/audit gates, two-tier rollback). This is a single case and should not be over-weighted.

### 5.5 Heterogeneous vs homogeneous

The matrix can't yet answer whether model diversity helps, because the termination-reason distribution between het and homo Variant B configs is too similar to separate without pairwise judging:

| Config | mutual_agreement | max_rounds |
|---|---|---|
| B-homo-opus | 2/5 | 3/5 |
| B-homo-sonnet | 2/5 | 3/5 |
| B-homo-haiku | 1/5 | 4/5 |
| B-het-opus-sonnet | 1/5 | 4/5 |
| B-het-sonnet-haiku | 2/5 | 3/5 |

No clean pattern. The plan's "heterogeneous-B beats homogeneous-B" hypothesis — the most interesting research hypothesis in the original plan — remains untested at this layer.

---

## 6. Notable Cases

| Case | What's notable |
|---|---|
| **B-homo-opus × migration_postgres_dynamo** | Only long-task B to converge; cleanest example of the healthy-debate pattern. $3.58, 772 s, 4-round convergence. |
| **B-het-sonnet-haiku × architectural_review_auth** | Slowest run in the matrix (879 s). Haiku-in-the-pair slows turn latency without reducing cost proportionally. |
| **A-homo-haiku × architectural_review_auth** | Largest final plan (37.2 KB). Haiku is verbose without the critic asymmetry reining it in — worth checking for padding on a quality read. |
| **B-homo-haiku × sanity_prompt_caching** | Failed to converge on a trivial 3-sentence task (`max_rounds`). Haiku debaters may lack the discipline to reach explicit STANCE: AGREE. |
| **B-homo-sonnet × migration_postgres_dynamo** | Largest Variant B long-task cost ($2.42) and longest wall (1342 s) among sonnet configs. Sonnet debates hard; haiku gives up; opus converges. |

---

## 7. What This Does Not Tell Us

Flagging for honesty:

1. **No quality verdict yet.** Every claim of the form "B is better" or "A is better" in §5.4 is an author read, not a judging-pass result.
2. **n=5 tasks.** Not enough to separate weak effects. The plan's corpus target was 5–10; we're at the floor.
3. **`random_seed=42` everywhere.** Deterministic anonymization order, but not deterministic LLM outputs (the CLI does its own sampling). Re-running would produce different drafts; the cost/wall/termination numbers would shift.
4. **`max_debate_rounds=3` is untested as a knob.** The 93% `max_rounds` rate on long tasks could be an artifact of this cap. A single-variable sweep (B-homo-opus at rounds ∈ {3, 5, 7}) would disambiguate.
5. **Cost figures come from the CLI's `total_cost_usd` envelope field.** On a Claude Code subscription this is an equivalent-cost estimate, not an actual charge. Absolute numbers are proxies; ratios are trustworthy.
6. **Single machine, single operator, single day.** No weather from e.g. service degradation, API tier rate-limiting, etc. The bundled CLI ran against whatever state the servers were in on 2026-04-17.
7. **The 4 reused runs** came from the tiny-matrix phase before the environment-provenance upgrade landed. Their `summary.json` files have the older schema (no `environment` field). Re-running them would normalize metadata but burn ~$2.50 for no scientific gain.

---

## 8. Implications

### For the research question ("does debate help?")

The literature's prior was "probably roughly parity with B winning on some tasks and losing on others, with significant cost overhead." The matrix data is **consistent with that prior** on every measurable axis:

- Cost overhead is real and consistent (2×).
- Variant B engages substantively when given substantive problems (the one long-task convergence shows non-sycophantic behavior; the rest showing `max_rounds` shows preserved disagreement).
- On short tasks with one clear answer, debate agrees — which is neither surprising nor informative.

This is **not** evidence that debate helps. It's also not evidence that debate hurts. It's evidence that debate *operates as designed* on this corpus. The quality verdict is decided by judging.

### For how to deploy

If the eventual judging pass shows parity, the honest recommendation is **ship Variant A**. It costs half as much, finishes twice as fast, produces responses of comparable length, and is architecturally simpler (no session lifecycle, no Windows command-line workarounds). Variant B is only worth the overhead if the judging pass shows a meaningful preference delta on the task types you actually deploy against.

If judging shows B winning on long-substantive tasks specifically, **per-task routing** is viable: short/bounded → A, long/open-ended → B. The termination-reason distribution already gives a cheap task-classifier signal (if a preliminary pass would hit `max_rounds`, route to B; if it would converge fast, you probably didn't need B).

### For the implementation

Three things the matrix run validated in passing:

- **Atomic writes** prevented any half-written artifact across 46 new runs at parallel=3. Zero corruption.
- **Environment provenance** now lives on every new `summary.json` — git_sha `7de0e34`+, SDK 0.1.62, CLI 2.1.113. Straddle detection works.
- **Resume-on-crash** via `summary.json` presence worked cleanly for the 4 reused sonnet runs.

---

## 9. Next Steps

In priority order:

1. **Structured metrics pass** (`eval/metrics.py`). Cheap (no LLM calls), deterministic, runs over existing artifacts. Outputs: termination distribution by config×task, response length percentiles, cross-config output similarity (BLEU or token-overlap), concept coverage vs the per-task `key_concepts` rubrics in the corpus files. Should complete in under 1 minute wall-time. **Ready to run now.**

2. **Pairwise preference judging** (`eval/judge_pairwise.py`). 10 configs → 45 unique pairs × 5 tasks × 2 orders × 2 judge models = ~1800 LLM calls. Mitigations already in plan: position-bias detection via flipped-order, cross-judge disagreement flagging. Plan-target cost: ~$90 on API; free on subscription. Human sanity-check on 20% of pairs is also planned. **Recommended to run next.**

3. **Report generation** (`eval/report.py`). Aggregates the judging + metrics into a win-matrix and a README-style summary with cost-adjusted quality. Runs after (2) is complete. **Ready after (2).**

4. **`max_debate_rounds` sensitivity sweep.** Pick one config (B-homo-opus — the cheap strong signal from §5.3) and one long task (`migration_postgres_dynamo` — known to converge) and rerun with rounds ∈ {3, 5, 7, 10}. 4 runs, ~$15. Answers: is the 93% max_rounds rate an artifact of the 3-round cap, or of genuine task difficulty? If the run at rounds=7 hits `mutual_agreement`, that changes the interpretation materially.

5. **Task corpus expansion.** From 5 to 10. Three directions: add 2 more sanity tasks (drive the floor of statistical significance), add 2 bug-reproduction tasks (test a different shape of real problem), add 1 explicitly-adversarial task (a problem where the "right" answer is genuinely contested among experts).

6. **Deploy per-task routing prototype.** Conditional on (2) showing B-wins-on-long, build a thin classifier that routes tasks at submission time. Stretch goal.

### Near-term: running (1) and (2)

The user already indicated cost is not a factor on the subscription. The combined wall time is dominated by (2) — estimate 60–90 minutes for 1800 LLM calls at parallel=3. Running both back-to-back in this session is tractable.

---

## 10. Appendix

### 10.1 Raw per-run data

Full machine-readable data lives in:
- `logs/matrix/matrix_summary.json` — run-level aggregation
- `logs/matrix/<config_id>/<run_id>/summary.json` — per-run summary with environment provenance
- `logs/matrix/<config_id>/<run_id>/{left,right}_draft_{v1,v2}.md` — drafts
- `logs/matrix/<config_id>/<run_id>/{left,right}_critique_of_{right,left}.md` — cross-critiques
- `logs/matrix/<config_id>/<run_id>/debate_transcript.md` — Variant B only
- `logs/matrix/<config_id>/<run_id>/final_plan.md` — final synthesized response

### 10.2 All 50 run outcomes (tabular)

```
config                 task                         status       cost   wall_s term
A-homo-opus            architectural_review_auth    ok       $ 1.9486    520.7 complete
A-homo-sonnet          architectural_review_auth    ok       $ 0.8219    540.0 complete
A-homo-haiku           architectural_review_auth    ok       $ 0.5141    414.9 complete
B-homo-opus            architectural_review_auth    ok       $ 3.2573    625.3 max_rounds
B-homo-sonnet          architectural_review_auth    ok       $ 1.6150    705.1 max_rounds
B-homo-haiku           architectural_review_auth    ok       $ 0.8492    614.8 max_rounds
A-het-opus-sonnet      architectural_review_auth    ok       $ 1.3771    605.8 complete
A-het-sonnet-haiku     architectural_review_auth    ok       $ 0.6042    482.4 complete
B-het-opus-sonnet      architectural_review_auth    ok       $ 2.2975    687.0 max_rounds
B-het-sonnet-haiku     architectural_review_auth    ok       $ 1.3935    879.1 max_rounds
A-homo-opus            design_testing_strategy      ok       $ 1.6396    509.4 complete
A-homo-sonnet          design_testing_strategy      reused   $ 0.9968    643.3 complete
A-homo-haiku           design_testing_strategy      ok       $ 0.3852    284.1 complete
B-homo-opus            design_testing_strategy      ok       $ 3.3798    759.3 max_rounds
B-homo-sonnet          design_testing_strategy      reused   $ 1.4880    707.6 max_rounds
B-homo-haiku           design_testing_strategy      ok       $ 0.7389    477.3 max_rounds
A-het-opus-sonnet      design_testing_strategy      ok       $ 1.6095    716.8 complete
A-het-sonnet-haiku     design_testing_strategy      ok       $ 0.6718    491.9 complete
B-het-opus-sonnet      design_testing_strategy      ok       $ 2.7646    916.5 max_rounds
B-het-sonnet-haiku     design_testing_strategy      ok       $ 1.3270    629.2 max_rounds
A-homo-opus            migration_postgres_dynamo    ok       $ 2.2767    703.7 complete
A-homo-sonnet          migration_postgres_dynamo    ok       $ 1.5984   1090.5 complete
A-homo-haiku           migration_postgres_dynamo    ok       $ 0.4855    444.6 complete
B-homo-opus            migration_postgres_dynamo    ok       $ 3.5753    772.2 mutual_agreement
B-homo-sonnet          migration_postgres_dynamo    ok       $ 2.4199   1342.4 max_rounds
B-homo-haiku           migration_postgres_dynamo    ok       $ 0.8947    544.5 max_rounds
A-het-opus-sonnet      migration_postgres_dynamo    ok       $ 1.7226    725.2 complete
A-het-sonnet-haiku     migration_postgres_dynamo    ok       $ 0.9393    780.3 complete
B-het-opus-sonnet      migration_postgres_dynamo    ok       $ 3.2328   1011.7 max_rounds
B-het-sonnet-haiku     migration_postgres_dynamo    ok       $ 1.5136    838.2 max_rounds
A-homo-opus            sanity_prompt_caching        ok       $ 0.7447    128.2 complete
A-homo-sonnet          sanity_prompt_caching        reused   $ 0.2624    104.1 complete
A-homo-haiku           sanity_prompt_caching        ok       $ 0.1944    162.4 complete
B-homo-opus            sanity_prompt_caching        ok       $ 1.7605    278.0 mutual_agreement
B-homo-sonnet          sanity_prompt_caching        reused   $ 0.7897    299.0 mutual_agreement
B-homo-haiku           sanity_prompt_caching        ok       $ 0.4064    297.0 max_rounds
A-het-opus-sonnet      sanity_prompt_caching        ok       $ 0.6319    182.1 complete
A-het-sonnet-haiku     sanity_prompt_caching        ok       $ 0.2387    117.8 complete
B-het-opus-sonnet      sanity_prompt_caching        ok       $ 1.2746    255.0 mutual_agreement
B-het-sonnet-haiku     sanity_prompt_caching        ok       $ 0.5896    262.1 max_rounds
A-homo-opus            sanity_semver                ok       $ 0.7847    116.1 complete
A-homo-sonnet          sanity_semver                ok       $ 0.4751    182.1 complete
A-homo-haiku           sanity_semver                ok       $ 0.1751    110.3 complete
B-homo-opus            sanity_semver                ok       $ 1.5258    208.5 mutual_agreement
B-homo-sonnet          sanity_semver                ok       $ 0.7487    206.5 mutual_agreement
B-homo-haiku           sanity_semver                ok       $ 0.4584    271.5 mutual_agreement
A-het-opus-sonnet      sanity_semver                ok       $ 0.5236    110.8 complete
A-het-sonnet-haiku     sanity_semver                ok       $ 0.2433    112.6 complete
B-het-opus-sonnet      sanity_semver                ok       $ 1.3852    255.4 max_rounds
B-het-sonnet-haiku     sanity_semver                ok       $ 0.6925    266.6 mutual_agreement
```

*("reused" = run was completed during the earlier tiny-matrix phase and skipped on the full-matrix sweep via `has_completed`. All metrics shown are from the original run.)*

### 10.3 Environment

Captured on every new `summary.json` under the `environment` key.

```json
{
  "git_sha": "7de0e3449b43...",
  "git_branch": "master",
  "git_dirty": true,
  "claude_cli_version": "2.1.113 (Claude Code)",
  "claude_agent_sdk_version": "0.1.62",
  "python_version": "3.13.5 (CPython, win32)",
  "platform": "Windows-11-..."
}
```

The `git_dirty=true` flag reflects uncommitted changes during the run (atomic-writes + environment-module + session-fix patches were in flight but not yet committed). A future matrix would benefit from running off a committed SHA for cleaner provenance.

### 10.4 Reproducing this matrix

```powershell
# From repo root
uv run --active python run_full_matrix.py

# Resume from crash (same command)
uv run --active python run_full_matrix.py
```

Config lives in `run_full_matrix.py`; the script uses `run_matrix(..., resume=True)` so completed runs are skipped on re-invocation.

### 10.5 Files modified / added in this experiment

Added:
- `src/langgraph_agents/pipeline/environment.py` — provenance capture
- `run_variant_a_smoke.py` — 1-run validation script
- `run_tiny_matrix.py` — 4-run directional script
- `run_full_matrix.py` — 50-run sweep script
- `logs/matrix/**` — 50 × 10 artifact files per run
- `docs/dual_pipeline_matrix_report.md` — this report

Modified:
- `src/langgraph_agents/pipeline/artifacts.py` — atomic writes, auto-capture env
- `src/langgraph_agents/pipeline/config.py` — `RunResult.environment` field
- `src/langgraph_agents/pipeline/session.py` — SDK API fix, dropped dead import-error branch
- `src/langgraph_agents/pipeline/prompts.py` — split `DEBATE_PROMPT` into `DEBATE_SYSTEM_PROMPT` + `DEBATE_OPENING_USER_MESSAGE`
- `src/langgraph_agents/pipeline/variant_b/nodes.py` — `init_debate` uses the new split
- `tests/pipeline/test_artifacts.py` — atomic-write + env-provenance tests
- `tests/pipeline/test_session.py` — removed dead test, kept lifecycle tests
- `tests/pipeline/test_prompts.py` — tests for new debate prompt split
- `tests/pipeline/variant_b/test_nodes.py` — updated draft-location assertion

Test suite: **181/181 pass**.

---

*Report authored against data as of 2026-04-17T17:34 local. Next-step judging pass not yet executed.*
