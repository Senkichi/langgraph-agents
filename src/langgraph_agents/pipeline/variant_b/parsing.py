"""Debate-message parsing and the stable-disagreement heuristic.

Each debate turn is required to end with two lines:

    STANCE: <AGREE | DISAGREE | AGREE_WITH_MODIFICATION>
    KEY_POINT: <one-sentence crux of the current position>

Parsing is tolerant of the LLM straying on whitespace or capitalisation but
strict about the tag name itself — missing/unknown STANCE is reported as
``None`` rather than guessed at.

``stable_disagreement`` compares the last two key_points per speaker. If both
speakers produced near-identical cruxes two turns running AND at least one of
them is currently DISAGREEing, we treat the debate as stalled. The similarity
metric is Jaccard over whitespace-tokenised lowercase words — crude but
adequate at this stage; a noisier metric only matters once we see real data.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

logger = logging.getLogger(__name__)

Stance = Literal["AGREE", "DISAGREE", "AGREE_WITH_MODIFICATION"]

_VALID_STANCES: frozenset[str] = frozenset(
    {"AGREE", "DISAGREE", "AGREE_WITH_MODIFICATION"}
)

_STANCE_RE = re.compile(r"^\s*STANCE\s*:\s*(\S.*?)\s*$", re.IGNORECASE | re.MULTILINE)
_KEY_POINT_RE = re.compile(r"^\s*KEY_POINT\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


def parse_stance(text: str) -> Stance | None:
    """Return the last valid STANCE token in ``text``, or ``None`` if absent.

    We take the last match rather than the first so a preceding ``STANCE:``
    embedded in quoted reasoning doesn't override the mandatory footer.
    """
    matches = _STANCE_RE.findall(text or "")
    for raw in reversed(matches):
        token = raw.strip().upper().rstrip(".")
        if token in _VALID_STANCES:
            return token  # type: ignore[return-value]
    return None


def parse_key_point(text: str) -> str | None:
    """Return the last KEY_POINT content line in ``text``, or ``None`` if absent."""
    matches = _KEY_POINT_RE.findall(text or "")
    if not matches:
        return None
    return matches[-1].strip()


def _tokenise(text: str) -> set[str]:
    # Lowercase, strip punctuation, drop single-char words (mostly noise).
    words = re.findall(r"[A-Za-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) > 1}


def jaccard(a: str | None, b: str | None) -> float:
    """Token-Jaccard similarity in [0, 1]. Empty strings → 0.0."""
    ta, tb = _tokenise(a or ""), _tokenise(b or "")
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def _last_n_by_speaker(
    transcript: list[dict], speaker: str, n: int
) -> list[dict]:
    return [e for e in transcript if e.get("speaker") == speaker][-n:]


def stable_disagreement(
    transcript: list[dict],
    *,
    similarity_threshold: float = 0.6,
) -> bool:
    """Return True when both speakers have repeated nearly the same key_point.

    Requires at least two turns per speaker. At least one of the most-recent
    stances must be DISAGREE — otherwise the repetition is "we both agreed
    twice" which should route through mutual_agreement, not stall.
    """
    left = _last_n_by_speaker(transcript, "left", 2)
    right = _last_n_by_speaker(transcript, "right", 2)
    if len(left) < 2 or len(right) < 2:
        return False

    left_repeats = jaccard(left[-1].get("key_point"), left[-2].get("key_point")) >= similarity_threshold
    right_repeats = jaccard(right[-1].get("key_point"), right[-2].get("key_point")) >= similarity_threshold
    if not (left_repeats and right_repeats):
        return False

    recent_stances = {left[-1].get("stance"), right[-1].get("stance")}
    return "DISAGREE" in recent_stances


def estimate_tokens(text: str) -> int:
    """Rough char/4 token estimate, matching the existing tracer heuristic."""
    return len(text or "") // 4


def transcript_token_estimate(transcript: list[dict]) -> int:
    """Sum of estimated tokens across all transcript message bodies."""
    return sum(estimate_tokens(e.get("content", "")) for e in transcript)
