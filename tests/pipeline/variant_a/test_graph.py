"""Integration tests for the Variant A graph.

`single_query` is mocked at the nodes module level. The graph is executed
end-to-end, and we assert:
  - all seven artifacts are produced on disk,
  - the run result carries final_plan, total_cost_usd, termination_reason,
  - summary.json lands in the run dir,
  - a mid-flight budget overrun short-circuits to synthesize.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from langgraph_agents.pipeline.config import RunConfig, models_all
from langgraph_agents.pipeline.variant_a.graph import (
    build_variant_a_graph,
    run_variant_a,
)


def _phase_router(prompt: str) -> tuple[str, float]:
    """Cheap single_query double that varies output by system prompt keywords
    so we can tell phases apart in assertions."""
    if "challenger reviewer" in prompt:
        return "CRIT-CH", 0.01
    if "builder reviewer" in prompt:
        return "CRIT-BU", 0.02
    if "revising your earlier draft" in prompt:
        return "REVISED", 0.03
    if "Two AI reviewers" in prompt:
        return "FINAL", 0.5
    # generator
    return "DRAFT", 0.1


def _patch_single_query():
    async def fake(system_prompt, _user_message, **_kwargs):
        return _phase_router(system_prompt)

    return patch("langgraph_agents.pipeline.variant_a.nodes.single_query", fake)


@pytest.fixture
def cfg(tmp_path) -> RunConfig:
    return RunConfig(
        variant="A",
        models=models_all("opus"),
        chatroom_dir=str(tmp_path),
        task="the task",
        run_id="rid-integration",
    )


class TestGraphStructure:
    def test_graph_compiles(self, cfg):
        graph = build_variant_a_graph(cfg)
        compiled = graph.compile()
        assert compiled is not None

    def test_nodes_registered(self, cfg):
        graph = build_variant_a_graph(cfg)
        expected = {
            "start_run",
            "generate_left",
            "generate_right",
            "cross_review_left",
            "cross_review_right",
            "revise_left",
            "revise_right",
            "synthesize",
        }
        assert expected.issubset(set(graph.nodes.keys()))


class TestEndToEnd:
    def test_full_run_produces_all_artifacts_and_summary(self, cfg):
        with _patch_single_query():
            result = asyncio.run(run_variant_a(cfg))

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
            "final_plan.md",
            "summary.json",
        ):
            assert (run_dir / name).is_file(), f"missing artifact: {name}"

        assert result.final_plan == "FINAL"
        assert result.variant == "A"
        assert result.termination_reason == "complete"
        # Cost = 2 generators (0.1) + 2 reviewers (0.01 + 0.02) + 2 revisers (0.03) + synth (0.5)
        assert result.total_cost_usd == pytest.approx(0.1 + 0.1 + 0.01 + 0.02 + 0.03 + 0.03 + 0.5)
        assert result.wall_clock_seconds >= 0.0

    def test_left_and_right_artifacts_reflect_their_critics(self, cfg):
        """left_critique_of_right.md should be the challenger output (CRIT-CH);
        right_critique_of_left.md should be the builder output (CRIT-BU).

        Guards against a subtle asymmetry-swap bug where both sides use the
        same persona.
        """
        with _patch_single_query():
            asyncio.run(run_variant_a(cfg))
        run_dir = Path(cfg.chatroom_dir) / cfg.run_id
        assert (run_dir / "left_critique_of_right.md").read_text(encoding="utf-8") == "CRIT-CH"
        assert (run_dir / "right_critique_of_left.md").read_text(encoding="utf-8") == "CRIT-BU"


class TestBudgetShortCircuit:
    def test_overrun_during_generation_skips_to_synthesize(self, tmp_path):
        """If the cost cap is already breached after generation, the review
        and revise phases must be skipped — we still emit a final plan and a
        truthful termination_reason."""
        # Cost budget smaller than a single draft: router will short-circuit.
        cfg = RunConfig(
            variant="A",
            models=models_all("opus"),
            chatroom_dir=str(tmp_path),
            task="the task",
            run_id="rid-short",
            max_total_cost_usd=0.05,  # tiny cap; generators cost 0.1 each
        )
        with _patch_single_query():
            result = asyncio.run(run_variant_a(cfg))

        run_dir = Path(cfg.chatroom_dir) / cfg.run_id
        # The v2 drafts must not have been produced because we short-circuited.
        assert not (run_dir / "left_draft_v2.md").exists()
        assert not (run_dir / "right_draft_v2.md").exists()
        # Final plan is still produced (synthesize uses empty-string drafts).
        assert (run_dir / "final_plan.md").is_file()
        assert result.termination_reason == "cost"
