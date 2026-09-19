import pytest

from app.agents.base import Agent
from app.schemas.chat import ChatRequestMessage
from app.services.chat_service import ChatService


class _StubAgent:
    def __init__(self, reply: str = "stub reply", raise_error: bool = False) -> None:
        self.reply = reply
        self.raise_error = raise_error
        self.calls: list[tuple[str, str]] = []

    async def respond(self, message: str, conversation_id: str) -> str:
        self.calls.append((message, conversation_id))
        if self.raise_error:
            raise RuntimeError("agent exploded")
        return self.reply


async def test_chat_service_returns_assistant_message():
    agent = _StubAgent(reply="hola de vuelta")
    service = ChatService(agent=agent)

    response = await service.handle_message(
        conversation_id="conv-1",
        message=ChatRequestMessage(role="user", content="Hola"),
    )

    assert response.conversation_id == "conv-1"
    assert response.message.role == "assistant"
    assert response.message.content == "hola de vuelta"


async def test_chat_service_forwards_content_and_conversation_id_to_agent():
    agent = _StubAgent()
    service = ChatService(agent=agent)

    await service.handle_message(
        conversation_id="conv-42",
        message=ChatRequestMessage(role="user", content="¿Cómo estás?"),
    )

    assert agent.calls == [("¿Cómo estás?", "conv-42")]


async def test_chat_service_wraps_agent_errors():
    agent = _StubAgent(raise_error=True)
    service = ChatService(agent=agent)

    with pytest.raises(RuntimeError):
        await service.handle_message(
            conversation_id="conv-1",
            message=ChatRequestMessage(role="user", content="Hola"),
        )


def test_chat_service_accepts_any_agent_protocol_implementation():
    class InlineAgent:
        async def respond(self, message: str, conversation_id: str) -> str:
            return "ok"

    service = ChatService(agent=InlineAgent())

    assert isinstance(service.agent, Agent)
