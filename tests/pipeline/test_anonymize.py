"""Tests for anonymisation helpers — key property is reproducibility."""

from __future__ import annotations

import random

from langgraph_agents.pipeline.anonymize import (
    anonymize_for_debate,
    anonymize_pair,
)


class TestAnonymizePair:
    def test_no_shuffle_preserves_order(self):
        a, b, mapping = anonymize_pair("MINE", "THEIRS", shuffle=False)
        assert a == "MINE" and b == "THEIRS"
        assert mapping == {"A": "my", "B": "their"}

    def test_seeded_rng_is_reproducible(self):
        """Same seed produces the same ordering — required for eval reproducibility."""
        rng1 = random.Random(42)
        rng2 = random.Random(42)
        out1 = [anonymize_pair("M", "T", rng=rng1) for _ in range(10)]
        out2 = [anonymize_pair("M", "T", rng=rng2) for _ in range(10)]
        assert out1 == out2

    def test_mapping_always_covers_both_slots(self):
        """Regardless of which side ended up in A, the mapping records both."""
        for seed in range(20):
            rng = random.Random(seed)
            a, b, mapping = anonymize_pair("MINE", "THEIRS", rng=rng)
            owners = {mapping["A"], mapping["B"]}
            assert owners == {"my", "their"}
            texts = {a, b}
            assert texts == {"MINE", "THEIRS"}

    def test_shuffle_eventually_flips(self):
        """Over many draws, both orderings appear — anonymisation isn't stuck."""
        rng = random.Random(0)
        seen: set[tuple[str, str]] = set()
        for _ in range(50):
            a, b, _ = anonymize_pair("MINE", "THEIRS", rng=rng)
            seen.add((a, b))
        assert ("MINE", "THEIRS") in seen
        assert ("THEIRS", "MINE") in seen


class TestAnonymizeForDebate:
    def test_default_labels(self):
        transcript = [
            {"speaker": "left", "content": "opening L"},
            {"speaker": "right", "content": "opening R"},
        ]
        out = anonymize_for_debate(transcript)
        assert "Reviewer 1" in out and "Reviewer 2" in out
        assert "opening L" in out and "opening R" in out
        # Neither raw speaker label leaks through the default mapping.
        assert "left" not in out.lower().replace("left brace", "") or out.count("left") == 0

    def test_custom_mapping(self):
        transcript = [{"speaker": "left", "content": "hello"}]
        out = anonymize_for_debate(transcript, reviewer_name_map={"left": "Proposer"})
        assert "Proposer" in out
        assert "hello" in out

    def test_unknown_speaker_falls_through_for_debuggability(self):
        transcript = [{"speaker": "moderator", "content": "x"}]
        out = anonymize_for_debate(transcript)
        # We deliberately want "moderator" to remain visible rather than being
        # silently mapped to something misleading.
        assert "moderator" in out
