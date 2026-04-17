"""End-to-end integration tests for Variant B.

Strategy: mock `single_query` (pre-debate phases + final synthesizer) and
`AgentSession` (debate sessions) at the nodes boundary. The graph runs the
real routing logic.

Focus:
  - full run produces all artifacts + debate transcript + summary
  - mutual agreement terminates before max rounds
  - max_rounds terminates when neither side agrees
  - close_all fires on exception
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langgraph_agents.pipeline.config import RunConfig, models_all
from langgraph_agents.pipeline.variant_b import registry
from langgraph_agents.pipeline.variant_b.graph import (
    build_variant_b_graph,
    run_variant_b,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    registry._reset_for_tests()
    yield
    registry._reset_for_tests()


def _pre_debate_router(prompt: str) -> tuple[str, float]:
    if "challenger reviewer" in prompt:
        return "CRIT-CH", 0.01
    if "builder reviewer" in prompt:
        return "CRIT-BU", 0.02
    if "revising your earlier draft" in prompt:
        return "REVISED", 0.03
    if "Two AI reviewers" in prompt:
        return "FINAL", 0.5
    return "DRAFT", 0.1  # generators


def _patch_pre_debate_single_query():
    async def fake(system_prompt, _user_message, **_kwargs):
        return _pre_debate_router(system_prompt)

    # Same underlying single_query is used by Variant A nodes and by the
    # Variant-B synthesize step, so one patch covers both.
    return patch("langgraph_agents.pipeline.variant_a.nodes.single_query", fake), patch(
        "langgraph_agents.pipeline.variant_b.nodes.single_query", fake
    )


def _make_session_factory(responses_per_session: dict[str, list[tuple[str, float]]]):
    """Return a factory that hands out MagicMock sessions whose start/send
    pop from the named response queue."""

    def factory(name, **_kwargs):
        session = MagicMock()

        async def start(_message):
            return responses_per_session[name].pop(0)

        async def send(_message):
            return responses_per_session[name].pop(0)

        session.start = AsyncMock(side_effect=start)
        session.send = AsyncMock(side_effect=send)
        session.close = AsyncMock()
        return session

    return factory


@pytest.fixture
def cfg(tmp_path) -> RunConfig:
    return RunConfig(
        variant="B",
        models=models_all("opus"),
        chatroom_dir=str(tmp_path),
        task="the task",
        run_id="rid-b-int",
        max_debate_rounds=3,
        random_seed=1,
    )


class TestGraphStructure:
    def test_compiles(self, cfg):
        graph = build_variant_b_graph(cfg)
        assert graph.compile() is not None

    def test_nodes_registered(self, cfg):
        graph = build_variant_b_graph(cfg)
        expected = {
            "start_run",
            "generate_left",
            "generate_right",
            "cross_review_left",
            "cross_review_right",
            "revise_left",
            "revise_right",
            "init_debate",
            "debate_turn",
            "compact",
            "record_termination",
            "synthesize_with_debate",
        }
        assert expected.issubset(set(graph.nodes.keys()))


class TestEndToEndMutualAgreement:
    def test_mutual_agreement_terminates_early(self, cfg):
        """Debate stops as soon as both sides AGREE on their most recent turn."""
        # Turn 1 (L opens): DISAGREE; Turn 2 (R opens): DISAGREE
        # Turn 3 (L): AGREE; Turn 4 (R): AGREE → mutual_agreement fires.
        responses = {
            "left": [
                ("open-L\nSTANCE: DISAGREE\nKEY_POINT: alpha", 0.2),
                ("reply-L\nSTANCE: AGREE\nKEY_POINT: alpha", 0.2),
            ],
            "right": [
                ("open-R\nSTANCE: DISAGREE\nKEY_POINT: beta", 0.2),
                ("reply-R\nSTANCE: AGREE\nKEY_POINT: beta", 0.2),
            ],
        }
        factory = _make_session_factory(responses)
        pre_patch, synth_patch = _patch_pre_debate_single_query()
        with pre_patch, synth_patch, patch(
            "langgraph_agents.pipeline.variant_b.nodes.AgentSession",
            side_effect=factory,
        ):
            result = asyncio.run(run_variant_b(cfg))

        assert result.termination_reason == "mutual_agreement"
        run_dir = Path(cfg.chatroom_dir) / cfg.run_id
        for name in (
            "config.json",
            "task.md",
            "left_draft_v1.md",
            "right_draft_v1.md",
            "left_critique_of_right.md",
            "right_critique_of_left.md",
            "left_draft_v2.md",
            "right_draft_v2.md",
            "debate_transcript.md",
            "final_plan.md",
            "summary.json",
        ):
            assert (run_dir / name).is_file(), f"missing artifact: {name}"
        assert result.final_plan == "FINAL"

        # close_all must have been called — registry is empty.
        assert registry.active_run_ids() == []


class TestEndToEndMaxRounds:
    def test_max_rounds_terminates_when_no_agreement(self, cfg):
        """With every turn DISAGREE and a genuinely distinct key_point each
        turn, stable_disagreement cannot trigger, so we must hit max_rounds.
        """
        import uuid

        def disagree(tag: str) -> tuple[str, float]:
            # uuid4 hex is long and unique — defeats the token-overlap heuristic.
            return (
                f"msg\nSTANCE: DISAGREE\nKEY_POINT: {uuid.uuid4().hex} {tag}",
                0.1,
            )

        responses = {
            "left": [disagree(f"L-{i}") for i in range(10)],
            "right": [disagree(f"R-{i}") for i in range(10)],
        }
        factory = _make_session_factory(responses)
        pre_patch, synth_patch = _patch_pre_debate_single_query()
        with pre_patch, synth_patch, patch(
            "langgraph_agents.pipeline.variant_b.nodes.AgentSession",
            side_effect=factory,
        ):
            result = asyncio.run(run_variant_b(cfg))
        assert result.termination_reason == "max_rounds"


class TestCleanupOnException:
    def test_close_all_fires_even_on_failure(self, cfg):
        """If init_debate raises, run_variant_b must still clean up any
        already-registered sessions."""
        closed: list[str] = []

        class _BoomSession:
            def __init__(self, name, **_kwargs):
                self.name = name
                registry.register(cfg.run_id, name, self)
                if name == "right":
                    raise RuntimeError("simulated SDK startup failure")

            async def start(self, _msg):
                return "x", 0.0

            async def send(self, _msg):
                return "x", 0.0

            async def close(self):
                closed.append(self.name)

        pre_patch, synth_patch = _patch_pre_debate_single_query()
        with pre_patch, synth_patch, patch(
            "langgraph_agents.pipeline.variant_b.nodes.AgentSession",
            side_effect=_BoomSession,
        ):
            with pytest.raises(Exception):
                asyncio.run(run_variant_b(cfg))

        # The first session was registered before the failure; close_all must
        # have been invoked and emptied the registry.
        assert registry.active_run_ids() == []
        assert "left" in closed
