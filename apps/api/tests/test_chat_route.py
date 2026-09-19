from app.api.deps import get_chat_service
from app.main import app
from app.services.chat_service import ChatService


async def test_send_message_returns_assistant_reply(client):
    response = await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": "conv-1",
            "message": {"role": "user", "content": "Hola"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == "conv-1"
    assert body["message"]["role"] == "assistant"
    assert body["message"]["content"]


async def test_send_message_rejects_empty_content(client):
    response = await client.post(
        "/api/v1/chat",
        json={"conversation_id": "conv-1", "message": {"role": "user", "content": ""}},
    )

    assert response.status_code == 422


async def test_send_message_rejects_missing_fields(client):
    response = await client.post("/api/v1/chat", json={"conversation_id": "conv-1"})

    assert response.status_code == 422


async def test_send_message_returns_502_on_agent_failure(client):
    class FailingAgent:
        async def respond(self, message: str, conversation_id: str) -> str:
            raise RuntimeError("boom")

    app.dependency_overrides[get_chat_service] = lambda: ChatService(agent=FailingAgent())
    try:
        response = await client.post(
            "/api/v1/chat",
            json={
                "conversation_id": "conv-1",
                "message": {"role": "user", "content": "Hola"},
            },
        )
    finally:
        app.dependency_overrides.pop(get_chat_service, None)

    assert response.status_code == 502
    assert "Intenta nuevamente" in response.json()["detail"]


async def test_send_message_preserves_conversation_id(client):
    response = await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": "conv-xyz",
            "message": {"role": "user", "content": "¿Qué es AGIChat?"},
        },
    )

    assert response.json()["conversation_id"] == "conv-xyz"
