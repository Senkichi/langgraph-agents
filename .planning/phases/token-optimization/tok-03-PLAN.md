---
phase: token-optimization
plan: "03"
type: execute
wave: 2
depends_on: ["tok-01", "tok-02"]
files_modified:
  - ~/.claude/skills/continuous-learning-v2/hooks/observe.sh
  - ~/.claude/hooks/token-opt/shared.py
  - ~/.claude/hooks/token-opt/post-tool.py
autonomous: true
requirements:
  - "CLv2 observation schema enriched with estimated_tokens field"
  - "File path extraction from Read/Write/Edit tool inputs into top-level observation field"
  - "Session-end anatomy freshness reminder"

must_haves:
  truths:
    - "CLv2 observations for Read tool_complete events include an estimated_tokens field"
    - "CLv2 observations for Read/Write/Edit events include a top-level file_path field"
    - "The token estimation uses the same formula as the read lifecycle hooks (chars / type-specific divisor)"
    - "Existing observation schema fields are preserved — new fields are additive only"
    - "post-tool.py emits a stderr reminder on Stop if anatomy.md is missing or stale"
  artifacts:
    - path: ~/.claude/skills/continuous-learning-v2/hooks/observe.sh
      provides: "Extended inline Python block extracting file_path and estimated_tokens into observation records"
    - path: ~/.claude/hooks/token-opt/post-tool.py
      provides: "Extended with anatomy freshness check on session end"
  key_links:
    - from: ~/.claude/skills/continuous-learning-v2/hooks/observe.sh
      to: ~/.claude/hooks/token-opt/shared.py
      via: "Token estimation formula replicated inline (observe.sh is bash+inline python, cannot import)"
      pattern: formula-duplication
---

# CLv2 Observation Enrichment — Implementation Plan

## Objective

Extend the existing continuous-learning-v2 observation pipeline to capture token estimates and
extracted file paths. This enables future waste-detection analytics (e.g., "which files burn the
most tokens across sessions?", "what's the Read:Edit token ratio?") without requiring any new
infrastructure — just richer observation records.

Also add a lightweight anatomy freshness reminder so Claude is nudged to run the scanner when
the index is missing or stale.

## Execution Context

Read these before starting:
- `~/.claude/skills/continuous-learning-v2/hooks/observe.sh` — the hook to modify
- `~/.claude/hooks/token-opt/shared.py` — token estimation formula to replicate
- `.planning/phases/token-optimization/RESEARCH.md` — rationale

**Critical constraint:** `observe.sh` is a bash script with inline Python. It cannot import from
`shared.py` (different execution context). The token estimation formula must be replicated inline.
Keep a comment noting the canonical source: `# Formula from ~/.claude/hooks/token-opt/shared.py`.

<tasks>

<task type="auto">
  <name>Task 1: Enrich CLv2 observations with file_path and estimated_tokens</name>
  <files>~/.claude/skills/continuous-learning-v2/hooks/observe.sh</files>
  <read_first>~/.claude/skills/continuous-learning-v2/hooks/observe.sh</read_first>
  <action>
    Find the inline Python block in `observe.sh` that constructs the observation JSON record.
    It currently builds: `timestamp, event, tool, session, project_id, project_name, input, output`.

    Extend the Python block to extract two additional fields:

    **`file_path`** (present on tool_start for Read/Write/Edit/MultiEdit):
    ```python
    file_path = None
    if tool in ("Read", "Write", "Edit", "MultiEdit"):
        inp = json.loads(tool_input) if isinstance(tool_input, str) else tool_input
        file_path = inp.get("file_path") or inp.get("path")
        if file_path:
            file_path = file_path.replace("\\", "/")
    ```
    Add `"file_path": file_path` to the observation dict (null if not applicable).

    **`estimated_tokens`** (present on tool_complete for Read):
    ```python
    estimated_tokens = None
    if event == "tool_complete" and tool == "Read" and tool_output:
        content = tool_output[:5000]  # already truncated, but cap for safety
        # Formula from ~/.claude/hooks/token-opt/shared.py
        ext = (file_path or "").rsplit(".", 1)[-1].lower() if file_path else ""
        code_exts = {"py","rs","go","js","ts","c","cpp","java","rb","sh","jsx","tsx"}
        prose_exts = {"md","txt","rst","adoc"}
        cpt = 3.5 if ext in code_exts else (4.0 if ext in prose_exts else 3.75)
        estimated_tokens = int(len(content) / cpt)
    ```
    Add `"estimated_tokens": estimated_tokens` to the observation dict (null if not applicable).

    **Do NOT change** the existing scrubbing, truncation, or anti-loop logic. Only add fields
    to the dict construction and the json.dumps output.

    Verify the modified observation record still writes valid JSONL by checking the output
    of a test invocation.
  </action>
  <verify>
    echo '{"tool_name":"Read","tool_input":{"file_path":"src/main.py"},"tool_output":{"content":"x = 1\ny = 2\n"},"session_id":"test","hook_type":"post"}' | bash -c 'export CLAUDE_CODE_ENTRYPOINT=cli; bash ~/.claude/skills/continuous-learning-v2/hooks/observe.sh post' 2>&1; tail -1 ~/.claude/homunculus/projects/*/observations.jsonl 2>/dev/null || tail -1 ~/.claude/homunculus/observations.jsonl 2>/dev/null
  </verify>
  <acceptance_criteria>
    - Observations for Read tool_complete include `"estimated_tokens": <int>`
    - Observations for Read/Write/Edit tool_start include `"file_path": "<path>"`
    - Observations for non-file tools have `"file_path": null, "estimated_tokens": null`
    - Existing fields (timestamp, event, tool, session, project_id, project_name, input, output) unchanged
    - Secret scrubbing still applied to input/output fields
    - Anti-loop guards still functional
    - JSONL format valid (each line is parseable JSON)
  </acceptance_criteria>
  <done>CLv2 observations include file_path and estimated_tokens fields. Existing schema preserved. Valid JSONL confirmed.</done>
</task>

<task type="auto">
  <name>Task 2: Anatomy freshness reminder</name>
  <files>~/.claude/hooks/token-opt/post-tool.py</files>
  <read_first>~/.claude/hooks/token-opt/post-tool.py, ~/.claude/hooks/token-opt/shared.py</read_first>
  <action>
    Add an anatomy freshness check that runs periodically (not on every tool call).

    At the top of post-tool.py's main block, after determining `op`, add a lightweight check
    that triggers once per session (tracked via a flag in the session JSONL):

    ```python
    # Anatomy freshness check — once per session, on first Write/Edit
    if op == "write":
        session_path = current_session_file()
        if session_path:
            events = session_path.read_text(errors="ignore").strip().split("\n")
            # Only check if this is the first write event in the session
            write_events = [e for e in events if '"event": "write"' in e]
            if len(write_events) <= 1:  # This is the first (just-appended) write
                project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
                anatomy_path = Path(project_dir) / ".claude" / "anatomy.md"
                if not anatomy_path.exists():
                    print("[token-opt] No anatomy.md found. Run `python ~/.claude/hooks/token-opt/scanner.py` to create a project index.", file=sys.stderr)
                else:
                    import time
                    age_hours = (time.time() - anatomy_path.stat().st_mtime) / 3600
                    if age_hours > 72:
                        print(f"[token-opt] anatomy.md is {int(age_hours)}h old. Consider re-running the scanner.", file=sys.stderr)
    ```

    This only fires on the first Write/Edit of each session — minimal overhead.
  </action>
  <verify>
    CLAUDE_PROJECT_DIR=/tmp/test_freshness mkdir -p /tmp/test_freshness/.claude && echo '{"session_id":"fresh-test"}' | python ~/.claude/hooks/token-opt/session-init.py && echo '{"tool_name":"Write","tool_input":{"file_path":"/tmp/test_freshness/foo.py","content":"x=1"}}' | python ~/.claude/hooks/token-opt/post-tool.py 2>&1 | grep "token-opt" && rm -rf /tmp/test_freshness
  </verify>
  <acceptance_criteria>
    - First write of a session with no anatomy.md prints "No anatomy.md found" to stderr
    - First write of a session with anatomy.md older than 72h prints age warning to stderr
    - Second and subsequent writes in the same session do NOT print the reminder
    - Reminder does not fire on Read operations
    - No error or output when anatomy.md exists and is fresh
  </acceptance_criteria>
  <done>Anatomy freshness reminder fires once per session on first write. Missing and stale anatomy detected correctly.</done>
</task>

</tasks>

<verification>
Before declaring plan complete:
- [ ] New CLv2 observation with Read tool_complete contains estimated_tokens > 0
- [ ] New CLv2 observation with Write tool_start contains file_path string
- [ ] Non-file tool observations have null for both new fields
- [ ] Existing observation fields unchanged
- [ ] observe.sh anti-loop guards still prevent subagent observation
- [ ] Secret scrubbing still replaces API keys in input/output
- [ ] Anatomy freshness reminder fires on first write of session, not subsequent writes
- [ ] Full CLv2 pipeline still works: observations recorded, instinct-cli.py analyze still parses them
</verification>

<success_criteria>
- CLv2 observations are enriched with file_path and estimated_tokens without breaking existing schema
- Token estimation formula matches shared.py (chars / type-specific divisor)
- Anatomy freshness reminder provides actionable guidance without being noisy
- instinct-cli.py analyze still works on enriched observations (additive schema change)
</success_criteria>

<output>
After completion, create `.planning/phases/token-optimization/tok-03-SUMMARY.md`
</output>
