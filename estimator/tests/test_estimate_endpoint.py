from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.services import llm_service

SAMPLE_ESTIMATION = """## Project estimate

| phase | duration_weeks | cost_eur | confidence_pct |
|-------|----------------|----------|----------------|
| MVP | 4 | 20,000 | 80% |
"""

SAMPLE_PAYLOAD = {
    "description": "We need a small CRM with auth, contacts and roles. MVP six weeks.",
    "project_type": "web_saas",
    "detail_level": "medium",
    "output_format": "phases_table",
}


def _fake_response(*, estimation: str = SAMPLE_ESTIMATION) -> dict:
    return {
        "estimation": estimation,
        "model": "gpt-4o-mini",
        "provider": "openai",
        "finish_reason": "stop",
        "usage": {"input_tokens": 1234, "output_tokens": 567, "total_tokens": 1801},
        "latency_ms": 12,
        "cost_usd": 0.001234,
        "cache_hit": False,
    }


@pytest.fixture
def call_log(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[dict]]:
    """Replace the LLM seam with a recording fake. Returns the list of calls."""
    calls: list[dict] = []

    def fake(
        *,
        system_prompt: str,
        user_message: str,
        model_override: str | None = None,
        max_tokens: int = 4000,
        thinking_budget: int | None = None,
    ) -> dict:
        calls.append(
            {
                "system_prompt": system_prompt,
                "user_message": user_message,
                "model_override": model_override,
                "max_tokens": max_tokens,
                "thinking_budget": thinking_budget,
            }
        )
        return _fake_response()

    monkeypatch.setattr(llm_service, "_invoke_llm", fake)
    yield calls


def test_estimate_returns_text_and_prompt_version(
    client: TestClient, call_log: list[dict]
) -> None:
    response = client.post("/api/v1/estimate", json=SAMPLE_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == SAMPLE_ESTIMATION
    assert body["prompt_version"] == "v1"
    assert len(call_log) == 1


def test_estimate_uses_separate_system_and_user_messages(
    client: TestClient, call_log: list[dict]
) -> None:
    response = client.post("/api/v1/estimate", json=SAMPLE_PAYLOAD)
    assert response.status_code == 200

    call = call_log[0]
    assert "senior project estimator" in call["system_prompt"]
    assert "<project_description>" in call["user_message"]
    assert SAMPLE_PAYLOAD["description"] in call["user_message"]
    assert SAMPLE_PAYLOAD["description"] not in call["system_prompt"]


def test_estimate_rejects_short_description(client: TestClient) -> None:
    payload = {**SAMPLE_PAYLOAD, "description": "too short"}
    response = client.post("/api/v1/estimate", json=payload)
    assert response.status_code == 422


def test_estimate_system_prompt_reflects_output_format(
    client: TestClient, call_log: list[dict]
) -> None:
    payload = {**SAMPLE_PAYLOAD, "output_format": "narrative"}
    response = client.post("/api/v1/estimate", json=payload)
    assert response.status_code == 200
    assert "one row per project phase" not in call_log[0]["system_prompt"]
    assert "flowing prose estimate" in call_log[0]["system_prompt"]
