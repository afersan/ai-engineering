"""Session management endpoints."""
from fastapi import APIRouter
from pydantic import BaseModel

from app.models.session import SessionStore

router = APIRouter(prefix="/api/v1", tags=["sessions"])

# Singleton session store (in-memory, process-scoped)
_session_store = SessionStore()


class SessionCreateResponse(BaseModel):
    session_id: str


@router.post("/sessions", response_model=SessionCreateResponse)
async def create_session() -> SessionCreateResponse:
    """Create a new conversational session."""
    session_id = _session_store.create_session()
    return SessionCreateResponse(session_id=session_id)


def get_session_store() -> SessionStore:
    """Dependency injection for session store (useful for testing)."""
    return _session_store
