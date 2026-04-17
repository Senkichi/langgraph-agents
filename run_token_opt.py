"""Token optimization hooks — sequential execution of plans 01 → 02 → 03.

Plans 01 and 02 share shared.py and post-tool.py:
  - tok-01 creates the initial versions
  - tok-02 extends them with anatomy functions
Sequential execution avoids write conflicts on these shared files.
tok-03 depends on both completing (CLv2 enrichment + anatomy freshness).

Usage:
    uv run python run_token_opt.py
"""

import sys
from pathlib import Path

# Force UTF-8 output on Windows to handle Unicode in e2e reports
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

from langgraph_agents.graph_runner import run_graph
from langgraph_agents.graphs.plan_build_review import plan_build_review_app

WORKSPACE = str(Path.home() / ".claude")

PLANS = Path(__file__).parent / ".planning/phases/token-optimization"


def load_plan(filename: str) -> str:
    return (PLANS / filename).read_text(encoding="utf-8")


def run_plan(label: str, plan_text: str, task_summary: str) -> dict:
    print(f"\n{'='*60}")
    print(f"  Starting {label}: {task_summary}")
    print(f"  Workspace: {WORKSPACE}")
    print(f"  Plan size: {len(plan_text):,} chars")
    print(f"{'='*60}\n")

    result = run_graph(
        plan_build_review_app,
        {
            "task": task_summary,
            "current_plan": plan_text,
            "current_code": "",
            "workspace_path": WORKSPACE,
            "e2e_verdict": "",
            "e2e_report": "",
            "e2e_cycle": 0,
        },
        graph_name=label,
    )

    verdict = result.get("e2e_verdict", "N/A")
    cycles = result.get("e2e_cycle", 0)
    print(f"\n{'='*60}")
    print(f"  {label} COMPLETE — verdict: {verdict}, e2e cycles: {cycles}")
    print(f"{'='*60}\n")

    report = result.get("e2e_report", "")
    if report:
        tail = report[-2000:] if len(report) > 2000 else report
        print(f"E2E REPORT (last {min(len(report), 2000)} chars):\n{tail}\n")

    diff = result.get("current_code", "")
    if diff:
        tail = diff[-1500:] if len(diff) > 1500 else diff
        print(f"FINAL DIFF (last {min(len(diff), 1500)} chars):\n{tail}\n")

    return result


def main() -> None:
    plans = [
        # tok-01 completed: shared.py, session-init/pre-read/post-tool.py, hooks registered
        # tok-02 completed: scanner.py, anatomy functions in shared.py, incremental post-tool update
        ("tok-03", "tok-03-PLAN.md", "CLv2 observation enrichment: file_path + estimated_tokens + anatomy freshness reminder"),
    ]

    results = {}
    for label, filename, summary in plans:
        plan_text = load_plan(filename)
        results[label] = run_plan(label, plan_text, summary)

    print("\n" + "="*60)
    print("TOKEN OPTIMIZATION — ALL PLANS COMPLETE")
    print("="*60)
    for label, _, _ in plans:
        r = results[label]
        print(f"  {label}: {r.get('e2e_verdict', 'N/A')} ({r.get('e2e_cycle', 0)} e2e cycles)")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
