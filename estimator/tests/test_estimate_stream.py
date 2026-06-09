"""Tests for the SSE streaming estimate endpoint."""

import json
from unittest.mock import patch

from fastapi.testclient import TestClient

SAMPLE_TRANSCRIPTION = (
    "The client wants to build a mobile app for managing restaurant reservations. "
    "They need user registration, search with filters, and push notifications."
)


def _mock_stream():
    def chunk_iter():
        yield "Hello "
        yield "world"

    meta = {
        "model": "gpt-4o-mini",
        "provider": "openai",
        "usage": {"input_tokens": 50, "output_tokens": 10, "total_tokens": 60},
        "cache_hit": False,
        "latency_ms": 800.0,
        "fallback_used": False,
    }
    return chunk_iter(), meta


def _parse_sse(body: str) -> tuple[list[str], dict | None]:
    """Parse SSE body into text chunks and optional meta event."""
    chunks: list[str] = []
    meta: dict | None = None
    event_type = "message"
    for line in body.split("\n"):
        if line.startswith("event:"):
            event_type = line[6:].strip()
        elif line.startswith("data:"):
            raw = line[5:].strip()
            if event_type == "meta":
                meta = json.loads(json.loads(raw))
            else:
                chunks.append(json.loads(raw))
            event_type = "message"
    return chunks, meta


@patch("app.routers.estimations.stream_estimation", return_value=_mock_stream())
def test_estimate_stream_returns_sse_chunks(mock_stream: object, client: TestClient) -> None:
    with client.stream(
        "POST",
        "/api/v1/estimate/stream",
        json={"transcription": SAMPLE_TRANSCRIPTION},
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        body = response.read().decode()
        chunks, meta = _parse_sse(body)

        assert chunks == ["Hello ", "world"]
        assert meta is not None
        assert meta["model"] == "gpt-4o-mini"
        assert meta["usage"]["total_tokens"] == 60
