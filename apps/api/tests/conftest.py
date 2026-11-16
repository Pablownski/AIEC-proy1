import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings

# Isolate every test, including app import, from local credentials on disk.
Settings.model_config["env_file"] = None

from app.agents.mock import MockAgent  # noqa: E402
from app.api.deps import get_chat_service  # noqa: E402
from app.main import app  # noqa: E402
from app.services.chat_service import ChatService  # noqa: E402


@pytest.fixture(autouse=True)
def _block_external_http(monkeypatch):
    async def blocked(*args, **kwargs):
        raise AssertionError("External HTTP is forbidden in unit tests")

    # ASGITransport used by route tests remains available.
    monkeypatch.setattr("httpx.AsyncHTTPTransport.handle_async_request", blocked)

    def blocked_sync(*args, **kwargs):
        raise AssertionError("External HTTP is forbidden in unit tests")

    monkeypatch.setattr("httpx.HTTPTransport.handle_request", blocked_sync)


@pytest.fixture(autouse=True)
def _isolate_groq_environment(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_BOOKS_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_PROVIDER", raising=False)


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
