from app.agents.mock import MockAgent
from app.api.deps import get_chat_service
from app.services.chat_service import ChatService


def test_get_chat_service_returns_a_chat_service_with_a_mock_agent():
    get_chat_service.cache_clear()

    service = get_chat_service()

    assert isinstance(service, ChatService)
    assert isinstance(service.agent, MockAgent)


def test_get_chat_service_is_memoized():
    get_chat_service.cache_clear()

    assert get_chat_service() is get_chat_service()
