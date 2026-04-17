"""One-shot runner: invoke plan-build-review on the RSS enrichment pipeline plan."""

import sys
from pathlib import Path

from langgraph_agents.graph_runner import run_graph
from langgraph_agents.graphs.plan_build_review import plan_build_review_app

PLAN_PATH = Path(r"C:\Users\senki\repos\rss-feed\docs\superpowers\plans\2026-04-01-rss-enrichment-pipeline.md")
WORKSPACE = r"C:\Users\senki\repos\rss-feed"

TASK = (
    "Build a local RSS feed enrichment pipeline that classifies, enriches, "
    "and re-serves RSS feeds for Readwise Reader. "
    "Single Python process with a timed poll loop and a static-file HTTP server. "
    "Feed entries are classified via heuristics, enriched through a 4-stage "
    "extraction fallback chain (trafilatura -> readability-lxml -> Playwright -> Wayback), "
    "and output as clean RSS XML."
)


def main() -> None:
    plan_text = PLAN_PATH.read_text(encoding="utf-8")
    print(f"Plan loaded: {len(plan_text)} chars from {PLAN_PATH.name}")
    print(f"Workspace: {WORKSPACE}")
    print("Starting plan-build-review workflow...\n")

    result = run_graph(
        plan_build_review_app,
        {
            "task": TASK,
            "current_plan": plan_text,
            "current_code": "",
            "workspace_path": WORKSPACE,
            "e2e_verdict": "",
            "e2e_report": "",
            "e2e_cycle": 0,
        },
        graph_name="rss_pipeline",
    )

    print("\n=== WORKFLOW COMPLETE ===")
    print(f"Plan verdict passed through: {len(result.get('current_plan', ''))} chars")
    print(f"Code diff length: {len(result.get('current_code', ''))}")
    if result.get("current_code"):
        # Print last 2000 chars of diff to stay readable
        diff = result["current_code"]
        if len(diff) > 2000:
            print(f"...(truncated, showing last 2000 of {len(diff)} chars)...")
            diff = diff[-2000:]
        print(diff)


if __name__ == "__main__":
    main()
