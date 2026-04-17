"""Deterministic per-run and cross-run metrics.

All metrics here are computed from artifacts on disk; no LLM calls. This
makes the metrics pass cheap to re-run after tuning or adding measures.

Per-run metrics (``run_metrics``):
  - ``total_cost_usd``, ``wall_clock_seconds``, ``termination_reason`` — from summary
  - ``final_plan_chars`` / ``final_plan_tokens_est`` — size of the final plan
  - ``concept_coverage_keyword`` — fraction of expected key_concepts whose
    lowercase token appears anywhere in the final plan
  - ``concept_coverage_token_jaccard`` — Jaccard between final-plan tokens
    and the expected-concept token set (complements raw presence)
  - Variant-B extras: ``round_count``, ``compaction_count``, ``stance_flip_count``

Cross-run metrics (``cross_run_similarity``):
  - pairwise token-Jaccard over final plans per task, so you can see whether
    configurations converge or diverge on the same task.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Mapping

from .corpus import Task

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokens(text: str) -> set[str]:
    if not text:
        return set()
    return {w.lower() for w in _TOKEN_RE.findall(text) if len(w) > 1}


def estimate_tokens(text: str) -> int:
    return len(text or "") // 4


# ---------------------------------------------------------------------------
# concept coverage
# ---------------------------------------------------------------------------


def concept_coverage_keyword(final_plan: str, concepts: Iterable[str]) -> float:
    """Fraction of concepts whose lowercase form appears in the final plan.

    Uses case-insensitive substring match so multi-word concepts ("partition
    key") still count. An empty concept list returns 1.0 — nothing to miss.
    """
    concepts = list(concepts)
    if not concepts:
        return 1.0
    haystack = (final_plan or "").lower()
    hits = sum(1 for c in concepts if c.lower() in haystack)
    return hits / len(concepts)


def concept_coverage_token_jaccard(final_plan: str, concepts: Iterable[str]) -> float:
    """Jaccard between final-plan tokens and the concept token set.

    Concept strings are tokenised the same way the plan is; empty concepts →
    0.0 rather than the "nothing to miss" interpretation so the two coverage
    metrics don't both max out on empty input.
    """
    concepts = list(concepts)
    if not concepts:
        return 0.0
    concept_tokens: set[str] = set()
    for c in concepts:
        concept_tokens |= _tokens(c)
    if not concept_tokens:
        return 0.0
    plan_tokens = _tokens(final_plan)
    inter = len(concept_tokens & plan_tokens)
    union = len(concept_tokens | plan_tokens)
    return inter / union if union else 0.0


# ---------------------------------------------------------------------------
# Variant-B transcript metrics
# ---------------------------------------------------------------------------


def stance_flip_count(transcript: Iterable[Mapping]) -> int:
    """Count of turns where a debater's stance differs from their previous turn.

    "Compaction" rows are skipped; they have no stance.
    """
    last_by_speaker: dict[str, str | None] = {}
    flips = 0
    for entry in transcript:
        speaker = entry.get("speaker")
        if speaker not in ("left", "right"):
            continue
        stance = entry.get("stance")
        prior = last_by_speaker.get(speaker)
        if prior is not None and stance is not None and stance != prior:
            flips += 1
        if stance is not None:
            last_by_speaker[speaker] = stance
    return flips


# ---------------------------------------------------------------------------
# Per-run composite
# ---------------------------------------------------------------------------


def _load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _load_transcript(run_dir: Path) -> list[dict]:
    """Best-effort transcript load from the debate_transcript.md artifact.

    We don't re-parse the rendered markdown; instead the debate path tests
    the in-memory transcript directly. For persisted runs the stance/flip
    numbers need the raw transcript list — if the caller has it, pass it via
    ``transcript`` to ``run_metrics``.
    """
    return []


def run_metrics(
    summary: Mapping,
    task: Task,
    *,
    run_dir: Path | str | None = None,
    transcript: list[Mapping] | None = None,
) -> dict:
    """Compute per-run metrics from a loaded ``summary.json`` plus the task spec.

    ``run_dir`` is optional; it's only used to load the final plan if the
    summary doesn't carry it inline. ``transcript`` is optional; provide it
    when you have the in-memory list for Variant-B metrics, otherwise the
    transcript-derived metrics are reported as ``None``.
    """
    final_plan = summary.get("final_plan") or ""
    if not final_plan and run_dir is not None:
        final_plan = _load_text(Path(run_dir) / "final_plan.md")

    variant = summary.get("variant")
    cfg = summary.get("config") or {}

    out: dict = {
        "run_id": summary.get("run_id"),
        "variant": variant,
        "config_id": cfg.get("run_id") if not summary.get("run_id") else None,
        "task_id": task.id,
        "total_cost_usd": float(summary.get("total_cost_usd") or 0.0),
        "wall_clock_seconds": float(summary.get("wall_clock_seconds") or 0.0),
        "termination_reason": summary.get("termination_reason") or "",
        "final_plan_chars": len(final_plan),
        "final_plan_tokens_est": estimate_tokens(final_plan),
        "concept_coverage_keyword": concept_coverage_keyword(
            final_plan, task.key_concepts
        ),
        "concept_coverage_token_jaccard": concept_coverage_token_jaccard(
            final_plan, task.key_concepts
        ),
        "round_count": None,
        "compaction_count": None,
        "stance_flip_count": None,
    }

    if variant == "B" and transcript is not None:
        rounds = max((int(e.get("round") or 0) for e in transcript), default=0)
        compactions = sum(1 for e in transcript if e.get("speaker") == "compaction") // 2
        out["round_count"] = rounds
        out["compaction_count"] = compactions
        out["stance_flip_count"] = stance_flip_count(transcript)

    return out


# ---------------------------------------------------------------------------
# Cross-run similarity
# ---------------------------------------------------------------------------


def cross_run_similarity(
    final_plans: Mapping[str, str],
) -> dict[tuple[str, str], float]:
    """Pairwise token-Jaccard between final plans keyed by config_id.

    Returns a mapping ``(config_a, config_b) -> similarity`` with
    ``config_a <= config_b`` lexicographically to avoid duplicate keys.
    """
    keys = sorted(final_plans.keys())
    out: dict[tuple[str, str], float] = {}
    tokens = {k: _tokens(v) for k, v in final_plans.items()}
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            ta, tb = tokens[a], tokens[b]
            if not ta and not tb:
                out[(a, b)] = 1.0
                continue
            if not ta or not tb:
                out[(a, b)] = 0.0
                continue
            inter = len(ta & tb)
            union = len(ta | tb)
            out[(a, b)] = inter / union if union else 0.0
    return out
