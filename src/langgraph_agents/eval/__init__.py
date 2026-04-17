"""Evaluation framework for the Variant A / Variant B pipelines.

Three independent layers:
  - matrix runner: executes every (configuration, task) pair, writes artifacts
  - pairwise judging: produces preference comparisons between configurations
  - metrics: deterministic post-hoc measurements per run

The report layer aggregates the other three into a decision-ready markdown
document plus raw CSVs for downstream slicing.
"""
