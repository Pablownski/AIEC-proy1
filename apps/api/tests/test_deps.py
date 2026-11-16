from unittest.mock import AsyncMock, patch

from app.agents.groq_agent import GroqAgent
from app.agents.mock import MockAgent
from app.api.deps import get_chat_service
from app.core.config import Settings
from app.services.chat_service import ChatService


def test_get_chat_service_returns_a_chat_service_with_a_mock_agent():
    get_chat_service.cache_clear()

    service = get_chat_service()

    assert isinstance(service, ChatService)
    assert isinstance(service.agent, MockAgent)


def test_get_chat_service_is_memoized():
    get_chat_service.cache_clear()

    assert get_chat_service() is get_chat_service()


async def test_groq_provider_is_wired_and_closed():
    from app.main import app, lifespan

    get_chat_service.cache_clear()
    with (
        patch("app.api.deps.get_settings", return_value=Settings(agent_provider="groq")),
        patch("app.api.deps.GroqClient", return_value=AsyncMock()) as factory,
    ):
        async with lifespan(app):
            service = get_chat_service()
            assert isinstance(service.agent, GroqAgent)
        factory.return_value.close.assert_awaited_once()
    get_chat_service.cache_clear()
