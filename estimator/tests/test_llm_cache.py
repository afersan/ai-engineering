"""Tests for exact-match LLM cache."""

import json
from unittest.mock import MagicMock

import pytest

from app.config import Settings
from app.services.llm_cache import LLMCache


@pytest.fixture
def cache_settings() -> Settings:
    return Settings(
        _env_file=None,
        OPENAI_API_KEY="test-key",
        CACHE_ENABLED=True,
        CACHE_TTL_SECONDS=3600,
        REDIS_URL="redis://localhost:6379/0",
    )


def test_cache_key_is_deterministic(cache_settings: Settings) -> None:
    cache = LLMCache(cache_settings)
    key1 = cache.cache_key("prompt", "model-a", "system")
    key2 = cache.cache_key("prompt", "model-a", "system")
    assert key1 == key2
    assert key1.startswith("llm:")


def test_cache_key_changes_with_different_prompt(cache_settings: Settings) -> None:
    cache = LLMCache(cache_settings)
    key1 = cache.cache_key("prompt-a", "model-a", "system")
    key2 = cache.cache_key("prompt-b", "model-a", "system")
    assert key1 != key2


def test_cache_get_returns_none_on_miss(cache_settings: Settings) -> None:
    cache = LLMCache(cache_settings)
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    cache._client = mock_redis

    result = cache.get("prompt", "model", "system")
    assert result is None
    mock_redis.get.assert_called_once()


def test_cache_get_returns_hit(cache_settings: Settings) -> None:
    cache = LLMCache(cache_settings)
    mock_redis = MagicMock()
    payload = {
        "estimation": "## Test",
        "model": "gpt-4o-mini",
        "provider": "openai",
        "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
    }
    mock_redis.get.return_value = json.dumps(payload)
    cache._client = mock_redis

    result = cache.get("prompt", "model", "system")
    assert result is not None
    assert result["cache_hit"] is True
    assert result["estimation"] == "## Test"


def test_cache_set_calls_setex(cache_settings: Settings) -> None:
    cache = LLMCache(cache_settings)
    mock_redis = MagicMock()
    cache._client = mock_redis

    value = {"estimation": "text", "model": "gpt-4o-mini"}
    cache.set("prompt", "model", "system", value)

    mock_redis.setex.assert_called_once()
    args = mock_redis.setex.call_args[0]
    assert args[1] == 3600


def test_cache_clear_all_deletes_matching_keys(cache_settings: Settings) -> None:
    cache = LLMCache(cache_settings)
    mock_redis = MagicMock()
    mock_redis.scan_iter.return_value = ["llm:abc", "llm:def"]
    cache._client = mock_redis

    deleted = cache.clear_all()

    assert deleted == 2
    assert mock_redis.delete.call_count == 2


def test_cache_disabled_returns_none(cache_settings: Settings) -> None:
    cache_settings.CACHE_ENABLED = False
    cache = LLMCache(cache_settings)
    assert cache.get("prompt", "model", "system") is None
