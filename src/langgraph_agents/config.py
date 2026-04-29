"""Central configuration for model selection and execution parameters.

All values are overridable via environment variables. This is the single
place to adjust model profiles across the entire workflow.

Example — run the full workflow with haiku reviewers for cost testing:
    REVIEWER_MODEL=haiku uv run python run_sync_opt_phase1.py

Defaults pin explicit model IDs (not aliases like ``opus`` / ``sonnet``)
so a silent CLI alias remap — e.g. the 2026-04-23 ``opus`` → 4.7 flip
documented in ``docs/experiment_002_results.md`` — cannot quietly change
the model used by production graphs. Explicit IDs are also what the
2026-04-24 experiment 002 results showed dominate every other pipeline
parameter; see ``memory/project_exp002_results.md``.

Override an alias intentionally with the env var, e.g.
``PLANNER_MODEL=opus`` (alias) or ``PLANNER_MODEL=claude-opus-4-7``.
"""

import logging
import os

logger = logging.getLogger(__name__)

# --- Pinned model IDs (single source of truth for defaults) ---
OPUS_PINNED: str = "claude-opus-4-7"
SONNET_PINNED: str = "claude-sonnet-4-6"
HAIKU_PINNED: str = "claude-haiku-4-5-20251001"

# Aliases that the CLI may silently remap between versions. If any of these
# show up as a *resolved* model name we want it to be loud — use
# ``warn_if_alias`` at call sites that care about reproducibility.
KNOWN_ALIASES: frozenset[str] = frozenset({"opus", "sonnet", "haiku"})


def warn_if_alias(model: str, *, role: str) -> str:
    """Log a warning if ``model`` is a CLI alias rather than an explicit ID.

    Returns ``model`` unchanged so callers can wrap inline:
        model = warn_if_alias(cfg.PLANNER_MODEL, role="planner")
    """
    if model in KNOWN_ALIASES:
        logger.warning(
            "%s model is an alias (%r) — alias remap can silently change "
            "behavior across CLI upgrades. Pin to an explicit ID "
            "(e.g. %r) for reproducibility.",
            role,
            model,
            OPUS_PINNED if model == "opus" else SONNET_PINNED if model == "sonnet" else HAIKU_PINNED,
        )
    return model


# --- Model selection ---
PLANNER_MODEL: str = os.environ.get("PLANNER_MODEL", OPUS_PINNED)
REVIEWER_MODEL: str = os.environ.get("REVIEWER_MODEL", SONNET_PINNED)
CODER_MODEL: str = os.environ.get("CODER_MODEL", SONNET_PINNED)
E2E_MODEL: str = os.environ.get("E2E_MODEL", SONNET_PINNED)
PROMPT_ENGINEER_MODEL: str = os.environ.get("PROMPT_ENGINEER_MODEL", SONNET_PINNED)
DISCOVER_MODEL: str = os.environ.get("DISCOVER_MODEL", SONNET_PINNED)

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
