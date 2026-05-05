# Project Anatomy

## .

- `.gitignore` — Python-generated files (~55 tok)
- `.python-version` — 3.13 (~1 tok)
- `debug-session-2026-04-06.md` — H1: Debug Session 2026-04-06 — run_todo_implementation.py; H2: What we were trying to do, Bugs fixed during this session, Operational issues, State of the codebase at end of session, Chunks completed (~996 tok)
- `plan.md` — H1: RSS Feed Enrichment Pipeline — Implementation Plan; H2: Objective, Execution Context, Task 1: Project Scaffold, Config Module, and Database Layer, Task 2: Classifier Module… (~4564 tok)
- `pyproject.toml` — Cross-family judge for experiment 003 Phase 0.1 (judge bias sanity check). (~237 tok)
- `readme.md` — (no description) (~1 tok)
- `run_companies_audit.py` — funcs: main (~1146 tok)
- `run_dataforseo_source.py` — funcs: main (~1078 tok)
- `run_eval.py` — funcs: _discover_configs, _variant_of, _load_all_summaries, run_metrics_pass, _print_aggregates, compute_cross_run_similarities, _judgment_key, _load_completed_judgments, _save_judgment… (~4121 tok)
- `run_eval_2a.py` — funcs: main (~904 tok)
- `run_eval_2b.py` — funcs: main (~723 tok)
- `run_eval_2e.py` — funcs: main (~720 tok)
- `run_eval_judge_sanity.py` — funcs: _read_response, _read_task, _claude_consensus, _judge_once, _collapse, _run_async, _dry_run, _parse_args, main; classes: Cell, CellResult (~3345 tok)
- `run_exp_2a_rounds.py` — funcs: _make_config, main (~1518 tok)
- `run_exp_2b_crossgen.py` — funcs: _het_model_config, main (~1399 tok)
- `run_exp_2e_anon.py` — funcs: main (~1116 tok)
- `run_full_matrix.py` — funcs: main (~1614 tok)
- `run_jd_quality.py` — funcs: main (~934 tok)
- `run_phase_1_2_backfill.py` — funcs: _pearson, _per_config_win_rate, _per_config_metric_means, main (~3006 tok)
- `run_rss_pipeline.py` — funcs: main (~558 tok)
- `run_smoke_phase_1_1.py` — funcs: main (~1227 tok)
- `run_sync_opt_phase1.py` — funcs: main (~1883 tok)
- `run_sync_opt_phase2.py` — funcs: main (~1810 tok)
- `run_sync_opt_phase3.py` — funcs: main (~1863 tok)
- `run_test_audit_a.py` — funcs: main (~4798 tok)
- `run_test_audit_b.py` — funcs: main (~2215 tok)
- `run_test_audit_c.py` — funcs: main (~2396 tok)
- `run_thordata_source.py` — funcs: main (~1085 tok)
- `run_tiny_matrix.py` — funcs: main (~825 tok)
- `run_todo_implementation.py` — funcs: parse_plan_chunks, validate_chunks, load_state, save_state, chunk_status, blocked_by, _now, run_chunk, print_chunk_header, print_summary, build_arg_parser, main (~5141 tok)
- `run_todo_state.json` — keys: chunks, run_started (~46 tok)
- `run_token_opt.py` — funcs: load_plan, run_plan, main (~865 tok)
- `run_variant_a_smoke.py` — funcs: main (~663 tok)
- `run_variant_b_smoke.py` — funcs: main (~975 tok)
- `uv.lock` — version = 1 (~92564 tok)

## .planning/

- `combined-plan.md` — H1: Combined LangGraph Workflow Improvements Plan; H2: Conflict Resolutions, Phase Dependency Graph, File Map, Phase 1: Correctness Fixes, Phase 2: Dead Code Removal (~16119 tok)
- `research-feedback-passing.md` — H1: Research: Feedback Passing in Multi-Agent LLM Plan→Build→Review→Revise Loops; H2: Summary, 1. Feedback Summarization, 2. Feedback Accumulation Patterns, 3. Structured Feedback Schemas… (~4987 tok)

## .planning/phases/token-optimization/

- `research.md` — H1: Research: Token Optimization for Claude Code Sessions; H2: Summary, Key Design Decisions from Field Survey, Architecture, References (~1250 tok)
- `tok-01-plan.md` — H1: Read Lifecycle Hooks — Implementation Plan; --- (~5118 tok)
- `tok-01-summary.md` — H1: tok-01 Summary — Read Lifecycle Hooks; H2: What was built, Lifecycle verified, Design decisions, Files modified (~453 tok)
- `tok-02-plan.md` — H1: File Anatomy Scanner — Implementation Plan; H2: Objective, Execution Context (~3332 tok)
- `tok-03-plan.md` — H1: CLv2 Observation Enrichment — Implementation Plan; H2: Objective, Execution Context (~2428 tok)
- `tok-03-summary.md` — H1: tok-03 Summary — CLv2 Observation Enrichment; H2: Changes Implemented, Design Notes, Files Modified, Verification Passed (~848 tok)

## .planning/phases/workflow-efficiency/

- `plan.md` — H1: Workflow Efficiency Implementation Plan; H2: Phase 1: Quick Wins (no state schema changes), Phase 2: Run Script Fixes (no graph changes), Phase 3: State Schema Extensions (~9072 tok)

## docs/

- `dual_pipeline_matrix_report.md` — H1: Dual-Pipeline Matrix Experiment — Report; H2: 1. Executive Summary, 2. What Was Built, 3. Matrix Composition, 4. Results, 5. Findings, 6. Notable Cases (~7412 tok)
- `dual_pipeline_with_eval_plan.md` — H1: Implementation Plan: Dual-Agent Pipeline with A/B Variants and Evaluation Matrix; H2: Context, Non-goals, Part 1: Shared infrastructure (used by both variants)… (~9652 tok)
- `experiment_001_baseline_eval.md` — H1: Experiment 001: Baseline Dual-Pipeline Evaluation; H2: Abstract, 1. Motivation, 2. Pipeline Architecture, 3. Experimental Design, 4. Results, 5. Key Findings (~5077 tok)
- `experiment_002_plan.md` — H1: Experiment Plan: Follow-Up Experiments; H2: Context, Experiment 2A: Max Debate Rounds Sweep, Experiment 2B: Cross-Generation Heterogeneous (Opus 4.6 × 4.7)… (~5441 tok)
- `experiment_002_results.md` — H1: Experiment 002: Follow-Up Sweeps — Rounds, Anonymization, Cross-Generation; H2: Abstract, 1. Motivation, 2. Pipeline and Methodology, 3. Experiment 2A — Max Debate Rounds × Model Generation… (~6526 tok)
- `experiment_003_phase_0_1_results.md` — H1: Experiment 003 Phase 0.1 — Judge Self-Preference Bias Sanity Check (Results); H2: TL;DR, Method, Results — cell by cell, Decision rule (per plan §3.1), Consequences, Cost actuals, Open follow-ups (~2021 tok)
- `experiment_003_phase_0_3_power.md` — H1: Phase 0.3 — 2E Re-run Power Analysis; H2: Question, Calculation, Feasibility against the $30 budget, Decision per plan §3.3 (~453 tok)
- `experiment_003_plan.md` — H1: Experiment 003 Plan: Stress-Tested Follow-Ups to Experiment 002; H2: 0. Why this plan does not just execute §9 of 002, 1. Stress-test of §9 recommendations, 2. Reordered phase plan… (~8078 tok)
- `phase_1_2_metric_validation.md` — H1: Phase 1.2 — `failure_mode_hit_rate` backfill validation; H2: matrix_2a_rounds × eval_2a, matrix_2b_crossgen × eval_2b, Pooled across eval pairs, Verdict… (~879 tok)
- `spike_reasoning_effort.md` — H1: Spike: `reasoning_effort` SDK feasibility (Experiment 003 Phase 0.2); H2: Question, Findings, Threading cost (if Phase 3.2 proceeds), Decision per plan §3.2, Open follow-ups (not gating) (~738 tok)

## docs/superpowers/plans/

- `2026-04-05-langgraph-improvements.md` — H1: LangGraph Workflow Improvements Implementation Plan; H2: File Map, Phase 1: Correctness Fixes, Phase 2: Remove Dead Code (M7), Phase 3: Centralize Model Configuration (M1) (~15869 tok)

## scripts/

- `probe_deepseek_response.py` — funcs: main (~551 tok)

## src/langgraph_agents/

- `__init__.py` — (no description) (~1 tok)
- `claude_cli.py` — funcs: invoke, invoke_structured, invoke_agent (~2040 tok)
- `config.py` — funcs: warn_if_alias (~1031 tok)
- `environment.py` — funcs: _git, _claude_cli_version, _sdk_version, capture (~1225 tok)
- `evaluate_resumes.py` — funcs: _read_file, _compute_diff, collect_pairs, build_analysis_prompt, validate_pairs, evaluate, evaluate_and_run (~2583 tok)
- `graph_runner.py` — funcs: run_graph, stream_graph, _print_summary (~1458 tok)
- `models.py` — classes: PlanVerdict, ChunkStep, ExecutionPlan, CodeVerdict (~601 tok)
- `node_contract.py` — funcs: non_empty, is_path, contains_verdict, is_verdict_value, is_non_negative_int, validate_node, parse_verdict, extract_verdict_block, format_verdict_feedback… (~2595 tok)
- `state.py` — classes: ParentState, PlanReviewState, BuildReviewState, PromptBuildState, PromptWorkflowState (~969 tok)
- `tracer.py` — funcs: get_tracer, set_tracer, get_current_node, set_current_node, _estimate_tokens, _field_sizes, _now_iso, traced_route; classes: TraceEvent, GraphStartEvent, GraphEndEvent, NodeStartEvent… (~3946 tok)

## src/langgraph_agents/eval/

- `__init__.py` — Evaluation framework for the Variant A / Variant B pipelines. (~123 tok)
- `corpus.py` — funcs: _split_on_expected, _extract_nested_bullets, parse_task, load_task, load_corpus; classes: Task (~1664 tok)
- `judge_backend.py` — funcs: classify_by_model, is_openai_compatible, query_openai_compatible; classes: OpenAICompatibleBackend (~1732 tok)
- `judge_pairwise.py` — funcs: parse_judgement, _render_prompt, judge_single, _collapse_votes, judge_pair_with_position_check, judge_multi; classes: JudgeVote, PairwiseOutcome (~2601 tok)
- `matrix.py` — funcs: _default_runner, run_matrix, default_configurations, load_matrix_summaries; classes: Configuration, MatrixResult (~2162 tok)
- `metrics.py` — funcs: _tokens, estimate_tokens, concept_coverage_keyword, concept_coverage_token_jaccard, failure_mode_hit_rate, stance_flip_count, _load_text, _load_transcript, run_metrics, cross_run_similarity (~2944 tok)
- `report.py` — funcs: compute_win_matrix, variant_aggregate, termination_distribution, cost_adjusted_win_rates, _config_id_from_row, _write_csv, _render_win_matrix_table, build_report, _outcome_to_row (~3159 tok)

## src/langgraph_agents/eval/corpus/

- `api_design_review.md` — H1: Task: Review and revise this proposed REST API contract; H2: Expected response shape (for eval reference only, not shown to pipeline) (~439 tok)
- `architectural_review_auth.md` — H1: Task: Review and harden this authentication design; H2: Expected response shape (for eval reference only, not shown to pipeline) (~374 tok)
- `caching_consistency.md` — H1: Task: Design a caching architecture for a high-skew workload; H2: Expected response shape (for eval reference only, not shown to pipeline) (~367 tok)
- `design_testing_strategy.md` — H1: Task: Design a testing strategy for a real-time pricing service; H2: Expected response shape (for eval reference only, not shown to pipeline) (~277 tok)
- `incident_postmortem.md` — H1: Task: Write an incident postmortem for this outage timeline; H2: Expected response shape (for eval reference only, not shown to pipeline) (~457 tok)
- `migration_postgres_dynamo.md` — H1: Task: Plan a migration from PostgreSQL to DynamoDB for a high-write workload; H2: Expected response shape (for eval reference only, not shown to pipeline) (~338 tok)
- `migration_with_downtime.md` — H1: Task: Design a zero-data-loss database migration plan; H2: Expected response shape (for eval reference only, not shown to pipeline) (~348 tok)
- `perf_tuning_hot_path.md` — H1: Task: Develop a performance tuning plan for a degraded JVM service; H2: Expected response shape (for eval reference only, not shown to pipeline) (~435 tok)
- `refactor_legacy_module.md` — H1: Task: Produce a refactoring roadmap for a legacy monolith module; H2: Expected response shape (for eval reference only, not shown to pipeline) (~405 tok)
- `sanity_prompt_caching.md` — H1: Task: Explain prompt caching in 3 sentences; H2: Expected response shape (for eval reference only, not shown to pipeline) (~153 tok)
- `sanity_semver.md` — H1: Task: Summarise semver in one paragraph; H2: Expected response shape (for eval reference only, not shown to pipeline) (~122 tok)

## src/langgraph_agents/graphs/

- `__init__.py` — (no description) (~1 tok)
- `build_review.py` — funcs: _fan_out_to_reviewers, _route_after_synthesis, build_build_review_graph, compile_build_review (~799 tok)
- `plan_build_review.py` — funcs: _call_build_review, _advance_chunk, _route_after_build_review, _route_after_e2e, _route_after_discovery, _route_entry, build_plan_build_review_graph, compile_plan_build_review (~2747 tok)
- `plan_review.py` — funcs: _route_entry, _route_after_review, build_plan_review_graph, compile_plan_review (~629 tok)
- `prompt_build_review.py` — funcs: _fan_out_to_reviewers, _route_after_synthesis, build_prompt_build_review_graph, compile_prompt_build_review (~860 tok)
- `prompt_workflow.py` — funcs: _call_plan_review, _call_prompt_build_review, build_prompt_workflow_graph, compile_prompt_workflow (~1104 tok)

## src/langgraph_agents/nodes/

- `__init__.py` — (no description) (~1 tok)
- `architectural_reviewer.py` — funcs: architectural_review (~1052 tok)
- `behavioral_reviewer.py` — funcs: behavioral_review (~1014 tok)
- `coder.py` — funcs: _build_coder_context, code (~1326 tok)
- `discover_architecture.py` — funcs: discover_architecture (~678 tok)
- `e2e_tester.py` — funcs: _extract_changed_files, _suggest_test_commands, _extract_proposed_fixes, _build_e2e_context, e2e_test (~2433 tok)
- `macro_reviewer.py` — funcs: _truncate_plan_for_reviewer, macro_review (~1137 tok)
- `micro_reviewer.py` — funcs: _truncate_plan_for_reviewer, micro_review (~954 tok)
- `plan_chunker.py` — funcs: _is_non_empty_list, chunk_plan (~795 tok)
- `plan_reviewer.py` — funcs: _format_verdict, review_plan (~606 tok)
- `planner.py` — funcs: plan (~424 tok)
- `prompt_engineer.py` — funcs: _build_context, prompt_engineer (~1133 tok)
- `prompt_review_synthesizer.py` — funcs: synthesize_prompt_reviews (~594 tok)
- `review_synthesizer.py` — funcs: _extract_critical_major_issues, _derive_rule, synthesize_reviews (~1376 tok)

## src/langgraph_agents/pipeline/

- `__init__.py` — Dual-pipeline scaffolding — Variant A (four-phase) and Variant B (plus debate). (~71 tok)
- `anonymize.py` — funcs: anonymize_pair, anonymize_for_debate (~700 tok)
- `artifacts.py` — funcs: run_dir, run_dir_from_state, _atomic_write_text, write_artifact, write_config, write_task, write_summary, has_completed, load_artifact, load_summary (~1245 tok)
- `budget.py` — funcs: over_budget, elapsed_seconds (~466 tok)
- `config.py` — funcs: models_all, models_split; classes: ModelConfig, RunConfig, RunResult (~1194 tok)
- `environment.py` — Backward-compatible re-export of the package-level environment module. (~160 tok)
- `prompts.py` — Single source of truth for pipeline prompts. (~1692 tok)
- `session.py` — funcs: _build_cli_args, _run_cli_sync, single_query; classes: AgentSession (~2823 tok)
- `state.py` — classes: SharedState, VariantAState, VariantBState (~563 tok)

## src/langgraph_agents/pipeline/variant_a/

- `__init__.py` — Variant A — four-phase pipeline: generate, cross-review, revise, synthesize. (~125 tok)
- `graph.py` — funcs: _bind, _route_post_phase, build_variant_a_graph, compile_variant_a, _initial_state, run_variant_a (~1864 tok)
- `nodes.py` — funcs: start_run, _generate, generate_left, generate_right, _cross_review, cross_review_left, cross_review_right, _revise, revise_left, revise_right, synthesize (~2296 tok)

## src/langgraph_agents/pipeline/variant_b/

- `__init__.py` — Variant B — four-phase pipeline plus debate loop between revise and synthesize. (~157 tok)
- `graph.py` — funcs: _bind, _route_to_pair, _route_to_single, _route_after_turn, build_variant_b_graph, compile_variant_b, _initial_state, run_variant_b (~2570 tok)
- `nodes.py` — funcs: _render_proposals, init_debate, _make_transcript_entry, debate_turn, compact, _determine_termination, record_termination, _render_transcript, synthesize_with_debate (~3883 tok)
- `parsing.py` — funcs: parse_stance, parse_key_point, _tokenise, jaccard, _last_n_by_speaker, stable_disagreement, estimate_tokens, transcript_token_estimate (~1166 tok)
- `registry.py` — funcs: register, get, get_or_raise, close_all, active_run_ids, _reset_for_tests (~799 tok)

## src/langgraph_agents/tools/

- `__init__.py` — (no description) (~1 tok)
- `dev_tools.py` — funcs: run_git_diff, truncate_diff (~542 tok)

## tests/

- `__init__.py` — (no description) (~1 tok)
- `test_build_review.py` — classes: TestBuildReviewGraph, TestRoutingLogic, TestSynthesizer, TestResolvedIssuesCap (~3242 tok)
- `test_claude_cli.py` — classes: TestInvokeStructured (~244 tok)
- `test_config.py` — funcs: test_default_values, test_pinned_ids_are_explicit, test_warn_if_alias_logs_for_alias, test_warn_if_alias_silent_for_explicit_id, test_env_override (~555 tok)
- `test_e2e_tester.py` — classes: TestParseVerdictE2E, TestExtractChangedFiles, TestSuggestTestCommands, TestExtractProposedFixes, TestBuildE2eContext, TestDiffTruncation, TestE2eTestNode (~3559 tok)
- `test_graph_runner.py` — funcs: async_generator, collect_stream; classes: TestStreamGraph, TestRunGraph (~493 tok)
- `test_models.py` — classes: TestPlanVerdict, TestCodeVerdict (~489 tok)
- `test_node_contract.py` — classes: TestNonEmpty, TestIsPath, TestContainsVerdict, TestIsVerdictValue, TestIsNonNegativeInt, TestParseVerdict, TestExtractVerdictBlock, TestValidateNode, TestFormatVerdictFeedback… (~4534 tok)
- `test_plan_build_review.py` — classes: TestPlanBuildReviewGraph, TestE2eRouting, TestSkipPlanReview, TestCheckpointing, TestBuildReviewFeedbackInjection (~2666 tok)
- `test_plan_chunker.py` — classes: TestChunkStepModel, TestExecutionPlanModel, TestChunkPlanNode, TestAdvanceChunk, TestRouteAfterBuildReview, TestEntryRouting, TestGraphStructure, TestBuildReviewChunkAwareness (~3770 tok)
- `test_plan_review.py` — classes: TestPlanReviewGraph (~669 tok)
- `test_prompt_build_review.py` — classes: TestPromptBuildReviewGraph, TestRoutingLogic, TestPromptSynthesizer (~1076 tok)
- `test_prompt_workflow.py` — classes: TestPromptWorkflowGraph (~312 tok)
- `test_tracer.py` — funcs: _read_events; classes: TestGraphTracer, TestContextVars, TestTracedRoute (~3297 tok)

## tests/eval/

- `__init__.py` — (no description) (~1 tok)
- `test_corpus.py` — funcs: _write; classes: TestParseTask, TestLoadCorpus, TestDefaultCorpus (~1021 tok)
- `test_judge_backend.py` — classes: TestClassifyByModel, TestIsOpenAICompatible, TestQueryOpenAICompatible (~2038 tok)
- `test_judge_pairwise.py` — funcs: _judge_text; classes: TestParseJudgement, TestCollapseVotes, TestJudgePairWithPositionCheck, TestJudgeMulti, TestJudgeSingleDispatch (~2371 tok)
- `test_matrix.py` — funcs: _task, _cfg, _fake_run_result; classes: TestConfiguration, TestRunMatrix, TestLoadMatrixSummaries, TestDefaultConfigurations (~1807 tok)
- `test_metrics.py` — funcs: _task; classes: TestConceptCoverageKeyword, TestConceptCoverageJaccard, TestFailureModeHitRate, TestMetricClassifications, TestStanceFlipCount, TestRunMetrics, TestCrossRunSimilarity… (~2264 tok)
- `test_report.py` — funcs: _outcome; classes: TestComputeWinMatrix, TestVariantAggregate, TestTerminationDistribution, TestCostAdjustedWinRates, TestBuildReport (~1603 tok)

## tests/pipeline/

- `__init__.py` — (no description) (~1 tok)
- `test_anonymize.py` — classes: TestAnonymizePair, TestAnonymizeForDebate (~806 tok)
- `test_artifacts.py` — funcs: _make_config; classes: TestRunDir, TestWriteArtifact, TestWriteConfigAndTask, TestSummary, TestAtomicWrite (~1869 tok)
- `test_budget.py` — funcs: _fresh_state; classes: TestOverBudget, TestElapsedSeconds (~950 tok)
- `test_config.py` — funcs: dataclasses_frozen_error; classes: TestModelConfig, TestHelpers, TestRunConfig, TestRunResult (~1078 tok)
- `test_prompts.py` — funcs: test_generator_base_is_non_empty, test_critic_personas_are_distinct, test_reviser_base_discourages_blind_acceptance, test_debate_system_prompt_has_required_slots… (~779 tok)
- `test_session.py` — funcs: _fake_cli_result; classes: TestSingleQuery, TestAgentSessionInterface (~1351 tok)
- `test_state.py` — funcs: test_shared_state_has_required_keys, test_variant_a_state_adds_no_new_keys, test_variant_b_state_adds_debate_keys, test_accumulator_annotations_present (~679 tok)

## tests/pipeline/variant_a/

- `__init__.py` — (no description) (~1 tok)
- `test_graph.py` — funcs: _phase_router, _patch_single_query, cfg; classes: TestGraphStructure, TestEndToEnd, TestBudgetShortCircuit (~1459 tok)
- `test_nodes.py` — funcs: config, _state, _patch_single_query; classes: TestStartRun, TestGenerate, TestCrossReview, TestRevise, TestSynthesize (~2290 tok)

## tests/pipeline/variant_b/

- `__init__.py` — (no description) (~1 tok)
- `test_graph.py` — funcs: _clean_registry, _pre_debate_router, _patch_pre_debate_single_query, _make_session_factory, cfg; classes: TestGraphStructure, TestEndToEndMutualAgreement, TestEndToEndMaxRounds… (~2132 tok)
- `test_nodes.py` — funcs: _clean_registry, cfg, _base_state, _make_session_mock; classes: TestInitDebate, TestDebateTurn, TestCompact, TestRecordTermination (~3210 tok)
- `test_parsing.py` — classes: TestParseStance, TestParseKeyPoint, TestJaccard, TestStableDisagreement, TestTranscriptTokenEstimate (~1283 tok)
- `test_registry.py` — funcs: _clean_registry, _fake_session; classes: TestRegister, TestCloseAll (~806 tok)

