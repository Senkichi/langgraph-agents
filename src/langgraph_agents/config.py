"""Central configuration for model selection and execution parameters.

All values are overridable via environment variables. This is the single
place to adjust model profiles across the entire workflow.

Example — run the full workflow with haiku reviewers for cost testing:
    REVIEWER_MODEL=haiku uv run python run_sync_opt_phase1.py
"""

import os

# --- Model selection ---
PLANNER_MODEL: str = os.environ.get("PLANNER_MODEL", "opus")
REVIEWER_MODEL: str = os.environ.get("REVIEWER_MODEL", "sonnet")
CODER_MODEL: str = os.environ.get("CODER_MODEL", "sonnet")
E2E_MODEL: str = os.environ.get("E2E_MODEL", "sonnet")
PROMPT_ENGINEER_MODEL: str = os.environ.get("PROMPT_ENGINEER_MODEL", "sonnet")
DISCOVER_MODEL: str = os.environ.get("DISCOVER_MODEL", "sonnet")

CHUNKER_MODEL: str = os.environ.get("CHUNKER_MODEL", PLANNER_MODEL)

# --- Timeouts (seconds) ---
CODER_TIMEOUT: int = int(os.environ.get("CODER_TIMEOUT_S", "7200"))
REVIEWER_TIMEOUT: int = int(os.environ.get("REVIEWER_TIMEOUT_S", "3600"))
E2E_TIMEOUT: int = int(os.environ.get("E2E_TIMEOUT_S", "2700"))
PROMPT_ENGINEER_TIMEOUT: int = int(os.environ.get("PROMPT_ENGINEER_TIMEOUT_S", "1800"))

# --- Budget caps (USD) ---
DISCOVER_BUDGET_USD: float = float(os.environ.get("DISCOVER_BUDGET_USD", "1.0"))
CODER_BUDGET_USD: float = float(os.environ.get("CODER_BUDGET_USD", "10.0"))
PROMPT_ENGINEER_BUDGET_USD: float = float(os.environ.get("PROMPT_ENGINEER_BUDGET_USD", "5.0"))
E2E_BUDGET_USD: float = float(os.environ.get("E2E_BUDGET_USD", "2.0"))
REVIEWER_BUDGET_USD: float = float(os.environ.get("REVIEWER_BUDGET_USD", "1.5"))

# --- Tracing ---
TRACE_ENABLED: bool = os.environ.get("TRACE_ENABLED", "true").lower() in ("true", "1", "yes")
TRACE_DIR: str = os.environ.get("TRACE_DIR", "logs")
TRACE_LEVEL: str = os.environ.get("TRACE_LEVEL", "debug")  # "timing" | "state" | "debug"
