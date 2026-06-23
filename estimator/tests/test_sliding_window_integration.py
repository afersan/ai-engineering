import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_sliding_window_limits_history():
    """After 8 turns, history should only contain last 6 turns + system prompt."""
    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create session
        session_resp = await client.post("/api/v1/sessions")
        session_id = session_resp.json()["session_id"]

        # Send 8 turns (exceeds max_turns=6)
        for i in range(1, 9):
            form_data = {
                "transcript": f"Turn {i}: Add feature {i}",
                "project_type": "web_saas",
                "detail_level": "summary",
                "output_format": "narrative",
            }
            resp = await client.post(
                f"/api/v1/sessions/{session_id}/estimate",
                data=form_data,
            )
            assert resp.status_code == 200

        # Verify turn number is 8
        final_body = resp.json()
        assert final_body["turn_number"] == 8

        # Check session history directly
        from app.routers.sessions import get_session_store
        store = get_session_store()
        session = store.get_session(session_id)

        messages = session.history.to_messages_list()

        # Should have: 1 system + (6 turns * 2 messages) = 13 messages
        assert len(messages) <= 13, f"History too long: {len(messages)} messages"
        assert messages[0]["role"] == "system"

        # First user message should NOT be Turn 1 (it should be discarded)
        user_messages = [m["content"] for m in messages if m["role"] == "user"]
        assert "Turn 1" not in user_messages[0]
        assert "Turn 3" in user_messages[0] or "Turn 4" in user_messages[0]  # Depending on exact window
