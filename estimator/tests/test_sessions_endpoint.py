"""Tests for sessions API endpoint."""
import pytest
from fastapi.testclient import TestClient


def test_create_session(client: TestClient) -> None:
    """POST /sessions should return a new session_id."""
    response = client.post("/api/v1/sessions")

    assert response.status_code == 200
    body = response.json()
    assert "session_id" in body
    assert len(body["session_id"]) == 36  # UUID format
