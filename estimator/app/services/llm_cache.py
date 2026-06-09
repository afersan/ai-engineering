"""Exact-match cache for LLM responses backed by Redis."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import redis
import structlog

from app.config import Settings, get_settings

log = structlog.get_logger()


class LLMCache:
    """Cache LLM responses by deterministic hash of prompt parameters."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: redis.Redis | None = None

    @property
    def enabled(self) -> bool:
        return self._settings.CACHE_ENABLED

    def _get_client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(
                self._settings.REDIS_URL,
                decode_responses=True,
            )
        return self._client

    def cache_key(self, prompt: str, model: str, system_prompt: str) -> str:
        """Build a deterministic Redis key from all parameters that affect the response."""
        raw = json.dumps(
            {"prompt": prompt, "model": model, "system_prompt": system_prompt},
            sort_keys=True,
        )
        return f"llm:{hashlib.sha256(raw.encode()).hexdigest()}"

    def get(self, prompt: str, model: str, system_prompt: str) -> dict[str, Any] | None:
        """Return cached response dict or None on miss/disabled."""
        if not self.enabled:
            return None

        key = self.cache_key(prompt, model, system_prompt)
        try:
            cached = self._get_client().get(key)
        except redis.RedisError as exc:
            log.warning("cache_get_failed", error=str(exc))
            return None

        if cached is None:
            log.debug("cache_miss", cache_key=key[:16])
            return None

        result = json.loads(cached)
        result["cache_hit"] = True
        log.info("cache_hit", cache_key=key[:16])
        return result

    def set(self, prompt: str, model: str, system_prompt: str, value: dict[str, Any]) -> None:
        """Store response in Redis with configured TTL."""
        if not self.enabled:
            return

        key = self.cache_key(prompt, model, system_prompt)
        payload = {k: v for k, v in value.items() if k != "cache_hit"}
        try:
            self._get_client().setex(
                key,
                self._settings.CACHE_TTL_SECONDS,
                json.dumps(payload),
            )
            log.debug("cache_set", cache_key=key[:16], ttl=self._settings.CACHE_TTL_SECONDS)
        except redis.RedisError as exc:
            log.warning("cache_set_failed", error=str(exc))
