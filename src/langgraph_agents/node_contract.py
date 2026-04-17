"""Node contract enforcement: pre/post-condition validation for graph nodes.

Provides a ``validate_node`` decorator that checks typed pre-conditions
(state fields a node depends on) and post-conditions (fields it promises to
produce) around every node invocation.  Failures raise ``NodeContractError``
with all violations listed — loud, not silent.

Also provides ``format_verdict_feedback``, a shared output normalizer that
logs a warning when the LLM response is missing a VERDICT: line.
"""

import functools
import logging
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class NodeContractError(ValueError):
    """Raised when a node's pre- or post-conditions are violated."""

    def __init__(self, node_name: str, violations: list[str]) -> None:
        self.node_name = node_name
        self.violations = violations
        detail = "\n  ".join(violations)
        super().__init__(f"Contract violation in '{node_name}':\n  {detail}")


# ---------------------------------------------------------------------------
# Validators — each returns an error string if invalid, ``None`` if valid.
# ---------------------------------------------------------------------------


def non_empty(value: Any) -> str | None:
    """Value must be a non-whitespace-only string."""
    if not isinstance(value, str) or not value.strip():
        return f"expected non-empty string, got {type(value).__name__}: {value!r:.80}"
    return None


def is_path(value: Any) -> str | None:
    """Value must be a non-empty string pointing to an existing directory."""
    err = non_empty(value)
    if err:
        return err
    if not Path(value).is_dir():
        return f"directory does not exist: {value}"
    return None


def contains_verdict(value: Any) -> str | None:
    """Value must be a non-empty string containing a ``VERDICT:`` line."""
    err = non_empty(value)
    if err:
        return err
    if "VERDICT:" not in value:
        return "missing VERDICT: line"
    return None


def is_verdict_value(*allowed: str) -> Callable[[Any], str | None]:
    """Factory: value must be one of *allowed* strings."""

    def _check(value: Any) -> str | None:
        if value not in allowed:
            return f"expected one of {allowed}, got {value!r}"
        return None

    return _check


def is_non_negative_int(value: Any) -> str | None:
    """Value must be an ``int >= 0``."""
    if not isinstance(value, int) or value < 0:
        return f"expected non-negative int, got {type(value).__name__}: {value!r}"
    return None


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------

type Validator = Callable[[Any], str | None]


def validate_node(
    *,
    pre: dict[str, Validator] | None = None,
    post: dict[str, Validator] | None = None,
) -> Callable:
    """Decorator that enforces pre/post-conditions on a LangGraph node function.

    *pre* maps state field names to validators checked before the node runs.
    *post* maps return-dict field names to validators checked after.
    All violations are collected before raising a single ``NodeContractError``.
    """
    _pre = pre or {}
    _post = post or {}

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(state: dict) -> dict:
            from langgraph_agents.tracer import get_tracer, set_current_node

            tracer = get_tracer()
            node_token = set_current_node(fn.__name__)

            # --- Pre-conditions ---
            errors: list[str] = []
            for field, validator in _pre.items():
                error = validator(state.get(field))
                if error:
                    errors.append(f"pre[{field}]: {error}")
            if errors:
                if tracer is not None:
                    tracer.contract_violation(fn.__name__, "pre", errors)
                raise NodeContractError(fn.__name__, errors)

            if tracer is not None:
                tracer.node_start(fn.__name__, state)

            t0 = time.perf_counter()
            try:
                result = fn(state)
            except Exception as exc:
                duration_ms = (time.perf_counter() - t0) * 1000
                if tracer is not None:
                    tracer.node_end(
                        fn.__name__, duration_ms, {}, error=str(exc)
                    )
                raise

            duration_ms = (time.perf_counter() - t0) * 1000

            # --- Post-conditions ---
            errors = []
            for field, validator in _post.items():
                error = validator(result.get(field))
                if error:
                    errors.append(f"post[{field}]: {error}")
            if errors:
                if tracer is not None:
                    tracer.contract_violation(fn.__name__, "post", errors)
                    tracer.node_end(
                        fn.__name__,
                        duration_ms,
                        result,
                        error="post-condition violation",
                    )
                raise NodeContractError(fn.__name__, errors)

            if tracer is not None:
                tracer.node_end(fn.__name__, duration_ms, result)

            return result

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Shared output normalizer
# ---------------------------------------------------------------------------


def parse_verdict(text: str, *allowed: str) -> str:
    """Extract VERDICT: value from text, normalizing whitespace and case.

    Returns the first matching VERDICT: line value, uppercased and stripped.
    Falls back to "REVISE" if no VERDICT: line found (safe default — never silently approves).
    """
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("VERDICT:"):
            value = stripped.split(":", 1)[1].strip().upper()
            if not allowed or value in allowed:
                return value
    return "REVISE"


def extract_verdict_block(feedback: str) -> str:
    """Extract the structured verdict block starting at the VERDICT: line.

    Strips the agent's tool-use exploration traces that precede the verdict.
    Returns everything from the first VERDICT: line onward.
    """
    lines = feedback.splitlines()
    for i, line in enumerate(lines):
        if line.strip().upper().startswith("VERDICT:"):
            return "\n".join(lines[i:]).strip()
    return feedback.strip()


def format_verdict_feedback(verdict_text: str) -> str:
    """Ensure feedback contains a parseable ``VERDICT:`` line.

    Logs a warning when it has to intervene — this means the LLM did not
    follow the verdict format instructions.
    """
    if "VERDICT:" not in verdict_text:
        logger.warning(
            "LLM response missing VERDICT: line — injecting VERDICT:REVISE. "
            "Response preview: %.200s",
            verdict_text,
        )
        return f"VERDICT:REVISE\n{verdict_text}"
    return verdict_text


def invoke_with_verdict_retry(
    response: str,
    invoke_fn: Callable[..., str],
    original_prompt: str,
    *,
    allowed_verdicts: tuple[str, ...] = ("APPROVE", "REVISE"),
    **invoke_kwargs: Any,
) -> str:
    """Ensure response contains VERDICT:; re-prompt once if missing.

    Args:
        response: The already-obtained LLM response string.
        invoke_fn: Callable (e.g. invoke_agent) for the retry call.
        original_prompt: The prompt that produced response, used to
                         build the follow-up re-prompt.
        allowed_verdicts: Tuple of accepted verdict values shown in the
                          re-prompt and log messages.
        **invoke_kwargs: Kwargs forwarded verbatim to invoke_fn on retry.

    Returns:
        Response string guaranteed to contain a VERDICT: line.
    """
    if "VERDICT:" in response:
        return response

    logger.warning(
        "LLM response missing VERDICT: line — sending follow-up re-prompt. "
        "Allowed: %s. Response preview: %.200s",
        allowed_verdicts,
        response,
    )

    followup_prompt = (
        f"{original_prompt}\n\n"
        f"--- Your previous response ---\n{response}\n"
        f"--- End of previous response ---\n\n"
        f"Your response is missing a required VERDICT: line. "
        f"Provide ONLY your verdict block now:\n\n"
        f"VERDICT:<{'|'.join(allowed_verdicts)}>\n"
        f"REASONING:<1-3 sentences>\n\n"
        f"Do not repeat your full analysis."
    )

    retry_response = invoke_fn(followup_prompt, **invoke_kwargs)

    if "VERDICT:" in retry_response:
        return f"{response}\n\n{retry_response}"

    logger.warning(
        "VERDICT re-prompt also produced no VERDICT: — falling back to injection. "
        "Retry preview: %.200s",
        retry_response,
    )
    return format_verdict_feedback(response)
