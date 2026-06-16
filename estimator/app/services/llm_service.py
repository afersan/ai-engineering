"""Estimation orchestration: prompt rendering and LLM dispatch."""

from __future__ import annotations

from typing import Any

import structlog

from app.dependencies import get_llm_wrapper
from app.prompts.loader import render_estimation_prompt
from app.schemas.estimation import EstimationRequest

log = structlog.get_logger()

DEFAULT_MAX_TOKENS = 4000


class LLMServiceError(Exception):
    """Raised when the LLM provider call fails."""


def _invoke_llm(
    *,
    system_prompt: str,
    user_message: str,
    model_override: str | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    thinking_budget: int | None = None,
) -> dict[str, Any]:
    """Single seam through which every LLM call passes. Tests monkeypatch this."""
    wrapper = get_llm_wrapper()
    return wrapper.complete(
        system_prompt=system_prompt,
        user_message=user_message,
        model_override=model_override,
        max_tokens=max_tokens,
        thinking_budget=thinking_budget,
    )


def generate_estimation(request: EstimationRequest) -> dict[str, str]:
    """Generate a software estimation from a typed product request."""
    system_prompt, user_message = render_estimation_prompt(request)

    log.info(
        "generating_estimation",
        project_type=request.project_type.value,
        detail_level=request.detail_level.value,
        output_format=request.output_format.value,
    )

    try:
        result = _invoke_llm(
            system_prompt=system_prompt,
            user_message=user_message,
        )
    except Exception as exc:
        log.error("llm_call_failed", error=str(exc), error_type=type(exc).__name__)
        raise LLMServiceError(f"LLM call failed: {exc}") from exc

    return {"text": result["estimation"]}
