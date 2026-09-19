import pytest
from httpx import ASGITransport, AsyncClient

from app.agents.mock import MockAgent
from app.api.deps import get_chat_service
from app.main import app
from app.services.chat_service import ChatService


@pytest.fixture(autouse=True)
def _fast_mock_agent():
    """Override the default agent so tests don't pay the simulated latency."""

    fast_service = ChatService(agent=MockAgent(delay_seconds=0))
    app.dependency_overrides[get_chat_service] = lambda: fast_service
    yield
    app.dependency_overrides.pop(get_chat_service, None)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
