"""Session state models for conversational memory.

This module manages in-memory session state. Volatility is accepted in this phase:
sessions are lost on service restart. Future modules will add Redis or database
persistence when multi-instance deployment requires it.
"""
from __future__ import annotations

import uuid
from collections import deque
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field


class ProjectMetadata(BaseModel):
    """Facts about the project extracted from conversation.

    Separate from conversational history. Injected into system prompt on each turn.
    """
    project_name: str | None = None
    assumed_team_size: int | None = Field(None, ge=1, le=50)
    mentioned_technologies: list[str] = Field(default_factory=list)
    agreed_scope: str = ""


class ConversationHistory:
    """Sliding window conversation history.

    Maintains last N turns (user+assistant pairs) plus system prompt.
    Older turns are discarded to control context window size.
    """

    def __init__(self, max_turns: int = 6):
        self.max_turns = max_turns
        self._system_prompt: str | None = None
        # Deque of (role, content) tuples - excludes system prompt
        self._messages: deque[tuple[str, str]] = deque(maxlen=max_turns * 2)

    def add_message(self, role: Literal["system", "user", "assistant"], content: str) -> None:
        """Add a message to history. System prompt is stored separately."""
        if role == "system":
            self._system_prompt = content
        else:
            self._messages.append((role, content))

    def to_messages_list(self) -> list[dict[str, str]]:
        """Return messages array ready for LLM API."""
        result = []
        if self._system_prompt:
            result.append({"role": "system", "content": self._system_prompt})
        result.extend({"role": role, "content": content} for role, content in self._messages)
        return result

    def update_system_prompt(self, content: str) -> None:
        """Update system prompt (used when project_metadata changes)."""
        self._system_prompt = content


@dataclass
class Session:
    """A conversational session with history and metadata."""
    session_id: str
    history: ConversationHistory
    metadata: ProjectMetadata


class SessionStore:
    """In-memory session storage.

    Sessions are volatile: lost on service restart. This is acceptable for the
    educational phase. Production deployments will need Redis or database backing.
    """

    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def create_session(self) -> str:
        """Create a new session and return its ID."""
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = Session(
            session_id=session_id,
            history=ConversationHistory(max_turns=6),
            metadata=ProjectMetadata(),
        )
        return session_id

    def get_session(self, session_id: str) -> Session | None:
        """Retrieve session by ID, or None if not found."""
        return self._sessions.get(session_id)
