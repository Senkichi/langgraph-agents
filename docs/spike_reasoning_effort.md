# Spike: `reasoning_effort` SDK feasibility (Experiment 003 Phase 0.2)

**Date**: 2026-04-29
**Status**: Complete
**Verdict**: **AVAILABLE** — both pipeline transports expose the knob.
**Decision**: Green-light Phase 3.2 (`reasoning_effort` matrix sweep).

---

## Question

Does the path the pipeline uses (Claude Code CLI for Variant A's `single_query`,
`claude-agent-sdk` for Variant B's `AgentSession`) expose a knob that controls
extended-thinking depth on Opus 4.7?

## Findings

### CLI (Variant A path) — claude 2.1.123

`claude --help` lists:

```
--effort <level>    Effort level for the current session
                    (low, medium, high, xhigh, max)
```

Five-level discrete control. Same flag for `claude --print` (the non-interactive
mode `single_query` shells out to). No additional API or auth requirement.

### SDK (Variant B path) — claude-agent-sdk 0.1.62

`ClaudeAgentOptions` (the dataclass passed to `ClaudeSDKClient`) exposes three
relevant fields:

- `effort` — same five-level knob as the CLI flag.
- `thinking` — boolean / config to enable extended thinking explicitly.
- `max_thinking_tokens` — cap on the thinking-block token budget.

These were enumerated by `dataclasses.fields(ClaudeAgentOptions)` against the
installed SDK; no source-tree dive required.

## Threading cost (if Phase 3.2 proceeds)

Both transports already centralise their option construction in one place per
variant — adding a single field is mechanically small.

| Surface | File | Change |
|---|---|---|
| Variant A CLI builder | `src/langgraph_agents/pipeline/session.py` `_build_cli_args` | Append `["--effort", effort]` when set |
| Variant B SDK options | `src/langgraph_agents/pipeline/session.py` `AgentSession.start` | Pass `effort=...` into `ClaudeAgentOptions(...)` |
| Config plumbing | `src/langgraph_agents/pipeline/config.py` `RunConfig` (or its model-config nested struct) | New optional `effort: Literal["low","medium","high","xhigh","max"] \| None = None` field |
| Provenance | `summary.json` `environment` block | Echo the resolved effort level so post-hoc reports can stratify by it |

Estimated: ~30 LOC plus tests. Within the §6.2 "1–2 sessions" budget the §9
recommendation cited.

## Decision per plan §3.2

> Available: green-light Phase 3.2 as scoped.

Phase 3.2 is **green-lit** to proceed once Phase 0.1 (judge bias) and the
Phase 1 corpus expansion are complete. Sweep design (low / medium / high
× Variant B 4.7 7-rnd × the expanded 9-task corpus) stands as written.

## Open follow-ups (not gating)

- Confirm at runtime that the CLI and SDK accept the same effort-level string
  (no silent value remap). A single smoke call per transport before Phase 3.2's
  matrix is sufficient.
- Confirm the `effort` value flows into `total_cost_usd` accounting on the
  CLI envelope (subscription mode may report differently from API mode). A
  one-task smoke at each level before the sweep gives us a per-level cost
  baseline.
