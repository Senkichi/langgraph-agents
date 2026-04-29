"""Judge backend dispatch.

Two transports live in the eval pipeline:

* **Claude CLI** — judges named ``opus`` / ``sonnet`` / ``haiku`` (aliases the
  Claude CLI silently maps) or ``claude-*`` explicit IDs. Routed through
  :func:`langgraph_agents.pipeline.session.single_query` which shells out to
  ``claude --print --model <id>``.

* **OpenAI-compatible API** — DeepSeek (``deepseek-*``) and OpenAI
  (``gpt-*`` / ``o1-*`` / ``o3-*``) accessed via the ``openai`` SDK. DeepSeek
  V4 Pro became a permanent third judge after experiment 003 Phase 0.1 found
  that Claude-only judges over-report unanimity by ~25%; this module is the
  single point of truth for that route.

Backend is chosen from the model id via :func:`classify_by_model`. Callers
should not branch on transport themselves — they pass a model id and this
module dispatches.

The OpenAI-compatible call uses ``max_tokens=8000`` because thinking-mode
models (DeepSeek V4 Pro, OpenAI o-series) consume completion budget on
internal reasoning before any visible content; smaller caps return empty
``content`` and the parser then maps to UNPARSEABLE. Falls back to
``reasoning_content`` if ``content`` is still empty — the model often
restates its answer in chain-of-thought.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

# Default token budget for OpenAI-compatible judge calls. See module docstring.
DEFAULT_MAX_TOKENS: int = 8000


@dataclass(frozen=True)
class OpenAICompatibleBackend:
    """A backend that speaks the OpenAI chat-completions wire format."""

    name: Literal["openai_compatible"]
    provider: str  # "deepseek", "openai" — informational, used in error messages
    base_url: str | None  # None means the openai SDK default
    api_key_env: str  # env var name to read for credentials


# Sentinel for the Claude CLI transport. Using a Literal keeps type-checking
# tight without a pointless dataclass.
ClaudeCLIBackend = Literal["claude_cli"]
Backend = ClaudeCLIBackend | OpenAICompatibleBackend


def classify_by_model(model: str) -> Backend:
    """Pick the transport for a judge model id.

    Recognises:
      - ``deepseek-*`` → DeepSeek (https://api.deepseek.com)
      - ``gpt-*`` / ``o1-*`` / ``o3-*`` → OpenAI default base URL
      - everything else → Claude CLI (covers ``opus``/``sonnet``/``haiku``
        aliases plus explicit ``claude-*`` IDs).

    Raises ``ValueError`` only on the empty string — any other unrecognised
    string falls through to the Claude CLI transport, which will then surface
    its own error if the CLI rejects the model. We do not maintain a positive
    allowlist for Claude IDs because the CLI's accepted set drifts faster
    than this code does.
    """
    if not model:
        raise ValueError("model id must be non-empty")
    if model.startswith("deepseek-"):
        return OpenAICompatibleBackend(
            name="openai_compatible",
            provider="deepseek",
            base_url="https://api.deepseek.com",
            api_key_env="DEEPSEEK_API_KEY",
        )
    if model.startswith(("gpt-", "o1-", "o3-")):
        return OpenAICompatibleBackend(
            name="openai_compatible",
            provider="openai",
            base_url=None,
            api_key_env="OPENAI_API_KEY",
        )
    return "claude_cli"


def is_openai_compatible(model: str) -> bool:
    """Convenience predicate for callers that just want a yes/no."""
    return classify_by_model(model) != "claude_cli"


async def query_openai_compatible(
    *,
    system_prompt: str,
    user_message: str,
    model: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> str:
    """Fire one chat-completion call against an OpenAI-compatible endpoint.

    Returns the raw text the parser will consume. Cost is not returned —
    OpenAI-compatible providers report usage on the response, but the eval
    pipeline does not currently aggregate per-judge cost the way it does for
    pipeline runs, and adding a return-value channel just for that would
    ripple through every caller. If we later want per-judge cost we can read
    the response here and emit it via a logging hook.
    """
    backend = classify_by_model(model)
    if backend == "claude_cli" or not isinstance(backend, OpenAICompatibleBackend):
        raise ValueError(
            f"query_openai_compatible called for model {model!r} which classifies as Claude CLI"
        )
    api_key = os.environ.get(backend.api_key_env)
    if not api_key:
        raise RuntimeError(
            f"{backend.api_key_env} not set (provider={backend.provider}, model={model})"
        )

    # Imported here so the openai package only has to be importable when an
    # OpenAI-compatible judge is actually used. The pipeline core never
    # imports it.
    from openai import OpenAI

    def _call_sync() -> str:
        client = (
            OpenAI(api_key=api_key, base_url=backend.base_url)
            if backend.base_url
            else OpenAI(api_key=api_key)
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0,
            max_tokens=max_tokens,
        )
        msg = resp.choices[0].message
        text = msg.content or ""
        if not text:
            rc = getattr(msg, "reasoning_content", None) or ""
            if rc:
                logger.warning(
                    "judge model %s returned empty content (finish_reason=%s, "
                    "completion_tokens=%s); falling back to reasoning_content (%d chars)",
                    model,
                    resp.choices[0].finish_reason,
                    getattr(resp.usage, "completion_tokens", "?"),
                    len(rc),
                )
                text = rc
        return text

    return await asyncio.to_thread(_call_sync)
