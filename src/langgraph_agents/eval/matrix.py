"""Matrix runner: execute every (configuration, task) pair.

A ``Configuration`` is a named recipe — variant + model pairing +
variant-specific overrides. The matrix runner turns it into a ``RunConfig``
for each task, dispatches through the right ``run_variant_*`` entry point,
and writes artifacts into ``<output_dir>/<config_id>/<task_id>/``.

Key resilience properties:
  - Resume-on-crash: ``has_completed`` skips runs whose ``summary.json`` is
    already present. A crashed run simply never wrote ``summary.json`` and
    will be redone.
  - Parallelism is bounded by ``asyncio.Semaphore``. Claude Code is CPU-bound
    on a local machine; 2-3 concurrent runs is the sensible starting point.
  - Per-run exceptions are captured as ``MatrixResult`` rows with
    ``status="error"`` — one failing configuration does not abort the matrix.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Literal

from langgraph_agents.pipeline.artifacts import has_completed, load_summary
from langgraph_agents.pipeline.config import ModelConfig, RunConfig, RunResult
from langgraph_agents.pipeline.variant_a.graph import run_variant_a
from langgraph_agents.pipeline.variant_b.graph import run_variant_b

from .corpus import Task

logger = logging.getLogger(__name__)

Variant = Literal["A", "B"]

VariantRunner = Callable[[RunConfig], Awaitable[RunResult]]
_VARIANT_RUNNERS: dict[Variant, VariantRunner] = {
    "A": run_variant_a,
    "B": run_variant_b,
}


@dataclass(frozen=True)
class Configuration:
    """A named recipe — variant, model pairing, and RunConfig overrides."""

    id: str
    variant: Variant
    models: ModelConfig
    overrides: dict[str, Any] = field(default_factory=dict)

    def to_run_config(
        self,
        task: Task,
        *,
        chatroom_dir: str,
        run_id: str | None = None,
    ) -> RunConfig:
        """Render this configuration into a full ``RunConfig`` for ``task``."""
        rid = run_id or f"{self.id}__{task.id}"
        return RunConfig(
            variant=self.variant,
            models=self.models,
            chatroom_dir=chatroom_dir,
            task=task.body,
            run_id=rid,
            **self.overrides,
        )


@dataclass(frozen=True)
class MatrixResult:
    config_id: str
    task_id: str
    run_id: str
    status: Literal["ok", "skipped", "error"]
    result: RunResult | None = None
    error: str | None = None
    artifacts_dir: str | None = None


def _default_runner(config: RunConfig) -> Awaitable[RunResult]:
    runner = _VARIANT_RUNNERS.get(config.variant)
    if runner is None:
        raise ValueError(f"Unknown variant: {config.variant}")
    return runner(config)


async def run_matrix(
    tasks: Iterable[Task],
    configurations: Iterable[Configuration],
    output_dir: Path | str,
    *,
    parallel: int = 2,
    runner: Callable[[RunConfig], Awaitable[RunResult]] | None = None,
    resume: bool = True,
) -> list[MatrixResult]:
    """Run every (configuration, task) pair and return a list of ``MatrixResult``.

    ``runner`` is the function dispatched per run — defaults to the
    variant-aware default. Injection exists so tests can exercise the runner
    without spinning up the pipelines.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    dispatch = runner if runner is not None else _default_runner
    semaphore = asyncio.Semaphore(max(1, int(parallel)))

    async def one_run(task: Task, cfg: Configuration) -> MatrixResult:
        run_id = f"{cfg.id}__{task.id}"
        chatroom_dir = str(output_dir / cfg.id)
        Path(chatroom_dir).mkdir(parents=True, exist_ok=True)
        run_config = cfg.to_run_config(task, chatroom_dir=chatroom_dir, run_id=run_id)
        artifacts_dir = str(Path(chatroom_dir) / run_id)

        if resume and has_completed(chatroom_dir, run_id):
            logger.info("matrix: skipping already-complete run %s", run_id)
            return MatrixResult(
                config_id=cfg.id,
                task_id=task.id,
                run_id=run_id,
                status="skipped",
                artifacts_dir=artifacts_dir,
            )

        async with semaphore:
            try:
                result = await dispatch(run_config)
                return MatrixResult(
                    config_id=cfg.id,
                    task_id=task.id,
                    run_id=run_id,
                    status="ok",
                    result=result,
                    artifacts_dir=artifacts_dir,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("matrix: run %s failed", run_id)
                return MatrixResult(
                    config_id=cfg.id,
                    task_id=task.id,
                    run_id=run_id,
                    status="error",
                    error=f"{type(exc).__name__}: {exc}",
                    artifacts_dir=artifacts_dir,
                )

    jobs = [one_run(task, cfg) for task in tasks for cfg in configurations]
    return await asyncio.gather(*jobs)


def default_configurations() -> list[Configuration]:
    """Opinionated starting matrix: 6 homogeneous + 4 heterogeneous = 10 configs.

    Edit freely in your own eval harness. This is only the plan's suggested
    baseline so ``run_matrix`` has a sensible default.
    """
    from langgraph_agents.pipeline.config import models_all, models_split

    opus47 = "claude-opus-4-7"
    opus46 = "claude-opus-4-6"
    sonnet = "claude-sonnet-4-6"

    configs: list[Configuration] = []
    for label, variant in (("A", "A"), ("B", "B")):
        for model_label, model in (("opus47", opus47), ("opus46", opus46), ("sonnet", sonnet)):
            configs.append(
                Configuration(
                    id=f"{label}-homo-{model_label}",
                    variant=variant,  # type: ignore[arg-type]
                    models=models_all(model),
                )
            )
    for label, variant in (("A", "A"), ("B", "B")):
        configs.append(
            Configuration(
                id=f"{label}-het-opus47-sonnet",
                variant=variant,  # type: ignore[arg-type]
                models=models_split(opus47, sonnet),
            )
        )
        configs.append(
            Configuration(
                id=f"{label}-het-opus47-opus46",
                variant=variant,  # type: ignore[arg-type]
                models=models_split(opus47, opus46),
            )
        )
    return configs


def load_matrix_summaries(
    output_dir: Path | str,
    configurations: Iterable[Configuration],
    tasks: Iterable[Task],
) -> dict[tuple[str, str], dict]:
    """Load ``summary.json`` for every (config, task) pair that has one.

    Returns a dict keyed by ``(config_id, task_id)`` — missing keys indicate
    the run never completed. Useful for report / metrics passes.
    """
    output_dir = Path(output_dir)
    out: dict[tuple[str, str], dict] = {}
    for cfg in configurations:
        chatroom_dir = str(output_dir / cfg.id)
        for task in tasks:
            run_id = f"{cfg.id}__{task.id}"
            if has_completed(chatroom_dir, run_id):
                try:
                    out[(cfg.id, task.id)] = load_summary(chatroom_dir, run_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("failed to load summary for %s: %s", run_id, exc)
    return out
