# Phase 0.3 — 2E Re-run Power Analysis

**Date**: 2026-04-29
**Status**: Complete
**Verdict**: **DROP Phase 3.3** — required N is ~10× the $30 budget at the observed effect size.

---

## Question

What N is required to reject H0 (no preference) at the 2E-observed effect
(~0.58 vs 0.42 anonymization-on vs anonymization-off)?

## Calculation

Two-sided binomial test, α=0.05, power=0.80, H0: p=0.50:

```
n = ((z_{α/2}·√(p₀·q₀) + z_β·√(p₁·q₁)) / (p₁ − p₀))²
  = ((1.96·√0.25 + 0.84·√(0.58·0.42)) / 0.08)²
  ≈ 304 judgments
```

Sensitivity around the observed effect:

| H1 effect | N required |
|---|---:|
| 0.55 | 782 |
| **0.58 (observed)** | **304** |
| 0.60 | 194 |
| 0.65 | 85 |
| 0.70 | 47 |

## Feasibility against the $30 budget

At the existing eval cost of ~$0.30 per judgment (judge-prompt + position-
bias correction), 304 judgments costs **~$91** — **3× the plan's $30 ceiling**.

Per-task judgment yield from a single matrix run is 4 (2 judges × 2 orders).
Even with the Phase 1.1 expanded 9-task corpus that's only 36 judgments per
seed — **~9 seeds (≈$80)** to reach 304. No combination of corpus expansion
and seed multiplication brings the cost inside the budget at the observed
effect size.

The ~$30 budget would only suffice if the true effect is ≥0.65 — but that is
larger than 2E actually measured, so we cannot assume it.

## Decision per plan §3.3

> Required N too costly: **drop Phase 3.3.** Anonymization stays at the
> current default; weak signal is acknowledged but not chased.

**Phase 3.3 is dropped.** The anonymization knob retains its current
default; its weak 2E signal is documented as known-and-not-resolved and
will not be re-litigated unless the budget posture changes or a sharper
prior on effect size emerges (e.g. a meta-analytic argument that 0.65+
is the right H1).
