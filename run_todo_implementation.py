#!/usr/bin/env python3
"""
Orchestrates all 16 TODO-IMPLEMENTATION-PLAN chunks through plan_build_review.

Reads chunk content directly from the plan file. Runs chunks in topological
order, enforcing the dependency graph. Persists state after every chunk so
the run is resumable across crashes.

Usage:
    cd ~/repos/langgraph-agents
    uv run python run_todo_implementation.py
    uv run python run_todo_implementation.py --dry-run
    uv run python run_todo_implementation.py --from-chunk 5
    uv run python run_todo_implementation.py --reset

Options:
    --dry-run         Print execution plan without invoking the graph.
    --from-chunk N    Mark all chunks before N as done and start from N.
                      Useful for manual resume when state file is missing or wrong.
    --reset           Clear the state file and start fresh (prompts for confirmation).

Resumability:
    State is written to run_todo_state.json after each chunk completes.
    Re-running automatically skips chunks already in a terminal state.

Dependency enforcement:
    If a chunk raises a Python exception (hard error), all downstream dependents
    are skipped. Partial completions (REVISE after max cycles) warn but do NOT
    block dependents — the code changes may still be partially applied.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langgraph_agents.graphs.plan_build_review import plan_build_review_app

# ─── Configuration ────────────────────────────────────────────────────────────

WORKSPACE = Path(r"C:\Users\senki\repos\job-cannon")
PLAN_FILE = WORKSPACE / ".planning" / "TODO-IMPLEMENTATION-PLAN.md"
STATE_FILE = Path(__file__).parent / "run_todo_state.json"

# Injected into the `task` field for every chunk — gives the coder workspace
# context that isn't in the chunk plan itself.
PROJECT_CONTEXT = """\
Context:
- job-cannon is a personal job search Flask app (Python 3.13, Flask 3.1, SQLite, HTMX 2.x)
- Run tests with: uv run --active pytest -q --tb=short  (NEVER bare pytest)
- config.yaml must ONLY be modified with the surgical Edit tool — NEVER Write/full-overwrite
- Raw SQLite SQL only (no ORM). Type hints on all new function signatures.
- APScheduler pinned <4.0. HTMX fragment routes MUST return 200 (not 204).
- Absolute imports from job_finder package root. Snake_case everywhere; PascalCase for classes.
- Single-user local app. No Docker, no CI/CD, no deployment.
"""

# ─── Dependency graph ─────────────────────────────────────────────────────────
# Topological execution order: independent chunks first, then dependents in
# wave order. Satisfies every edge in the plan's dependency graph.
#
#   Wave 0 (independent):        1, 3, 4, 10, 11, 13, 14, 15
#   Wave 1 (depends on wave 0):  2 (←1),  5 (←3,4),  8 (←3)
#   Wave 1.5 (prefer after 5):   12
#   Wave 2 (depends on wave 1):  6 (←5)
#   Wave 3 (depends on wave 2):  9 (←4,5,6),  7 (←6)
#   Wave 4 (depends on wave 3):  16 (←5,6,7,8,9)

EXECUTION_ORDER: list[int] = [1, 3, 4, 10, 11, 13, 14, 15, 2, 5, 8, 12, 6, 9, 7, 16]

DEPS: dict[int, frozenset[int]] = {
    1:  frozenset(),
    2:  frozenset({1}),
    3:  frozenset(),
    4:  frozenset(),
    5:  frozenset({3, 4}),
    6:  frozenset({5}),
    7:  frozenset({6}),
    8:  frozenset({3}),
    9:  frozenset({4, 5, 6}),
    10: frozenset(),
    11: frozenset(),
    12: frozenset(),    # independent; placed after chunk 5 per plan note
    13: frozenset(),
    14: frozenset(),
    15: frozenset(),
    16: frozenset({5, 6, 7, 8, 9}),
}

assert set(EXECUTION_ORDER) == set(DEPS), "EXECUTION_ORDER and DEPS must cover the same chunks"

# ─── Status legend ────────────────────────────────────────────────────────────
# done    → e2e_verdict APPROVE or SKIP (clean pass)
# partial → e2e_verdict REVISE after max cycles (changes may still be applied)
# error   → Python exception (no changes guaranteed; blocks downstream chunks)
# skipped → dependency was in error state
# pending → not yet run (initial state)
# running → in-flight (intermediate; cleaned up on resume)

TERMINAL_STATUSES = frozenset({"done", "partial", "error", "skipped"})
ERROR_STATUSES = frozenset({"error"})   # only these block dependents

STATUS_ICON = {
    "done":    "✓",
    "partial": "~",
    "error":   "✗",
    "skipped": "⊘",
    "pending": "·",
    "running": "▶",
}


# ─── Plan file parsing ────────────────────────────────────────────────────────

def parse_plan_chunks(plan_path: Path) -> dict[int, dict[str, str]]:
    """
    Extract chunk sections from TODO-IMPLEMENTATION-PLAN.md.

    Splits on bare '---' horizontal rules (surrounded by blank lines) and
    collects any section whose first heading matches '## Chunk N: Title'.

    Returns: {chunk_id: {"title": str, "scope": str, "plan": str}}
    """
    content = plan_path.read_text(encoding="utf-8")

    # Split on blank-line-surrounded horizontal rules.
    sections = re.split(r"\n\n---\n\n", content)

    chunks: dict[int, dict[str, str]] = {}
    for section in sections:
        # Match the ## Chunk N: Title header (may be preceded by whitespace from split)
        header_m = re.search(r"##\s+Chunk\s+(\d+):\s+(.+)", section)
        if not header_m:
            continue

        chunk_id = int(header_m.group(1))
        title = header_m.group(2).strip()

        scope_m = re.search(r"\*\*Scope\*\*:\s*(.+)", section)
        scope = scope_m.group(1).strip() if scope_m else ""

        chunks[chunk_id] = {
            "title": title,
            "scope": scope,
            "plan": section.strip(),
        }

    return chunks


def validate_chunks(chunks: dict[int, dict]) -> list[str]:
    """Return a list of validation errors, empty if all good."""
    errors = []
    expected = set(EXECUTION_ORDER)
    parsed = set(chunks)
    for missing in expected - parsed:
        errors.append(f"Chunk {missing} not found in plan file")
    for extra in parsed - expected:
        errors.append(f"Chunk {extra} found in plan but not in EXECUTION_ORDER")
    return errors


# ─── State persistence ────────────────────────────────────────────────────────

def load_state() -> dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[warn] State file unreadable ({exc}); starting fresh.", file=sys.stderr)
    return {"run_started": None, "chunks": {}}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def chunk_status(state: dict, chunk_id: int) -> str:
    return state["chunks"].get(str(chunk_id), {}).get("status", "pending")


def blocked_by(state: dict, chunk_id: int) -> list[int]:
    """Return list of prerequisite chunk IDs that are in an error state."""
    return [dep for dep in DEPS[chunk_id] if chunk_status(state, dep) in ERROR_STATUSES]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Graph invocation ─────────────────────────────────────────────────────────

def run_chunk(chunk_id: int, info: dict[str, str]) -> dict[str, Any]:
    """
    Invoke plan_build_review_app for a single chunk.

    The `task` field is the brief context header; `current_plan` is the full
    chunk content from the plan file. This matches the Runner Script Template
    in the plan document.

    Returns a result dict (never raises — callers check status field).
    """
    from langgraph_agents.config import TRACE_DIR, TRACE_ENABLED, TRACE_LEVEL
    from langgraph_agents.tracer import GraphTracer, set_tracer

    task = (
        f"Chunk {chunk_id}: {info['title']}\n\n"
        f"Scope: {info['scope']}\n\n"
        f"{PROJECT_CONTEXT}"
    )

    inputs = {
        "task": task,
        "current_plan": info["plan"],
        "current_code": "",
        "workspace_path": str(WORKSPACE),
        "e2e_verdict": "",
        "e2e_report": "",
        "e2e_cycle": 0,
        "skip_plan_review": True,
    }
    config = {"configurable": {"thread_id": f"chunk-{chunk_id}"}}

    tracer: GraphTracer | None = None
    token = None
    if TRACE_ENABLED:
        tracer = GraphTracer(
            run_id=f"chunk-{chunk_id}",
            graph_name=f"chunk_{chunk_id}",
            log_dir=Path(TRACE_DIR),
            trace_level=TRACE_LEVEL,
        )
        token = set_tracer(tracer)
        tracer.graph_start(inputs)
        print(f"          [trace] {tracer.log_path}", flush=True)

    t0 = time.perf_counter()
    try:
        result = plan_build_review_app.invoke(inputs, config=config)
    except Exception:
        if tracer is not None:
            tracer.graph_end((time.perf_counter() - t0) * 1000)
        raise
    finally:
        if token is not None:
            set_tracer(None)

    if tracer is not None:
        summary = tracer.graph_end((time.perf_counter() - t0) * 1000)
        print(
            f"          [trace] done  {summary['total_duration_s']:.0f}s"
            f"  ~{summary['total_tokens_in']:,}tok-in"
            f"  ~{summary['total_tokens_out']:,}tok-out",
            flush=True,
        )

    verdict = result.get("e2e_verdict", "")
    e2e_cycles = result.get("e2e_cycle", 0)
    diff = result.get("current_code", "")
    report = result.get("e2e_report", "")

    # APPROVE / SKIP → clean pass; REVISE → max cycles exhausted (partial)
    status = "done" if verdict in ("APPROVE", "SKIP") else "partial"

    return {
        "status": status,
        "verdict": verdict,
        "e2e_cycles": e2e_cycles,
        "diff_chars": len(diff),
        "e2e_report_tail": report[-2000:] if len(report) > 2000 else report,
    }


# ─── Reporting ────────────────────────────────────────────────────────────────

def print_chunk_header(idx: int, total: int, chunk_id: int, info: dict) -> None:
    print(f"\n[{idx:2d}/{total}] >>  Chunk {chunk_id}: {info['title']}")
    print(f"          Scope : {info['scope']}")
    deps = sorted(DEPS[chunk_id])
    print(f"          Deps  : {deps if deps else 'none'}")


def print_summary(state: dict, chunks: dict[int, dict]) -> None:
    width = 70
    print("\n" + "=" * width)
    print(" EXECUTION SUMMARY")
    print("=" * width)

    counts: dict[str, int] = {}
    for cid in EXECUTION_ORDER:
        rec = state["chunks"].get(str(cid), {})
        status = rec.get("status", "pending")
        counts[status] = counts.get(status, 0) + 1

        icon = STATUS_ICON.get(status, "?")
        title = chunks.get(cid, {}).get("title", f"Chunk {cid}")
        verdict = rec.get("verdict", "")
        diff = rec.get("diff_chars", 0)
        skip_reason = rec.get("skip_reason", "")

        detail = ""
        if verdict:
            detail = f"  verdict={verdict}  diff={diff:,}c  e2e={rec.get('e2e_cycles', 0)}"
        if skip_reason:
            detail = f"  ({skip_reason})"

        print(f"  {icon} [{cid:2d}] {title}{detail}")

    print("-" * width)
    for s in ("done", "partial", "error", "skipped", "pending"):
        if n := counts.get(s, 0):
            print(f"  {STATUS_ICON[s]} {s}: {n}")
    print("=" * width)


# ─── CLI ──────────────────────────────────────────────────────────────────────

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run all 16 TODO implementation chunks through plan_build_review.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--from-chunk",
        type=int,
        metavar="N",
        help="Mark chunks before N as done and start execution from N.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would run without invoking the graph.",
    )
    p.add_argument(
        "--reset",
        action="store_true",
        help="Clear saved state and restart from scratch (prompts for confirmation).",
    )
    return p


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    args = build_arg_parser().parse_args()

    # ── Validate inputs ──────────────────────────────────────────────────────
    if not PLAN_FILE.exists():
        print(f"ERROR: Plan file not found: {PLAN_FILE}", file=sys.stderr)
        return 1

    chunks = parse_plan_chunks(PLAN_FILE)
    errors = validate_chunks(chunks)
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    # ── State setup ──────────────────────────────────────────────────────────
    if args.reset:
        print("WARNING: This will discard all saved progress.")
        if input("Type 'yes' to confirm reset: ").strip().lower() != "yes":
            print("Aborted.")
            return 0
        state: dict[str, Any] = {"run_started": None, "chunks": {}}
        save_state(state)
        print("State cleared.\n")
    else:
        state = load_state()

    if state["run_started"] is None:
        state["run_started"] = _now()
        save_state(state)

    # ── --from-chunk: mark preceding chunks as done in state ─────────────────
    if args.from_chunk is not None:
        if args.from_chunk not in EXECUTION_ORDER:
            print(f"ERROR: Chunk {args.from_chunk} is not in the execution order.", file=sys.stderr)
            return 1
        start_idx = EXECUTION_ORDER.index(args.from_chunk)
        for cid in EXECUTION_ORDER[:start_idx]:
            if chunk_status(state, cid) not in TERMINAL_STATUSES:
                state["chunks"].setdefault(str(cid), {}).update(
                    {"status": "done", "note": "--from-chunk override"}
                )
        save_state(state)

    # ── Dry-run ───────────────────────────────────────────────────────────────
    if args.dry_run:
        print(f"Dry run — {len(EXECUTION_ORDER)} chunks in execution order\n")
        print(f"  Plan file  : {PLAN_FILE}")
        print(f"  Workspace  : {WORKSPACE}")
        print(f"  State file : {STATE_FILE}\n")
        for cid in EXECUTION_ORDER:
            status = chunk_status(state, cid)
            title = chunks[cid]["title"]
            dep_str = f"deps={sorted(DEPS[cid])}" if DEPS[cid] else "no deps"
            icon = STATUS_ICON.get(status, "?")
            print(f"  {icon} [{cid:2d}] {title}  [{status}]  {dep_str}")
        return 0

    # ── Run loop ──────────────────────────────────────────────────────────────
    total = len(EXECUTION_ORDER)
    print(f"Starting TODO implementation run ({total} chunks).")
    print(f"  Plan      : {PLAN_FILE}")
    print(f"  Workspace : {WORKSPACE}")
    print(f"  State     : {STATE_FILE}")

    for idx, chunk_id in enumerate(EXECUTION_ORDER, start=1):
        info = chunks[chunk_id]
        current_status = chunk_status(state, chunk_id)

        # Already finished — skip silently (show one-liner)
        if current_status in TERMINAL_STATUSES:
            icon = STATUS_ICON.get(current_status, "?")
            print(
                f"\n[{idx:2d}/{total}] {icon}  Chunk {chunk_id} ({info['title']})"
                f" — already {current_status}, skipping"
            )
            continue

        # Dependency check — only hard errors block
        blockers = blocked_by(state, chunk_id)
        if blockers:
            reason = f"blocked by failed deps: {sorted(blockers)}"
            print(f"\n[{idx:2d}/{total}] ⊘  Chunk {chunk_id} ({info['title']}) — {reason}")
            state["chunks"].setdefault(str(chunk_id), {}).update(
                {"status": "skipped", "skip_reason": reason, "skipped_at": _now()}
            )
            save_state(state)
            continue

        # Mark as running before invoking (allows crash detection on resume)
        print_chunk_header(idx, total, chunk_id, info)
        state["chunks"].setdefault(str(chunk_id), {}).update(
            {"status": "running", "started_at": _now()}
        )
        save_state(state)

        try:
            result = run_chunk(chunk_id, info)
        except Exception:
            err_text = traceback.format_exc()
            print(f"          ✗  EXCEPTION:\n{err_text}")
            state["chunks"][str(chunk_id)].update(
                {
                    "status": "error",
                    "error": err_text[-3000:],
                    "finished_at": _now(),
                }
            )
            save_state(state)
            # Partial downstream skips will be evaluated lazily in the loop above
            continue

        result["finished_at"] = _now()
        state["chunks"][str(chunk_id)].update(result)
        save_state(state)

        icon = STATUS_ICON[result["status"]]
        print(
            f"          {icon}  verdict={result['verdict']}"
            f"  e2e_cycles={result['e2e_cycles']}"
            f"  diff={result['diff_chars']:,}c"
        )

        if result["status"] == "partial":
            print("          ~  WARNING: REVISE verdict — max cycles exhausted.")
            print("               Downstream chunks will still proceed.")
            print("               Review the workspace before continuing.")

        if result["e2e_report_tail"]:
            print(f"\n          ── E2E report (last 2000c) ──\n{result['e2e_report_tail']}")

    print_summary(state, chunks)

    # Exit non-zero if any chunk errored or is still pending
    final_statuses = {str(cid): chunk_status(state, cid) for cid in EXECUTION_ORDER}
    has_errors = any(s == "error" for s in final_statuses.values())
    has_pending = any(s == "pending" for s in final_statuses.values())

    if has_errors:
        print("\nRun completed with errors. Review state file and fix before re-running.")
        return 2
    if has_pending:
        print("\nRun completed with pending chunks (unexpected). Check state file.")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
