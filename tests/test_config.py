"""Tests that config module reads env vars correctly."""

import importlib
import os


def test_default_values():
    import langgraph_agents.config as cfg

    assert cfg.PLANNER_MODEL == os.environ.get("PLANNER_MODEL", "opus")
    assert cfg.CODER_TIMEOUT == int(os.environ.get("CODER_TIMEOUT_S", "7200"))
    assert cfg.CODER_BUDGET_USD == float(os.environ.get("CODER_BUDGET_USD", "10.0"))


def test_env_override(monkeypatch):
    monkeypatch.setenv("PLANNER_MODEL", "haiku")
    monkeypatch.setenv("CODER_TIMEOUT_S", "300")
    import langgraph_agents.config as cfg

    importlib.reload(cfg)
    assert cfg.PLANNER_MODEL == "haiku"
    assert cfg.CODER_TIMEOUT == 300
    importlib.reload(cfg)
