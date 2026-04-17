"""Run-time configuration objects for dual-pipeline runs.

`ModelConfig` captures which model fills each role. `RunConfig` bundles the
model choice with task / budget / variant metadata. `RunResult` is the summary
a completed run writes to disk.

All three are immutable-friendly dataclasses with JSON serialisation helpers;
the eval matrix runner reads/writes them as the handoff format between the
pipeline and the evaluation framework.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from typing import Any, Literal

Variant = Literal["A", "B"]


@dataclass(frozen=True)
class ModelConfig:
    """Which model each role uses. Roles may collide or differ."""

    generator_left: str
    generator_right: str
    critic_left: str
    critic_right: str
    reviser_left: str
    reviser_right: str
    synthesizer: str
    debater_left: str | None = None  # Variant B only
    debater_right: str | None = None  # Variant B only

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class RunConfig:
    """All inputs a single pipeline run needs."""

    variant: Variant
    models: ModelConfig
    chatroom_dir: str
    task: str
    run_id: str

    max_total_cost_usd: float = 20.0
    max_wall_clock_seconds: int = 1800

    # Variant-B-specific (ignored by Variant A)
    max_debate_rounds: int = 3
    soft_compact_threshold_tokens: int = 20_000
    anonymize_in_debate: bool = True

    # Reproducibility for anonymize shuffling etc.
    random_seed: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


@dataclass(frozen=True)
class RunResult:
    """Summary a completed run writes to `<run_dir>/summary.json`."""

    variant: Variant
    run_id: str
    final_plan: str
    total_cost_usd: float
    wall_clock_seconds: float
    termination_reason: str
    artifacts_dir: str
    config: RunConfig

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant": self.variant,
            "run_id": self.run_id,
            "final_plan": self.final_plan,
            "total_cost_usd": self.total_cost_usd,
            "wall_clock_seconds": self.wall_clock_seconds,
            "termination_reason": self.termination_reason,
            "artifacts_dir": self.artifacts_dir,
            "config": self.config.to_dict(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


def models_all(model: str, *, include_debaters: bool = True) -> ModelConfig:
    """Homogeneous config helper — every role uses the same model."""
    debater = model if include_debaters else None
    return ModelConfig(
        generator_left=model,
        generator_right=model,
        critic_left=model,
        critic_right=model,
        reviser_left=model,
        reviser_right=model,
        synthesizer=model,
        debater_left=debater,
        debater_right=debater,
    )


def models_split(left: str, right: str, *, synthesizer: str | None = None,
                 include_debaters: bool = True) -> ModelConfig:
    """Heterogeneous config helper — left-side roles use `left`, right-side use `right`."""
    synth = synthesizer if synthesizer is not None else left
    debater_left = left if include_debaters else None
    debater_right = right if include_debaters else None
    return ModelConfig(
        generator_left=left,
        generator_right=right,
        critic_left=left,
        critic_right=right,
        reviser_left=left,
        reviser_right=right,
        synthesizer=synth,
        debater_left=debater_left,
        debater_right=debater_right,
    )
