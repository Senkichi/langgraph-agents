"""Tests for pairwise judging — parsing, position bias, multi-judge."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from langgraph_agents.eval import judge_pairwise as jp


def _judge_text(pref: str, conf: str = "medium", reasoning: str = "ok") -> str:
    return (
        "some preamble\n\n"
        f"PREFERENCE: {pref}\n"
        f"CONFIDENCE: {conf}\n"
        f"REASONING: {reasoning}\n"
    )


class TestParseJudgement:
    def test_basic_parse(self):
        v = jp.parse_judgement(_judge_text("X", "high"), judge_model="m", swapped=False)
        assert v.preference == "X"
        assert v.confidence == "high"
        assert v.reasoning.startswith("ok")

    def test_tie_preference(self):
        v = jp.parse_judgement(_judge_text("TIE"), judge_model="m", swapped=False)
        assert v.preference == "TIE"

    def test_unparseable_when_missing(self):
        v = jp.parse_judgement("no fields here", judge_model="m", swapped=False)
        assert v.preference == "UNPARSEABLE"
        assert v.confidence == "unknown"

    def test_invalid_preference_is_unparseable(self):
        v = jp.parse_judgement(
            "PREFERENCE: maybe\nCONFIDENCE: high\nREASONING: x",
            judge_model="m",
            swapped=False,
        )
        assert v.preference == "UNPARSEABLE"

    def test_case_insensitive_tags(self):
        text = "preference: Y\nconfidence: LOW\nreasoning: because"
        v = jp.parse_judgement(text, judge_model="m", swapped=False)
        assert v.preference == "Y"
        assert v.confidence == "low"


class TestCollapseVotes:
    def _vote(self, pref, conf="medium", swapped=False):
        return jp.JudgeVote(
            preference=pref, confidence=conf, reasoning="",
            judge_model="m", swapped=swapped,
        )

    def test_consistent_x_then_y_means_a_wins(self):
        """Natural: X means A wins. Swapped: Y means A wins (because X=B when swapped)."""
        votes = (self._vote("X", swapped=False), self._vote("Y", swapped=True))
        preferred, _, _, bias = jp._collapse_votes(votes, config_a="A", config_b="B")
        assert preferred == "A"
        assert bias is False

    def test_flip_means_position_bias(self):
        """Both votes say X — but X is A in one order, B in the other → flip."""
        votes = (self._vote("X", swapped=False), self._vote("X", swapped=True))
        preferred, _, _, bias = jp._collapse_votes(votes, config_a="A", config_b="B")
        assert bias is True
        assert preferred == "tie"

    def test_tie_and_non_tie_trusts_non_tie(self):
        votes = (self._vote("TIE", swapped=False), self._vote("X", swapped=True))
        preferred, _, _, bias = jp._collapse_votes(votes, config_a="A", config_b="B")
        # Non-tie vote says X when swapped → B wins.
        assert preferred == "B"
        assert bias is False

    def test_both_tie(self):
        votes = (self._vote("TIE", swapped=False), self._vote("TIE", swapped=True))
        preferred, _, _, bias = jp._collapse_votes(votes, config_a="A", config_b="B")
        assert preferred == "tie"
        assert bias is False


class TestJudgePairWithPositionCheck:
    def test_happy_path_no_bias(self):
        responses = [
            _judge_text("X", "high"),   # natural order: X means A wins
            _judge_text("Y", "medium"),  # swapped order: Y means A wins
        ]
        mock = AsyncMock(side_effect=[(r, 0.0) for r in responses])
        with patch("langgraph_agents.eval.judge_pairwise.single_query", mock):
            outcome = asyncio.run(
                jp.judge_pair_with_position_check(
                    task_id="t1",
                    task_body="do it",
                    response_a="A_resp",
                    response_b="B_resp",
                    config_a="A",
                    config_b="B",
                    judge_model="opus",
                    cwd="/tmp",
                )
            )
        assert outcome.preferred == "A"
        assert outcome.position_bias_detected is False
        assert outcome.confidence_natural == "high"
        assert outcome.confidence_swapped == "medium"

    def test_position_bias_flagged(self):
        # Judge picks X in both orders — same position regardless of content.
        responses = [_judge_text("X"), _judge_text("X")]
        mock = AsyncMock(side_effect=[(r, 0.0) for r in responses])
        with patch("langgraph_agents.eval.judge_pairwise.single_query", mock):
            outcome = asyncio.run(
                jp.judge_pair_with_position_check(
                    task_id="t1",
                    task_body="do it",
                    response_a="A_resp",
                    response_b="B_resp",
                    config_a="A",
                    config_b="B",
                    judge_model="opus",
                    cwd="/tmp",
                )
            )
        assert outcome.position_bias_detected is True
        assert outcome.preferred == "tie"


class TestJudgeMulti:
    def test_runs_each_judge(self):
        # Two judges, two orders each = 4 LLM calls.
        responses = [
            _judge_text("X"), _judge_text("Y"),  # judge 1
            _judge_text("X"), _judge_text("X"),  # judge 2 (position bias)
        ]
        mock = AsyncMock(side_effect=[(r, 0.0) for r in responses])
        with patch("langgraph_agents.eval.judge_pairwise.single_query", mock):
            outcomes = asyncio.run(
                jp.judge_multi(
                    task_id="t1",
                    task_body="do it",
                    response_a="A_resp",
                    response_b="B_resp",
                    config_a="A",
                    config_b="B",
                    judge_models=["j1", "j2"],
                    cwd="/tmp",
                )
            )
        assert len(outcomes) == 2
        assert outcomes[0].preferred == "A"
        assert outcomes[1].position_bias_detected is True


class TestJudgeSingleDispatch:
    """``judge_single`` routes Claude IDs through ``single_query`` and OpenAI-
    compatible IDs through ``query_openai_compatible``. The two paths must not
    bleed into each other — patching one and exercising the other model class
    confirms the dispatch is doing real work.
    """

    def test_claude_id_uses_single_query_not_openai(self):
        single_q_mock = AsyncMock(return_value=(_judge_text("X"), 0.0))
        openai_mock = AsyncMock(return_value=_judge_text("Y"))
        with (
            patch("langgraph_agents.eval.judge_pairwise.single_query", single_q_mock),
            patch("langgraph_agents.eval.judge_pairwise.query_openai_compatible", openai_mock),
        ):
            asyncio.run(
                jp.judge_single(
                    task="t", response_x="x", response_y="y",
                    judge_model="claude-opus-4-7", cwd="/tmp", swapped=False,
                )
            )
        assert single_q_mock.await_count == 1
        assert openai_mock.await_count == 0

    def test_deepseek_id_uses_openai_compatible_not_single_query(self):
        single_q_mock = AsyncMock(return_value=(_judge_text("X"), 0.0))
        openai_mock = AsyncMock(return_value=_judge_text("Y"))
        with (
            patch("langgraph_agents.eval.judge_pairwise.single_query", single_q_mock),
            patch("langgraph_agents.eval.judge_pairwise.query_openai_compatible", openai_mock),
        ):
            vote = asyncio.run(
                jp.judge_single(
                    task="t", response_x="x", response_y="y",
                    judge_model="deepseek-v4-pro", cwd="/tmp", swapped=False,
                )
            )
        assert openai_mock.await_count == 1
        assert single_q_mock.await_count == 0
        assert vote.preference == "Y"

    def test_gpt_id_uses_openai_compatible(self):
        openai_mock = AsyncMock(return_value=_judge_text("X"))
        with patch("langgraph_agents.eval.judge_pairwise.query_openai_compatible", openai_mock):
            asyncio.run(
                jp.judge_single(
                    task="t", response_x="x", response_y="y",
                    judge_model="gpt-4o-2024-11-20", cwd="/tmp", swapped=False,
                )
            )
        assert openai_mock.await_count == 1
