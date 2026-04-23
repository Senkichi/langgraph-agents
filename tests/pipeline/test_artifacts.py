"""Tests for pipeline.artifacts — on-disk layout contract."""

from __future__ import annotations

import json
from unittest.mock import patch

from langgraph_agents.pipeline.artifacts import (
    _atomic_write_text,
    has_completed,
    load_artifact,
    load_summary,
    run_dir,
    run_dir_from_state,
    write_artifact,
    write_config,
    write_summary,
    write_task,
)
from langgraph_agents.pipeline.config import (
    RunConfig,
    RunResult,
    models_all,
)


def _make_config(tmp_path) -> RunConfig:
    return RunConfig(
        variant="A",
        models=models_all("opus"),
        chatroom_dir=str(tmp_path),
        task="the task body\nwith newlines",
        run_id="run-test-001",
    )


class TestRunDir:
    def test_creates_missing_dir(self, tmp_path):
        target = run_dir(str(tmp_path), "new-run")
        assert target.is_dir()
        assert target.name == "new-run"

    def test_idempotent(self, tmp_path):
        a = run_dir(str(tmp_path), "r")
        b = run_dir(str(tmp_path), "r")
        assert a == b and a.is_dir()

    def test_from_state(self, tmp_path):
        state = {"chatroom_dir": str(tmp_path), "run_id": "s"}
        assert run_dir_from_state(state).name == "s"


class TestWriteArtifact:
    def test_roundtrip(self, tmp_path):
        state = {"chatroom_dir": str(tmp_path), "run_id": "r"}
        path = write_artifact(state, "left_draft_v1.md", "# Draft\ncontent")
        assert path.read_text(encoding="utf-8") == "# Draft\ncontent"
        assert load_artifact(str(tmp_path), "r", "left_draft_v1.md").startswith("# Draft")

    def test_overwrites(self, tmp_path):
        state = {"chatroom_dir": str(tmp_path), "run_id": "r"}
        write_artifact(state, "x.md", "first")
        write_artifact(state, "x.md", "second")
        assert load_artifact(str(tmp_path), "r", "x.md") == "second"


class TestWriteConfigAndTask:
    def test_config_file_parses_as_json(self, tmp_path):
        cfg = _make_config(tmp_path)
        path = write_config(cfg)
        parsed = json.loads(path.read_text(encoding="utf-8"))
        assert parsed["run_id"] == "run-test-001"
        assert parsed["models"]["generator_left"] == "opus"

    def test_task_file_preserves_body_verbatim(self, tmp_path):
        cfg = _make_config(tmp_path)
        path = write_task(cfg)
        assert path.read_text(encoding="utf-8") == "the task body\nwith newlines"


class TestSummary:
    def test_write_and_load_summary(self, tmp_path):
        cfg = _make_config(tmp_path)
        artifacts_dir = str(run_dir(cfg.chatroom_dir, cfg.run_id))
        result = RunResult(
            variant="A",
            run_id=cfg.run_id,
            final_plan="the final plan",
            total_cost_usd=0.42,
            wall_clock_seconds=12.5,
            termination_reason="complete",
            artifacts_dir=artifacts_dir,
            config=cfg,
        )
        write_summary(result)
        loaded = load_summary(cfg.chatroom_dir, cfg.run_id)
        assert loaded["total_cost_usd"] == 0.42
        assert loaded["termination_reason"] == "complete"
        assert loaded["config"]["variant"] == "A"

    def test_has_completed_reflects_summary_presence(self, tmp_path):
        cfg = _make_config(tmp_path)
        run_dir(cfg.chatroom_dir, cfg.run_id)  # dir exists
        assert has_completed(cfg.chatroom_dir, cfg.run_id) is False

        artifacts_dir = str(run_dir(cfg.chatroom_dir, cfg.run_id))
        result = RunResult(
            variant="A",
            run_id=cfg.run_id,
            final_plan="plan",
            total_cost_usd=0.0,
            wall_clock_seconds=0.0,
            termination_reason="complete",
            artifacts_dir=artifacts_dir,
            config=cfg,
        )
        write_summary(result)
        assert has_completed(cfg.chatroom_dir, cfg.run_id) is True

    def test_summary_captures_environment_by_default(self, tmp_path):
        cfg = _make_config(tmp_path)
        artifacts_dir = str(run_dir(cfg.chatroom_dir, cfg.run_id))
        result = RunResult(
            variant="A",
            run_id=cfg.run_id,
            final_plan="plan",
            total_cost_usd=0.0,
            wall_clock_seconds=0.0,
            termination_reason="complete",
            artifacts_dir=artifacts_dir,
            config=cfg,
            environment=None,
        )
        write_summary(result)
        loaded = load_summary(cfg.chatroom_dir, cfg.run_id)
        env = loaded["environment"]
        assert env is not None
        # Not all probes succeed in every sandbox, but shape is fixed.
        assert set(env.keys()) >= {
            "git_sha",
            "git_branch",
            "git_dirty",
            "claude_cli_version",
            "claude_agent_sdk_version",
            "python_version",
            "platform",
        }
        assert env["python_version"]  # always populated

    def test_summary_preserves_explicit_environment(self, tmp_path):
        cfg = _make_config(tmp_path)
        artifacts_dir = str(run_dir(cfg.chatroom_dir, cfg.run_id))
        explicit = {"git_sha": "deadbeef", "python_version": "3.13.5"}
        result = RunResult(
            variant="A",
            run_id=cfg.run_id,
            final_plan="plan",
            total_cost_usd=0.0,
            wall_clock_seconds=0.0,
            termination_reason="complete",
            artifacts_dir=artifacts_dir,
            config=cfg,
            environment=explicit,
        )
        write_summary(result)
        loaded = load_summary(cfg.chatroom_dir, cfg.run_id)
        assert loaded["environment"] == explicit


class TestAtomicWrite:
    def test_write_leaves_no_tmp_file(self, tmp_path):
        target = tmp_path / "out.txt"
        _atomic_write_text(target, "hello")
        assert target.read_text(encoding="utf-8") == "hello"
        assert list(tmp_path.glob("*.tmp")) == []

    def test_crash_during_rename_preserves_old_content(self, tmp_path):
        target = tmp_path / "out.txt"
        target.write_text("original", encoding="utf-8")

        def _boom(src, dst):
            raise RuntimeError("simulated crash during rename")

        with patch("langgraph_agents.pipeline.artifacts.os.replace", _boom):
            try:
                _atomic_write_text(target, "new content")
            except RuntimeError:
                pass

        # Old file intact; partial tmp cleaned up manually in a real crash,
        # but the *target* never saw a half-write.
        assert target.read_text(encoding="utf-8") == "original"
