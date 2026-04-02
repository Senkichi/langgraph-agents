"""Evaluate resume-engine output by comparing generated vs submitted versions.

Reads generated resume-content.md + process-narrative.md alongside
submitted.md + submitted-narrative.md for each target job. Produces a
structured analysis of systematic differences that can be fed into the
plan-build-review loop to fix the engine.

Usage:
    # Standalone — prints the analysis
    uv run python -m langgraph_agents.evaluate_resumes

    # As a library — returns the analysis string
    from langgraph_agents.evaluate_resumes import evaluate
    analysis = evaluate(resume_engine_path, job_dirs)
"""

import difflib
import os
import sys

from langgraph_agents.claude_cli import invoke

RESUME_ENGINE_PATH = os.path.expanduser("~/repos/resume-engine")

TARGET_JOBS = [
    "apple-senior-marketing-data-scientist",
    "smithrx-staff-data-analyst",
    "strava-senior-business-analyst",
    "gitlab-senior-data-analyst-marketing-analytics",
]

ANALYSIS_SYSTEM_PROMPT = (
    "You are a senior resume strategist analyzing systematic differences "
    "between AI-generated resumes and human-edited submitted versions.\n\n"
    "You will receive, for each job application:\n"
    "1. A unified diff of the resume content (generated → submitted)\n"
    "2. The AI engine's process narrative (its reasoning)\n"
    "3. The human's process narrative for the submitted version (their reasoning)\n\n"
    "Your job is to identify SYSTEMATIC PATTERNS across all applications — "
    "not one-off edits. Categorize findings as:\n\n"
    "- **Strategic Reasoning Gaps**: Where the engine's decision-making logic "
    "diverges from human judgment (e.g., misreading JD signals, wrong framing)\n"
    "- **Content Quality Issues**: Bullet wording, specificity, quantification, "
    "tone problems that the human consistently fixes\n"
    "- **Structural/Formatting Issues**: Section ordering, length, whitespace, "
    "summary construction patterns\n"
    "- **Selection Logic Issues**: Wrong bullets chosen, missing emphasis, "
    "over/under-indexing on certain experiences\n\n"
    "For each pattern, cite specific evidence from multiple applications. "
    "Rank patterns by frequency and impact. End with a prioritized list of "
    "concrete fixes the engine needs, written as actionable requirements "
    "that a planning agent can turn into implementation tasks."
)


def _read_file(path: str) -> str | None:
    """Read a file, returning None if it doesn't exist."""
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def _compute_diff(generated: str, submitted: str, label: str) -> str:
    """Compute a unified diff between generated and submitted text."""
    gen_lines = generated.splitlines(keepends=True)
    sub_lines = submitted.splitlines(keepends=True)
    diff = difflib.unified_diff(
        gen_lines, sub_lines,
        fromfile=f"{label}/generated",
        tofile=f"{label}/submitted",
        lineterm="",
    )
    return "".join(diff)


def collect_pairs(
    resume_engine_path: str, job_dirs: list[str]
) -> list[dict[str, str | None]]:
    """Collect generated/submitted pairs for each job directory.

    Returns a list of dicts with keys:
        job, generated_resume, submitted_resume, generated_narrative, submitted_narrative
    Missing files are None.
    """
    pairs = []
    for job in job_dirs:
        output_dir = os.path.join(resume_engine_path, "outputs", job)
        pairs.append({
            "job": job,
            "generated_resume": _read_file(
                os.path.join(output_dir, "resume-content.md")
            ),
            "submitted_resume": _read_file(
                os.path.join(output_dir, "submitted.md")
            ),
            "generated_narrative": _read_file(
                os.path.join(output_dir, "process-narrative.md")
            ),
            "submitted_narrative": _read_file(
                os.path.join(output_dir, "submitted-narrative.md")
            ),
        })
    return pairs


def build_analysis_prompt(pairs: list[dict[str, str | None]]) -> str:
    """Build the LLM prompt from collected resume pairs."""
    sections: list[str] = []

    for pair in pairs:
        job = pair["job"]
        header = f"# Application: {job}\n"
        parts = [header]

        gen_resume = pair["generated_resume"]
        sub_resume = pair["submitted_resume"]

        if gen_resume and sub_resume:
            diff = _compute_diff(gen_resume, sub_resume, job)
            parts.append(f"## Resume Diff (generated → submitted)\n```diff\n{diff}\n```\n")
        elif not sub_resume:
            parts.append("## Resume Diff\n*submitted.md not found — skipping diff*\n")

        if pair["generated_narrative"]:
            parts.append(
                f"## Engine Process Narrative\n{pair['generated_narrative']}\n"
            )

        if pair["submitted_narrative"]:
            parts.append(
                f"## Human Process Narrative (submitted version)\n"
                f"{pair['submitted_narrative']}\n"
            )
        else:
            parts.append(
                "## Human Process Narrative\n"
                "*submitted-narrative.md not found — skipping*\n"
            )

        sections.append("\n".join(parts))

    return "\n---\n\n".join(sections)


def validate_pairs(pairs: list[dict[str, str | None]]) -> list[str]:
    """Return a list of warning messages for missing files."""
    warnings: list[str] = []
    for pair in pairs:
        job = pair["job"]
        if not pair["generated_resume"]:
            warnings.append(f"  {job}: missing resume-content.md")
        if not pair["submitted_resume"]:
            warnings.append(f"  {job}: missing submitted.md")
        if not pair["generated_narrative"]:
            warnings.append(f"  {job}: missing process-narrative.md")
        if not pair["submitted_narrative"]:
            warnings.append(f"  {job}: missing submitted-narrative.md")
    return warnings


def evaluate(
    resume_engine_path: str = RESUME_ENGINE_PATH,
    job_dirs: list[str] | None = None,
) -> str:
    """Run the full evaluation pipeline. Returns the LLM analysis string.

    Raises FileNotFoundError if no submitted resumes are found at all.
    """
    from langgraph_agents.llm import get_llm

    if job_dirs is None:
        job_dirs = TARGET_JOBS

    pairs = collect_pairs(resume_engine_path, job_dirs)

    warnings = validate_pairs(pairs)
    if warnings:
        print("Warnings (missing files):")
        for w in warnings:
            print(w)
        print()

    has_any_submitted = any(p["submitted_resume"] for p in pairs)
    if not has_any_submitted:
        raise FileNotFoundError(
            "No submitted.md files found in any target job directory. "
            "Please add submitted resume content before running evaluation.\n"
            "Expected locations:\n"
            + "\n".join(
                f"  {resume_engine_path}/outputs/{j}/submitted.md"
                for j in job_dirs
            )
        )

    prompt_content = build_analysis_prompt(pairs)
    return invoke(
        prompt_content,
        system_prompt=ANALYSIS_SYSTEM_PROMPT,
    )


def evaluate_and_run(
    resume_engine_path: str = RESUME_ENGINE_PATH,
    job_dirs: list[str] | None = None,
) -> dict:
    """Run evaluation then feed results into the plan-build-review loop.

    Returns the final state from the plan-build-review graph.
    """
    from langgraph_agents.graphs.prompt_workflow import prompt_workflow_app

    analysis = evaluate(resume_engine_path, job_dirs)
    print("--- Analysis complete. Starting prompt workflow loop... ---\n")

    result = prompt_workflow_app.invoke({
        "task": (
            "Based on the following analysis of systematic differences between "
            "AI-generated resumes and human-edited submitted versions, fix the "
            "resume-engine's agent prompts and knowledge files to eliminate "
            "these gaps. The analysis compares both the resume content diffs "
            "AND the process narratives (engine reasoning vs human reasoning) "
            "to identify where the engine's decision-making diverges from "
            "human judgment.\n\n"
            f"{analysis}"
        ),
        "current_plan": "",
        "agent_architecture": "",
        "prompt_diff": "",
        "workspace_path": resume_engine_path,
    })
    return result


if __name__ == "__main__":
    # Force UTF-8 stdout on Windows to handle Unicode in resume content
    sys.stdout.reconfigure(encoding="utf-8")

    if "--full" in sys.argv:
        result = evaluate_and_run()
        print("\n=== Prompt Workflow Complete ===")
        print(f"\nFinal plan:\n{result.get('current_plan', 'N/A')[:500]}...")
        print(f"\nPrompt diff:\n{result.get('prompt_diff', 'N/A')[:500]}...")
    else:
        analysis = evaluate()
        print(analysis)
        print("\n---")
        print("Run with --full to feed this analysis into the plan-build-review loop.")
