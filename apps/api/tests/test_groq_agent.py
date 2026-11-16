import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.agents.groq_agent import SAFE_ERROR, SYSTEM_PROMPT, GroqAgent
from app.api.deps import get_chat_service
from app.clients.catalog import CatalogClient
from app.core.config import Settings
from app.main import app
from app.services.chat_service import ChatService
from app.tools.models import ToolResult
from tests.test_catalog import MOVIE
from tests.test_groq_client import completion


def tool_reply(*names):
    return completion(
        content=None,
        tool_calls=[
            {
                "id": f"call-{index}",
                "type": "function",
                "function": {"name": name, "arguments": '{"query":"x"}'},
            }
            for index, name in enumerate(names)
        ],
    )


@pytest.fixture
def agent_setup():
    tools = AsyncMock()
    tools.discover.return_value = [{"type": "function", "function": {"name": "search_movies"}}]
    tools.call.return_value = ToolResult(source="tmdb", items=[CatalogClient._movie(MOVIE)])

    @asynccontextmanager
    async def connect(settings):
        yield tools

    client = AsyncMock()
    with patch("app.agents.groq_agent.open_catalog_tools", connect):
        yield GroqAgent(Settings(), client), client, tools


async def test_dynamic_multiple_calls_and_followup_memory(agent_setup):
    agent, client, tools = agent_setup
    client.complete.side_effect = [
        tool_reply("search_movies", "search_books"),
        tool_reply("movie_details"),
        completion(content="Tres películas de fantasía"),
        completion(content="Puedo comparar con libros, pero no puedo confirmar la relación."),
    ]
    await agent.respond("Tres películas de fantasía", "one")
    reply = await agent.respond("¿Cuál de esas está basada en un libro?", "one")
    assert "no puedo confirmar" in reply
    assert tools.call.await_count == 3
    context = client.complete.call_args.args[0]
    assert context[0]["content"] == SYSTEM_PROMPT
    assert any(msg.get("content") == "Tres películas de fantasía" for msg in context)
    assert not any(msg["role"] == "tool" for msg in context)
    assert "Obra de prueba" in str(context)
    assert len(agent.memory.entries["one"].turns) == 2
    assert agent.memory.entries["one"].artifacts


async def test_conversation_isolation_and_immediate_retry_dedup(agent_setup):
    agent, client, _ = agent_setup
    client.complete.return_value = completion(content="Puedo comparar películas y libros")
    assert await agent.respond("Hola", "one") == await agent.respond("Hola", "one")
    assert client.complete.await_count == 1
    await agent.respond("Otra conversación", "two")
    assert len(client.complete.call_args.args[0]) == 2
    assert "Hola" not in str(client.complete.call_args.args[0])


@pytest.mark.parametrize("mode", ["provider", "rounds", "tool_count", "empty", "long"])
async def test_failures_do_not_commit_and_can_retry(agent_setup, mode):
    agent, client, _ = agent_setup
    if mode == "provider":
        client.complete.side_effect = RuntimeError("private-detail")
    elif mode in {"empty", "long"}:
        client.complete.return_value = completion(content="" if mode == "empty" else "x" * 12001)
    else:
        agent.max_rounds = 2
        agent.max_tool_calls = 1 if mode == "tool_count" else 8
        client.complete.return_value = tool_reply("search_movies", "search_books")
    assert await agent.respond("Busca", "one") == SAFE_ERROR
    assert not agent.memory.entries["one"].turns
    assert agent.active == 0
    client.complete.side_effect = None
    client.complete.return_value = completion(content="Respuesta recuperada")
    assert (await agent.respond("Busca", "one")).startswith("Respuesta recuperada")


async def test_tool_error_is_safe_feedback_to_model(agent_setup):
    agent, client, tools = agent_setup
    tools.call.side_effect = ValueError("private-detail")
    client.complete.side_effect = [
        tool_reply("unknown"),
        completion(content="No hay datos disponibles"),
    ]
    assert "No hay datos" in await agent.respond("Busca", "one")
    history = str(client.complete.call_args.args[0])
    assert "private-detail" not in history
    assert "servicio no disponible" in history


async def test_no_results_and_unknown_relation_are_available_to_model(agent_setup):
    agent, client, tools = agent_setup
    tools.call.return_value = ToolResult(source="tmdb")
    client.complete.side_effect = [
        tool_reply("search_movies"),
        completion(content="Una película inventada con título no obtenido"),
    ]
    assert "No hay resultados" in await agent.respond("Busca", "one")
    assert "inventada" not in agent.memory.entries["one"].last_reply
    assert '"items":[]' in str(client.complete.call_args.args[0])
    assert "Títulos similares no prueban relación" in SYSTEM_PROMPT
    assert "inferencias" in SYSTEM_PROMPT


async def test_timeout_and_concurrency_limits(agent_setup):
    agent, client, _ = agent_setup
    agent.active = 8
    assert "ocupado" in await agent.respond("Hola", "one")
    client.complete.assert_not_called()
    agent.active = 0
    agent.timeout_seconds = 0.001

    async def slow(*args, **kwargs):
        await asyncio.sleep(1)

    client.complete.side_effect = slow
    assert await agent.respond("Hola", "one") == SAFE_ERROR
    assert not agent.memory.entries["one"].turns


@pytest.mark.parametrize(
    "text,cid", [(" ", "one"), ("x" * 4001, "one"), ("x", ""), ("x", "a" * 129)]
)
async def test_input_bounds(agent_setup, text, cid):
    with pytest.raises(ValueError):
        await agent_setup[0].respond(text, cid)


async def test_only_source_urls_survive_and_client_is_closed(agent_setup):
    agent, client, _ = agent_setup
    result = ToolResult(source="tmdb", items=[CatalogClient._movie(MOVIE)])
    filtered = agent._filter_urls("https://evil.test https://www.themoviedb.org/movie/11", [result])
    assert "evil.test" not in filtered
    assert "https://www.themoviedb.org/movie/11" in filtered
    await agent.close()
    client.close.assert_awaited_once()


async def test_real_agent_through_existing_http_contract(agent_setup, client):
    agent, groq, _ = agent_setup
    groq.complete.side_effect = [
        tool_reply("search_movies"),
        completion(content="Respuesta real simulada"),
    ]
    app.dependency_overrides[get_chat_service] = lambda: ChatService(agent=agent)
    response = await client.post(
        "/api/v1/chat",
        json={
            "conversation_id": "http-one",
            "message": {"role": "user", "content": "Busca películas"},
        },
    )
    assert response.status_code == 200
    assert response.json()["message"]["content"].startswith("Respuesta real simulada")
    assert "comparar películas con libros" in response.json()["message"]["content"]
    assert response.json()["message"]["role"] == "assistant"
    assert response.json()["conversation_id"] == "http-one"
    assert response.json()["message"]["created_at"]


def test_real_agent_through_existing_websocket_contract(agent_setup):
    agent, groq, _ = agent_setup
    groq.complete.return_value = completion(content="Puedo comparar películas y libros")
    app.dependency_overrides[get_chat_service] = lambda: ChatService(agent=agent)
    with TestClient(app) as client, client.websocket_connect("/ws/chat") as socket:
        socket.send_json({"conversation_id": "ws-one", "content": "Hola"})
        assert socket.receive_json()["type"] == "agent_start"
        message = socket.receive_json()
        assert message["type"] == "agent_message"
        assert message["message"]["content"] == "Puedo comparar películas y libros"
        assert socket.receive_json()["type"] == "agent_end"
