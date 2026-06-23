"""Session management endpoints."""
import structlog
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.models.session import SessionStore
from app.schemas.session import MultiTurnEstimationResponse
from app.schemas.estimation import (
    EstimationRequest,
    MAX_DESCRIPTION_LENGTH,
    MAX_TRANSCRIPT_LENGTH,
    ProjectType,
    DetailLevel,
    OutputFormat,
)
from app.services.attachment_processor import process_attachments, AttachmentProcessingError
from app.services.metadata_extractor import extract_project_metadata
from app.prompts.loader import render_estimation_prompt
from app.dependencies import get_llm_wrapper

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["sessions"])

# Singleton session store (in-memory, process-scoped)
_session_store = SessionStore()


class SessionCreateResponse(BaseModel):
    session_id: str


@router.post("/sessions", response_model=SessionCreateResponse)
async def create_session() -> SessionCreateResponse:
    """Create a new conversational session."""
    try:
        session_id = _session_store.create_session()
    except Exception as exc:
        log.error("session_endpoint_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))

    return SessionCreateResponse(session_id=session_id)


@router.post(
    "/sessions/{session_id}/estimate",
    response_model=MultiTurnEstimationResponse,
)
async def estimate_with_session(
    session_id: str,
    transcript: str = Form(..., min_length=20, max_length=MAX_TRANSCRIPT_LENGTH),
    project_type: str = Form(...),
    detail_level: str = Form(...),
    output_format: str = Form(...),
    attachments: list[UploadFile] = File(default=[]),
) -> MultiTurnEstimationResponse:
    """Generate estimation within a conversational session.

    Accepts transcript and optional file attachments. Maintains conversation
    history and project metadata across turns.
    """
    # Retrieve session
    session = _session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    log.info(
        "multiturn_estimation_request",
        session_id=session_id,
        has_attachments=len(attachments) > 0,
    )

    # Process attachments if present
    try:
        attachment_text = await process_attachments(attachments)
    except AttachmentProcessingError as exc:
        log.error("attachment_processing_failed", error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))

    # Combine transcript with attachment text
    full_transcript = transcript
    if attachment_text:
        full_transcript = f"{transcript}\n\n{attachment_text}"

    if len(full_transcript) > MAX_DESCRIPTION_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=(
                f"El texto combinado (transcripción + adjuntos) supera el límite "
                f"de {MAX_DESCRIPTION_LENGTH} caracteres"
            ),
        )

    # Build typed request (for compatibility with existing prompt renderer)
    request = EstimationRequest(
        description=full_transcript,
        project_type=ProjectType(project_type),
        detail_level=DetailLevel(detail_level),
        output_format=OutputFormat(output_format),
    )

    # Render prompts with current project metadata
    system_prompt, user_message = render_estimation_prompt(
        request,
        project_metadata=session.metadata,
    )

    # Update system prompt in history
    session.history.update_system_prompt(system_prompt)

    # Add user message to history
    session.history.add_message(role="user", content=user_message)

    # Get conversation history for LLM
    messages = session.history.to_messages_list()

    # Call LLM with full conversation history
    wrapper = get_llm_wrapper()
    try:
        result = wrapper.complete_with_history(messages=messages)
        estimation_text = result["estimation"]
    except Exception as exc:
        log.error("llm_call_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"LLM call failed: {exc}")

    # Add assistant response to history
    session.history.add_message(role="assistant", content=estimation_text)

    # Extract and update project metadata
    session.metadata = extract_project_metadata(
        user_message=full_transcript,
        assistant_response=estimation_text,
        current_metadata=session.metadata,
    )

    # Update system prompt with new metadata for next turn
    updated_system_prompt, _ = render_estimation_prompt(request, project_metadata=session.metadata)
    session.history.update_system_prompt(updated_system_prompt)

    # Get absolute turn number from history
    turn_number = session.history.get_turn_count()

    return MultiTurnEstimationResponse(
        estimation=estimation_text,
        project_metadata=session.metadata,
        turn_number=turn_number,
    )


def get_session_store() -> SessionStore:
    """Dependency injection for session store (useful for testing)."""
    return _session_store
