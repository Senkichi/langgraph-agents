"""Wrapper around the `claude` CLI for running prompts via Claude Code subscription.

All LLM calls in the plan-build-review workflow go through this module
instead of the Anthropic API.
"""

import json
import subprocess
import sys
import time


def invoke(
    prompt: str,
    *,
    system_prompt: str | None = None,
    cwd: str | None = None,
    output_format: str = "json",
    model: str | None = None,
    allowed_tools: list[str] | None = None,
    add_dirs: list[str] | None = None,
    max_budget_usd: float | None = None,
    json_schema: dict | None = None,
    permission_mode: str = "bypassPermissions",
    timeout: int = 1800,
) -> str:
    """Invoke the claude CLI in print mode and return the response text.

    Args:
        prompt: The user prompt to send.
        system_prompt: Optional system prompt override.
        cwd: Working directory for the claude process.
        output_format: "json" (default) or "text".
        model: Model override (e.g. "sonnet", "opus").
        allowed_tools: List of tools to allow (e.g. ["Read", "Bash"]).
        add_dirs: Additional directories to grant tool access to.
        max_budget_usd: Budget cap for this invocation.
        json_schema: JSON Schema for structured output validation.
        permission_mode: Permission mode (default: bypassPermissions for automation).

    Returns:
        The response text from Claude.

    Raises:
        RuntimeError: If the CLI call fails or returns an error.
    """
    cmd = ["claude", "--print", "--output-format", output_format]

    if system_prompt:
        cmd.extend(["--system-prompt", system_prompt])
    if model:
        cmd.extend(["--model", model])
    if allowed_tools:
        cmd.extend(["--allowed-tools", ",".join(allowed_tools)])
    if add_dirs:
        for d in add_dirs:
            cmd.extend(["--add-dir", d])
    if max_budget_usd is not None:
        cmd.extend(["--max-budget-usd", str(max_budget_usd)])
    if json_schema:
        cmd.extend(["--json-schema", json.dumps(json_schema)])
    if permission_mode:
        cmd.extend(["--permission-mode", permission_mode])

    # Pass prompt via stdin to avoid Windows command-line length limits.
    # The "-" argument tells claude to read the prompt from stdin.
    cmd.append("-")

    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    # --- Tracing: LLM call start ---
    from langgraph_agents.tracer import get_current_node, get_tracer

    tracer = get_tracer()
    current_node = get_current_node()
    if tracer is not None:
        tracer.llm_call_start(current_node, model or "default", prompt)

    t0 = time.perf_counter()
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            **kwargs,
        )
    except Exception as exc:
        duration_ms = (time.perf_counter() - t0) * 1000
        if tracer is not None:
            tracer.llm_call_end(
                current_node, model or "default", duration_ms, "", error=str(exc)
            )
        raise

    duration_ms = (time.perf_counter() - t0) * 1000

    if result.returncode != 0:
        error_msg = (
            f"claude CLI failed (exit {result.returncode}):\n"
            f"STDERR: {result.stderr}\n"
            f"STDOUT: {result.stdout}"
        )
        if tracer is not None:
            tracer.llm_call_end(
                current_node,
                model or "default",
                duration_ms,
                result.stdout,
                error=error_msg,
            )
        raise RuntimeError(error_msg)

    if output_format == "json":
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            if tracer is not None:
                tracer.llm_call_end(
                    current_node,
                    model or "default",
                    duration_ms,
                    result.stdout,
                    error="JSON parse failure",
                )
            raise RuntimeError(
                f"Failed to parse claude CLI JSON output:\n{result.stdout}"
            )

        if data.get("is_error"):
            error_msg = f"claude CLI returned error: {data.get('result', '')}"
            if tracer is not None:
                tracer.llm_call_end(
                    current_node,
                    model or "default",
                    duration_ms,
                    data.get("result", ""),
                    error=error_msg,
                )
            raise RuntimeError(error_msg)

        response_text = data.get("result", "")
        if not response_text and json_schema is not None and "structured_output" in data:
            response_text = json.dumps(data["structured_output"])
        if tracer is not None:
            tracer.llm_call_end(
                current_node, model or "default", duration_ms, response_text
            )
        return response_text

    response_text = result.stdout.strip()
    if tracer is not None:
        tracer.llm_call_end(
            current_node, model or "default", duration_ms, response_text
        )
    return response_text


def invoke_structured(
    prompt: str,
    schema: dict,
    *,
    system_prompt: str | None = None,
    cwd: str | None = None,
    model: str | None = None,
    max_budget_usd: float | None = None,
) -> dict:
    """Invoke claude CLI with --json-schema for structured output.

    Args:
        prompt: The user prompt.
        schema: JSON Schema dict for output validation.
        system_prompt: Optional system prompt.
        cwd: Working directory.
        model: Model override.
        max_budget_usd: Budget cap.

    Returns:
        Parsed JSON dict matching the schema.
    """
    # Use text tools only for structured output (no file writes needed)
    raw = invoke(
        prompt,
        system_prompt=system_prompt,
        cwd=cwd,
        model=model,
        allowed_tools=None,  # omit --allowed-tools; --json-schema suppresses tool calls
        max_budget_usd=max_budget_usd,
        json_schema=schema,
    )

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"Structured output is not valid JSON:\n{raw}")


def invoke_agent(
    prompt: str,
    *,
    system_prompt: str | None = None,
    cwd: str | None = None,
    allowed_tools: list[str] | None = None,
    add_dirs: list[str] | None = None,
    model: str | None = None,
    max_budget_usd: float | None = None,
    timeout: int = 1800,
) -> str:
    """Invoke claude CLI as a full agent with tool access.

    Used for the coder and reviewer agents that need to interact with
    the filesystem, run commands, etc.

    Returns the final response text.
    """
    return invoke(
        prompt,
        system_prompt=system_prompt,
        cwd=cwd,
        model=model,
        allowed_tools=allowed_tools,
        add_dirs=add_dirs,
        max_budget_usd=max_budget_usd,
        timeout=timeout,
    )
