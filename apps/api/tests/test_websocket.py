from fastapi.testclient import TestClient

from app.agents.mock import MockAgent
from app.api.deps import get_chat_service
from app.main import app
from app.services.chat_service import ChatService

app.dependency_overrides[get_chat_service] = lambda: ChatService(agent=MockAgent(delay_seconds=0))
client = TestClient(app)


def test_websocket_connects_and_streams_agent_events():
    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"conversation_id": "conv-1", "content": "Hola"})

        start = websocket.receive_json()
        message = websocket.receive_json()
        end = websocket.receive_json()

    assert start == {"type": "agent_start"}
    assert message["type"] == "agent_message"
    assert message["conversation_id"] == "conv-1"
    assert message["message"]["role"] == "assistant"
    assert end == {"type": "agent_end"}


def test_websocket_rejects_empty_message():
    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"conversation_id": "conv-1", "content": ""})

        response = websocket.receive_json()

    assert response == {"type": "error", "detail": "Mensaje inválido."}


def test_websocket_disconnect_closes_cleanly():
    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"conversation_id": "conv-1", "content": "Hola"})
        websocket.receive_json()
        websocket.receive_json()
        websocket.receive_json()
        websocket.close()


def test_websocket_reports_agent_errors_without_leaking_details():
    class FailingAgent:
        async def respond(self, message: str, conversation_id: str) -> str:
            raise RuntimeError("boom")

    app.dependency_overrides[get_chat_service] = lambda: ChatService(agent=FailingAgent())
    try:
        with client.websocket_connect("/ws/chat") as websocket:
            websocket.send_json({"conversation_id": "conv-1", "content": "Hola"})
            start = websocket.receive_json()
            response = websocket.receive_json()
    finally:
        app.dependency_overrides[get_chat_service] = lambda: ChatService(
            agent=MockAgent(delay_seconds=0)
        )

    assert start == {"type": "agent_start"}
    assert response["type"] == "error"
    assert "boom" not in response["detail"]
