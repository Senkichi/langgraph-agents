"""One-shot runner: invoke plan-build-review for DataForSEO source."""

from pathlib import Path

from langgraph_agents.graphs.plan_build_review import plan_build_review_app

PLAN_PATH = Path(r"C:\Users\senki\repos\job-cannon\.planning\DATAFORSEO_SOURCE_PLAN.md")
WORKSPACE = r"C:\Users\senki\repos\job-cannon"

TASK = (
    "Add DataForSEO as an additional job discovery source to the job-cannon ingestion pipeline.\n\n"
    "DataForSEO is a Google Jobs SERP API with a task-queue architecture (no live endpoint):\n"
    "  1. POST tasks to /v3/serp/google/jobs/task_post (billed here)\n"
    "  2. Poll /v3/serp/google/jobs/tasks_ready every 30s until task IDs appear\n"
    "  3. GET /v3/serp/google/jobs/task_get/advanced/{id} for each completed task (free)\n\n"
    "Key constraints:\n"
    "- No live endpoint — async task queue only (confirmed: /live/ returns 404)\n"
    "- Authentication: HTTP Basic Auth with pre-encoded base64 'login:password' string\n"
    "- Returns google_jobs_item objects with: job_id, title, employer_name, location,\n"
    "  source_url, salary, contract_type, timestamp (ISO-8601 UTC)\n"
    "- Does NOT return job description — enrichment pipeline fills that\n"
    "- Age filter: exclude jobs older than max_age_days (uses timestamp field)\n"
    "- Cost: $0.0006/10 results (normal priority), depth=20 recommended\n"
    "- tasks_ready rate limit: 20 calls/min — poll every 30s is safe\n"
    "- Use 'uv run pytest' for all test commands (never bare pytest)\n"
    "- config.yaml must ONLY be modified with surgical Edit tool, NEVER full Write\n"
    "- Credential (base64-encoded, already encoded): ZGZzLmdhcmxpYzE1MUBwYXNzaW5ib3guY29tOjA1OTVlMDVhNDcyNTlkOTI=\n\n"
    "Files to create/modify:\n"
    "- NEW: job_finder/sources/dataforseo_source.py\n"
    "- MODIFY: job_finder/web/pipeline_runner.py (add _fetch_dataforseo, wire into run_ingestion)\n"
    "- MODIFY: config.example.yaml (add dataforseo: block under sources:)\n"
    "- NEW: tests/test_dataforseo_source.py\n\n"
    "--- FULL PLAN (self-contained spec with API reference, implementation spec, and test spec) ---\n\n"
)


def main() -> None:
    plan_text = PLAN_PATH.read_text(encoding="utf-8")
    task = TASK + plan_text

    print(f"Plan loaded: {len(plan_text)} chars from {PLAN_PATH.name}")
    print(f"Total task prompt: {len(task)} chars")
    print(f"Workspace: {WORKSPACE}")
    print("Starting plan-build-review workflow...\n")

    result = plan_build_review_app.invoke({
        "task": task,
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
