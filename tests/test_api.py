"""
Integration-style tests for the FastAPI routes.

All external services (OpenRouter, Supabase) are mocked.
Tests exercise the HTTP layer, request validation, and error handling.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.models.schemas import ChatResponse


# ── App factory with mocked services ─────────────────────────────────────────

def make_test_app():
    """
    Create a FastAPI test app with all external dependencies mocked.
    We patch the lifespan to inject mock services directly into app.state.
    """
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock, MagicMock
    from fastapi import FastAPI
    from app.api.routes import chat, health

    mock_settings = MagicMock()
    mock_settings.app_env = "test"
    mock_settings.is_production = False
    mock_settings.cors_origins = ["*"]
    mock_settings.log_level = "INFO"

    mock_agent_config = MagicMock()
    mock_agent_config.agent_name = "TestAgent"
    mock_agent_config.initial_state = "GREETING"
    mock_agent_config.states = {"GREETING": MagicMock(), "CLOSED": MagicMock()}

    mock_openrouter = MagicMock()
    mock_openrouter.health_check = AsyncMock(return_value=True)

    mock_db = MagicMock()
    mock_db.health_check = AsyncMock(return_value=True)
    mock_db.get_conversation = AsyncMock(return_value=None)
    mock_db.get_messages = AsyncMock(return_value=[])

    mock_state_machine = MagicMock()
    mock_state_machine.process_message = AsyncMock(
        return_value=ChatResponse(
            conversation_id="test-conv-id",
            reply="Hello! How can I help you today?",
            current_state="GREETING",
            is_terminal=False,
            turn_count=1,
        )
    )

    @asynccontextmanager
    async def mock_lifespan(app):
        app.state.settings = mock_settings
        app.state.agent_config = mock_agent_config
        app.state.openrouter_service = mock_openrouter
        app.state.supabase_service = mock_db
        app.state.state_machine = mock_state_machine
        yield

    app = FastAPI(lifespan=mock_lifespan)
    app.include_router(health.router)
    app.include_router(chat.router, prefix="/api/v1")
    return app


@pytest.fixture(scope="module")
def client():
    app = make_test_app()
    with TestClient(app) as c:
        yield c


# ── /health ───────────────────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_returns_200_when_services_ok(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "openrouter" in data["checks"]
        assert "supabase" in data["checks"]

    def test_response_has_version(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert "version" in resp.json()


# ── POST /api/v1/chat ─────────────────────────────────────────────────────────

class TestChatEndpoint:
    def test_new_conversation_returns_reply(self, client: TestClient) -> None:
        resp = client.post("/api/v1/chat", json={"message": "Hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["reply"] == "Hello! How can I help you today?"
        assert data["conversation_id"] == "test-conv-id"
        assert data["current_state"] == "GREETING"
        assert data["turn_count"] == 1
        assert data["is_terminal"] is False

    def test_empty_message_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/chat", json={"message": ""})
        assert resp.status_code == 422

    def test_missing_message_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/chat", json={})
        assert resp.status_code == 422

    def test_message_too_long_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/v1/chat", json={"message": "x" * 5000})
        assert resp.status_code == 422

    def test_conversation_id_passed_through(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/chat",
            json={"message": "Hello again", "conversation_id": "existing-id"},
        )
        assert resp.status_code == 200

    def test_metadata_accepted(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/chat",
            json={"message": "Hi", "metadata": {"user_id": "u123", "locale": "en-GB"}},
        )
        assert resp.status_code == 200

    def test_service_error_returns_503(self, client: TestClient) -> None:
        app = client.app
        original = app.state.state_machine.process_message
        app.state.state_machine.process_message = AsyncMock(
            side_effect=RuntimeError("OpenRouter is down")
        )
        try:
            resp = client.post("/api/v1/chat", json={"message": "Hello"})
            assert resp.status_code == 503
        finally:
            app.state.state_machine.process_message = original

    def test_not_found_returns_404(self, client: TestClient) -> None:
        app = client.app
        original = app.state.state_machine.process_message
        app.state.state_machine.process_message = AsyncMock(
            side_effect=ValueError("Conversation 'xyz' not found.")
        )
        try:
            resp = client.post(
                "/api/v1/chat",
                json={"message": "Hello", "conversation_id": "xyz"},
            )
            assert resp.status_code == 404
        finally:
            app.state.state_machine.process_message = original
