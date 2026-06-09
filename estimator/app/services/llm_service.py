"""Business logic for software estimation via LLM with CAG context."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import structlog

from app.config import get_settings
from app.context.examples import ESTIMATION_EXAMPLES, format_examples_for_prompt
from app.services.llm_wrapper import LLMWrapper, LLMWrapperError

log = structlog.get_logger()

MAX_TOKENS = 4000

_wrapper: LLMWrapper | None = None


class LLMServiceError(Exception):
    """Raised when the LLM provider call fails."""


def get_wrapper() -> LLMWrapper:
    """Return a process-level LLM wrapper singleton."""
    global _wrapper
    if _wrapper is None:
        _wrapper = LLMWrapper()
    return _wrapper


def build_system_prompt() -> str:
    """Construct the system prompt with role definition and reference examples."""
    examples_text = format_examples_for_prompt(ESTIMATION_EXAMPLES)
    return (
        "You are a senior software consultant with 15+ years of experience in project "
        "estimation. Your task is to produce a detailed software project estimation based "
        "on a meeting transcription provided by the user.\n\n"
        "Below are reference estimations from previous projects. Use them as a guide for "
        "structure, level of detail, and realistic pricing. Adapt the content to match the "
        "specific project described in the transcription.\n\n"
        "Your output MUST follow this exact format:\n"
        "- Project title as an H2 heading\n"
        "- A task breakdown table with columns: Task, Hours, Cost (EUR)\n"
        "- Total hours\n"
        "- Total cost in EUR\n"
        "- Recommended team composition\n"
        "- Estimated duration in weeks\n\n"
        "Use a developer rate of approximately 62.50 EUR/hour (500 EUR/day) and a designer "
        "rate of approximately 50 EUR/hour (400 EUR/day). Provide realistic, well-justified "
        "numbers.\n\n"
        f"{examples_text}"
    )


def generate_estimation(transcription: str) -> dict[str, Any]:
    """Generate a software estimation from a meeting transcription using the LLM wrapper."""
    settings = get_settings()
    system_prompt = build_system_prompt()

    log.info(
        "generating_estimation",
        provider=settings.LLM_PROVIDER,
        model=settings.LLM_MODEL,
    )

    try:
        result = get_wrapper().completion(system_prompt, transcription)
        return {
            "estimation": result["estimation"],
            "model": result["model"],
            "provider": result["provider"],
            "usage": result["usage"],
            "cache_hit": result.get("cache_hit", False),
            "latency_ms": result.get("latency_ms"),
            "fallback_used": result.get("fallback_used", False),
        }
    except LLMWrapperError as exc:
        raise LLMServiceError(str(exc)) from exc
    except Exception as exc:
        log.error("llm_call_failed", error=str(exc), provider=settings.LLM_PROVIDER)
        raise LLMServiceError(f"LLM call failed: {exc}") from exc


def stream_estimation(
    transcription: str,
) -> tuple[Iterator[str], dict[str, Any]]:
    """Stream estimation tokens and return metadata holder updated after iteration."""
    system_prompt = build_system_prompt()
    settings = get_settings()

    log.info(
        "streaming_estimation",
        provider=settings.LLM_PROVIDER,
        model=settings.LLM_MODEL,
    )

    try:
        return get_wrapper().stream_completion(system_prompt, transcription)
    except LLMWrapperError as exc:
        raise LLMServiceError(str(exc)) from exc
