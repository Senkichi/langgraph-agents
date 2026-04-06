"""One-shot runner: invoke plan-build-review for Thordata source + scheduler change."""

from pathlib import Path

from langgraph_agents.graphs.plan_build_review import plan_build_review_app

PLAN_PATH = Path(r"C:\Users\senki\.claude\plans\stateless-gathering-mochi.md")
WORKSPACE = r"C:\Users\senki\repos\job-cannon"

TASK = (
    "Add Thordata as an additional job discovery source to the job-cannon ingestion "
    "pipeline, and change the scheduler from every-30-minutes to 3x/day.\n\n"
    "Thordata is a Google Jobs SERP API (POST https://scraperapi.thordata.com/request "
    "with engine=google_jobs). It returns jobs_results[] with: title, company_name, "
    "location, share_link, extensions[] (flat array with salary, posting date, schedule), "
    "via, rank. It does NOT return description, job_highlights, or apply_options.\n\n"
    "Key requirements:\n"
    "- Only ingest jobs posted in the last 3 days (parse posting age from extensions[])\n"
    "- Extract stable source_id from htidocid param in share_link URL\n"
    "- Parse salary from extensions[] array (e.g. '204K-276K a year')\n"
    "- Change ingestion scheduler from IntervalTrigger(minutes=30) to "
    "CronTrigger(hour='0,8,16', timezone='US/Pacific')\n"
    "- Add settings UI for Thordata config (mirror existing SerpAPI pattern)\n"
    "- Use 'uv run pytest' for all test commands (never bare pytest)\n"
    "- config.yaml must ONLY be modified with surgical Edit tool, NEVER full Write\n"
    "- Thordata API key for config.yaml: 26b52e6275f201aa6ff6b154bb12cf17\n\n"
    "Sample Thordata API response (first result):\n"
    '{"title": "Staff Data Scientist- Forcasting", "company_name": "Intuit", '
    '"location": "San Diego, CA", "rank": 1, "via": "Intuit Careers", '
    '"extensions": ["29 days ago", "Full-time", "Health insurance"], '
    '"share_link": "https://www.google.com/search?ibp=htl;jobs&q=Staff+Data+Scientist'
    '&htidocid=_lTbCUIJ6iKqxDCVAAAAAA%3D%3D&hl=en-US&..."}\n\n'
    "Result with salary in extensions:\n"
    '{"extensions": ["21 days ago", "204K\\u2013276K a year", "Full-time", "Health insurance"]}\n\n'
    "--- FULL PLAN ---\n\n"
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
