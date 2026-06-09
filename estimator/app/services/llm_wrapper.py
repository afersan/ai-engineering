"""LLM abstraction layer with LiteLLM Router, fallback, cache and observability."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import structlog
from litellm import Router, completion_cost, token_counter

from app.config import Settings, get_settings
from app.services.llm_cache import LLMCache

log = structlog.get_logger()

MAX_TOKENS = 4000
LOGICAL_MODEL = "estimator"
FALLBACK_MODEL = "estimator-fallback"


class LLMWrapperError(Exception):
    """Raised when all LLM providers fail."""


class LLMWrapper:
    """Unified LLM interface: cache, LiteLLM Router with fallback, structured logging."""

    def __init__(
        self,
        settings: Settings | None = None,
        cache: LLMCache | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._cache = cache or LLMCache(self._settings)
        self._router = self._build_router()

    def _build_router(self) -> Router:
        model_list: list[dict[str, Any]] = []

        if self._settings.LLM_PROVIDER == "openai" and self._settings.OPENAI_API_KEY:
            model_list.append(
                {
                    "model_name": LOGICAL_MODEL,
                    "litellm_params": {
                        "model": self._settings.LLM_MODEL,
                        "api_key": self._settings.OPENAI_API_KEY,
                    },
                }
            )
        elif self._settings.LLM_PROVIDER == "anthropic" and self._settings.ANTHROPIC_API_KEY:
            model_list.append(
                {
                    "model_name": LOGICAL_MODEL,
                    "litellm_params": {
                        "model": self._settings.LLM_MODEL,
                        "api_key": self._settings.ANTHROPIC_API_KEY,
                    },
                }
            )

        if self._settings.LLM_PROVIDER == "openai" and self._settings.ANTHROPIC_API_KEY:
            model_list.append(
                {
                    "model_name": FALLBACK_MODEL,
                    "litellm_params": {
                        "model": self._settings.LLM_FALLBACK_MODEL,
                        "api_key": self._settings.ANTHROPIC_API_KEY,
                    },
                }
            )
        elif self._settings.LLM_PROVIDER == "anthropic" and self._settings.OPENAI_API_KEY:
            model_list.append(
                {
                    "model_name": FALLBACK_MODEL,
                    "litellm_params": {
                        "model": self._settings.LLM_FALLBACK_MODEL,
                        "api_key": self._settings.OPENAI_API_KEY,
                    },
                }
            )

        fallbacks: list[dict[str, list[str]]] = []
        has_primary = any(m["model_name"] == LOGICAL_MODEL for m in model_list)
        has_fallback = any(m["model_name"] == FALLBACK_MODEL for m in model_list)
        if has_primary and has_fallback:
            fallbacks = [{LOGICAL_MODEL: [FALLBACK_MODEL]}]

        return Router(
            model_list=model_list,
            fallbacks=fallbacks,
            num_retries=2,
        )

    def _messages(self, system_prompt: str, user_message: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

    def _resolve_provider(self, model: str) -> str:
        model_lower = model.lower()
        if "claude" in model_lower or "anthropic" in model_lower:
            return "anthropic"
        return "openai"

    def _usage_from_response(self, usage: Any) -> dict[str, int]:
        if usage is None:
            return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0
        total_tokens = getattr(usage, "total_tokens", 0) or (input_tokens + output_tokens)
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }

    def _estimate_usage(
        self,
        model: str,
        messages: list[dict[str, str]],
        output_text: str,
    ) -> dict[str, int]:
        input_tokens = token_counter(model=model, messages=messages)
        output_tokens = token_counter(model=model, text=output_text)
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }

    def _ensure_usage(
        self,
        usage: dict[str, int],
        *,
        model: str,
        messages: list[dict[str, str]],
        output_text: str,
    ) -> dict[str, int]:
        if usage.get("total_tokens", 0) > 0:
            return usage
        return self._estimate_usage(model, messages, output_text)

    def _normalize_response(
        self,
        response: Any,
        *,
        cache_hit: bool = False,
        latency_ms: float,
        requested_model: str,
    ) -> dict[str, Any]:
        content = response.choices[0].message.content or ""
        usage = response.usage
        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0
        model_used = response.model or requested_model
        fallback_used = model_used != requested_model and not cache_hit

        cost_usd: float | None = None
        try:
            cost_usd = completion_cost(completion_response=response)
        except Exception:
            pass

        return {
            "estimation": content,
            "model": model_used,
            "provider": self._resolve_provider(model_used),
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
            "cache_hit": cache_hit,
            "latency_ms": round(latency_ms, 1),
            "fallback_used": fallback_used,
            "cost_usd": cost_usd,
            "finish_reason": response.choices[0].finish_reason,
        }

    def completion(self, system_prompt: str, user_message: str) -> dict[str, Any]:
        """Generate a completion with cache lookup, fallback and logging."""
        requested_model = self._settings.LLM_MODEL
        cache_key_model = f"{LOGICAL_MODEL}:{requested_model}"

        call_log = log.bind(model=requested_model, logical_model=LOGICAL_MODEL)
        call_log.info("llm_call_started", cache_lookup=self._cache.enabled)

        start = time.perf_counter()
        cached = self._cache.get(user_message, cache_key_model, system_prompt)
        if cached is not None:
            latency_ms = (time.perf_counter() - start) * 1000
            result = {
                **cached,
                "cache_hit": True,
                "latency_ms": round(latency_ms, 1),
                "fallback_used": cached.get("fallback_used", False),
            }
            call_log.info(
                "llm_call_completed",
                cache_hit=True,
                latency_ms=result["latency_ms"],
                tokens_in=result.get("usage", {}).get("input_tokens"),
                tokens_out=result.get("usage", {}).get("output_tokens"),
            )
            return result

        try:
            response = self._router.completion(
                model=LOGICAL_MODEL,
                messages=self._messages(system_prompt, user_message),
                max_tokens=MAX_TOKENS,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            call_log.error(
                "llm_call_failed",
                error_type=type(exc).__name__,
                error_msg=str(exc),
                latency_ms=round(latency_ms, 1),
            )
            raise LLMWrapperError(f"LLM call failed: {exc}") from exc

        latency_ms = (time.perf_counter() - start) * 1000
        result = self._normalize_response(
            response,
            cache_hit=False,
            latency_ms=latency_ms,
            requested_model=requested_model,
        )

        call_log.info(
            "llm_call_completed",
            cache_hit=False,
            latency_ms=result["latency_ms"],
            tokens_in=result["usage"]["input_tokens"],
            tokens_out=result["usage"]["output_tokens"],
            cost_usd=result.get("cost_usd"),
            fallback_used=result["fallback_used"],
            finish_reason=result.get("finish_reason"),
            provider=result["provider"],
            model=result["model"],
        )

        self._cache.set(user_message, cache_key_model, system_prompt, result)
        return result

    def stream_completion(
        self, system_prompt: str, user_message: str
    ) -> tuple[Iterator[str], dict[str, Any]]:
        """Stream tokens; returns (chunk_iterator, metadata_dict).

        On cache hit, yields the full cached text in one chunk.
        Metadata is populated after streaming completes (or immediately on cache hit).
        """
        requested_model = self._settings.LLM_MODEL
        cache_key_model = f"{LOGICAL_MODEL}:{requested_model}"

        messages = self._messages(system_prompt, user_message)
        start = time.perf_counter()
        cached = self._cache.get(user_message, cache_key_model, system_prompt)
        if cached is not None:
            text = cached.get("estimation", "")
            usage = self._ensure_usage(
                cached.get("usage", {}),
                model=requested_model,
                messages=messages,
                output_text=text,
            )
            meta_holder: dict[str, Any] = {}

            def cached_iter() -> Iterator[str]:
                if text:
                    yield text
                latency_ms = (time.perf_counter() - start) * 1000
                meta_holder.update(
                    {
                        **cached,
                        "usage": usage,
                        "cache_hit": True,
                        "latency_ms": round(latency_ms, 1),
                        "fallback_used": cached.get("fallback_used", False),
                    }
                )

            return cached_iter(), meta_holder

        collected: list[str] = []
        meta_holder = {}

        call_log = log.bind(model=requested_model, logical_model=LOGICAL_MODEL)
        call_log.info("llm_call_started", cache_lookup=False, streaming=True)

        try:
            response = self._router.completion(
                model=LOGICAL_MODEL,
                messages=messages,
                max_tokens=MAX_TOKENS,
                stream=True,
                stream_options={"include_usage": True},
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            call_log.error(
                "llm_call_failed",
                error_type=type(exc).__name__,
                error_msg=str(exc),
                latency_ms=round(latency_ms, 1),
                streaming=True,
            )
            raise LLMWrapperError(f"LLM stream failed: {exc}") from exc

        def stream_iter() -> Iterator[str]:
            nonlocal collected
            usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            model_used = requested_model

            for chunk in response:
                chunk_usage = getattr(chunk, "usage", None)
                if chunk_usage is not None:
                    usage = self._usage_from_response(chunk_usage)
                if getattr(chunk, "model", None):
                    model_used = chunk.model

                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None) or ""
                if content:
                    collected.append(content)
                    yield content

            latency_ms = (time.perf_counter() - start) * 1000
            full_text = "".join(collected)
            usage = self._ensure_usage(
                usage,
                model=model_used,
                messages=messages,
                output_text=full_text,
            )
            meta_holder.update(
                {
                    "estimation": full_text,
                    "model": model_used,
                    "provider": self._resolve_provider(model_used),
                    "usage": usage,
                    "cache_hit": False,
                    "latency_ms": round(latency_ms, 1),
                    "fallback_used": model_used != requested_model,
                }
            )

            call_log.info(
                "llm_call_completed",
                cache_hit=False,
                latency_ms=meta_holder["latency_ms"],
                tokens_in=usage["input_tokens"],
                tokens_out=usage["output_tokens"],
                streaming=True,
            )

            self._cache.set(
                user_message,
                cache_key_model,
                system_prompt,
                meta_holder,
            )

        return stream_iter(), meta_holder
