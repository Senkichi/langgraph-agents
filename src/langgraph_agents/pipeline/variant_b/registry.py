"""Out-of-band registry for debate ``AgentSession`` instances.

LangGraph state is pickled/serialised across nodes and must not carry
unserialisable objects like open SDK clients. The registry holds the live
sessions keyed by ``(run_id, speaker_name)`` so nodes retrieve them by key.

Keeping this as a module-level dict is intentional: all Variant B nodes run
in the same Python process, and session objects have no equivalent reachable
via durable state. The registry is NOT thread-safe across parallel matrix
runs with colliding ``run_id`` values — the contract is that ``run_id`` must
be unique per run (the matrix runner constructs it as ``{config_id}__{task_id}``
which guarantees that).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langgraph_agents.pipeline.session import AgentSession

logger = logging.getLogger(__name__)

_DEBATE_SESSIONS: dict[str, dict[str, "AgentSession"]] = {}


def register(run_id: str, name: str, session: "AgentSession") -> None:
    """Add ``session`` under ``(run_id, name)``. Overwriting logs a warning."""
    bucket = _DEBATE_SESSIONS.setdefault(run_id, {})
    if name in bucket:
        logger.warning(
            "registry.register: replacing existing session run_id=%s name=%s",
            run_id,
            name,
        )
    bucket[name] = session


def get(run_id: str, name: str) -> "AgentSession | None":
    """Return the session or ``None`` if absent — nodes decide how to handle."""
    return _DEBATE_SESSIONS.get(run_id, {}).get(name)


def get_or_raise(run_id: str, name: str) -> "AgentSession":
    session = get(run_id, name)
    if session is None:
        raise RuntimeError(
            f"No debate session registered for run_id={run_id!r} name={name!r}"
        )
    return session


async def close_all(run_id: str) -> None:
    """Close every session for a run. Per-session errors are logged, not raised.

    Always safe to call — a missing ``run_id`` is a no-op so the Variant B
    ``finally`` block can invoke this unconditionally.
    """
    sessions = _DEBATE_SESSIONS.pop(run_id, {})
    for name, session in sessions.items():
        try:
            await session.close()
        except Exception as exc:  # noqa: BLE001 — best-effort cleanup
            logger.warning(
                "registry.close_all: error closing session run_id=%s name=%s: %s",
                run_id,
                name,
                exc,
            )


def active_run_ids() -> list[str]:
    """Diagnostic: run_ids with at least one live session. Used in tests."""
    return [rid for rid, bucket in _DEBATE_SESSIONS.items() if bucket]


def _reset_for_tests() -> None:
    """Test-only: clear all state without closing sessions."""
    _DEBATE_SESSIONS.clear()
