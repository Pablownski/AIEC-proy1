import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatMessage, ChatRequest, ChatRequestMessage, ChatResponse


def test_chat_message_generates_id_and_timestamp_when_omitted():
    message = ChatMessage(role="assistant", content="hola")

    assert message.id
    assert message.created_at is not None


def test_chat_message_rejects_empty_content():
    with pytest.raises(ValidationError):
        ChatMessage(role="user", content="")


def test_chat_message_rejects_invalid_role():
    with pytest.raises(ValidationError):
        ChatMessage(role="bot", content="hola")  # type: ignore[arg-type]


def test_chat_request_parses_nested_message():
    request = ChatRequest(
        conversation_id="conv-1",
        message=ChatRequestMessage(role="user", content="Hola"),
    )

    assert request.conversation_id == "conv-1"
    assert request.message.content == "Hola"


def test_chat_response_roundtrip_serialization():
    response = ChatResponse(
        conversation_id="conv-1",
        message=ChatMessage(role="assistant", content="Hola, ¿cómo puedo ayudarte?"),
    )

    payload = response.model_dump(mode="json")

    assert payload["conversation_id"] == "conv-1"
    assert payload["message"]["role"] == "assistant"
    assert "created_at" in payload["message"]
