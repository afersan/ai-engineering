from pydantic import BaseModel, Field


class EstimationRequest(BaseModel):
    """Incoming request containing a meeting transcription to estimate."""

    transcription: str = Field(..., min_length=50, description="Meeting transcription text")


class TokenUsage(BaseModel):
    """Token consumption details from the LLM call."""

    input_tokens: int
    output_tokens: int
    total_tokens: int


class EstimationResponse(BaseModel):
    """Response containing the generated estimation and metadata."""

    estimation: str = Field(..., description="Generated software estimation in markdown")
    model: str = Field(..., description="LLM model used")
    provider: str = Field(..., description="LLM provider used")
    usage: TokenUsage
    cache_hit: bool = Field(default=False, description="Whether the response came from cache")
    latency_ms: float | None = Field(default=None, description="End-to-end latency in milliseconds")
    fallback_used: bool = Field(
        default=False, description="Whether a fallback provider was used"
    )


class StreamMeta(BaseModel):
    """Metadata sent as final SSE event after streaming completes."""

    model: str
    provider: str
    usage: TokenUsage
    cache_hit: bool = False
    latency_ms: float | None = None
    fallback_used: bool = False
