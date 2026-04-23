# Project Anatomy

## .

- `.gitignore` — Python-generated files (~55 tok)
- `.python-version` — 3.13 (~1 tok)
- `=8.0` — (no description) (~1 tok)
- `plan.md` — --- (~4564 tok)
- `pyproject.toml` — [build-system] (~158 tok)
- `readme.md` — (no description) (~1 tok)
- `run_companies_audit.py` — One-shot runner: invoke plan-build-review on the Companies audit & fix plan. (~1104 tok)
- `run_dataforseo_source.py` — One-shot runner: invoke plan-build-review for DataForSEO source. (~1035 tok)
- `run_eval.py` — Structured metrics + pairwise preference judging + report generation. (~3991 tok)
- `run_full_matrix.py` — Full 10-config × 5-task eval sweep. (~1614 tok)
- `run_jd_quality.py` — One-shot runner: invoke plan-build-review on the JD quality remediation plan. (~893 tok)
- `run_rss_pipeline.py` — One-shot runner: invoke plan-build-review on the RSS enrichment pipeline plan. (~516 tok)
- `run_sync_opt_phase1.py` — Phase 1: Gmail message-level dedup + parse failure dedup. (~1851 tok)
- `run_sync_opt_phase2.py` — Phase 2: Pre-ingestion batch dedup + runs table pruning. (~1768 tok)
- `run_sync_opt_phase3.py` — Phase 3: DataForSEO early submit + overlapped poll. (~1831 tok)
- `run_test_audit_a.py` — Chunk A: Fix All Broken, Wrong, and Weak Tests. (~4756 tok)
- `run_test_audit_b.py` — Chunk B: Delete Duplicates & Structural Cleanup. (~2173 tok)
- `run_test_audit_c.py` — Chunk C: Add Missing Coverage. (~2354 tok)
- `run_thordata_source.py` — One-shot runner: invoke plan-build-review for Thordata source + scheduler change. (~1043 tok)
- `run_tiny_matrix.py` — Tiny directional matrix: 2 configs (A vs B, same models) × 2 tasks = 4 runs. (~825 tok)
- `run_todo_implementation.py` — !/usr/bin/env python3 (~5141 tok)
- `run_todo_state.json` — { (~11 tok)
- `run_token_opt.py` — Token optimization hooks — sequential execution of plans 01 → 02 → 03. (~826 tok)
- `run_variant_a_smoke.py` — Smoke test: Variant A on the smallest sanity task with sonnet everywhere. (~663 tok)
- `uv.lock` — version = 1 (~69432 tok)

## .planning/

- `combined-plan.md` — > **Consolidated from:** (~16119 tok)
- `research-feedback-passing.md` — *Researched:** 2026-04-03 (~4987 tok)

## .planning/phases/token-optimization/

- `research.md` — *Researched:** 2026-04-04 (~1250 tok)
- `tok-01-plan.md` — --- (~5118 tok)
- `tok-01-summary.md` — *Status:** COMPLETE (~453 tok)
- `tok-02-plan.md` — --- (~3332 tok)
- `tok-03-plan.md` — --- (~2428 tok)
- `tok-03-summary.md` — *Edit 1A-extract** (Block 1, parsing stage): (~848 tok)

## .planning/phases/workflow-efficiency/

- `plan.md` — *Source:** Audit of all graph nodes, state schemas, run scripts, and orchestration (~9072 tok)

## .pytest_cache/

- `.gitignore` — Created by pytest automatically. (~9 tok)
- `cachedir.tag` — Signature: 8a477f597d28d172789f06886806bc55 (~50 tok)
- `readme.md` — This directory contains data from the pytest's cache plugin, (~75 tok)

## .pytest_cache/v/cache/

- `lastfailed` — {} (~1 tok)
- `nodeids` — [ (~1844 tok)

## docs/

- `dual_pipeline_matrix_report.md` — *Date:** 2026-04-17 (~7412 tok)
- `experiment_001_baseline_eval.md` — *Date**: 2026-04-18 (~5077 tok)
- `experiment_002_plan.md` — *Date**: 2026-04-18 (~5441 tok)

## docs/superpowers/plans/

- `2026-04-05-langgraph-improvements.md` — > **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents av... (~15869 tok)

## src/langgraph_agents/

- `__init__.py` — (no description) (~1 tok)
- `claude_cli.py` — Wrapper around the `claude` CLI for running prompts via Claude Code subscription. (~1995 tok)
- `config.py` — Central configuration for model selection and execution parameters. (~527 tok)
- `evaluate_resumes.py` — Evaluate resume-engine output by comparing generated vs submitted versions. (~2583 tok)
- `graph_runner.py` — Streaming and synchronous runners for LangGraph workflows. (~1353 tok)
- `llm.py` — import os (~254 tok)
- `models.py` — from typing import Literal (~601 tok)
- `node_contract.py` — Node contract enforcement: pre/post-condition validation for graph nodes. (~2059 tok)
- `state.py` — from typing_extensions import TypedDict (~969 tok)
- `tracer.py` — Graph execution tracer: structured JSONL logging for observability. (~3762 tok)

## src/langgraph_agents/eval/

- `__init__.py` — Evaluation framework for the Variant A / Variant B pipelines. (~123 tok)
- `corpus.py` — Task corpus loader. (~1664 tok)
- `judge_pairwise.py` — Pairwise preference judging with position-bias detection and multi-judge support. (~2279 tok)
- `matrix.py` — Matrix runner: execute every (configuration, task) pair. (~2162 tok)
- `metrics.py` — Deterministic per-run and cross-run metrics. (~2136 tok)
- `report.py` — Aggregate matrix runs + judgments + metrics into a decision-ready report. (~2971 tok)

## src/langgraph_agents/eval/corpus/

- `architectural_review_auth.md` — A team is proposing the following authentication scheme for a new B2B (~374 tok)
- `design_testing_strategy.md` — A Python service consumes supplier price updates from Kafka, applies a rules (~277 tok)
- `migration_postgres_dynamo.md` — A mid-sized SaaS app currently stores all data in a PostgreSQL cluster. The (~338 tok)
- `sanity_prompt_caching.md` — Write a 3-sentence explanation of why prompt caching matters for agentic (~153 tok)
- `sanity_semver.md` — Write a one-paragraph summary of semantic versioning suitable for a new (~122 tok)

## src/langgraph_agents/graphs/

- `__init__.py` — (no description) (~1 tok)
- `build_review.py` — Build-review loop subgraph. (~799 tok)
- `orchestrator.py` — from langgraph.graph import END, START, StateGraph (~268 tok)
- `plan_build_review.py` — Parent graph: composes plan-review, plan-chunking, build-review, and e2e-test. (~2371 tok)
- `plan_review.py` — Plan-review loop subgraph. (~629 tok)
- `prompt_build_review.py` — Prompt build-review loop subgraph. (~860 tok)
- `prompt_workflow.py` — Parent graph for prompt engineering workflows. (~1104 tok)

## src/langgraph_agents/nodes/

- `__init__.py` — (no description) (~1 tok)
- `architectural_reviewer.py` — Architectural reviewer: evaluates prompt changes for workflow integrity. (~1052 tok)
- `behavioral_reviewer.py` — Behavioral reviewer: evaluates prompt changes for instruction quality. (~1014 tok)
- `coder.py` — Coder node: invokes claude CLI as a full development agent. (~1326 tok)
- `discover_architecture.py` — Discovery node: scans a Claude Code agent workspace and builds a compressed (~678 tok)
- `e2e_tester.py` — End-to-end tester: validates that the built code achieves its intended purpose. (~2345 tok)
- `macro_reviewer.py` — Macro reviewer: focuses on architecture, design, extensibility, plan alignment. (~1049 tok)
- `micro_reviewer.py` — Micro reviewer: focuses on code quality, bugs, edge cases, correctness. (~866 tok)
- `plan_chunker.py` — Plan chunker node: decomposes an approved plan into ordered implementation steps. (~795 tok)
- `plan_reviewer.py` — from langgraph_agents.claude_cli import invoke_structured (~606 tok)
- `planner.py` — from langgraph_agents.claude_cli import invoke (~424 tok)
- `prompt_engineer.py` — Prompt engineer node: edits agent prompts, knowledge files, and workflow (~1133 tok)
- `prompt_review_synthesizer.py` — Prompt review synthesizer: merges behavioral and architectural review verdicts. (~594 tok)
- `researcher.py` — from langchain_core.messages import SystemMessage (~161 tok)
- `review_synthesizer.py` — Review synthesizer: merges micro and macro review verdicts. (~1362 tok)
- `writer.py` — from langchain_core.messages import SystemMessage (~163 tok)

## src/langgraph_agents/pipeline/

- `__init__.py` — Dual-pipeline scaffolding — Variant A (four-phase) and Variant B (plus debate). (~71 tok)
- `anonymize.py` — Identity-anonymisation helpers for cross-review and debate prompts. (~700 tok)
- `artifacts.py` — Run-artifact layout on disk. (~1245 tok)
- `budget.py` — Cost and wall-clock guard rails. (~466 tok)
- `config.py` — Run-time configuration objects for dual-pipeline runs. (~1194 tok)
- `environment.py` — Environment provenance capture for run summaries. (~1093 tok)
- `prompts.py` — Single source of truth for pipeline prompts. (~1692 tok)
- `session.py` — Pipeline session primitives. (~2823 tok)
- `state.py` — TypedDict state schemas for Variant A and Variant B pipelines. (~563 tok)

## src/langgraph_agents/pipeline/variant_a/

- `__init__.py` — Variant A — four-phase pipeline: generate, cross-review, revise, synthesize. (~125 tok)
- `graph.py` — Variant A graph builder and entry point. (~1864 tok)
- `nodes.py` — Variant A phase nodes. (~2296 tok)

## src/langgraph_agents/pipeline/variant_b/

- `__init__.py` — Variant B — four-phase pipeline plus debate loop between revise and synthesize. (~157 tok)
- `graph.py` — Variant B graph builder and entry point. (~2570 tok)
- `nodes.py` — Variant B debate-phase nodes and the debate-aware synthesis node. (~3883 tok)
- `parsing.py` — Debate-message parsing and the stable-disagreement heuristic. (~1166 tok)
- `registry.py` — Out-of-band registry for debate ``AgentSession`` instances. (~799 tok)

## src/langgraph_agents/tools/

- `__init__.py` — (no description) (~1 tok)
- `dev_tools.py` — Utilities for interacting with git in a workspace directory. (~542 tok)
- `search.py` — from langchain_core.tools import tool (~72 tok)

## tests/

- `__init__.py` — (no description) (~1 tok)
- `test_build_review.py` — from langgraph.graph import END (~2384 tok)
- `test_config.py` — Tests that config module reads env vars correctly. (~200 tok)
- `test_e2e_tester.py` — from unittest.mock import patch (~3559 tok)
- `test_graph_runner.py` — Tests for graph_runner: streaming and synchronous runners. (~493 tok)
- `test_models.py` — import pytest (~489 tok)
- `test_node_contract.py` — Tests for node_contract: validators, decorator, and format_verdict_feedback. (~3343 tok)
- `test_orchestrator.py` — from langgraph_agents.graphs.orchestrator import build_graph (~133 tok)
- `test_plan_build_review.py` — from unittest.mock import patch (~2218 tok)
- `test_plan_chunker.py` — Tests for plan chunker node and chunk-loop routing. (~3504 tok)
- `test_plan_review.py` — from langgraph.graph import END (~582 tok)
- `test_prompt_build_review.py` — from langgraph.graph import END (~1076 tok)
- `test_prompt_workflow.py` — from langgraph_agents.graphs.prompt_workflow import build_prompt_workflow_graph (~312 tok)
- `test_tracer.py` — Tests for the tracer module: GraphTracer, traced_route, context vars. (~2714 tok)

## tests/eval/

- `__init__.py` — (no description) (~1 tok)
- `test_corpus.py` — Tests for the corpus loader and the shipped default corpus. (~1021 tok)
- `test_judge_pairwise.py` — Tests for pairwise judging — parsing, position bias, multi-judge. (~1710 tok)
- `test_matrix.py` — Tests for the matrix runner — structure, dispatch, resume, error capture. (~1807 tok)
- `test_metrics.py` — Tests for eval.metrics — concept coverage, transcript metrics, similarity. (~1536 tok)
- `test_report.py` — Tests for eval.report — aggregations and output file shapes. (~1603 tok)

## tests/pipeline/

- `__init__.py` — (no description) (~1 tok)
- `test_anonymize.py` — Tests for anonymisation helpers — key property is reproducibility. (~806 tok)
- `test_artifacts.py` — Tests for pipeline.artifacts — on-disk layout contract. (~1869 tok)
- `test_budget.py` — Tests for pipeline.budget — cost and wall-clock guards. (~950 tok)
- `test_config.py` — Tests for pipeline.config dataclasses and helper constructors. (~1078 tok)
- `test_prompts.py` — Smoke tests on prompt templates — catch accidental deletions or formatting drift. (~779 tok)
- `test_session.py` — Tests for pipeline.session.single_query — mocks the subprocess CLI. (~1351 tok)
- `test_state.py` — Tests for pipeline.state TypedDict contracts. (~679 tok)

## tests/pipeline/variant_a/

- `__init__.py` — (no description) (~1 tok)
- `test_graph.py` — Integration tests for the Variant A graph. (~1459 tok)
- `test_nodes.py` — Unit tests for Variant A phase nodes. (~2290 tok)

## tests/pipeline/variant_b/

- `__init__.py` — (no description) (~1 tok)
- `test_graph.py` — End-to-end integration tests for Variant B. (~2132 tok)
- `test_nodes.py` — Unit tests for Variant B debate-phase nodes. (~3210 tok)
- `test_parsing.py` — Tests for STANCE/KEY_POINT parsing and the stable_disagreement heuristic. (~1283 tok)
- `test_registry.py` — Tests for the debate session registry. (~806 tok)

