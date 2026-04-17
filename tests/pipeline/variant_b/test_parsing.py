"""Tests for STANCE/KEY_POINT parsing and the stable_disagreement heuristic."""

from __future__ import annotations

from langgraph_agents.pipeline.variant_b.parsing import (
    jaccard,
    parse_key_point,
    parse_stance,
    stable_disagreement,
    transcript_token_estimate,
)


class TestParseStance:
    def test_basic_agree(self):
        assert parse_stance("foo\nSTANCE: AGREE\nKEY_POINT: x") == "AGREE"

    def test_disagree(self):
        assert parse_stance("STANCE: DISAGREE") == "DISAGREE"

    def test_agree_with_modification(self):
        assert parse_stance("STANCE: AGREE_WITH_MODIFICATION") == "AGREE_WITH_MODIFICATION"

    def test_case_insensitive_tag_but_canonical_value(self):
        assert parse_stance("stance: agree") == "AGREE"

    def test_ignores_unknown_value(self):
        assert parse_stance("STANCE: something-else") is None

    def test_last_match_wins(self):
        """A STANCE mention inside reasoning must not override the footer."""
        text = (
            "I thought your STANCE: AGREE was odd.\n\n"
            "STANCE: DISAGREE\n"
            "KEY_POINT: the premise fails"
        )
        assert parse_stance(text) == "DISAGREE"

    def test_missing_returns_none(self):
        assert parse_stance("no footer here") is None


class TestParseKeyPoint:
    def test_basic(self):
        assert parse_key_point("STANCE: AGREE\nKEY_POINT: the thesis holds") == "the thesis holds"

    def test_trims_whitespace(self):
        assert parse_key_point("KEY_POINT:    trimmed   ") == "trimmed"

    def test_missing_returns_none(self):
        assert parse_key_point("STANCE: AGREE\n") is None


class TestJaccard:
    def test_identical_strings_are_one(self):
        assert jaccard("the premise fails", "the premise fails") == 1.0

    def test_disjoint_are_zero(self):
        assert jaccard("alpha beta", "gamma delta") == 0.0

    def test_partial_overlap_is_fractional(self):
        # {the, premise, fails} vs {the, premise, holds}
        # intersection=2, union=4 -> 0.5
        assert jaccard("the premise fails", "the premise holds") == 0.5

    def test_empty_handled(self):
        assert jaccard("", "anything") == 0.0
        assert jaccard(None, "anything") == 0.0


class TestStableDisagreement:
    def _entry(self, speaker, stance, key_point, turn):
        return {
            "speaker": speaker,
            "stance": stance,
            "key_point": key_point,
            "turn": turn,
        }

    def test_requires_two_per_speaker(self):
        transcript = [
            self._entry("left", "DISAGREE", "x", 1),
            self._entry("right", "DISAGREE", "x", 2),
        ]
        assert stable_disagreement(transcript) is False

    def test_fires_when_both_speakers_repeat_and_someone_disagrees(self):
        transcript = [
            self._entry("left", "DISAGREE", "the premise fails", 1),
            self._entry("right", "DISAGREE", "the premise holds", 2),
            self._entry("left", "DISAGREE", "the premise fails further", 3),
            self._entry("right", "DISAGREE", "the premise holds strong", 4),
        ]
        assert stable_disagreement(transcript) is True

    def test_not_stalled_when_key_points_diverge(self):
        transcript = [
            self._entry("left", "DISAGREE", "alpha beta gamma", 1),
            self._entry("right", "DISAGREE", "delta epsilon zeta", 2),
            self._entry("left", "DISAGREE", "eta theta iota", 3),  # completely different
            self._entry("right", "DISAGREE", "kappa lambda mu", 4),
        ]
        assert stable_disagreement(transcript) is False

    def test_not_stalled_when_both_currently_agree(self):
        """Repeated AGREE stances should route through mutual_agreement, not stall."""
        transcript = [
            self._entry("left", "AGREE", "happy consensus", 1),
            self._entry("right", "AGREE", "happy consensus", 2),
            self._entry("left", "AGREE", "happy consensus", 3),
            self._entry("right", "AGREE", "happy consensus", 4),
        ]
        assert stable_disagreement(transcript) is False


class TestTranscriptTokenEstimate:
    def test_sums_content_lengths(self):
        transcript = [
            {"content": "a" * 100},  # 25 tokens
            {"content": "b" * 40},   # 10 tokens
        ]
        assert transcript_token_estimate(transcript) == 35

    def test_handles_missing_content(self):
        assert transcript_token_estimate([{"speaker": "left"}]) == 0
