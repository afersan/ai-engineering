"""Request/response schemas for session endpoints."""
from pydantic import BaseModel, Field

from app.models.session import ProjectMetadata


class MultiTurnEstimationResponse(BaseModel):
    """Response from multi-turn estimation endpoint."""
    estimation: str
    project_metadata: ProjectMetadata
    prompt_version: str = "v1"
    turn_number: int = Field(ge=1, description="Current turn number in session")
