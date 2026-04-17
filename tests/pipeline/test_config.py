"""Tests for pipeline.config dataclasses and helper constructors."""

from __future__ import annotations

import json

import pytest

from langgraph_agents.pipeline.config import (
    ModelConfig,
    RunConfig,
    RunResult,
    models_all,
    models_split,
)


class TestModelConfig:
    def test_all_roles_required(self):
        cfg = ModelConfig(
            generator_left="A",
            generator_right="B",
            critic_left="A",
            critic_right="B",
            reviser_left="A",
            reviser_right="B",
            synthesizer="J",
        )
        assert cfg.debater_left is None and cfg.debater_right is None
        assert cfg.to_dict()["synthesizer"] == "J"

    def test_frozen(self):
        cfg = models_all("m")
        with pytest.raises(dataclasses_frozen_error()):
            cfg.generator_left = "other"  # type: ignore[misc]


def dataclasses_frozen_error():
    # FrozenInstanceError is a subclass of AttributeError; match on either.
    import dataclasses

    return dataclasses.FrozenInstanceError


class TestHelpers:
    def test_models_all_homogeneous(self):
        cfg = models_all("opus")
        d = cfg.to_dict()
        assert all(v == "opus" for v in d.values() if v is not None)
        assert cfg.debater_left == "opus" and cfg.debater_right == "opus"

    def test_models_all_no_debaters(self):
        cfg = models_all("sonnet", include_debaters=False)
        assert cfg.debater_left is None and cfg.debater_right is None
        assert cfg.synthesizer == "sonnet"

    def test_models_split_asymmetric(self):
        cfg = models_split("opus", "sonnet")
        assert cfg.generator_left == "opus" and cfg.generator_right == "sonnet"
        assert cfg.critic_left == "opus" and cfg.critic_right == "sonnet"
        assert cfg.synthesizer == "opus"  # default = left

    def test_models_split_explicit_synthesizer(self):
        cfg = models_split("opus", "sonnet", synthesizer="haiku")
        assert cfg.synthesizer == "haiku"


class TestRunConfig:
    def _make(self, **overrides) -> RunConfig:
        base = dict(
            variant="A",
            models=models_all("opus"),
            chatroom_dir="/tmp/chatroom",
            task="test task",
            run_id="run-001",
        )
        base.update(overrides)
        return RunConfig(**base)

    def test_to_dict_roundtrip(self):
        cfg = self._make()
        d = cfg.to_dict()
        assert d["variant"] == "A"
        assert d["models"]["generator_left"] == "opus"
        assert d["max_total_cost_usd"] == 20.0
        assert d["max_wall_clock_seconds"] == 1800

    def test_to_json_is_valid_json(self):
        cfg = self._make(random_seed=42)
        parsed = json.loads(cfg.to_json())
        assert parsed["random_seed"] == 42

    def test_variant_b_defaults(self):
        cfg = self._make(variant="B")
        assert cfg.max_debate_rounds == 3
        assert cfg.anonymize_in_debate is True
        assert cfg.soft_compact_threshold_tokens == 20_000


class TestRunResult:
    def test_summary_json_embeds_config(self):
        cfg = RunConfig(
            variant="A",
            models=models_all("opus"),
            chatroom_dir="/tmp/chatroom",
            task="t",
            run_id="rid",
        )
        result = RunResult(
            variant="A",
            run_id="rid",
            final_plan="plan text",
            total_cost_usd=1.25,
            wall_clock_seconds=42.0,
            termination_reason="complete",
            artifacts_dir="/tmp/chatroom/rid",
            config=cfg,
        )
        parsed = json.loads(result.to_json())
        assert parsed["config"]["run_id"] == "rid"
        assert parsed["total_cost_usd"] == 1.25
        assert parsed["final_plan"] == "plan text"
