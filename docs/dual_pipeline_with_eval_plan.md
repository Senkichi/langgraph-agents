# Implementation Plan: Dual-Agent Pipeline with A/B Variants and Evaluation Matrix

## Context

Build two pipeline variants for running tasks through independent-perspective LLM review, plus an evaluation framework that compares them across a matrix of model configurations. The goal is empirical grounding: the research literature on multi-agent debate is mixed, and our own experience of "peak performance" in debate includes patterns that the research flags as potential sycophantic artifacts. Build both variants, measure them, decide based on data.

- **Variant A (conservative):** four-phase pipeline — generate, cross-review, revise, synthesize. No debate loop. Research support: strong. This is the reflection-pattern cross-critique setup.
- **Variant B (experimental):** same four phases plus a debate loop between the revised drafts and before synthesis. Research support: mixed, with documented failure modes. Mitigations for the failure modes baked in.
- **Evaluation framework:** runs a task corpus through a matrix of configurations (variant × model pairing) and produces pairwise preference judgments plus structured quality scores.

The two variants share 70%+ of their implementation. The plan builds the shared infrastructure first, then each variant, then the eval harness. Ship order favors getting something running end-to-end quickly so you can start collecting data.

## Non-goals

- Running on remote Anthropic API. Local Claude Code execution only.
- >2 agents per pipeline. The dynamics change at 3+ and both the research and our design assume two.
- Automated mitigation strategies that change the pipeline dynamically (adaptive debate depth, sycophancy detection that triggers re-runs, etc.). Keep the pipeline deterministic given config; let the eval framework compare static variants.
- Full benchmark replication (MMLU, GSM8K, etc.). Eval tasks are plan-review-shaped, matching the actual use case.

---

## Part 1: Shared infrastructure (used by both variants)

### Step 1.1: Agent SDK session wrappers

**Purpose.** Persistent SDK client wrapper with startup, turn-sending, and cleanup. Used by Variant B's debate phase and optionally by Variant A if we want session reuse across its four phases.

**Scope.**
- New module: `pipeline/session.py`

**Implementation.**

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

class AgentSession:
    """Persistent SDK client, held open across turns."""

    def __init__(self, name: str, system_prompt: str, cwd: str, model: str,
                 allowed_tools: list[str] = None):
        self.name = name
        self.system_prompt = system_prompt
        self.cwd = cwd
        self.model = model
        self.allowed_tools = allowed_tools if allowed_tools is not None else []
        self._client = None
        self._session_id = None
        self._total_cost_usd = 0.0
        self._turn_count = 0

    async def start(self, first_message: str) -> tuple[str, float]:
        """Open client, send first message. Returns (response, cost_delta)."""
        options = ClaudeAgentOptions(
            system_prompt=self.system_prompt,
            cwd=self.cwd,
            model=self.model,
            allowed_tools=self.allowed_tools,
            permission_mode="default",
        )
        self._client = ClaudeSDKClient(options=options)
        await self._client.connect()
        return await self._send(first_message)

    async def send(self, message: str) -> tuple[str, float]:
        """Send a turn. Returns (response, cost_delta)."""
        if self._client is None:
            raise RuntimeError(f"Session {self.name} not started")
        return await self._send(message)

    async def close(self):
        if self._client is not None:
            await self._client.disconnect()
            self._client = None

    @property
    def total_cost_usd(self) -> float:
        return self._total_cost_usd

    @property
    def session_id(self) -> str | None:
        return self._session_id

    async def _send(self, message: str) -> tuple[str, float]:
        parts = []
        cost_before = self._total_cost_usd
        async for msg in self._client.query(message):
            if hasattr(msg, "result") and getattr(msg, "subtype", None) == "success":
                parts.append(msg.result)
            if hasattr(msg, "session_id") and msg.session_id:
                self._session_id = msg.session_id
            if hasattr(msg, "usage"):
                self._total_cost_usd += _extract_cost(msg.usage)
        self._turn_count += 1
        return "\n".join(parts), self._total_cost_usd - cost_before
```

Also provide a one-shot helper for phases that don't need persistence:

```python
async def single_query(system_prompt: str, user_message: str, cwd: str,
                      model: str, allowed_tools: list[str] = None) -> tuple[str, float]:
    """One-shot query. Opens, sends, closes."""
    session = AgentSession("transient", system_prompt, cwd, model, allowed_tools)
    response, cost = await session.start(user_message)
    await session.close()
    return response, cost
```

**Verification.** Unit test: start session, send 3 messages, close. Response lengths non-zero, cost accumulates, session_id populated. Unit test: `single_query` round-trip works and releases resources.

**Risk.** Low-medium. SDK integration specifics may surprise us; validate empirically before relying on.

---

### Step 1.2: Shared state types and config

**Purpose.** TypedDicts for the state each pipeline variant uses, plus a config object that captures the model choices for a run.

**Scope.**
- New module: `pipeline/state.py`
- New module: `pipeline/config.py`

**Implementation.**

```python
# config.py
from dataclasses import dataclass
from typing import Literal

@dataclass
class ModelConfig:
    """Which model each role uses. Roles may collide or differ."""
    generator_left: str       # e.g. "claude-opus-4-7"
    generator_right: str
    critic_left: str          # who critiques left's draft (usually = generator_right's persona)
    critic_right: str
    reviser_left: str
    reviser_right: str
    debater_left: str | None = None      # only used by Variant B
    debater_right: str | None = None
    synthesizer: str = "claude-opus-4-7"  # judge / tiebreak role

@dataclass
class RunConfig:
    variant: Literal["A", "B"]
    models: ModelConfig
    chatroom_dir: str
    task: str
    max_cost_usd: float = 20.0
    max_wall_clock_seconds: int = 1800
    # Variant-B-specific
    max_debate_rounds: int = 3
    soft_compact_threshold_tokens: int = 20_000
    anonymize_in_debate: bool = True   # recommended by research; keep on by default

@dataclass
class RunResult:
    variant: Literal["A", "B"]
    config: RunConfig
    final_plan: str
    total_cost_usd: float
    wall_clock_seconds: float
    termination_reason: str
    run_id: str                    # unique, used for eval lookups
    artifacts_dir: str             # where drafts, transcript, summary live
```

```python
# state.py
class SharedState(TypedDict):
    """Fields common to both variants."""
    task: str
    chatroom_dir: str
    run_id: str

    # Phase 1 outputs
    left_draft_v1: str
    right_draft_v1: str
    left_critique_of_right: str
    right_critique_of_left: str
    left_draft_v2: str
    right_draft_v2: str

    # Cost / time tracking (reduced across nodes)
    total_cost_usd: Annotated[float, add]
    max_total_cost_usd: float
    run_start_time: str

    # Final output
    final_plan: str
    termination_reason: str


class VariantAState(SharedState):
    """No additional fields — A goes straight from revise to synthesize."""
    pass


class VariantBState(SharedState):
    """Debate phase fields."""
    # Session registry keys — actual sessions held in out-of-band registry keyed by run_id
    debate_sessions_initialized: bool

    transcript: Annotated[list[dict], add]
    transcript_token_estimate: int
    current_speaker: Literal["left", "right"]
    turn_count: int
    round_count: int
    left_signaled_agreement: bool
    right_signaled_agreement: bool
    compaction_count: int
    anonymize_in_debate: bool
```

**Verification.** Type checking passes. Sample `RunConfig` objects serialize to JSON for logging.

**Risk.** Trivial.

---

### Step 1.3: Anonymization helpers

**Purpose.** The research (Choi et al. 2025 on identity bias) shows that removing "you said" vs "they said" framing from debate prompts eliminates most identity-driven bias. Variant B needs this. Build it as a shared helper so Variant A can use it for the cross-review phase too (an easy improvement Variant A gets for free).

**Scope.**
- New module: `pipeline/anonymize.py`

**Implementation.**

```python
# anonymize.py

def anonymize_pair(my_draft: str, their_draft: str,
                   shuffle: bool = True) -> tuple[str, str, dict]:
    """
    Present two drafts as 'Proposal A' and 'Proposal B' in random order.

    Returns (proposal_a_text, proposal_b_text, mapping) where mapping is
    {'A': 'my'|'their', 'B': 'my'|'their'} so the caller can de-anonymize after.
    """
    if shuffle and random.random() < 0.5:
        return their_draft, my_draft, {"A": "their", "B": "my"}
    return my_draft, their_draft, {"A": "my", "B": "their"}


def anonymize_for_debate(transcript: list[dict], speaker: str) -> str:
    """
    Render the transcript with anonymized speaker attribution.
    'left' and 'right' become 'Reviewer 1' and 'Reviewer 2' (or 'Proposal A/B').
    """
    ...
```

**Verification.** Unit test: given two distinguishable drafts, `anonymize_pair` returns them in one of two orderings with correct mapping.

**Risk.** Trivial.

---

### Step 1.4: Prompts module

**Purpose.** Single source of truth for all system prompts. Research-informed.

**Scope.**
- New module: `pipeline/prompts.py`

**Implementation.**

Every prompt is constructed from a role-independent base plus role-specific asymmetry. Per the research on homogeneity, symmetric "both are just reviewers" configurations produce worse debate dynamics than asymmetric ones. Build two personas:

```python
GENERATOR_BASE = """
You are producing a draft response to a user's task. Be concrete, specific,
and claim-dense. Prefer explicit recommendations over balanced surveys.
"""

# Asymmetric critic personas — research suggests this helps.
CRITIC_CHALLENGER = """
You are a challenger reviewer. Your job is to find what's wrong, weak, or
underspecified in a draft. Name specific claims and challenge them.
Do not rewrite. Use the structured format:

CRITICAL: <issues that would block approval>
MAJOR: <issues that materially weaken the draft>
MINOR: <suggestions that would improve the draft>

Err on the side of finding problems. A draft with zero critical issues is
suspicious — look harder.
"""

CRITIC_BUILDER = """
You are a builder reviewer. Your job is to find what's right and where the
draft could be strengthened or extended. Name specific claims you think are
strongest and specific places the draft could go further. Use the format:

CRITICAL: <missing elements that would materially weaken the draft if unaddressed>
MAJOR: <places where the draft would be improved by concrete additions>
MINOR: <light touches>

Err on the side of finding opportunities. A draft you find nothing to strengthen
in is suspicious.
"""
```

The asymmetry matters — research shows symmetric cooperative debaters collapse into agreement more readily. One challenger + one builder maintains adversarial tension without the "both agents are told to be antagonistic" anti-pattern that just produces both agents being equally harsh.

**Variant B debate prompt** (used by both debaters, parameterized by their proposal):

```python
DEBATE_PROMPT = """
You are {role} in a structured debate about the best response to a task. Two
independent drafts have been produced and critiqued. Your job is to engage in
dialogue to converge on the best combined answer — or fail to converge with
clear reasons.

{proposals_section}
# ^ this block is either identity-anonymized ("Proposal A", "Proposal B") or
#   identity-revealed depending on RunConfig.anonymize_in_debate

## Rules
- Concrete > general. Name specific claims, not general directions.
- Concede specific points when the other side's argument is stronger on that
  point. Concession is a signal of engagement, not defeat.
- Do NOT produce a final merged plan yourself. Your job is the dialogue;
  synthesis runs separately.
- Keep each message under 400 words.

## Required response format
Every message must end with exactly two lines:

STANCE: <AGREE | DISAGREE | AGREE_WITH_MODIFICATION>
KEY_POINT: <one-sentence crux of your current position>

## Anti-patterns to avoid
- Do not agree just because the other reviewer is confident or verbose.
- Do not flip your position without a specific reason you can name.
- If you find yourself reaching for harmony over substance, stop and restate
  your actual disagreement.
"""
```

The "anti-patterns to avoid" section is an explicit attempt to counteract the sycophancy / confidence-mimicry failure modes the research flags. It may not work — research says such prompts have modest effect — but it's cheap.

**Synthesis prompt** (Variant A and B both use this, with variant-specific context):

```python
SYNTHESIS_JUDGE_PROMPT = """
Two AI reviewers have produced and cross-critiqued drafts of a response to a task.
{debate_section_or_empty}
Your job is to produce the final response.

## Your task
Produce the final response. You may:
- Select one draft wholesale if it is clearly stronger.
- Merge sections from each.
- Preserve unresolved disagreements if the drafts diverge materially; name them
  explicitly at the top of the response so the reader knows this is unresolved.

## Evaluation criteria (in order)
1. Concreteness — prefer specific claims over general ones.
2. Correctness — flag or exclude claims that appear unsupported.
3. Completeness — the final response should cover the task scope.
4. Internal consistency — no contradictions within the final response.

Do not preserve a claim just because both drafts contained it. Do not exclude a
claim just because only one draft contained it.
"""
```

**Verification.** Prompts are plain strings. Verification comes from the integration tests further down.

**Risk.** Trivial for the code. The prompt wording itself will need tuning once we see outputs — flag this.

---

### Step 1.5: Cost / time guards and artifact writing

**Purpose.** Stop runs that exceed the cost ceiling or wall-clock timeout. Write run artifacts to disk for later inspection and eval.

**Scope.**
- New module: `pipeline/budget.py`
- New module: `pipeline/artifacts.py`

**Implementation.**

Budget guard (same pattern used in the hardening plan):

```python
def over_budget(state: SharedState) -> tuple[bool, str]:
    cap = state.get("max_total_cost_usd", 0.0)
    if cap > 0 and state.get("total_cost_usd", 0.0) >= cap:
        return True, "cost"
    start = datetime.fromisoformat(state["run_start_time"]).timestamp()
    if time.time() - start > MAX_WALL_CLOCK_SECONDS:
        return True, "timeout"
    return False, ""
```

Artifacts layout per run:

```
<chatroom_dir>/<run_id>/
    config.json              # RunConfig serialized
    task.md                  # task text
    left_draft_v1.md
    right_draft_v1.md
    left_critique_of_right.md
    right_critique_of_left.md
    left_draft_v2.md
    right_draft_v2.md
    debate_transcript.md     # Variant B only
    final_plan.md
    summary.json             # RunResult serialized (cost, time, termination)
```

Every phase writes its outputs to disk as it completes. This is crucial for the eval framework — it reads artifacts from this layout, not from in-memory state.

**Verification.** Integration test: run a trivial pipeline, assert the expected files exist and parse cleanly.

**Risk.** Low.

---

## Part 2: Variant A — four-phase pipeline

### Step 2.1: Phase nodes

**Purpose.** Generate, cross-review, revise, synthesize. One node per phase per side (generate_left, generate_right, etc.), with `Send`-based fan-out for parallel phases.

**Scope.**
- New module: `pipeline/variant_a/nodes.py`
- New module: `pipeline/variant_a/graph.py`

**Implementation.**

Each node is a thin async function calling `single_query` with the appropriate prompt, writing artifacts, and returning a state update. Illustrated for one:

```python
async def generate_left(state: VariantAState, config: RunConfig) -> dict:
    prompt = f"## Task\n{state['task']}\n\nProduce your draft."
    response, cost = await single_query(
        system_prompt=GENERATOR_BASE,
        user_message=prompt,
        cwd=state["chatroom_dir"],
        model=config.models.generator_left,
    )
    write_artifact(state, "left_draft_v1.md", response)
    return {"left_draft_v1": response, "total_cost_usd": cost}
```

Cross-review uses asymmetric personas: `critic_left` uses `CRITIC_CHALLENGER` to critique right's draft, `critic_right` uses `CRITIC_BUILDER` to critique left's draft. (Assignment is a config knob; this is the default.)

Revise reads one's own draft plus the other's critique and produces v2. Synthesize is a single judge invocation reading both v2 drafts.

**Graph shape:**

```
START
  │
  ▼
  ┌────────────────┐
  │ fan_out_gen    │  Send(generate_left), Send(generate_right)
  └────────────────┘
  │                │
  ▼                ▼
generate_left  generate_right
  │                │
  └──── defer ─────┤  (synchronization barrier)
                   ▼
  ┌────────────────┐
  │ fan_out_review │  Send(cross_review_left), Send(cross_review_right)
  └────────────────┘
  │                │
  ▼                ▼
cross_review_l  cross_review_r
  │                │
  └──── defer ─────┤
                   ▼
  ┌────────────────┐
  │ fan_out_revise │  Send(revise_left), Send(revise_right)
  └────────────────┘
  │                │
  ▼                ▼
revise_left    revise_right
  │                │
  └──── defer ─────┤
                   ▼
              synthesize
                   │
                   ▼
                 END
```

Synchronization barriers via `defer=True` at the collecting nodes — the pattern used in the existing `plan_build_review` code.

**Verification.** Integration test: run a trivial task end-to-end. All six artifacts + final plan produced. Cost under $2 for trivial task. No leftover processes.

**Risk.** Low-medium. Standard LangGraph patterns applied to async.

---

### Step 2.2: Variant A entry point

```python
async def run_variant_a(config: RunConfig) -> RunResult:
    app = build_variant_a_graph().compile()
    initial_state = _initial_state_for(config)
    final = await app.ainvoke(initial_state, config={"configurable": {"thread_id": config.run_id}})
    return _result_from_state(final, config)
```

Simple. No persistent sessions means no registry, no cleanup complexity.

---

## Part 3: Variant B — four phases plus debate loop

Variant B inherits Variant A's phases 1-3 unchanged. It adds a debate phase between revise and synthesize, and runs synthesize over the debate transcript in addition to the v2 drafts.

### Step 3.1: Session registry

**Scope.** `pipeline/variant_b/registry.py`

```python
_DEBATE_SESSIONS: dict[str, dict[str, AgentSession]] = {}

def register(run_id: str, name: str, session: AgentSession):
    _DEBATE_SESSIONS.setdefault(run_id, {})[name] = session

def get(run_id: str, name: str) -> AgentSession | None:
    return _DEBATE_SESSIONS.get(run_id, {}).get(name)

async def close_all(run_id: str):
    sessions = _DEBATE_SESSIONS.pop(run_id, {})
    for s in sessions.values():
        try:
            await s.close()
        except Exception as e:
            logger.warning(f"Failed to close session: {e}")
```

Critical: `close_all` must be called in a finally block at the top level. Session leaks are real.

### Step 3.2: Initialize, debate_turn, compact, record_termination nodes

Follows the structure of the previous plan's Part 2, updated with research-informed mitigations:

**Initialization.** Both debaters start in parallel via `Send`. Each receives their own draft, the other's draft (anonymized if `config.anonymize_in_debate`), and the debate primer. They produce opening statements independently (neither sees the other's before producing their own).

**Debate turn.** Sequential alternation. On each turn, the speaker's session receives:
- The other speaker's most recent message (anonymized if configured)
- An instruction to respond and include the STANCE/KEY_POINT footer

**Compaction.** When `transcript_token_estimate > soft_compact_threshold`, both debaters are asked in parallel to self-summarize their position in ~300 words. Summary used as context preface for subsequent turns. Hard cap at 3 compactions.

**Record termination.** Pure-Python node that inspects state and sets `termination_reason`. Conditions (first match wins):
- `budget` — cost or wall-clock cap hit
- `mutual_agreement` — both signaled AGREE on their most recent turn
- `max_rounds` — `round_count >= config.max_debate_rounds` (default 3, up from my original 6 — research suggests shorter is better)
- `stable_disagreement` — last-two key_points similar for both speakers

### Step 3.3: Termination logic (research-updated)

```python
MAX_DEBATE_ROUNDS_DEFAULT = 3     # was 6; research says shorter

def _route_after_turn(state: VariantBState, config: RunConfig) -> str:
    hit, reason = over_budget(state)
    if hit:
        return "record_termination"

    # Note: bilateral agreement is a WEAK signal per research. Still use it as a
    # termination condition, but the synthesis judge will re-evaluate independently.
    if state["left_signaled_agreement"] and state["right_signaled_agreement"]:
        return "record_termination"

    if state["round_count"] >= config.max_debate_rounds:
        return "record_termination"

    if _stable_disagreement(state):
        return "record_termination"

    if _should_compact(state, config):
        return "compact"

    return "debate_turn"
```

### Step 3.4: Synthesis (same judge for both variants, slightly different inputs)

The synthesis judge for Variant B reads: task, both v2 drafts, full transcript (or compacted summaries if compacted), termination reason. Per research, we do *not* weight bilateral agreement heavily — the judge re-evaluates independently and can disagree with whatever convergence the debate reached.

```python
async def synthesize_with_debate(state: VariantBState, config: RunConfig) -> dict:
    debate_section = f"""
## Debate transcript
{_render_transcript(state['transcript'])}

## Termination reason
{state['termination_reason']}
    """
    response, cost = await single_query(
        system_prompt=SYNTHESIS_JUDGE_PROMPT.format(debate_section_or_empty=debate_section),
        user_message=_format_synthesis_task(state),
        cwd=state["chatroom_dir"],
        model=config.models.synthesizer,
    )
    return {"final_plan": response, "total_cost_usd": cost}
```

### Step 3.5: Variant B entry point with cleanup

```python
async def run_variant_b(config: RunConfig) -> RunResult:
    app = build_variant_b_graph().compile()
    initial_state = _initial_state_for(config, variant="B")
    try:
        final = await app.ainvoke(initial_state, config={"configurable": {"thread_id": config.run_id}})
        return _result_from_state(final, config)
    finally:
        await close_all(config.run_id)   # always clean up sessions
```

**Verification.** Integration test: run a trivial task through Variant B. All Variant A artifacts present plus `debate_transcript.md`. Debate terminates on one of the four conditions. Sessions closed after run (registry empty).

**Risk.** Medium. The async session lifecycle is the most intricate piece. Test aggressively.

---

## Part 4: Evaluation framework

This is where the research question gets answered. Two independent tracks: **pairwise preference judging** for qualitative comparison, and **structured metrics** for quantitative comparison.

### Step 4.1: Task corpus

**Purpose.** A set of real plan-review-shaped tasks to run the matrix against.

**Scope.**
- `eval/corpus/` directory with one `.md` file per task.

**Guidance.** 5-10 tasks of varying complexity. Each task should be something where:
- The answer is open-ended (no single correct response).
- There's room for substantive disagreement between reviewers.
- A human reader can judge which of two responses is better.

Examples suitable for this corpus:
- "Review this architectural proposal for [X] and produce a hardening plan."
- "Design a testing strategy for [Y system]."
- "Write a migration plan from [A] to [B] accounting for [constraints]."

Include 1-2 "sanity check" tasks where the right answer is obvious — if the pipeline fails these, something is fundamentally broken. Example: "Write a 3-sentence explanation of why prompt caching matters for agentic workflows." Short, bounded, one clear good answer.

**Format.** Each task file has:
```markdown
# Task: <name>
<task description>

## Expected response shape (for eval reference only, not shown to pipeline)
- Length: short | medium | long
- Key concepts that should appear: [...]
- Common failure modes: [...]
```

The "expected response shape" is used by the structured-metrics evaluator (Step 4.3), not by the pipeline itself.

**Verification.** 5 tasks written and reviewed by a human before running any eval.

---

### Step 4.2: Matrix runner

**Purpose.** Run every configuration in the matrix against every task, save artifacts.

**Scope.**
- New module: `eval/matrix.py`

**Implementation.**

The matrix to start with:

```python
CONFIGURATIONS = [
    # Homogeneous — both sides same model
    ("A-homo-opus47",    "A", models_all("claude-opus-4-7")),
    ("A-homo-opus46",    "A", models_all("claude-opus-4-6")),
    ("A-homo-sonnet",    "A", models_all("claude-sonnet-4-6")),
    ("B-homo-opus47",    "B", models_all("claude-opus-4-7")),
    ("B-homo-opus46",    "B", models_all("claude-opus-4-6")),
    ("B-homo-sonnet",    "B", models_all("claude-sonnet-4-6")),

    # Heterogeneous — left-right differ, tests diversity hypothesis
    ("A-het-opus47-sonnet",   "A", models_split("claude-opus-4-7", "claude-sonnet-4-6")),
    ("A-het-opus47-opus46",   "A", models_split("claude-opus-4-7", "claude-opus-4-6")),
    ("B-het-opus47-sonnet",   "B", models_split("claude-opus-4-7", "claude-sonnet-4-6")),
    ("B-het-opus47-opus46",   "B", models_split("claude-opus-4-7", "claude-opus-4-6")),
]
```

10 configurations × N tasks = 10N runs. At ~$1-3 per run depending on variant and task, 10 tasks × 10 configs = ~$150-300 for a full sweep. Tractable.

Runner:

```python
async def run_matrix(tasks: list[Task], configurations: list[Config],
                    output_dir: str, parallel: int = 2) -> MatrixResults:
    """Run every config against every task. Writes to output_dir/<config_id>/<task_id>/."""
    semaphore = asyncio.Semaphore(parallel)   # limit concurrent Claude Code invocations

    async def one_run(task, config):
        async with semaphore:
            run_id = f"{config.id}__{task.id}"
            return await (run_variant_a if config.variant == "A" else run_variant_b)(
                config.with_task(task, run_id=run_id)
            )

    results = await asyncio.gather(*[
        one_run(task, config) for task in tasks for config in configurations
    ], return_exceptions=True)
    return _collate(results)
```

The `parallel` knob matters. Claude Code local execution is CPU-bound on your machine; running 10 configs × 10 tasks in parallel will make your laptop unhappy. Start with 2-3.

**Verification.** Dry run with 1 trivial task and 2 configurations. Assert both runs complete, produce artifacts in the expected directory structure, and total cost is recorded.

**Risk.** Medium. Long runs; plan for resume-on-crash (don't re-run configs that already have complete artifacts).

---

### Step 4.3: Pairwise preference judging

**Purpose.** For each task, produce pairwise comparisons between configurations. The research is unambiguous that LLM judges have biases (position, verbosity, identity) — mitigate by running judgments in both orders and using multiple judges.

**Scope.**
- New module: `eval/judge_pairwise.py`

**Implementation.**

```python
@dataclass
class PairwisePreference:
    task_id: str
    config_a: str
    config_b: str
    judge_model: str
    preferred: Literal["A", "B", "tie"]
    reasoning: str
    # For bias measurement: same comparison in opposite order
    flipped_preferred: Literal["A", "B", "tie"] | None = None
    position_bias_detected: bool = False       # flipped != preferred
```

For each pair of configurations (on the same task):

1. Present both outputs to the judge, labeled "Response X" and "Response Y", in a random order.
2. Judge produces: which is better, brief reasoning, and a confidence level.
3. **Also run the comparison with the order flipped.** If the judge flips its preference when the order flips, that's position bias — flag the comparison as unreliable.
4. Run the same comparison with **at least two different judge models** to cross-check. Disagreement between judges is a flag on the comparison.

Judge prompt:

```python
JUDGE_PAIRWISE_PROMPT = """
You are comparing two AI-generated responses to a task. Your job is to pick the
better one, or declare a tie.

## Task
{task}

## Response X
{response_x}

## Response Y
{response_y}

## Criteria (in order of priority)
1. Concreteness — specific claims over general ones.
2. Correctness — no obvious errors or unsupported claims.
3. Completeness — covers the task scope.
4. Internal consistency — no contradictions.

## Your response format
PREFERENCE: <X | Y | TIE>
CONFIDENCE: <high | medium | low>
REASONING: <2-3 sentences explaining your judgment>

Do not consider which response is longer unless the longer one contains
meaningfully more substance. Verbosity without substance is a weakness.
"""
```

For human judging (the gold standard): build a simple CLI tool that presents anonymized response pairs one at a time with the task, asks for a preference, saves the judgment. No time for a UI; stdin/stdout is fine. Track inter-rater agreement between human and LLM judges.

**Judge models to use.**
- Opus 4.7 (likely the strongest current judge)
- Sonnet (cheaper; cross-check)
- Human (you) — at minimum on a 20% sample for validation

**Number of pairs.** 10 configs pairwise = 45 unique pairs per task. 10 tasks × 45 pairs = 450 pairs. Each pair judged twice (flipped order) × 2 LLM judges = 1800 LLM judgments. At ~$0.05/judgment, $90. Add human judgments on 20% = 90 human judgments. Plan for that time cost.

This is the most expensive part of the eval by far. Consider: do you need pairwise across all 10 configs, or is a round-robin tournament (each config faces N random others) sufficient? Round-robin with N=5 cuts the work in half with modest statistical cost.

**Verification.** Unit test: judge prompt produces parseable output. Integration test: judge 1 real pair in both orders and confirm the position-bias detection triggers correctly on a rigged input.

**Risk.** Medium. Judge quality bounds the eval quality. If LLM judges are too noisy, fall back to more human judgments.

---

### Step 4.4: Structured metrics

**Purpose.** Quantitative metrics that don't require judging. Complementary signal to preference judgments.

**Scope.**
- New module: `eval/metrics.py`

**Metrics to compute per run:**

- **Cost.** Already tracked.
- **Wall-clock time.** Already tracked.
- **Termination reason distribution.** For Variant B: what fraction of runs hit mutual_agreement vs max_rounds vs stable_disagreement? A high mutual_agreement rate might be convergence, or might be sycophancy — cross-reference with preference judgments.
- **Response length.** Token count of final plan. Variance tells you whether configs converge on similar lengths.
- **Concept coverage.** For tasks with annotated expected concepts (in the task file), compute the fraction that appear in the final response. Simple keyword match; not perfect but cheap and interpretable.
- **Cross-configuration consistency.** For the same task, how similar are the final plans across configurations? Low similarity (high variance) means configuration choice matters; high similarity means the configurations are roughly fungible. Measure with BLEU or a simple token-overlap ratio.
- **Variant-B-specific:** debate round distribution, compaction rate, stance-flip count (how often did a debater change STANCE between turns).

All of these are deterministic and cheap to compute. Run them over the matrix automatically after runs complete.

**Verification.** Unit tests per metric on small synthetic inputs.

**Risk.** Low.

---

### Step 4.5: Results analysis and report

**Purpose.** Turn raw judgments and metrics into something you can read and make decisions from.

**Scope.**
- New module: `eval/report.py`

**What the report contains.**

1. **Win matrix.** 10×10 table of pairwise preference rates (config X preferred to config Y, averaged across tasks and judges, position-bias-filtered). Read the diagonals and clusters.
2. **Variant A vs Variant B, aggregated.** Across all model pairings, does B beat A? By how much? On which tasks?
3. **Homogeneous vs heterogeneous.** Does model diversity help? In which variants?
4. **Model-specific performance.** For each model, how does it perform as a debater vs as a single-agent generator?
5. **Termination pattern analysis.** For Variant B runs that won, what's the termination distribution? For runs that lost, what's the distribution? Pattern here tells you whether debate is actually helping or whether it's a cost to pay for parity.
6. **Cost-adjusted quality.** Preference-win-rate per dollar spent. If B beats A on quality but costs 3×, that's a different recommendation than B beats A at parity.
7. **Failure cases.** Tasks where the matrix shows wide divergence. These are the most informative cases to read by hand.

The report is a markdown file plus raw CSVs for anyone who wants to slice differently.

**Verification.** Run the report on mock data; check that the aggregations are correct.

**Risk.** Low once the data is in; high if the data collection is incomplete.

---

## Dependencies and build order

```
Part 1 (shared infrastructure)
  ↓
Part 2 (Variant A)  —  smoke test Variant A end-to-end before Part 3
  ↓
Part 3 (Variant B)  —  smoke test Variant B end-to-end before Part 4
  ↓
Part 4 (eval framework)
  4.1 (corpus) can be done in parallel with Parts 2-3
  4.2 (matrix runner) needs Parts 2-3 complete
  4.3 (judging) can be built against any run artifacts
  4.4 (metrics) can be built against any run artifacts
  4.5 (report) needs 4.3 and 4.4
```

**Recommended ship order:**

1. Part 1 (shared infrastructure) — foundation
2. Part 2 (Variant A) — earliest end-to-end output
3. Step 4.1 (task corpus) — write these while Variant A is in review
4. **Smoke test:** run Variant A on the corpus, inspect outputs by hand. If A's outputs are bad, Variant B won't help — stop and fix before proceeding.
5. Part 3 (Variant B) — adds debate
6. Step 4.2 (matrix runner) — full sweep infrastructure
7. Step 4.4 (metrics) — cheap to compute, run early
8. Step 4.3 (judging) — the expensive part
9. Step 4.5 (report) — aggregation

---

## Operational notes

**Local resource management.** Claude Code local execution runs subprocesses. Running 10 matrix configurations in parallel will pin your machine. Start with `parallel=2` in the matrix runner; tune up only if system load allows.

**Cost ceiling for the whole experiment.** Hard cap at $400 for a full matrix sweep. If the eval runs past that, something is wrong — most likely a runaway debate or a session leak. Set `max_cost_usd` per run low enough that even 100 runs at cap stays under the ceiling.

**Resume on crash.** The matrix runner should check for existing artifacts and skip completed runs. Each run's `summary.json` marks completion. Treat a missing `summary.json` as "needs to run."

**Judging costs dominate.** If the eval framework's cost is surprising, it's probably the judging (1800 LLM calls). Consider: round-robin tournament instead of full pairwise, or human-only judging on a smaller sample.

**What to do when the results come in.** Three likely outcomes:

1. **Variant A wins or ties Variant B across the board.** Ship A, don't build more. The research prediction matches.
2. **Variant B wins on some tasks and loses on others, with a predictable pattern (e.g., B wins on complex open-ended tasks, loses on sanity-check tasks).** Ship both as a per-task choice. Write a routing heuristic.
3. **Variant B wins broadly.** Revisit the research — either our implementation got something right that the literature missed, or we're measuring something other than what we think. Dig in before shipping.

---

## What's deliberately not in this plan

- **Sycophancy detection at runtime.** Flagged in research; no mature technique exists; not worth building without a clearer target.
- **Adaptive debate depth.** Dynamically extending debate when progress is made, cutting it when stuck. Tempting but adds complexity that obscures the A/B comparison we're trying to run. Hold for v2.
- **Cross-task learning.** Storing useful patterns from one run and using them in another. Different project.
- **UI for judging.** CLI is fine. If the eval framework sees enough use to justify a UI, that's a good problem.
- **Full MAST-taxonomy failure annotation.** Research-grade analysis. Interesting, large, out of scope.

---

## A note on expectations

The literature's prior is that the honest outcome is "Variant A roughly matches Variant B at the aggregate level, with Variant B winning on specific task types and losing on others, and with substantial cost overhead." If that's what the data shows, it's not a failed experiment — it's the answer. The goal of the evaluation framework is not to prove that Variant B is better; it's to know.

The thing to watch for as most interesting: cases where the heterogeneous Variant B configurations beat both the homogeneous Variant B and Variant A. That would be evidence for the research's "diversity matters" finding applied to our specific use case, and it would shape how you deploy this beyond the experiment.

Budget roughly 2-3 weeks of part-time work to build through Part 3, another 1-2 weeks for the eval framework, then the actual eval sweep is a day of compute plus a few hours of human judgment on your part.
