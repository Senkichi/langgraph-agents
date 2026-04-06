"""One-shot runner: invoke plan-build-review on the Companies audit & fix plan."""

from pathlib import Path

from langgraph_agents.graphs.plan_build_review import plan_build_review_app

PLAN_PATH = Path(r"C:\Users\senki\repos\job-cannon\.planning\COMPANIES_AUDIT_AND_FIX_PLAN.md")
WORKSPACE = r"C:\Users\senki\repos\job-cannon"

TASK = (
    "Companies subsystem quality & observability improvements — Wave 3 + Wave 4.\n\n"
    "CONTEXT: Waves 1-2 (Fixes 1-7, 11) are already implemented and committed. "
    "This run implements the remaining fixes from the audit plan.\n\n"
    "SCOPE: Implement Fixes 8, 9, 10, 12, 13, and 14 only.\n\n"
    "Wave 3 (P2 — quality & observability):\n"
    "- Fix 8: Add pagination to companies index — server-side with HTMX infinite scroll, "
    "per_page=50, sentinel row with hx-trigger='revealed'\n"
    "- Fix 9: Make jobs_found_total accurate — change from append-only (jobs_found_total + ?) "
    "to replacement (jobs_found_total = ?) in run_ats_scan() and HTML fallback loop\n"
    "- Fix 10: Differentiated scan logging — add jobs_matched column to company_scan_log "
    "via migration, track pre-dedup count vs new count\n"
    "- Fix 12: Homepage discovery tests — create tests/test_homepage_discoverer.py with "
    "full coverage for _strip_company_suffixes, _name_to_slug, discover_homepage tiers, "
    "_try_slug_heuristic, run_homepage_discovery batch processing\n"
    "- Fix 13: Clean up orphan data — one-time SQL cleanup (delete orphan companies, "
    "recalibrate jobs_found_total). Implement as a function that can be called from scheduler.\n\n"
    "Wave 4 (P3 — dashboard health):\n"
    "- Fix 14: Add Companies Pipeline Health section to companies index page showing "
    "pending probe backlog, enrichment coverage, homepage coverage, unlinked jobs, "
    "and last scan date with age warning\n\n"
    "Important project conventions:\n"
    "- Raw SQL only (no ORM), SQLite with WAL mode\n"
    "- Schema migrations via db_migrate.py (list of discrete SQL strings)\n"
    "- APScheduler 3.11 (pinned <4.0)\n"
    "- Tests use uv run pytest, temp DB per test, mocked Claude client\n"
    "- HTMX 2.x + Tailwind CDN, Jinja2 templates\n"
    "- Fragment routes MUST check HX-Request header and return full page for direct access\n"
    "- Immutable data patterns preferred (new objects, not mutation)\n"
    "- Run uv run pytest after implementation to verify nothing is broken\n"
)


def main() -> None:
    plan_text = PLAN_PATH.read_text(encoding="utf-8")
    print(f"Plan loaded: {len(plan_text)} chars from {PLAN_PATH.name}")
    print(f"Workspace: {WORKSPACE}")
    print("Starting plan-build-review workflow...\n")

    result = plan_build_review_app.invoke({
        "task": TASK,
        "current_plan": plan_text,
        "current_code": "",
        "workspace_path": WORKSPACE,
        "e2e_verdict": "",
        "e2e_report": "",
        "e2e_cycle": 0,
    })

    print("\n=== WORKFLOW COMPLETE ===")
    print(f"E2E verdict: {result.get('e2e_verdict', 'N/A')}")
    print(f"E2E cycles: {result.get('e2e_cycle', 0)}")
    print(f"Plan length: {len(result.get('current_plan', ''))} chars")
    print(f"Code diff length: {len(result.get('current_code', ''))}")

    if result.get("e2e_report"):
        report = result["e2e_report"]
        print(f"\n=== E2E REPORT ({len(report)} chars) ===")
        if len(report) > 3000:
            print(f"...(showing last 3000 of {len(report)} chars)...")
            report = report[-3000:]
        print(report)

    if result.get("current_code"):
        diff = result["current_code"]
        print(f"\n=== FINAL DIFF ({len(diff)} chars) ===")
        if len(diff) > 2000:
            print(f"...(truncated, showing last 2000 of {len(diff)} chars)...")
            diff = diff[-2000:]
        print(diff)


if __name__ == "__main__":
    main()
