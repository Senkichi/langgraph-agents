"""One-shot runner: invoke plan-build-review on the JD quality remediation plan."""

from pathlib import Path

from langgraph_agents.graphs.plan_build_review import plan_build_review_app

INVESTIGATION_PATH = Path(r"C:\Users\senki\repos\job-cannon\docs\JD_QUALITY_INVESTIGATION.md")
WORKSPACE = r"C:\Users\senki\repos\job-cannon"

TASK = (
    "Remediate JD quality contamination in the job-cannon enrichment pipeline.\n\n"
    "The investigation below documents the full scope: 14% of JDs are contaminated "
    "with LinkedIn page chrome, 'Similar jobs' sections, and HTML tags. Contamination "
    "enters through fetch_direct_jd() and free-tier URL fetches that scrape entire "
    "LinkedIn pages instead of the targeted div.show-more-less-html__markup container. "
    "Salary cross-contamination affects ~10 jobs. Sonnet scoring uses contaminated "
    "jd_full; Haiku scoring is unaffected (uses clean description field).\n\n"
    "Implement the four remediation recommendations from the investigation:\n"
    "1. Post-scrape sanitization — strip LinkedIn page chrome, 'Similar jobs' sections, "
    "and HTML tags from jd_full before storage\n"
    "2. Apply validation consistently — has_jd_content() and company_name_in_text() "
    "should gate all tiers, not just DDG\n"
    "3. Retroactive cleanup — scan existing jd_full values, truncate at contamination markers\n"
    "4. Separate JD quality from salary enrichment — salary should only come from "
    "structured sources, not from AI extraction on scraped page fragments\n\n"
    "--- FULL INVESTIGATION ---\n\n"
)


def main() -> None:
    investigation_text = INVESTIGATION_PATH.read_text(encoding="utf-8")
    task = TASK + investigation_text

    print(f"Investigation loaded: {len(investigation_text)} chars from {INVESTIGATION_PATH.name}")
    print(f"Total task prompt: {len(task)} chars")
    print(f"Workspace: {WORKSPACE}")
    print("Starting plan-build-review workflow...\n")

    result = plan_build_review_app.invoke({
        "task": task,
        "current_plan": "",
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
