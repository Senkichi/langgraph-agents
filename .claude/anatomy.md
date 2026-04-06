# Project Anatomy

## .

- `.gitignore` — Python-generated files (~45 tok)
- `.python-version` — 3.13 (~1 tok)
- `=8.0` — (no description) (~1 tok)
- `plan.md` — --- (~4564 tok)
- `pyproject.toml` — [build-system] (~158 tok)
- `readme.md` — (no description) (~1 tok)
- `run_companies_audit.py` — One-shot runner: invoke plan-build-review on the Companies audit & fix plan. (~1104 tok)
- `run_dataforseo_source.py` — One-shot runner: invoke plan-build-review for DataForSEO source. (~1035 tok)
- `run_jd_quality.py` — One-shot runner: invoke plan-build-review on the JD quality remediation plan. (~893 tok)
- `run_rss_pipeline.py` — One-shot runner: invoke plan-build-review on the RSS enrichment pipeline plan. (~516 tok)
- `run_sync_opt_phase1.py` — Phase 1: Gmail message-level dedup + parse failure dedup. (~1851 tok)
- `run_sync_opt_phase2.py` — Phase 2: Pre-ingestion batch dedup + runs table pruning. (~1768 tok)
- `run_sync_opt_phase3.py` — Phase 3: DataForSEO early submit + overlapped poll. (~1831 tok)
- `run_test_audit_a.py` — Chunk A: Fix All Broken, Wrong, and Weak Tests. (~4756 tok)
- `run_test_audit_b.py` — Chunk B: Delete Duplicates & Structural Cleanup. (~2173 tok)
- `run_test_audit_c.py` — Chunk C: Add Missing Coverage. (~2354 tok)
- `run_thordata_source.py` — One-shot runner: invoke plan-build-review for Thordata source + scheduler change. (~1043 tok)
- `run_todo_implementation.py` — Orchestrates all 16 TODO-IMPLEMENTATION-PLAN chunks through plan_build_review. (~5132 tok)
- `run_todo_state.json` — { (~11 tok)
- `run_token_opt.py` — Token optimization hooks — sequential execution of plans 01 → 02 → 03. (~826 tok)
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

## docs/superpowers/plans/

- `2026-04-05-langgraph-improvements.md` — > **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents av... (~15869 tok)

## src/langgraph_agents/

- `__init__.py` — (no description) (~1 tok)
- `claude_cli.py` — Wrapper around the `claude` CLI for running prompts via Claude Code subscription. (~1995 tok)
- `config.py` — Central configuration for model selection and execution parameters. (~507 tok)
- `evaluate_resumes.py` — Evaluate resume-engine output by comparing generated vs submitted versions. (~2583 tok)
- `graph_runner.py` — Streaming and synchronous runners for LangGraph workflows. (~1353 tok)
- `llm.py` — import os (~254 tok)
- `models.py` — from typing import Literal (~396 tok)
- `node_contract.py` — Node contract enforcement: pre/post-condition validation for graph nodes. (~2059 tok)
- `state.py` — from typing_extensions import TypedDict (~846 tok)
- `tracer.py` — Graph execution tracer: structured JSONL logging for observability. (~3762 tok)

## src/langgraph_agents/graphs/

- `__init__.py` — (no description) (~1 tok)
- `build_review.py` — Build-review loop subgraph. (~799 tok)
- `orchestrator.py` — from langgraph.graph import END, START, StateGraph (~268 tok)
- `plan_build_review.py` — Parent graph: composes plan-review, build-review, and e2e-test. (~1428 tok)
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
- `plan_reviewer.py` — from langgraph_agents.claude_cli import invoke_structured (~606 tok)
- `planner.py` — from langgraph_agents.claude_cli import invoke (~424 tok)
- `prompt_engineer.py` — Prompt engineer node: edits agent prompts, knowledge files, and workflow (~1133 tok)
- `prompt_review_synthesizer.py` — Prompt review synthesizer: merges behavioral and architectural review verdicts. (~594 tok)
- `researcher.py` — from langchain_core.messages import SystemMessage (~161 tok)
- `review_synthesizer.py` — Review synthesizer: merges micro and macro review verdicts. (~1362 tok)
- `writer.py` — from langchain_core.messages import SystemMessage (~163 tok)

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
- `test_plan_review.py` — from langgraph.graph import END (~582 tok)
- `test_prompt_build_review.py` — from langgraph.graph import END (~1076 tok)
- `test_prompt_workflow.py` — from langgraph_agents.graphs.prompt_workflow import build_prompt_workflow_graph (~312 tok)
- `test_tracer.py` — Tests for the tracer module: GraphTracer, traced_route, context vars. (~2714 tok)

