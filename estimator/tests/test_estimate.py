"""Tests for the estimate endpoint."""

from unittest.mock import patch

from fastapi.testclient import TestClient

SAMPLE_TRANSCRIPTION = (
    "The client wants to build a mobile app for managing restaurant reservations. "
    "They need user registration, search with filters, and push notifications."
)

MOCK_RESULT = {
    "estimation": "## Mobile App\n\n| Task | Hours | Cost (EUR) |\n|------|------:|-----------:|\n| Auth | 20 | 1250 |",
    "model": "gpt-4o-mini",
    "provider": "openai",
    "usage": {"input_tokens": 100, "output_tokens": 200, "total_tokens": 300},
    "cache_hit": False,
    "latency_ms": 1500.0,
    "fallback_used": False,
}


@patch("app.routers.estimations.generate_estimation", return_value=MOCK_RESULT)
def test_estimate_returns_200(mock_generate: object, client: TestClient) -> None:
    response = client.post(
        "/api/v1/estimate",
        json={"transcription": SAMPLE_TRANSCRIPTION},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["estimation"].startswith("## Mobile App")
    assert data["model"] == "gpt-4o-mini"
    assert data["usage"]["total_tokens"] == 300
    assert data["cache_hit"] is False
    assert data["latency_ms"] == 1500.0


@patch("app.routers.estimations.generate_estimation", return_value={**MOCK_RESULT, "cache_hit": True})
def test_estimate_returns_cache_hit(mock_generate: object, client: TestClient) -> None:
    response = client.post(
        "/api/v1/estimate",
        json={"transcription": SAMPLE_TRANSCRIPTION},
    )
    assert response.status_code == 200
    assert response.json()["cache_hit"] is True


def test_estimate_rejects_short_transcription(client: TestClient) -> None:
    response = client.post(
        "/api/v1/estimate",
        json={"transcription": "too short"},
    )
    assert response.status_code == 422
