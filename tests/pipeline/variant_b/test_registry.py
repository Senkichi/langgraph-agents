"""Tests for the debate session registry."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from langgraph_agents.pipeline.variant_b import registry


@pytest.fixture(autouse=True)
def _clean_registry():
    registry._reset_for_tests()
    yield
    registry._reset_for_tests()


def _fake_session(close_raises: bool = False) -> MagicMock:
    s = MagicMock()
    if close_raises:
        s.close = AsyncMock(side_effect=RuntimeError("boom"))
    else:
        s.close = AsyncMock()
    return s


class TestRegister:
    def test_register_and_get(self):
        s = _fake_session()
        registry.register("rid-1", "left", s)
        assert registry.get("rid-1", "left") is s

    def test_get_missing_returns_none(self):
        assert registry.get("rid-missing", "left") is None

    def test_get_or_raise_raises(self):
        with pytest.raises(RuntimeError, match="No debate session"):
            registry.get_or_raise("rid-missing", "left")

    def test_register_duplicate_overwrites_with_warning(self, caplog):
        s1, s2 = _fake_session(), _fake_session()
        registry.register("rid-1", "left", s1)
        registry.register("rid-1", "left", s2)
        assert registry.get("rid-1", "left") is s2

    def test_different_run_ids_are_isolated(self):
        s1, s2 = _fake_session(), _fake_session()
        registry.register("rid-A", "left", s1)
        registry.register("rid-B", "left", s2)
        assert registry.get("rid-A", "left") is s1
        assert registry.get("rid-B", "left") is s2


class TestCloseAll:
    def test_closes_all_sessions(self):
        s1, s2 = _fake_session(), _fake_session()
        registry.register("rid-1", "left", s1)
        registry.register("rid-1", "right", s2)
        asyncio.run(registry.close_all("rid-1"))
        s1.close.assert_awaited_once()
        s2.close.assert_awaited_once()

    def test_pops_entry(self):
        registry.register("rid-1", "left", _fake_session())
        assert "rid-1" in registry.active_run_ids()
        asyncio.run(registry.close_all("rid-1"))
        assert "rid-1" not in registry.active_run_ids()

    def test_missing_run_id_is_noop(self):
        # Must not raise even if called speculatively in a finally block.
        asyncio.run(registry.close_all("rid-never-existed"))

    def test_session_close_error_does_not_abort_cleanup(self):
        s_bad = _fake_session(close_raises=True)
        s_good = _fake_session()
        registry.register("rid-1", "left", s_bad)
        registry.register("rid-1", "right", s_good)
        asyncio.run(registry.close_all("rid-1"))
        # Good session must still have been closed despite the bad one raising.
        s_good.close.assert_awaited_once()
        assert "rid-1" not in registry.active_run_ids()
