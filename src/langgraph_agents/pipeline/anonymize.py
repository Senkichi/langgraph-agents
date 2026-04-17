"""Identity-anonymisation helpers for cross-review and debate prompts.

Choi et al. (2025) find that "you said" vs "they said" framing drives most of
the identity bias in multi-agent debate. Stripping that framing by renaming
drafts to "Proposal A / Proposal B" and shuffling order eliminates most of the
bias in their setup. Both variants benefit from this; Variant A opts in for
cross-review, Variant B for the debate loop.

Anonymisation must be **reproducible** across eval runs — we therefore route
all random choices through a caller-supplied `random.Random` instance instead
of the process-global RNG.
"""

from __future__ import annotations

import random
from typing import Literal

Owner = Literal["my", "their"]
Slot = Literal["A", "B"]


def anonymize_pair(
    my_draft: str,
    their_draft: str,
    *,
    shuffle: bool = True,
    rng: random.Random | None = None,
) -> tuple[str, str, dict[Slot, Owner]]:
    """Present two drafts as Proposal A and Proposal B in a shuffled order.

    Returns ``(proposal_a_text, proposal_b_text, mapping)`` where ``mapping``
    records which original draft landed in each slot so the caller can
    de-anonymise the judge's response afterwards.

    Pass a seeded ``rng`` when the order must be reproducible (eval runs).
    """
    _rng = rng if rng is not None else random.Random()
    flip = shuffle and _rng.random() < 0.5
    if flip:
        return their_draft, my_draft, {"A": "their", "B": "my"}
    return my_draft, their_draft, {"A": "my", "B": "their"}


def anonymize_for_debate(
    transcript: list[dict],
    *,
    reviewer_name_map: dict[str, str] | None = None,
) -> str:
    """Render a transcript with speaker labels anonymised.

    Expects transcript entries of the shape:
        {"speaker": "left" | "right", "content": str, ...}

    ``reviewer_name_map`` defaults to ``{"left": "Reviewer 1", "right": "Reviewer 2"}``.
    Unknown speakers fall through unchanged so misconfigured entries are
    visible during debugging rather than silently masked.
    """
    mapping = reviewer_name_map if reviewer_name_map is not None else {
        "left": "Reviewer 1",
        "right": "Reviewer 2",
    }
    parts: list[str] = []
    for entry in transcript:
        speaker = entry.get("speaker", "?")
        label = mapping.get(speaker, speaker)
        content = entry.get("content", "")
        parts.append(f"### {label}\n{content}".rstrip())
    return "\n\n".join(parts)
