"""Unit tests for Variant A phase nodes.

Each node is tested by stubbing `single_query` to return a known
`(response, cost)` tuple, then asserting the node:
 1. calls single_query with the right system prompt and model,
 2. writes the right artifact filename with the response body, and
 3. returns a state delta with the right field name and cost.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from langgraph_agents.pipeline.config import RunConfig, models_split
from langgraph_agents.pipeline.prompts import (
    CRITIC_BUILDER,
    CRITIC_CHALLENGER,
    GENERATOR_BASE,
    REVISER_BASE,
)
from langgraph_agents.pipeline.state import VariantAState
from langgraph_agents.pipeline.variant_a import nodes


@pytest.fixture
def config(tmp_path) -> RunConfig:
    return RunConfig(
        variant="A",
        models=models_split("opus-L", "sonnet-R"),
        chatroom_dir=str(tmp_path),
        task="Summarise X",
        run_id="rid",
    )


def _state(config: RunConfig, **overrides) -> VariantAState:
    base: VariantAState = {
        "task": config.task,
        "chatroom_dir": config.chatroom_dir,
        "run_id": config.run_id,
        "total_cost_usd": 0.0,
        "max_total_cost_usd": config.max_total_cost_usd,
        "max_wall_clock_seconds": config.max_wall_clock_seconds,
        "run_start_time": datetime.now(timezone.utc).isoformat(),
    }
    base.update(overrides)
    return base


def _patch_single_query(response: str = "RESP", cost: float = 0.11):
    mock = AsyncMock(return_value=(response, cost))
    return patch("langgraph_agents.pipeline.variant_a.nodes.single_query", mock), mock


class TestStartRun:
    def test_writes_config_and_task_and_stamps_metadata(self, config):
        state = _state(config)
        delta = asyncio.run(nodes.start_run(state, config=config))

        run_dir = Path(config.chatroom_dir) / config.run_id
        assert (run_dir / "config.json").is_file()
        assert (run_dir / "task.md").read_text(encoding="utf-8") == config.task

        assert "run_start_time" in delta
        assert delta["max_total_cost_usd"] == config.max_total_cost_usd
        assert delta["max_wall_clock_seconds"] == config.max_wall_clock_seconds


class TestGenerate:
    def test_generate_left_uses_generator_base_and_left_model(self, config):
        state = _state(config)
        patcher, mock = _patch_single_query("DRAFT-L", 0.2)
        with patcher:
            delta = asyncio.run(nodes.generate_left(state, config=config))
        mock.assert_awaited_once()
        # positional args: system_prompt, user_message
        sys_prompt, user_msg = mock.await_args.args
        assert sys_prompt == GENERATOR_BASE
        assert config.task in user_msg
        assert mock.await_args.kwargs["model"] == "opus-L"

        assert delta == {"left_draft_v1": "DRAFT-L", "total_cost_usd": 0.2}
        artifact = (
            Path(config.chatroom_dir) / config.run_id / "left_draft_v1.md"
        ).read_text(encoding="utf-8")
        assert artifact == "DRAFT-L"

    def test_generate_right_uses_right_model_and_writes_own_artifact(self, config):
        state = _state(config)
        patcher, mock = _patch_single_query("DRAFT-R", 0.3)
        with patcher:
            delta = asyncio.run(nodes.generate_right(state, config=config))
        assert mock.await_args.kwargs["model"] == "sonnet-R"
        assert delta == {"right_draft_v1": "DRAFT-R", "total_cost_usd": 0.3}
        assert (
            Path(config.chatroom_dir) / config.run_id / "right_draft_v1.md"
        ).is_file()


class TestCrossReview:
    def test_left_reviews_right_draft_with_challenger_persona(self, config):
        state = _state(
            config,
            right_draft_v1="RIGHT_DRAFT_TEXT",
            left_draft_v1="LEFT_DRAFT_TEXT",
        )
        patcher, mock = _patch_single_query("CRIT-L", 0.05)
        with patcher:
            delta = asyncio.run(nodes.cross_review_left(state, config=config))
        sys_prompt, user_msg = mock.await_args.args
        assert sys_prompt == CRITIC_CHALLENGER
        assert "RIGHT_DRAFT_TEXT" in user_msg
        # Left must NOT critique its own draft here.
        assert "LEFT_DRAFT_TEXT" not in user_msg
        assert mock.await_args.kwargs["model"] == "opus-L"
        assert delta == {"left_critique_of_right": "CRIT-L", "total_cost_usd": 0.05}

    def test_right_reviews_left_draft_with_builder_persona(self, config):
        state = _state(
            config,
            right_draft_v1="RIGHT_DRAFT_TEXT",
            left_draft_v1="LEFT_DRAFT_TEXT",
        )
        patcher, mock = _patch_single_query("CRIT-R", 0.06)
        with patcher:
            delta = asyncio.run(nodes.cross_review_right(state, config=config))
        sys_prompt, user_msg = mock.await_args.args
        assert sys_prompt == CRITIC_BUILDER
        assert "LEFT_DRAFT_TEXT" in user_msg
        assert "RIGHT_DRAFT_TEXT" not in user_msg
        assert mock.await_args.kwargs["model"] == "sonnet-R"
        assert delta == {"right_critique_of_left": "CRIT-R", "total_cost_usd": 0.06}


class TestRevise:
    def test_revise_left_reads_own_draft_and_critique_of_self(self, config):
        state = _state(
            config,
            left_draft_v1="OWN_V1",
            right_critique_of_left="CRITIQUE_OF_ME",
            right_draft_v1="NOT_MINE",
            left_critique_of_right="CRITIQUE_OF_OTHER",
        )
        patcher, mock = _patch_single_query("V2-L", 0.07)
        with patcher:
            delta = asyncio.run(nodes.revise_left(state, config=config))
        sys_prompt, user_msg = mock.await_args.args
        assert sys_prompt == REVISER_BASE
        # Must see own draft and the critique of own draft.
        assert "OWN_V1" in user_msg
        assert "CRITIQUE_OF_ME" in user_msg
        # Must NOT leak the other side's draft or the critique of the other side.
        assert "NOT_MINE" not in user_msg
        assert "CRITIQUE_OF_OTHER" not in user_msg
        assert mock.await_args.kwargs["model"] == "opus-L"
        assert delta == {"left_draft_v2": "V2-L", "total_cost_usd": 0.07}

    def test_revise_right_reads_own_draft_and_critique_of_self(self, config):
        state = _state(
            config,
            right_draft_v1="OWN_V1_R",
            left_critique_of_right="CRITIQUE_OF_R",
            left_draft_v1="OTHER_DRAFT",
            right_critique_of_left="OTHER_CRITIQUE",
        )
        patcher, mock = _patch_single_query("V2-R", 0.08)
        with patcher:
            delta = asyncio.run(nodes.revise_right(state, config=config))
        _, user_msg = mock.await_args.args
        assert "OWN_V1_R" in user_msg and "CRITIQUE_OF_R" in user_msg
        assert "OTHER_DRAFT" not in user_msg and "OTHER_CRITIQUE" not in user_msg
        assert mock.await_args.kwargs["model"] == "sonnet-R"
        assert delta == {"right_draft_v2": "V2-R", "total_cost_usd": 0.08}


class TestSynthesize:
    def test_synthesize_reads_v2_drafts_and_returns_final_plan(self, config):
        state = _state(
            config,
            left_draft_v2="L_FINAL",
            right_draft_v2="R_FINAL",
        )
        patcher, mock = _patch_single_query("SYNTH", 0.5)
        with patcher:
            delta = asyncio.run(nodes.synthesize(state, config=config))
        sys_prompt, user_msg = mock.await_args.args
        # The synthesis template must be populated with an empty debate section
        # in Variant A.
        assert "Two AI reviewers" in sys_prompt
        assert "L_FINAL" in user_msg and "R_FINAL" in user_msg
        assert mock.await_args.kwargs["model"] == config.models.synthesizer
        assert delta["final_plan"] == "SYNTH"
        assert delta["total_cost_usd"] == 0.5
        assert delta["termination_reason"] == "complete"
        assert (
            Path(config.chatroom_dir) / config.run_id / "final_plan.md"
        ).is_file()
