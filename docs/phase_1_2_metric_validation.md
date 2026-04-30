# Phase 1.2 — `failure_mode_hit_rate` backfill validation
**Date**: 2026-04-29
**Question**: Does `failure_mode_hit_rate` correlate negatively with judged win-rate across historical eval data? If yes, promote from `decorative` to `judged-independent` in `METRIC_CLASSIFICATIONS`.

**Method**: For each (matrix, eval) pair, compute per-config mean of each metric across tasks, and per-config win rate from `judgments.jsonl` (ties + position-bias contribute 0.5). Pearson correlation between metric mean and win rate. Negative correlation means lower failure rate co-occurs with higher wins (the desired signal). For comparison, `concept_coverage_keyword` (known decorative per 002 Finding 2) and `final_plan_chars` (size) are included as null-hypothesis baselines.

## matrix_2a_rounds × eval_2a

| config | n_tasks | mean failure_mode_hit_rate | mean concept_coverage_keyword | mean final_plan_chars | win_rate |
|---|---|---|---|---|---|
| `B-opus46-1rnd` | 3 | 0.0000 | 0.8049 | 26553 | 0.1905 |
| `B-opus46-3rnd` | 3 | 0.0000 | 0.7936 | 25073 | 0.0952 |
| `B-opus46-5rnd` | 3 | 0.0000 | 0.7841 | 27961 | 0.2738 |
| `B-opus46-7rnd` | 3 | 0.0000 | 0.7121 | 29797 | 0.3214 |
| `B-opus47-1rnd` | 3 | 0.0000 | 0.6932 | 23735 | 0.7738 |
| `B-opus47-3rnd` | 3 | 0.0000 | 0.6307 | 21664 | 0.6667 |
| `B-opus47-5rnd` | 3 | 0.0000 | 0.7027 | 24225 | 0.7927 |
| `B-opus47-7rnd` | 3 | 0.0000 | 0.7330 | 26338 | 0.9024 |

**Pearson r vs win_rate**: failure_mode_hit_rate=**+0.000**, concept_coverage_keyword=-0.697, final_plan_chars=-0.469.

## matrix_2b_crossgen × eval_2b

| config | n_tasks | mean failure_mode_hit_rate | mean concept_coverage_keyword | mean final_plan_chars | win_rate |
|---|---|---|---|---|---|
| `B-het-opus46-opus47` | 3 | 0.0000 | 0.6932 | 22833 | 0.5833 |
| `B-homo-opus46` | 3 | 0.0000 | 0.7330 | 25451 | 0.0000 |
| `B-homo-opus47` | 3 | 0.0000 | 0.6288 | 19864 | 0.9167 |

**Pearson r vs win_rate**: failure_mode_hit_rate=**+0.000**, concept_coverage_keyword=-0.958, final_plan_chars=-0.982.

## Pooled across eval pairs

| dataset | n_configs | r(failure_mode_hit_rate, win) | r(concept_coverage_keyword, win) | r(final_plan_chars, win) |
|---|---|---|---|---|
| matrix_2a_rounds | 8 | +0.000 | -0.697 | -0.469 |
| matrix_2b_crossgen | 3 | +0.000 | -0.958 | -0.982 |
| **pooled** | **11** | **+0.000** | **-0.694** | **-0.544** |

## Verdict

**Keep `failure_mode_hit_rate` as decorative.** Pooled r=+0.000 does not clear the -0.30 promotion threshold. The metric's recall is too low for these rubrics -- failure-mode phrases are descriptive rather than detection-keyword shaped, so substring hits are sparse and the signal is swamped by noise. Future work: add per-task detection phrases in the corpus, or replace substring matching with a phrase-classifier or judge-prompted hit detection.

## Side finding -- `concept_coverage_keyword` is worse than decorative

Pooled r(concept_coverage_keyword, win)=-0.694 -- a strong NEGATIVE correlation. Experiment 002 Finding 2 said the metric "does not track quality". This backfill shows it actively anti-tracks: configs that hit MORE rubric keywords WIN LESS. Likely confounded by plan size (r(final_plan_chars, win)=-0.544) -- larger plans hit more keywords AND tend to lose to the more-focused entries that won the judgments. Recommendation: hide `concept_coverage_keyword` and `concept_coverage_token_jaccard` from report.md tables in future eval reports; keep them computed only because the cost is trivial and historical CSVs still surface them.
