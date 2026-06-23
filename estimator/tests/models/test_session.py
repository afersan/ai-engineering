from app.models.session import ProjectMetadata, ConversationHistory, Session, SessionStore


def test_project_metadata_empty_initialization():
    """An empty ProjectMetadata should have all optional fields as None/empty."""
    metadata = ProjectMetadata()
    assert metadata.project_name is None
    assert metadata.assumed_team_size is None
    assert metadata.mentioned_technologies == []
    assert metadata.agreed_scope == ""


def test_conversation_history_sliding_window():
    """History should preserve only last N turns and always keep system prompt."""
    history = ConversationHistory(max_turns=2)

    # Add system prompt
    history.add_message(role="system", content="You are an estimator")

    # Add 3 turns (6 messages) - should keep only last 2 turns + system
    history.add_message(role="user", content="Turn 1 user")
    history.add_message(role="assistant", content="Turn 1 assistant")

    history.add_message(role="user", content="Turn 2 user")
    history.add_message(role="assistant", content="Turn 2 assistant")

    history.add_message(role="user", content="Turn 3 user")
    history.add_message(role="assistant", content="Turn 3 assistant")

    messages = history.to_messages_list()

    # Should have: system + 2 turns (4 messages) = 5 total
    assert len(messages) == 5
    assert messages[0]["role"] == "system"
    assert messages[1]["content"] == "Turn 2 user"  # Turn 1 discarded
    assert messages[4]["content"] == "Turn 3 assistant"


def test_session_store_create_and_retrieve():
    """SessionStore should create sessions with unique IDs and allow retrieval."""
    store = SessionStore()

    session_id = store.create_session()
    assert session_id is not None
    assert len(session_id) == 36  # UUID format

    session = store.get_session(session_id)
    assert session is not None
    assert session.session_id == session_id
    assert isinstance(session.history, ConversationHistory)
    assert isinstance(session.metadata, ProjectMetadata)

    # Non-existent session should return None
    assert store.get_session("nonexistent") is None
