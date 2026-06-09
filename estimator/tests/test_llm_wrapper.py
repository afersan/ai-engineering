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
def test_stream_cache_hit_uses_current_latency_not_stored(
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
    mock_router_cls.return_value = MagicMock()

    wrapper = LLMWrapper(settings=settings, cache=MagicMock())
    wrapper._cache.get.return_value = {
        "estimation": "Cached text",
        "model": "claude-haiku-4-5",
        "provider": "anthropic",
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        "latency_ms": 8888.8,
    }

    stream_iter, meta_holder = wrapper.stream_completion("system", "user message")
    "".join(stream_iter)

    assert meta_holder["cache_hit"] is True
    assert meta_holder["latency_ms"] < 100
    assert meta_holder["latency_ms"] != 8888.8


@patch("app.services.llm_wrapper.Router")
def test_stream_completion_reports_usage(mock_router_cls: MagicMock) -> None:
    settings = Settings(
        _env_file=None,
        OPENAI_API_KEY=None,
        ANTHROPIC_API_KEY="test-anthropic",
        LLM_PROVIDER="anthropic",
        LLM_MODEL="claude-haiku-4-5",
        CACHE_ENABLED=False,
    )

    usage = SimpleNamespace(prompt_tokens=120, completion_tokens=45, total_tokens=165)

    def chunk(content: str = "", with_usage: bool = False):
        return SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=content))],
            model="claude-haiku-4-5",
            usage=usage if with_usage else None,
        )

    mock_router = MagicMock()
    mock_router.completion.return_value = iter(
        [chunk("Hola"), chunk("", with_usage=True)]
    )
    mock_router_cls.return_value = mock_router

    wrapper = LLMWrapper(settings=settings, cache=MagicMock())
    wrapper._cache.get.return_value = None

    stream_iter, meta_holder = wrapper.stream_completion("system", "user message")
    text = "".join(stream_iter)

    assert text == "Hola"
    assert meta_holder["usage"]["input_tokens"] == 120
    assert meta_holder["usage"]["output_tokens"] == 45
    assert meta_holder["usage"]["total_tokens"] == 165
    mock_router.completion.assert_called_once()
    assert mock_router.completion.call_args.kwargs["stream_options"] == {
        "include_usage": True
    }


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
