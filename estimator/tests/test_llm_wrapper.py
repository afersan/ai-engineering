"""Tests for LLM wrapper normalization and cache integration."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.services.llm_wrapper import LLMWrapper


@pytest.fixture
def wrapper_settings() -> Settings:
    return Settings(
        OPENAI_API_KEY="test-openai",
        ANTHROPIC_API_KEY="test-anthropic",
        LLM_MODEL="gpt-4o-mini",
        LLM_FALLBACK_MODEL="claude-haiku-4-5",
        CACHE_ENABLED=False,
    )


def _mock_response(content: str = "Estimation text", model: str = "gpt-4o-mini"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason="stop",
            )
        ],
        model=model,
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
    )


@patch("app.services.llm_wrapper.Router")
def test_completion_returns_normalized_result(mock_router_cls: MagicMock, wrapper_settings: Settings) -> None:
    mock_router = MagicMock()
    mock_router.completion.return_value = _mock_response()
    mock_router_cls.return_value = mock_router

    wrapper = LLMWrapper(settings=wrapper_settings, cache=MagicMock())
    wrapper._cache.get.return_value = None

    result = wrapper.completion("system prompt", "user message")

    assert result["estimation"] == "Estimation text"
    assert result["model"] == "gpt-4o-mini"
    assert result["provider"] == "openai"
    assert result["usage"]["input_tokens"] == 100
    assert result["cache_hit"] is False
    wrapper._cache.set.assert_called_once()


@patch("app.services.llm_wrapper.Router")
def test_build_router_anthropic_only_registers_primary(
    mock_router_cls: MagicMock,
) -> None:
    settings = Settings(
        _env_file=None,
        OPENAI_API_KEY=None,
        ANTHROPIC_API_KEY="test-anthropic",
        LLM_PROVIDER="anthropic",
        LLM_MODEL="claude-haiku-4-5",
        CACHE_ENABLED=False,
    )
    LLMWrapper(settings=settings, cache=MagicMock())

    model_list = mock_router_cls.call_args.kwargs["model_list"]
    assert len(model_list) == 1
    assert model_list[0]["model_name"] == "estimator"
    assert model_list[0]["litellm_params"]["model"] == "claude-haiku-4-5"
    assert mock_router_cls.call_args.kwargs["fallbacks"] == []


@patch("app.services.llm_wrapper.Router")
def test_completion_returns_cached_result(mock_router_cls: MagicMock, wrapper_settings: Settings) -> None:
    cached = {
        "estimation": "Cached estimation",
        "model": "gpt-4o-mini",
        "provider": "openai",
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "latency_ms": 0.0,
    }
    mock_router_cls.return_value = MagicMock()

    wrapper = LLMWrapper(settings=wrapper_settings, cache=MagicMock())
    wrapper._cache.get.return_value = {**cached, "cache_hit": True}

    result = wrapper.completion("system prompt", "user message")

    assert result["estimation"] == "Cached estimation"
    assert result["cache_hit"] is True
    wrapper._router.completion.assert_not_called()
