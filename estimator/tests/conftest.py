import os

# Configurar entorno antes de importar la aplicación (Settings valida API keys al arrancar).
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("CACHE_ENABLED", "false")
os.environ.setdefault("LLM_PROVIDER", "openai")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Provide a FastAPI test client configured with the application."""
    return TestClient(app)
