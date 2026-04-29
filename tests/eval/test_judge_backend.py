"""Tests for judge_backend — model-id classification and dispatch contract."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from langgraph_agents.eval import judge_backend as jb


class TestClassifyByModel:
    def test_deepseek_routes_to_openai_compatible(self):
        b = jb.classify_by_model("deepseek-v4-pro")
        assert isinstance(b, jb.OpenAICompatibleBackend)
        assert b.provider == "deepseek"
        assert b.base_url == "https://api.deepseek.com"
        assert b.api_key_env == "DEEPSEEK_API_KEY"

    def test_gpt_routes_to_openai_default_base_url(self):
        b = jb.classify_by_model("gpt-4o-2024-11-20")
        assert isinstance(b, jb.OpenAICompatibleBackend)
        assert b.provider == "openai"
        assert b.base_url is None  # SDK default
        assert b.api_key_env == "OPENAI_API_KEY"

    def test_o1_routes_to_openai(self):
        b = jb.classify_by_model("o1-preview")
        assert isinstance(b, jb.OpenAICompatibleBackend)
        assert b.provider == "openai"

    def test_o3_routes_to_openai(self):
        b = jb.classify_by_model("o3-mini")
        assert isinstance(b, jb.OpenAICompatibleBackend)
        assert b.provider == "openai"

    def test_claude_alias_routes_to_cli(self):
        for alias in ("opus", "sonnet", "haiku"):
            assert jb.classify_by_model(alias) == "claude_cli"

    def test_explicit_claude_id_routes_to_cli(self):
        assert jb.classify_by_model("claude-opus-4-7") == "claude_cli"
        assert jb.classify_by_model("claude-sonnet-4-6") == "claude_cli"

    def test_empty_model_raises(self):
        with pytest.raises(ValueError):
            jb.classify_by_model("")

    def test_unknown_string_falls_through_to_claude(self):
        # The classifier doesn't maintain a positive allowlist for Claude IDs.
        # Unrecognised strings route to the CLI which then surfaces its own error.
        assert jb.classify_by_model("some-future-model") == "claude_cli"


class TestIsOpenAICompatible:
    def test_predicate_matches_classification(self):
        assert jb.is_openai_compatible("deepseek-v4-pro") is True
        assert jb.is_openai_compatible("gpt-4o") is True
        assert jb.is_openai_compatible("opus") is False
        assert jb.is_openai_compatible("claude-opus-4-7") is False


class TestQueryOpenAICompatible:
    def test_rejects_claude_model(self):
        with pytest.raises(ValueError, match="Claude CLI"):
            asyncio.run(
                jb.query_openai_compatible(
                    system_prompt="x", user_message="y", model="opus"
                )
            )

    def test_missing_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY not set"):
            asyncio.run(
                jb.query_openai_compatible(
                    system_prompt="x", user_message="y", model="deepseek-v4-pro"
                )
            )

    def test_returns_content_when_present(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

        mock_msg = MagicMock()
        mock_msg.content = "PREFERENCE: X\nCONFIDENCE: high\nREASONING: ok"
        mock_msg.reasoning_content = "internal thinking"
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=mock_msg, finish_reason="stop")]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp

        with patch("openai.OpenAI", return_value=mock_client):
            text = asyncio.run(
                jb.query_openai_compatible(
                    system_prompt="sys", user_message="usr", model="deepseek-v4-pro"
                )
            )
        assert text == "PREFERENCE: X\nCONFIDENCE: high\nREASONING: ok"
        # Confirm the request used the right model + max_tokens default
        call = mock_client.chat.completions.create.call_args
        assert call.kwargs["model"] == "deepseek-v4-pro"
        assert call.kwargs["max_tokens"] == jb.DEFAULT_MAX_TOKENS
        assert call.kwargs["temperature"] == 0
        assert call.kwargs["messages"][0] == {"role": "system", "content": "sys"}
        assert call.kwargs["messages"][1] == {"role": "user", "content": "usr"}

    def test_falls_back_to_reasoning_content_on_empty(self, monkeypatch):
        """The Phase 0.1 first-run gotcha: thinking models can drain max_tokens
        on internal reasoning before any visible content."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

        mock_msg = MagicMock()
        mock_msg.content = ""  # empty
        mock_msg.reasoning_content = "thought process that contains the answer"
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=mock_msg, finish_reason="length")]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_resp

        with patch("openai.OpenAI", return_value=mock_client):
            text = asyncio.run(
                jb.query_openai_compatible(
                    system_prompt="sys", user_message="usr", model="deepseek-v4-pro"
                )
            )
        assert text == "thought process that contains the answer"

    def test_passes_base_url_for_deepseek(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
        captured: dict[str, object] = {}

        def fake_openai(**kwargs):
            captured.update(kwargs)
            mock_msg = MagicMock(content="x", reasoning_content=None)
            mock_resp = MagicMock(choices=[MagicMock(message=mock_msg, finish_reason="stop")])
            client = MagicMock()
            client.chat.completions.create.return_value = mock_resp
            return client

        with patch("openai.OpenAI", side_effect=fake_openai):
            asyncio.run(
                jb.query_openai_compatible(
                    system_prompt="s", user_message="u", model="deepseek-v4-pro"
                )
            )
        assert captured.get("base_url") == "https://api.deepseek.com"
        assert captured.get("api_key") == "test-key"

    def test_omits_base_url_for_openai(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        captured: dict[str, object] = {}

        def fake_openai(**kwargs):
            captured.update(kwargs)
            mock_msg = MagicMock(content="x", reasoning_content=None)
            mock_resp = MagicMock(choices=[MagicMock(message=mock_msg, finish_reason="stop")])
            client = MagicMock()
            client.chat.completions.create.return_value = mock_resp
            return client

        with patch("openai.OpenAI", side_effect=fake_openai):
            asyncio.run(
                jb.query_openai_compatible(
                    system_prompt="s", user_message="u", model="gpt-4o"
                )
            )
        # base_url should not be passed when omitted (lets SDK use its default)
        assert "base_url" not in captured
        assert captured.get("api_key") == "test-key"
