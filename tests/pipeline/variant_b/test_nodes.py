"""Unit tests for Variant B debate-phase nodes.

AgentSession is replaced at the module boundary so the SDK is never exercised.
Each node's contract is checked in isolation: what it writes to state, what it
calls on the session, what reducer signal it emits.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langgraph_agents.pipeline.config import RunConfig, models_all
from langgraph_agents.pipeline.variant_b import nodes as b_nodes
from langgraph_agents.pipeline.variant_b import registry


@pytest.fixture(autouse=True)
def _clean_registry():
    registry._reset_for_tests()
    yield
    registry._reset_for_tests()


@pytest.fixture
def cfg(tmp_path) -> RunConfig:
    return RunConfig(
        variant="B",
        models=models_all("opus"),
        chatroom_dir=str(tmp_path),
        task="the task",
        run_id="rid-b",
        max_debate_rounds=3,
        random_seed=7,
    )


def _base_state(cfg: RunConfig, **overrides):
    state = {
        "task": cfg.task,
        "chatroom_dir": cfg.chatroom_dir,
        "run_id": cfg.run_id,
        "total_cost_usd": 0.0,
        "max_total_cost_usd": cfg.max_total_cost_usd,
        "max_wall_clock_seconds": cfg.max_wall_clock_seconds,
        "run_start_time": datetime.now(timezone.utc).isoformat(),
        "anonymize_in_debate": cfg.anonymize_in_debate,
        "transcript": [],
        "transcript_token_estimate": 0,
        "turn_count": 0,
        "round_count": 0,
        "compaction_count": 0,
        "left_signaled_agreement": False,
        "right_signaled_agreement": False,
        "debate_sessions_initialized": False,
    }
    state.update(overrides)
    return state


def _make_session_mock(response: str, cost: float) -> MagicMock:
    s = MagicMock()
    s.start = AsyncMock(return_value=(response, cost))
    s.send = AsyncMock(return_value=(response, cost))
    s.close = AsyncMock()
    return s


class TestInitDebate:
    def test_registers_both_sessions_and_produces_openings(self, cfg):
        state = _base_state(
            cfg,
            left_draft_v2="LEFT_V2",
            right_draft_v2="RIGHT_V2",
        )
        left_session = _make_session_mock("OPEN-L\nSTANCE: DISAGREE\nKEY_POINT: foo", 0.2)
        right_session = _make_session_mock("OPEN-R\nSTANCE: DISAGREE\nKEY_POINT: bar", 0.3)

        def make_session(name, **_kwargs):
            return left_session if name == "left" else right_session

        with patch(
            "langgraph_agents.pipeline.variant_b.nodes.AgentSession",
            side_effect=make_session,
        ):
            delta = asyncio.run(b_nodes.init_debate(state, config=cfg))

        left_session.start.assert_awaited_once()
        right_session.start.assert_awaited_once()
        assert registry.get(cfg.run_id, "left") is left_session
        assert registry.get(cfg.run_id, "right") is right_session

        assert delta["debate_sessions_initialized"] is True
        assert len(delta["transcript"]) == 2
        # Both opening stances recognised
        assert delta["transcript"][0]["stance"] == "DISAGREE"
        assert delta["transcript"][1]["stance"] == "DISAGREE"
        assert delta["turn_count"] == 2
        assert delta["round_count"] == 1
        assert delta["total_cost_usd"] == pytest.approx(0.5)
        assert delta["current_speaker"] == "left"

    def test_falls_back_to_v1_drafts_when_v2_absent(self, cfg):
        """Defensive: budget blown before revise → v2 missing → use v1.

        Drafts live in the opening USER message (not the system prompt) to
        stay under Windows CreateProcess arg limits; the v1 fallback must
        reach that message.
        """
        state = _base_state(
            cfg,
            left_draft_v1="LEFT_V1",
            right_draft_v1="RIGHT_V1",
        )
        captured_openings: list[str] = []

        def make_session(name, *, system_prompt, **_kwargs):
            session = _make_session_mock(
                f"body\nSTANCE: DISAGREE\nKEY_POINT: {name}", 0.1
            )
            # Capture the opening user message passed to .start()
            original_start = session.start

            async def capture_start(opening):
                captured_openings.append(opening)
                return await original_start(opening)

            session.start = capture_start
            return session

        with patch(
            "langgraph_agents.pipeline.variant_b.nodes.AgentSession",
            side_effect=make_session,
        ):
            asyncio.run(b_nodes.init_debate(state, config=cfg))

        # Anonymisation renames drafts to "Proposal A / Proposal B" in the
        # opening message, so the raw v1 text must appear in at least one.
        assert any("LEFT_V1" in o for o in captured_openings)
        assert any("RIGHT_V1" in o for o in captured_openings)


class TestDebateTurn:
    def test_alternates_and_appends_single_entry(self, cfg):
        opening = {
            "speaker": "right",
            "content": "opening R",
            "stance": "DISAGREE",
            "key_point": "k",
            "turn": 2,
            "round": 1,
        }
        state = _base_state(
            cfg,
            current_speaker="left",
            transcript=[opening],
            turn_count=2,
            round_count=1,
        )
        left_session = _make_session_mock(
            "reply L\nSTANCE: DISAGREE\nKEY_POINT: left-crux", 0.05
        )
        registry.register(cfg.run_id, "left", left_session)
        registry.register(cfg.run_id, "right", _make_session_mock("x", 0.0))

        delta = asyncio.run(b_nodes.debate_turn(state, config=cfg))

        # The speaker's session got the send, and the other's message was in the prompt.
        left_session.send.assert_awaited_once()
        sent_prompt = left_session.send.await_args.args[0]
        assert "opening R" in sent_prompt

        assert delta["current_speaker"] == "right"
        assert delta["turn_count"] == 3
        assert delta["round_count"] == 2  # turns 3-4 form round 2
        assert len(delta["transcript"]) == 1
        new_entry = delta["transcript"][0]
        assert new_entry["stance"] == "DISAGREE"
        assert new_entry["speaker"] == "left"
        assert delta["left_signaled_agreement"] is False
        assert delta["total_cost_usd"] == 0.05

    def test_agree_stance_flips_agreement_flag(self, cfg):
        opening = {
            "speaker": "left",
            "content": "x",
            "stance": "AGREE",
            "key_point": "k",
            "turn": 1,
            "round": 1,
        }
        state = _base_state(
            cfg,
            current_speaker="right",
            transcript=[opening],
            turn_count=2,
            round_count=1,
        )
        registry.register(cfg.run_id, "left", _make_session_mock("x", 0.0))
        right_session = _make_session_mock(
            "body\nSTANCE: AGREE\nKEY_POINT: agreeing now", 0.01
        )
        registry.register(cfg.run_id, "right", right_session)

        delta = asyncio.run(b_nodes.debate_turn(state, config=cfg))
        assert delta["right_signaled_agreement"] is True

    def test_raises_when_opponent_has_no_prior_message(self, cfg):
        state = _base_state(cfg, current_speaker="left", transcript=[])
        registry.register(cfg.run_id, "left", _make_session_mock("x", 0.0))
        registry.register(cfg.run_id, "right", _make_session_mock("x", 0.0))
        with pytest.raises(RuntimeError, match="no prior message"):
            asyncio.run(b_nodes.debate_turn(state, config=cfg))


class TestCompact:
    def test_summarises_both_sides_and_resets_estimate(self, cfg):
        state = _base_state(
            cfg,
            transcript=[{"speaker": "left", "content": "x"}],
            transcript_token_estimate=25_000,
            compaction_count=0,
            turn_count=6,
            round_count=3,
        )
        left_session = _make_session_mock("summary-L", 0.05)
        right_session = _make_session_mock("summary-R", 0.07)
        registry.register(cfg.run_id, "left", left_session)
        registry.register(cfg.run_id, "right", right_session)

        delta = asyncio.run(b_nodes.compact(state, config=cfg))
        left_session.send.assert_awaited_once()
        right_session.send.assert_awaited_once()
        assert delta["compaction_count"] == 1
        # Summaries appended as "compaction" speaker entries.
        assert all(e["speaker"] == "compaction" for e in delta["transcript"])
        # Estimate reset to reflect only the compacted summaries.
        assert delta["transcript_token_estimate"] < 25_000
        assert delta["total_cost_usd"] == pytest.approx(0.12)


class TestRecordTermination:
    def _entry(self, speaker, stance, key_point, turn):
        return {"speaker": speaker, "stance": stance, "key_point": key_point, "turn": turn}

    def test_mutual_agreement(self, cfg):
        state = _base_state(
            cfg,
            left_signaled_agreement=True,
            right_signaled_agreement=True,
            round_count=2,
        )
        delta = b_nodes.record_termination(state, config=cfg)
        assert delta["termination_reason"] == "mutual_agreement"

    def test_max_rounds(self, cfg):
        state = _base_state(
            cfg,
            left_signaled_agreement=False,
            right_signaled_agreement=False,
            round_count=cfg.max_debate_rounds,
        )
        delta = b_nodes.record_termination(state, config=cfg)
        assert delta["termination_reason"] == "max_rounds"

    def test_budget_wins_over_agreement(self, cfg):
        state = _base_state(
            cfg,
            left_signaled_agreement=True,
            right_signaled_agreement=True,
            total_cost_usd=999.0,
            max_total_cost_usd=1.0,
        )
        delta = b_nodes.record_termination(state, config=cfg)
        assert delta["termination_reason"] == "cost"

    def test_stable_disagreement_detected(self, cfg):
        transcript = [
            self._entry("left", "DISAGREE", "alpha beta gamma delta", 1),
            self._entry("right", "DISAGREE", "one two three four", 2),
            self._entry("left", "DISAGREE", "alpha beta gamma delta epsilon", 3),
            self._entry("right", "DISAGREE", "one two three four five", 4),
        ]
        state = _base_state(
            cfg,
            transcript=transcript,
            round_count=2,
            left_signaled_agreement=False,
            right_signaled_agreement=False,
        )
        delta = b_nodes.record_termination(state, config=cfg)
        assert delta["termination_reason"] == "stable_disagreement"

    def test_writes_transcript_artifact(self, cfg):
        state = _base_state(
            cfg,
            transcript=[{"speaker": "left", "content": "hi", "turn": 1, "round": 1}],
            round_count=cfg.max_debate_rounds,
        )
        b_nodes.record_termination(state, config=cfg)
        path = Path(cfg.chatroom_dir) / cfg.run_id / "debate_transcript.md"
        assert path.is_file()
        assert "Turn 1" in path.read_text(encoding="utf-8")
