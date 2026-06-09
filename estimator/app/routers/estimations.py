from collections.abc import AsyncIterable

import structlog
from fastapi import APIRouter, HTTPException
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.schemas.estimation import EstimationRequest, EstimationResponse, StreamMeta, TokenUsage
from app.services.llm_cache import LLMCache
from app.services.llm_service import LLMServiceError, generate_estimation, stream_estimation

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["estimations"])


@router.post("/estimate", response_model=EstimationResponse)
async def create_estimation(request: EstimationRequest) -> EstimationResponse:
    """Receive a meeting transcription and return a software project estimation."""
    try:
        result = generate_estimation(request.transcription)
    except LLMServiceError as exc:
        log.error("estimation_endpoint_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))

    return EstimationResponse(**result)


@router.delete("/cache")
async def clear_llm_cache() -> dict[str, int]:
    """Remove all cached LLM responses from Redis."""
    try:
        deleted = LLMCache().clear_all()
    except Exception as exc:
        log.error("cache_clear_endpoint_error", error=str(exc))
        raise HTTPException(status_code=500, detail="No se pudo vaciar la caché") from exc

    return {"cleared": deleted}


@router.post("/estimate/stream", response_class=EventSourceResponse)
async def create_estimation_stream(
    request: EstimationRequest,
) -> AsyncIterable[ServerSentEvent]:
    """Stream estimation tokens via Server-Sent Events."""
    try:
        chunk_iter, meta_holder = stream_estimation(request.transcription)
    except LLMServiceError as exc:
        log.error("estimation_stream_error", error=str(exc))
        yield ServerSentEvent(event="error", data=str(exc))
        return

    for chunk in chunk_iter:
        yield ServerSentEvent(data=chunk)

    if meta_holder:
        meta = StreamMeta(
            model=meta_holder.get("model", ""),
            provider=meta_holder.get("provider", ""),
            usage=TokenUsage(**meta_holder.get("usage", {})),
            cache_hit=meta_holder.get("cache_hit", False),
            latency_ms=meta_holder.get("latency_ms"),
            fallback_used=meta_holder.get("fallback_used", False),
        )
        yield ServerSentEvent(event="meta", data=meta.model_dump_json())
