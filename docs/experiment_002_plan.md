# Experiment Plan: Follow-Up Experiments

**Date**: 2026-04-18
**Status**: Planned
**Prerequisite**: Experiment 001 baseline (see `docs/experiment_001_baseline_eval.md`)

---

## Context

Experiment 001 established that Variant B's debate loop produces a 15-point win-rate advantage over Variant A on complex tasks (57.3% vs 42.7%), with B-homo-opus achieving 93.5% win rate. Under Claude Code flat-rate pricing, API cost per run is irrelevant — only quality and wall time matter.

Several promising dimensions were not explored in the baseline. This document defines follow-up experiments ordered by expected signal-to-noise ratio. Each experiment is designed to be run independently; shared infrastructure changes (if any) are called out.

**Evaluation methodology is unchanged** unless noted: same 3 complex tasks, same 2-judge (Opus + Sonnet) pairwise preference judging with position-bias correction, same eval pipeline (`run_eval.py`).

---

## Experiment 2A: Max Debate Rounds Sweep

### Hypothesis

17 of 25 Variant B baseline runs hit the 3-round cap (`max_rounds`). The debaters may have had productive disagreement remaining. Increasing the round limit may improve quality — or it may just add cost with diminishing returns.

### Design

Sweep `max_debate_rounds` across {1, 3, 5, 7} using B-homo-opus (the strongest baseline config) on the 3 complex tasks.

### Configurations

```python
CONFIGS = [
    Configuration("B-opus-1rnd",  "B", models_all("opus"), overrides={
        "max_total_cost_usd": 10.0,
        "max_wall_clock_seconds": 3600,
        "max_debate_rounds": 1,
        "random_seed": 42,
    }),
    Configuration("B-opus-3rnd",  "B", models_all("opus"), overrides={
        "max_total_cost_usd": 10.0,
        "max_wall_clock_seconds": 3600,
        "max_debate_rounds": 3,
        "random_seed": 42,
    }),
    Configuration("B-opus-5rnd",  "B", models_all("opus"), overrides={
        "max_total_cost_usd": 10.0,
        "max_wall_clock_seconds": 3600,
        "max_debate_rounds": 5,
        "random_seed": 42,
    }),
    Configuration("B-opus-7rnd",  "B", models_all("opus"), overrides={
        "max_total_cost_usd": 10.0,
        "max_wall_clock_seconds": 3600,
        "max_debate_rounds": 7,
        "random_seed": 42,
    }),
]
```

Budget is raised to $10 / 3600s to ensure the round limit (not budget) is the binding constraint. The 3-round config acts as a within-experiment control that should reproduce the baseline result.

### Implementation

**No code changes required.** Copy `run_full_matrix.py` to `run_exp_2a_rounds.py`, replace the `CONFIGS` list with the above, and filter `TASKS` to the 3 complex task IDs:

```python
TASKS = [t for t in load_corpus(DEFAULT_CORPUS_DIR)
         if t.id in {"architectural_review_auth", "design_testing_strategy", "migration_postgres_dynamo"}]
```

Set `OUTPUT_DIR = Path("logs/matrix_2a_rounds")`.

**Eval**: Copy `run_eval.py` to `run_eval_2a.py`, point `MATRIX_DIR` at `logs/matrix_2a_rounds`, and `EVAL_DIR` at `logs/eval_2a`.

### What to Measure

- Win rate by round count (4-way pairwise comparison)
- Termination reason distribution (do 5-round and 7-round runs reach agreement, or still exhaust the cap?)
- Wall time scaling (does debate time grow linearly with rounds?)
- Transcript analysis: stance flip count and compaction count by round limit
- Whether the 3-round control reproduces baseline B-homo-opus results (sanity check)

### Expected Runs

4 configs × 3 tasks = 12 matrix runs, C(4,2) × 3 × 2 = 36 judgments.

---

## Experiment 2B: Cross-Generation Heterogeneous (Opus 4.6 × 4.7)

### Hypothesis

Baseline heterogeneous configs paired different model families (Opus vs Sonnet, Sonnet vs Haiku). These differ in capability, not just perspective. Pairing two models of equivalent capability but different training (Opus 4.6 vs Opus 4.7) may produce the diversity benefit without the capability gap that drags down weaker-model pairings.

### Design

Compare three Variant B configs on the 3 complex tasks:

| Config | Left Side | Right Side | Synthesizer |
|--------|-----------|------------|-------------|
| B-homo-opus46 | Opus 4.6 | Opus 4.6 | Opus 4.6 |
| B-homo-opus47 | Opus 4.7 | Opus 4.7 | Opus 4.7 |
| B-het-opus46-opus47 | Opus 4.6 | Opus 4.7 | Opus 4.7 |

### Configurations

```python
from langgraph_agents.pipeline.config import ModelConfig

CONFIGS = [
    Configuration("B-homo-opus46", "B", models_all("opus"), overrides={
        "max_total_cost_usd": 10.0,
        "max_wall_clock_seconds": 3600,
        "max_debate_rounds": 3,
        "random_seed": 42,
    }),
    Configuration("B-homo-opus47", "B", ModelConfig(
        generator_left="claude-opus-4-7",
        generator_right="claude-opus-4-7",
        critic_left="claude-opus-4-7",
        critic_right="claude-opus-4-7",
        reviser_left="claude-opus-4-7",
        reviser_right="claude-opus-4-7",
        synthesizer="claude-opus-4-7",
        debater_left="claude-opus-4-7",
        debater_right="claude-opus-4-7",
    ), overrides={
        "max_total_cost_usd": 10.0,
        "max_wall_clock_seconds": 3600,
        "max_debate_rounds": 3,
        "random_seed": 42,
    }),
    Configuration("B-het-opus46-opus47", "B", ModelConfig(
        generator_left="opus",
        generator_right="claude-opus-4-7",
        critic_left="opus",
        critic_right="claude-opus-4-7",
        reviser_left="opus",
        reviser_right="claude-opus-4-7",
        synthesizer="claude-opus-4-7",
        debater_left="opus",
        debater_right="claude-opus-4-7",
    ), overrides={
        "max_total_cost_usd": 10.0,
        "max_wall_clock_seconds": 3600,
        "max_debate_rounds": 3,
        "random_seed": 42,
    }),
]
```

**Important model alias note**: The baseline used short aliases (`opus`, `sonnet`, `haiku`) resolved by the Claude Code CLI. Verify that `claude-opus-4-7` resolves correctly before running the matrix. If the CLI only accepts short aliases, check `claude --help` or test with `claude --print --model claude-opus-4-7 - <<< "hello"`. The short alias `opus` currently maps to Opus 4.6 in this installation — confirm this hasn't changed.

### Implementation

**No code changes required** if model strings pass through to the CLI correctly. The `ModelConfig` dataclass accepts arbitrary strings and passes them via `--model` to the CLI.

Create `run_exp_2b_crossgen.py` following the same pattern as 2A. Output to `logs/matrix_2b_crossgen`, eval to `logs/eval_2b`.

### What to Measure

- Win rate: B-het-opus46-opus47 vs both homogeneous configs
- Cross-run similarity: do the cross-generation outputs diverge more than same-generation?
- Debate dynamics: do cross-generation debaters disagree more productively (more stance flips, later convergence)?
- Whether the synthesizer model matters (Opus 4.7 synthesizer might be strictly better regardless of debate pairing)

### Expected Runs

3 configs × 3 tasks = 9 matrix runs, C(3,2) × 3 × 2 = 18 judgments.

---

## Experiment 2C: Reasoning Effort Levels

### Hypothesis

Extended thinking / higher reasoning effort may matter most for specific roles (critic, debater, synthesizer) where deep analysis is required, rather than generators where breadth matters more. Asymmetric effort assignment (high effort on critique/debate, low on generation) might hit a better quality/speed tradeoff.

### Design

This experiment requires **infrastructure changes** to pass reasoning effort through to the CLI. Two sub-experiments:

**2C-i: Uniform effort sweep** — compare low/medium/high effort across all roles using B-homo-opus.

**2C-ii: Asymmetric effort** — high effort for critics + debaters + synthesizer, low/default for generators.

### Infrastructure Changes Required

The Claude Code CLI supports `--reasoning-effort` (or equivalent flag — verify via `claude --help`). Changes needed:

1. **`RunConfig`**: Add optional field `reasoning_effort: str | None = None` (values: `"low"`, `"medium"`, `"high"`, or `None` for default).

   ```python
   # In src/langgraph_agents/pipeline/config.py
   @dataclass(frozen=True)
   class RunConfig:
       ...
       reasoning_effort: str | None = None
   ```

2. **`ModelConfig`**: For asymmetric effort, effort needs to be per-role, not per-run. Extend `ModelConfig` with an optional effort map:

   ```python
   @dataclass(frozen=True)
   class ModelConfig:
       ...
       effort_overrides: dict[str, str] | None = None
       # Keys: "generator_left", "critic_left", "debater_left", "synthesizer", etc.
       # Values: "low", "medium", "high"
   ```

3. **`session.py` → `_build_cli_args()`**: Thread `reasoning_effort` through to CLI args:

   ```python
   def _build_cli_args(
       *,
       ...
       reasoning_effort: str | None = None,
   ) -> list[str]:
       ...
       if reasoning_effort:
           cmd.extend(["--reasoning-effort", reasoning_effort])
       ...
   ```

4. **`session.py` → `single_query()`**: Accept and forward `reasoning_effort` parameter.

5. **`session.py` → `AgentSession.__init__()`**: Accept and store `reasoning_effort`, pass to `ClaudeAgentOptions` on connect.

6. **Node functions** (both `variant_a/nodes.py` and `variant_b/nodes.py`): Look up the current node's role in `config.models.effort_overrides` and pass the effort level to `single_query()` or `AgentSession`.

   The mapping from node name to role key:
   - `generate_left` → `"generator_left"`
   - `generate_right` → `"generator_right"`
   - `cross_review_left` → `"critic_left"`
   - `cross_review_right` → `"critic_right"`
   - `revise_left` → `"reviser_left"`
   - `revise_right` → `"reviser_right"`
   - `synthesize` / `synthesize_with_debate` → `"synthesizer"`
   - `init_debate` (left session) → `"debater_left"`
   - `init_debate` (right session) → `"debater_right"`
   - `debate_turn` → looked up from `current_speaker` ��� `"debater_left"` or `"debater_right"`

### Configurations (2C-i: Uniform Effort)

```python
CONFIGS = [
    Configuration("B-opus-effort-low", "B", models_all("opus"), overrides={
        "max_total_cost_usd": 10.0,
        "max_wall_clock_seconds": 3600,
        "max_debate_rounds": 3,
        "random_seed": 42,
        "reasoning_effort": "low",
    }),
    Configuration("B-opus-effort-med", "B", models_all("opus"), overrides={
        "max_total_cost_usd": 10.0,
        "max_wall_clock_seconds": 3600,
        "max_debate_rounds": 3,
        "random_seed": 42,
        "reasoning_effort": "medium",
    }),
    Configuration("B-opus-effort-high", "B", models_all("opus"), overrides={
        "max_total_cost_usd": 10.0,
        "max_wall_clock_seconds": 3600,
        "max_debate_rounds": 3,
        "random_seed": 42,
        "reasoning_effort": "high",
    }),
]
```

### Configurations (2C-ii: Asymmetric Effort)

```python
CONFIGS = [
    # Control: all high
    Configuration("B-opus-all-high", "B", ModelConfig(
        generator_left="opus", generator_right="opus",
        critic_left="opus", critic_right="opus",
        reviser_left="opus", reviser_right="opus",
        synthesizer="opus",
        debater_left="opus", debater_right="opus",
        effort_overrides={
            "generator_left": "high", "generator_right": "high",
            "critic_left": "high", "critic_right": "high",
            "reviser_left": "high", "reviser_right": "high",
            "synthesizer": "high",
            "debater_left": "high", "debater_right": "high",
        },
    ), overrides={
        "max_total_cost_usd": 10.0,
        "max_wall_clock_seconds": 3600,
        "max_debate_rounds": 3,
        "random_seed": 42,
    }),
    # Experimental: low generators, high everything else
    Configuration("B-opus-gen-low-rest-high", "B", ModelConfig(
        generator_left="opus", generator_right="opus",
        critic_left="opus", critic_right="opus",
        reviser_left="opus", reviser_right="opus",
        synthesizer="opus",
        debater_left="opus", debater_right="opus",
        effort_overrides={
            "generator_left": "low", "generator_right": "low",
            "critic_left": "high", "critic_right": "high",
            "reviser_left": "high", "reviser_right": "high",
            "synthesizer": "high",
            "debater_left": "high", "debater_right": "high",
        },
    ), overrides={
        "max_total_cost_usd": 10.0,
        "max_wall_clock_seconds": 3600,
        "max_debate_rounds": 3,
        "random_seed": 42,
    }),
    # Experimental: high only on synthesizer and debaters
    Configuration("B-opus-synth-debate-high", "B", ModelConfig(
        generator_left="opus", generator_right="opus",
        critic_left="opus", critic_right="opus",
        reviser_left="opus", reviser_right="opus",
        synthesizer="opus",
        debater_left="opus", debater_right="opus",
        effort_overrides={
            "synthesizer": "high",
            "debater_left": "high", "debater_right": "high",
        },
    ), overrides={
        "max_total_cost_usd": 10.0,
        "max_wall_clock_seconds": 3600,
        "max_debate_rounds": 3,
        "random_seed": 42,
    }),
]
```

### What to Measure

- Win rate across effort levels (does high effort produce better debate?)
- Wall time impact (high effort may significantly increase per-turn latency)
- Whether asymmetric effort matches uniform-high quality at reduced wall time
- Debate dynamics: do high-effort debaters produce more stance flips or converge faster?

### Expected Runs

2C-i: 3 configs × 3 tasks = 9 runs, 18 judgments.
2C-ii: 3 configs × 3 tasks = 9 runs, 18 judgments.

---

## Experiment 2D: Prompt Structure Variations

### Hypothesis

The current debate prompt encourages general position statements. Forcing debaters to identify their **strongest remaining objection** each turn might produce more focused, productive disagreement and faster convergence.

### Design

Compare 3 debate prompt variants using B-homo-opus on the 3 complex tasks. This requires modifying the debate system prompt and parsing, but no architectural changes.

### Prompt Variants

**Variant D1 — Baseline (current)**:
Current `DEBATE_SYSTEM_PROMPT` with free-form argumentation and STANCE/KEY_POINT footer.

**Variant D2 — Objection-Focused**:
Replace the debate system prompt with a variant that structures each turn as:

```
STRONGEST_OBJECTION: <the single most important point you disagree with>
RESPONSE_TO_THEIR_OBJECTION: <your rebuttal to their strongest objection>
CONCESSION: <one specific point you now accept from the other side>
STANCE: <AGREE | DISAGREE>
KEY_POINT: <one-sentence crux>
```

**Variant D3 — Convergence-Oriented**:
Add explicit convergence pressure in later rounds:

```
## Round-specific instructions
- Round 1: State your position freely.
- Round 2: You MUST concede at least one specific point from the other side.
- Round 3+: You MUST either (a) concede and signal AGREE, or (b) name your
  single remaining disagreement with a concrete example that would resolve it.
```

### Implementation

1. **Add prompt variants to `prompts.py`**: Define `DEBATE_SYSTEM_PROMPT_V2` and `DEBATE_SYSTEM_PROMPT_V3` alongside the existing prompt.

2. **Add parsing for new footers**: Extend `variant_b/parsing.py` with `parse_objection(text)` and `parse_concession(text)` for Variant D2. These are additive — existing parsing continues to work.

3. **Thread prompt selection through config**: Add optional field to `RunConfig`:

   ```python
   @dataclass(frozen=True)
   class RunConfig:
       ...
       debate_prompt_variant: str = "default"  # "default", "objection", "convergence"
   ```

4. **Update `variant_b/nodes.py`**: In `init_debate`, select system prompt based on `config.debate_prompt_variant`.

5. **Update transcript metrics**: For D2, track concession count and objection specificity as additional metrics.

### Configurations

```python
CONFIGS = [
    Configuration("B-opus-prompt-default", "B", models_all("opus"), overrides={
        "max_total_cost_usd": 10.0,
        "max_wall_clock_seconds": 3600,
        "max_debate_rounds": 5,  # Use 5 rounds to see convergence effects
        "random_seed": 42,
        "debate_prompt_variant": "default",
    }),
    Configuration("B-opus-prompt-objection", "B", models_all("opus"), overrides={
        "max_total_cost_usd": 10.0,
        "max_wall_clock_seconds": 3600,
        "max_debate_rounds": 5,
        "random_seed": 42,
        "debate_prompt_variant": "objection",
    }),
    Configuration("B-opus-prompt-convergence", "B", models_all("opus"), overrides={
        "max_total_cost_usd": 10.0,
        "max_wall_clock_seconds": 3600,
        "max_debate_rounds": 5,
        "random_seed": 42,
        "debate_prompt_variant": "convergence",
    }),
]
```

Note: uses 5 rounds (not 3) to give convergence-oriented prompts room to demonstrate their effect.

### What to Measure

- Win rate across prompt variants
- Convergence rate: what fraction reach mutual_agreement before max_rounds?
- Debate quality: are objection-focused debates more specific? (Could measure by key_point token diversity across turns)
- Whether forced concessions lead to better or worse synthesis quality

### Expected Runs

3 configs × 3 tasks = 9 runs, 18 judgments.

---

## Experiment 2E: Anonymization Toggle

### Hypothesis

The baseline runs with `anonymize_in_debate=True` (proposals labeled "Proposal A/B" instead of "Your draft / Their draft"). This mitigates identity bias in debate but might also reduce the debaters' sense of ownership over their positions. Turning it off might produce more vigorous defense of positions.

### Design

Simple A/B test: B-homo-opus with anonymization on vs off, 3 complex tasks.

### Configurations

```python
CONFIGS = [
    Configuration("B-opus-anon-on", "B", models_all("opus"), overrides={
        "max_total_cost_usd": 10.0,
        "max_wall_clock_seconds": 3600,
        "max_debate_rounds": 3,
        "random_seed": 42,
        "anonymize_in_debate": True,
    }),
    Configuration("B-opus-anon-off", "B", models_all("opus"), overrides={
        "max_total_cost_usd": 10.0,
        "max_wall_clock_seconds": 3600,
        "max_debate_rounds": 3,
        "random_seed": 42,
        "anonymize_in_debate": False,
    }),
]
```

### Implementation

**No code changes required.** The `anonymize_in_debate` field already exists on `RunConfig` (default: `True`) and is threaded through `init_debate` in `variant_b/nodes.py` via `anonymize_pair()`.

### What to Measure

- Win rate: anon-on vs anon-off
- Debate dynamics: does non-anonymized debate produce more stance flips?
- Termination: does one variant converge faster?

### Expected Runs

2 configs × 3 tasks = 6 runs, 6 judgments. This is the cheapest experiment to run.

---

## Experiment Priority and Dependencies

| Priority | Experiment | Code Changes | Runs | Judgments | Dependencies |
|----------|-----------|-------------|------|-----------|-------------|
| 1 | **2A: Max Rounds Sweep** | None | 12 | 36 | None |
| 2 | **2E: Anonymization Toggle** | None | 6 | 6 | None |
| 3 | **2B: Cross-Gen Heterogeneous** | None (verify model aliases) | 9 | 18 | None |
| 4 | **2D: Prompt Structure** | Moderate (new prompts, parsing, config field) | 9 | 18 | None |
| 5 | **2C: Reasoning Effort** | Moderate (thread effort through session/config/nodes) | 18 | 36 | CLI flag verification |

**Recommended execution order**: 2A and 2E first (zero code changes, high signal). 2B next (verify model alias, then run). 2D and 2C require infrastructure work and should be planned as implementation phases.

### Running an Experiment

For any experiment requiring no code changes (2A, 2B, 2E):

1. Create `run_exp_<id>.py` by copying `run_full_matrix.py`
2. Replace `CONFIGS` list with the experiment's configurations
3. Filter `TASKS` to complex tasks only
4. Set `OUTPUT_DIR = Path("logs/matrix_<id>")`
5. Run: `uv run --active python run_exp_<id>.py`
6. Create `run_eval_<id>.py` by copying `run_eval.py`
7. Set `MATRIX_DIR = Path("logs/matrix_<id>")` and `EVAL_DIR = Path("logs/eval_<id>")`
8. Run: `uv run --active python run_eval_<id>.py`
9. Read `logs/eval_<id>/report.md` for results

### Cross-Experiment Comparison

After running experiments, compare winning configs across experiments using a **tournament bracket**: take the best config from each experiment and run a final pairwise eval. This requires a custom eval script that loads summaries from multiple matrix directories.

---

## Open Questions for Future Experiments

These are beyond the scope of the immediate follow-ups but worth tracking:

1. **Task corpus expansion**: 3 complex tasks is enough to see trends but not enough for statistical confidence. Adding 5-10 more complex tasks (different domains: performance tuning, API design review, incident postmortem, threat modeling) would strengthen all findings.

2. **Multi-run variance**: Running each config-task pair 3 times with different seeds would let us compute confidence intervals on win rates.

3. **Cross-model judging**: Using GPT-4 or Gemini as an additional judge would test for Claude self-preference bias in the eval framework.

4. **Variant C exploration**: Could there be a better pipeline architecture entirely? E.g., a "tournament" variant where 4 generators compete in elimination rounds, or a "committee" variant with majority voting.

5. **Synthesis prompt optimization**: The synthesizer instruction to "treat bilateral agreement as a weak signal" was a design choice, not an empirical finding. Testing synthesizers with vs without this instruction would validate the design.

6. **Task-conditional routing**: If debate helps complex tasks but not simple ones, a router that predicts task complexity and selects the variant accordingly could get the best of both worlds without wasting compute.
