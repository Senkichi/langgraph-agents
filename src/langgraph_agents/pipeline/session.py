"""Pipeline session primitives.

Part 1 ships only ``single_query`` — the one-shot wrapper Variant A needs.
It uses the subprocess-backed Claude CLI (same integration mode as the rest of
this package). Per the dual-pipeline plan, persistent debate sessions for
Variant B land in Part 3 with ``claude-agent-sdk`` as a new dependency; a
placeholder ``AgentSession`` class is exposed here so the interface is
discoverable from the start, but every method raises until Part 3 wires it up.

The cost-delta returned by ``single_query`` is whatever the CLI reports in its
JSON envelope's ``total_cost_usd`` field. On a Claude Code subscription this
may be an equivalent-cost estimate rather than a real spend — per the
evaluation-framework decision, we treat it as a proxy metric.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from typing import Any

from langgraph_agents.tracer import get_current_node, get_tracer


def _build_cli_args(
    *,
    system_prompt: str | None,
    model: str | None,
    allowed_tools: list[str] | None,
    add_dirs: list[str] | None,
    max_budget_usd: float | None,
    permission_mode: str,
    output_format: str = "json",
) -> list[str]:
    cmd: list[str] = ["claude", "--print", "--output-format", output_format]
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
    if permission_mode:
        cmd.extend(["--permission-mode", permission_mode])
    cmd.append("-")  # read prompt from stdin
    return cmd


def _run_cli_sync(
    prompt: str,
    *,
    system_prompt: str | None,
    cwd: str | None,
    model: str | None,
    allowed_tools: list[str] | None,
    add_dirs: list[str] | None,
    max_budget_usd: float | None,
    permission_mode: str,
    timeout: int,
) -> tuple[str, float, dict[str, Any]]:
    """Synchronous CLI invocation that preserves the full envelope.

    Returns ``(response_text, cost_usd, envelope)``. Raised exceptions are not
    swallowed — the caller decides whether to retry.
    """
    cmd = _build_cli_args(
        system_prompt=system_prompt,
        model=model,
        allowed_tools=allowed_tools,
        add_dirs=add_dirs,
        max_budget_usd=max_budget_usd,
        permission_mode=permission_mode,
    )

    kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

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
            f"STDERR: {result.stderr}\nSTDOUT: {result.stdout}"
        )
        if tracer is not None:
            tracer.llm_call_end(
                current_node, model or "default", duration_ms, result.stdout, error=error_msg
            )
        raise RuntimeError(error_msg)

    try:
        envelope = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        if tracer is not None:
            tracer.llm_call_end(
                current_node,
                model or "default",
                duration_ms,
                result.stdout,
                error=f"JSON parse failure: {exc}",
            )
        raise RuntimeError(f"Failed to parse claude CLI JSON output:\n{result.stdout}") from exc

    if envelope.get("is_error"):
        error_msg = f"claude CLI returned error: {envelope.get('result', '')}"
        if tracer is not None:
            tracer.llm_call_end(
                current_node, model or "default", duration_ms, envelope.get("result", ""),
                error=error_msg,
            )
        raise RuntimeError(error_msg)

    response_text = envelope.get("result", "") or ""
    cost_usd = float(envelope.get("total_cost_usd") or 0.0)

    if tracer is not None:
        tracer.llm_call_end(current_node, model or "default", duration_ms, response_text)

    return response_text, cost_usd, envelope


async def single_query(
    system_prompt: str,
    user_message: str,
    *,
    cwd: str,
    model: str,
    allowed_tools: list[str] | None = None,
    add_dirs: list[str] | None = None,
    max_budget_usd: float | None = None,
    permission_mode: str = "bypassPermissions",
    timeout: int = 1800,
) -> tuple[str, float]:
    """Async wrapper: open, send one prompt, close. Returns ``(response, cost_usd)``.

    The CLI spawns its own subprocess, so ``asyncio.to_thread`` is sufficient —
    we don't need true async I/O to cooperate with ``asyncio.gather`` for the
    parallel fan-out nodes Variant A uses.
    """
    response, cost, _envelope = await asyncio.to_thread(
        _run_cli_sync,
        user_message,
        system_prompt=system_prompt,
        cwd=cwd,
        model=model,
        allowed_tools=allowed_tools,
        add_dirs=add_dirs,
        max_budget_usd=max_budget_usd,
        permission_mode=permission_mode,
        timeout=timeout,
    )
    return response, cost


class AgentSession:
    """Persistent ``claude-agent-sdk`` client wrapper for Variant B debate.

    The SDK is a hard dependency declared in ``pyproject.toml``. Imports are
    local to methods rather than module-level only because the SDK's CLI-bundled
    runtime probes the environment at import time, and we don't want that probe
    to run for Variant A tests that never instantiate a session.

    Lifecycle:
        session = AgentSession(...)
        await session.start(first_message)    # connect + send
        await session.send(next_message)       # subsequent turns
        await session.close()                  # disconnect (idempotent)
    """

    def __init__(
        self,
        name: str,
        system_prompt: str,
        cwd: str,
        model: str,
        allowed_tools: list[str] | None = None,
    ) -> None:
        self.name = name
        self.system_prompt = system_prompt
        self.cwd = cwd
        self.model = model
        self.allowed_tools = list(allowed_tools) if allowed_tools else []
        self._client = None
        self._total_cost_usd = 0.0
        self._turn_count = 0
        self._session_id: str | None = None

    async def start(self, first_message: str) -> tuple[str, float]:
        """Open the SDK client and send the first message."""
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

        options = ClaudeAgentOptions(
            system_prompt=self.system_prompt,
            cwd=self.cwd,
            model=self.model,
            allowed_tools=self.allowed_tools,
            permission_mode="default",
        )
        self._client = ClaudeSDKClient(options=options)
        await self._client.connect()
        return await self._send(first_message)

    async def send(self, message: str) -> tuple[str, float]:
        """Send a subsequent turn on the existing connection."""
        if self._client is None:
            raise RuntimeError(f"Session {self.name!r} not started")
        return await self._send(message)

    async def close(self) -> None:
        """Disconnect the SDK client. Idempotent."""
        if self._client is None:
            return
        try:
            await self._client.disconnect()
        finally:
            self._client = None

    @property
    def total_cost_usd(self) -> float:
        return self._total_cost_usd

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def turn_count(self) -> int:
        return self._turn_count

    async def _send(self, message: str) -> tuple[str, float]:
        """Stream one turn, accumulate cost, return ``(response, cost_delta)``.

        SDK 0.1.x pattern: ``query()`` is a coroutine that enqueues the turn
        (no return value worth iterating), and ``receive_response()`` is the
        async iterator that streams ``AssistantMessage`` / ``ResultMessage``
        back. Text lives inside ``AssistantMessage.content`` as ``TextBlock``
        entries; cost and session id arrive on ``ResultMessage``.
        """
        from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

        assert self._client is not None
        parts: list[str] = []
        cost_before = self._total_cost_usd

        await self._client.query(message)
        async for msg in self._client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        parts.append(block.text)
            elif isinstance(msg, ResultMessage):
                if msg.session_id:
                    self._session_id = msg.session_id
                if msg.total_cost_usd is not None:
                    self._total_cost_usd += float(msg.total_cost_usd)

        self._turn_count += 1
        return "\n".join(parts), self._total_cost_usd - cost_before
