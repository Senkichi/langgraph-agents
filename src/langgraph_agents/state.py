from typing_extensions import TypedDict


class ParentState(TypedDict):
    """Top-level state for the plan-build-review workflow."""

    task: str  # Original task description (optional if plan provided)
    current_plan: str  # Pre-written plan OR empty string
    current_code: str  # Final code summary/diff after build phase
    workspace_path: str  # Directory where code is written
    e2e_verdict: str  # "APPROVE" | "REVISE" | "SKIP" | ""
    e2e_report: str  # LLM-optimized diagnostic report (or skip reason)
    agent_architecture: str  # compressed workspace architecture summary
    e2e_cycle: int  # 0 → max 2
    skip_plan_review: bool  # True = bypass plan_review, go straight to plan_chunker
    # --- Chunking fields ---
    chunks: list[dict]  # serialized ChunkStep dicts from plan_chunker
    chunk_index: int  # current position in chunks list (0-based)
    full_plan: str  # preserved copy of the complete approved plan
    resolved_issues: list[str]  # accumulated across chunks — confirmed-fixed CRITICAL/MAJOR issues
    persistent_rules: str  # accumulated across chunks — constraint list from resolved CRITICALs


class PlanReviewState(TypedDict):
    """State for the plan-review loop subgraph."""

    task: str
    current_plan: str  # Replaced each cycle
    agent_architecture: str  # Shared key with ParentState — flows down automatically
    plan_feedback: str  # Replaced each cycle
    plan_verdict: str  # "APPROVE" | "REVISE" | ""
    plan_cycle: int  # 0 → max 2


class BuildReviewState(TypedDict):
    """State for the build-review loop subgraph."""

    task: str
    current_plan: str  # Read-only approved plan
    agent_architecture: str  # Pre-discovered workspace summary (shared key with ParentState)
    code_diff: str  # git diff captured after each coder run
    workspace_path: str  # Working directory for file ops
    micro_feedback: str  # Replaced each cycle
    macro_feedback: str  # Replaced each cycle
    build_verdict: str  # Synthesized: "APPROVE" | "REVISE"
    build_feedback: str  # Merged feedback for coder
    build_cycle: int  # 0 → max 4
    # Injected by parent graph's _call_build_review wrapper on re-entry after
    # e2e failure. No subgraph node writes this field — it is the only
    # BuildReviewState field populated from outside the subgraph.
    e2e_feedback: str
    resolved_issues: list[str]  # confirmed-fixed CRITICAL/MAJOR issues
    persistent_rules: str  # constraint list derived from resolved CRITICALs; bounded at 5 rules


class PromptBuildState(TypedDict):
    """State for the prompt-engineering build-review loop subgraph."""

    task: str
    current_plan: str  # Approved plan from plan-review phase
    agent_architecture: str  # Compressed architecture summary from discover node
    prompt_diff: str  # git diff of prompt/knowledge file changes
    workspace_path: str  # Target project directory
    behavioral_feedback: str  # Replaced each cycle
    architectural_feedback: str  # Replaced each cycle
    build_verdict: str  # Synthesized: "APPROVE" | "REVISE"
    build_feedback: str  # Merged feedback for prompt engineer
    build_cycle: int  # 0 → max 4


class PromptWorkflowState(TypedDict):
    """Top-level state for the prompt workflow (discover → plan → build)."""

    task: str
    current_plan: str
    agent_architecture: str
    prompt_diff: str
    workspace_path: str
