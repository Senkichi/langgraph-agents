"""Tests that config module reads env vars correctly."""

import importlib
import logging
import os


def test_default_values():
    import langgraph_agents.config as cfg

    assert cfg.PLANNER_MODEL == os.environ.get("PLANNER_MODEL", cfg.OPUS_PINNED)
    assert cfg.REVIEWER_MODEL == os.environ.get("REVIEWER_MODEL", cfg.SONNET_PINNED)
    assert cfg.CODER_TIMEOUT == int(os.environ.get("CODER_TIMEOUT_S", "7200"))
    assert cfg.CODER_BUDGET_USD == float(os.environ.get("CODER_BUDGET_USD", "10.0"))


def test_pinned_ids_are_explicit():
    """Defaults must be explicit IDs, not aliases — guards against the silent
    alias remap documented in docs/experiment_002_results.md."""
    import langgraph_agents.config as cfg

    assert cfg.OPUS_PINNED.startswith("claude-opus-")
    assert cfg.SONNET_PINNED.startswith("claude-sonnet-")
    assert cfg.HAIKU_PINNED.startswith("claude-haiku-")
    for pinned in (cfg.OPUS_PINNED, cfg.SONNET_PINNED, cfg.HAIKU_PINNED):
        assert pinned not in cfg.KNOWN_ALIASES


def test_warn_if_alias_logs_for_alias(caplog):
    import langgraph_agents.config as cfg

    with caplog.at_level(logging.WARNING, logger="langgraph_agents.config"):
        out = cfg.warn_if_alias("opus", role="planner")
    assert out == "opus"
    assert any("alias" in rec.message for rec in caplog.records)


def test_warn_if_alias_silent_for_explicit_id(caplog):
    import langgraph_agents.config as cfg

    with caplog.at_level(logging.WARNING, logger="langgraph_agents.config"):
        out = cfg.warn_if_alias(cfg.OPUS_PINNED, role="planner")
    assert out == cfg.OPUS_PINNED
    assert caplog.records == []


def test_env_override(monkeypatch):
    monkeypatch.setenv("PLANNER_MODEL", "haiku")
    monkeypatch.setenv("CODER_TIMEOUT_S", "300")
    import langgraph_agents.config as cfg

    importlib.reload(cfg)
    assert cfg.PLANNER_MODEL == "haiku"
    assert cfg.CODER_TIMEOUT == 300
    importlib.reload(cfg)
