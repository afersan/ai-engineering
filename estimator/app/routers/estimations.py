import structlog
from fastapi import APIRouter, HTTPException

from app.schemas.estimation import EstimationRequest, EstimationResponse
from app.services.llm_service import LLMServiceError, generate_estimation

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["estimations"])


@router.post("/estimate", response_model=EstimationResponse)
async def create_estimation(request: EstimationRequest) -> EstimationResponse:
    """Receive a typed estimation request and return the generated estimate."""
    try:
        result = generate_estimation(request)
    except LLMServiceError as exc:
        log.error("estimation_endpoint_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))

    return EstimationResponse(text=result["text"], prompt_version="v1")
