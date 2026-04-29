"""Graph execution tracer: structured JSONL logging for observability.

Provides a ``GraphTracer`` that emits timestamped events to a JSONL file,
covering node lifecycle, LLM calls, edge routing, and contract violations.
Thread-safe for parallel fan-out (micro/macro reviewer).

The active tracer propagates via ``contextvars`` — node functions never need
to accept a tracer parameter.

Trace levels:
    timing  — node_start/end, graph_start/end, errors, contract violations
    state   — + edge_route, state/return field sizes in node events
    debug   — + llm_call_start/end with prompt/response sizes and token estimates
"""

from __future__ import annotations

import contextvars
import dataclasses
import functools
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Context variables — thread-safe propagation through LangGraph internals
# ---------------------------------------------------------------------------

_active_tracer: contextvars.ContextVar[GraphTracer | None] = contextvars.ContextVar(
    "active_tracer", default=None
)

_current_node: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_node", default="unknown"
)


def get_tracer() -> GraphTracer | None:
    """Get the active tracer from context. Returns None if tracing disabled."""
    return _active_tracer.get()


def set_tracer(tracer: GraphTracer | None) -> contextvars.Token:
    """Set the active tracer in context. Returns token for reset."""
    return _active_tracer.set(tracer)


def get_current_node() -> str:
    """Get the current node name from context."""
    return _current_node.get()


def set_current_node(name: str) -> contextvars.Token:
    """Set the current node name in context."""
    return _current_node.set(name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LEVEL_ORDER = {"timing": 0, "state": 1, "debug": 2}


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: chars / 4."""
    return len(text) // 4


def _field_sizes(d: dict) -> dict[str, int]:
    """Map each field to len(str(value))."""
    return {k: len(str(v)) for k, v in d.items()}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


# ---------------------------------------------------------------------------
# Event dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TraceEvent:
    """Base event — every event carries these fields."""

    event_type: str
    timestamp: str = field(default_factory=_now_iso)
    run_id: str = ""
    graph_name: str = ""
    node_name: str | None = None


@dataclass(frozen=True)
class GraphStartEvent(TraceEvent):
    event_type: str = "graph_start"
    input_field_sizes: dict[str, int] = field(default_factory=dict)
    environment: dict[str, Any] | None = None


@dataclass(frozen=True)
class GraphEndEvent(TraceEvent):
    event_type: str = "graph_end"
    duration_ms: float = 0.0
    summary: dict = field(default_factory=dict)


@dataclass(frozen=True)
class NodeStartEvent(TraceEvent):
    event_type: str = "node_start"
    state_field_sizes: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class NodeEndEvent(TraceEvent):
    event_type: str = "node_end"
    duration_ms: float = 0.0
    return_field_sizes: dict[str, int] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True)
class LLMCallStartEvent(TraceEvent):
    event_type: str = "llm_call_start"
    model: str = ""
    prompt_chars: int = 0
    estimated_prompt_tokens: int = 0


@dataclass(frozen=True)
class LLMCallEndEvent(TraceEvent):
    event_type: str = "llm_call_end"
    model: str = ""
    duration_ms: float = 0.0
    response_chars: int = 0
    estimated_response_tokens: int = 0
    error: str | None = None


@dataclass(frozen=True)
class EdgeRouteEvent(TraceEvent):
    event_type: str = "edge_route"
    source_node: str = ""
    chosen_target: str = ""
    available_targets: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ContractViolationEvent(TraceEvent):
    event_type: str = "contract_violation"
    phase: str = ""  # "pre" or "post"
    violations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ErrorEvent(TraceEvent):
    event_type: str = "error"
    error_type: str = ""
    error_message: str = ""


# ---------------------------------------------------------------------------
# GraphTracer
# ---------------------------------------------------------------------------


class GraphTracer:
    """Thread-safe JSONL event emitter for graph execution tracing.

    Creates ``<trace_dir>/<timestamp>_<graph_name>.jsonl`` and writes one
    JSON object per line, flushed immediately for real-time tailing.
    """

    def __init__(
        self,
        run_id: str,
        graph_name: str,
        log_dir: Path,
        trace_level: str = "debug",
        capture_environment: bool = True,
    ) -> None:
        self.run_id = run_id
        self._trace_level = trace_level
        self._level_num = _LEVEL_ORDER.get(trace_level, 2)
        self._capture_environment = capture_environment
        self._lock = threading.Lock()
        self._graph_stack: list[str] = [graph_name]
        self._start_time: float = time.perf_counter()

        # Accumulators for summary
        self._node_timings: list[dict] = []  # {"node": str, "duration_ms": float}
        self._token_in: int = 0
        self._token_out: int = 0

        # Create log file
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        self._log_path = log_dir / f"{ts}_{graph_name}.jsonl"
        self._file = open(self._log_path, "a", encoding="utf-8")

    @property
    def graph_name(self) -> str:
        return self._graph_stack[-1]

    @property
    def log_path(self) -> Path:
        return self._log_path

    def _should_emit(self, min_level: str) -> bool:
        return self._level_num >= _LEVEL_ORDER.get(min_level, 0)

    def emit(self, event: TraceEvent) -> None:
        """Serialize event to JSON and append to JSONL file. Thread-safe."""
        d = dataclasses.asdict(event)
        d["run_id"] = self.run_id
        d["graph_name"] = self.graph_name
        line = json.dumps(d, default=str) + "\n"
        with self._lock:
            self._file.write(line)
            self._file.flush()

    # --- Graph lifecycle ---

    def graph_start(self, inputs: dict) -> None:
        sizes = _field_sizes(inputs) if self._should_emit("state") else {}
        self._start_time = time.perf_counter()
        env: dict[str, Any] | None = None
        if self._capture_environment:
            try:
                from langgraph_agents.environment import capture as _capture_env

                env = _capture_env()
            except Exception as exc:
                # Environment capture is best-effort: never fail a run because
                # git is missing or the SDK probe blew up.
                logger.debug("environment capture failed: %s", exc)
                env = None
        self.emit(GraphStartEvent(input_field_sizes=sizes, environment=env))

    def graph_end(self, duration_ms: float) -> dict:
        summary = self._build_summary(duration_ms)
        self.emit(GraphEndEvent(duration_ms=duration_ms, summary=summary))
        self._close()
        return summary

    # --- Node lifecycle ---

    def node_start(self, node_name: str, state: dict) -> None:
        sizes = _field_sizes(state) if self._should_emit("state") else {}
        self.emit(NodeStartEvent(node_name=node_name, state_field_sizes=sizes))

    def node_end(
        self,
        node_name: str,
        duration_ms: float,
        result: dict,
        *,
        error: str | None = None,
    ) -> None:
        sizes = _field_sizes(result) if self._should_emit("state") else {}
        self.emit(
            NodeEndEvent(
                node_name=node_name,
                duration_ms=duration_ms,
                return_field_sizes=sizes,
                error=error,
            )
        )
        with self._lock:
            self._node_timings.append(
                {"node": node_name, "duration_ms": duration_ms}
            )

    # --- LLM calls ---

    def llm_call_start(self, node_name: str, model: str, prompt: str) -> None:
        if not self._should_emit("debug"):
            return
        chars = len(prompt)
        self.emit(
            LLMCallStartEvent(
                node_name=node_name,
                model=model,
                prompt_chars=chars,
                estimated_prompt_tokens=_estimate_tokens(prompt),
            )
        )
        with self._lock:
            self._token_in += _estimate_tokens(prompt)

    def llm_call_end(
        self,
        node_name: str,
        model: str,
        duration_ms: float,
        response: str,
        *,
        error: str | None = None,
    ) -> None:
        if not self._should_emit("debug"):
            return
        chars = len(response)
        self.emit(
            LLMCallEndEvent(
                node_name=node_name,
                model=model,
                duration_ms=duration_ms,
                response_chars=chars,
                estimated_response_tokens=_estimate_tokens(response),
                error=error,
            )
        )
        with self._lock:
            self._token_out += _estimate_tokens(response)

    # --- Edge routing ---

    def edge_route(
        self, source_node: str, chosen: str, available: list[str]
    ) -> None:
        if not self._should_emit("state"):
            return
        self.emit(
            EdgeRouteEvent(
                source_node=source_node,
                chosen_target=chosen,
                available_targets=available,
            )
        )

    # --- Contract violations ---

    def contract_violation(
        self, node_name: str, phase: str, violations: list[str]
    ) -> None:
        self.emit(
            ContractViolationEvent(
                node_name=node_name, phase=phase, violations=violations
            )
        )

    # --- Error ---

    def error(self, node_name: str | None, exc: Exception) -> None:
        self.emit(
            ErrorEvent(
                node_name=node_name,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
        )

    # --- Subgraph stack ---

    def push_graph(self, name: str) -> None:
        with self._lock:
            self._graph_stack.append(name)

    def pop_graph(self) -> None:
        with self._lock:
            if len(self._graph_stack) > 1:
                self._graph_stack.pop()

    # --- Summary ---

    def _build_summary(self, total_duration_ms: float) -> dict:
        total_s = total_duration_ms / 1000

        # Aggregate per-node
        per_node: dict[str, dict] = {}
        for entry in self._node_timings:
            name = entry["node"]
            if name not in per_node:
                per_node[name] = {"total_ms": 0.0, "cycles": 0}
            per_node[name]["total_ms"] += entry["duration_ms"]
            per_node[name]["cycles"] += 1

        breakdown = []
        for name, data in per_node.items():
            node_s = data["total_ms"] / 1000
            pct = (data["total_ms"] / total_duration_ms * 100) if total_duration_ms > 0 else 0
            breakdown.append(
                {
                    "node": name,
                    "total_s": round(node_s, 1),
                    "pct_of_total": round(pct, 1),
                    "cycles": data["cycles"],
                }
            )
        breakdown.sort(key=lambda x: x["total_s"], reverse=True)

        bottleneck = breakdown[0] if breakdown else None

        return {
            "graph_name": self._graph_stack[0],
            "total_duration_s": round(total_s, 1),
            "total_tokens_in": self._token_in,
            "total_tokens_out": self._token_out,
            "node_breakdown": breakdown,
            "bottleneck": bottleneck,
            "log_file": str(self._log_path),
        }

    def _close(self) -> None:
        try:
            self._file.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# traced_route decorator
# ---------------------------------------------------------------------------


def traced_route(
    source_node: str,
    available_targets: list[str],
) -> Callable:
    """Decorator that wraps a routing function to emit edge_route events.

    Usage::

        @traced_route("e2e_test", ["__end__", "build_review"])
        def _route_after_e2e(state: ParentState) -> str:
            ...
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(state: dict) -> Any:
            result = fn(state)
            tracer = get_tracer()
            if tracer is not None:
                if isinstance(result, str):
                    tracer.edge_route(source_node, result, available_targets)
                elif isinstance(result, list):
                    targets = [getattr(s, "node", str(s)) for s in result]
                    tracer.edge_route(
                        source_node, str(targets), available_targets
                    )
            return result

        return wrapper

    return decorator
