"""Regression transcript: three recommendations, then an evidence-based comparison."""

import json
import logging
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from mcp.types import CallToolResult, ListToolsResult, Tool

from app.agents.groq_agent import RATE_LIMIT_ERROR, SAFE_ERROR, GroqAgent
from app.clients.catalog import CatalogClient
from app.clients.groq_client import GroqClientError
from app.clients.mcp_client import MCPTools
from app.core.config import Settings
from app.tools.comparison import compare_movies
from app.tools.models import INPUTS
from tests.test_catalog import BOOK, MOVIE
from tests.test_groq_client import completion


def request_tool(name, arguments, index):
    return completion(
        content=None,
        tool_calls=[
            {
                "id": f"call-{index}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ],
    )


@pytest.fixture
async def comparison_setup():
    def handle(request):
        if request.url.host == "api.themoviedb.org":
            if request.url.path.endswith("/search/movie"):
                return httpx.Response(200, json={"results": [MOVIE]})
            if request.url.path.endswith("/discover/movie"):
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {**MOVIE, "id": index, "title": f"Fantasía {index}"}
                            for index in (11, 12, 13)
                        ]
                    },
                )
            index = int(request.url.path.rsplit("/", 1)[-1])
            return httpx.Response(200, json={**MOVIE, "id": index, "title": f"Fantasía {index}"})
        return httpx.Response(
            200, json=BOOK if request.url.path.endswith("/test_volume") else {"items": [BOOK]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        catalog = CatalogClient(Settings(tmdb_api_key="test-key"), http)
        session = AsyncMock()
        session.list_tools.return_value = ListToolsResult(
            tools=[
                Tool(name=name, inputSchema=model.model_json_schema())
                for name, model in INPUTS.items()
            ]
        )

        async def call_tool(name, arguments):
            result = (
                await compare_movies(catalog, arguments["movie_ids"])
                if name == "compare_movies"
                else await catalog.execute(name, arguments)
            )
            return CallToolResult(content=[], structuredContent=result.model_dump(mode="json"))

        session.call_tool.side_effect = call_tool

        @asynccontextmanager
        async def connect(settings):
            yield MCPTools(session)

        client = AsyncMock()
        with patch("app.agents.groq_agent.open_catalog_tools", connect):
            yield client, session


def comparison_steps():
    # Three detail lookups, three book searches and one selected book's details:
    # seven serial tool calls and one final LLM answer, within the 8-tool budget.
    return [
        *(request_tool("movie_details", {"movie_id": index}, index) for index in (11, 12, 13)),
        *(
            request_tool("search_books", {"title": f"Fantasía {index}"}, index + 10)
            for index in (11, 12, 13)
        ),
        request_tool("book_details", {"volume_id": "test_volume"}, 30),
    ]


async def seed_recommendations(agent, client):
    client.complete.side_effect = [
        request_tool("discover_movies", {"genre": "fantasía"}, 0),
        completion(content="Fantasía 11, Fantasía 12 y Fantasía 13"),
    ]
    assert (
        await agent.respond("Recomiéndame tres películas de fantasía", "comparison") != SAFE_ERROR
    )


async def test_three_movie_comparison_fits_tool_budget_and_preserves_context(comparison_setup):
    client, session = comparison_setup
    agent = GroqAgent(Settings(), client)
    await seed_recommendations(agent, client)
    client.complete.side_effect = [
        *comparison_steps(),
        completion(
            content="Las fuentes consultadas aportan créditos y datos bibliográficos. "
            "No puedo confirmar diferencias de escenas. Como opinión, vale la pena por su género."
        ),
    ]
    reply = await agent.respond(
        "¿Cuál de las tres está basada en un libro? Compárala.", "comparison"
    )
    assert reply != SAFE_ERROR
    assert "Como opinión" in reply
    assert session.call_tool.await_count == 8  # Discovery + 7 calls in the follow-up.
    context = client.complete.call_args.args[0]
    assert "Fantasía 11" in str(context)
    assert "Fantasía 12" in str(context)
    assert "Fantasía 13" in str(context)
    assert "Libro de prueba" in str(context)
    assert len(agent.memory.entries["comparison"].turns) == 2


async def test_five_rounds_are_insufficient_and_failure_preserves_previous_turn(
    comparison_setup, caplog
):
    client, _ = comparison_setup
    agent = GroqAgent(Settings(), client, max_rounds=5)
    await seed_recommendations(agent, client)
    entry = agent.memory.entries["comparison"]
    previous = list(entry.turns)
    previous_artifacts = list(entry.artifacts)
    client.complete.side_effect = [*comparison_steps(), completion(content="Comparación")]
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        reply = await agent.respond("Compara las tres con libros", "comparison")
    assert reply == SAFE_ERROR
    assert entry.turns == previous
    assert entry.artifacts == previous_artifacts
    assert entry.last_input == "Recomiéndame tres películas de fantasía"
    event = json.loads(caplog.records[-1].getMessage())
    assert event["event"] == "agent_turn_failed"
    assert event["code"] == "tools_after_limit"
    assert event["rounds"] == 5
    assert event["memory_committed"] is False


async def test_eight_tools_reserve_ninth_completion_without_extra_calls(comparison_setup):
    client, session = comparison_setup
    agent = GroqAgent(Settings(), client)
    await seed_recommendations(agent, client)
    client.complete.reset_mock()
    client.complete.side_effect = [
        *(request_tool("movie_details", {"movie_id": 11}, index) for index in range(8)),
        completion(content="Comparación limitada a los datos consultados"),
    ]
    assert await agent.respond("Compara", "comparison") != SAFE_ERROR
    assert client.complete.await_count == 9
    assert client.complete.call_args.kwargs["allow_tools"] is False
    assert (
        session.call_tool.await_count == 2
    )  # One discovery + one detail; duplicate calls use cache.


@pytest.mark.parametrize("mode", ["transport", "catalog"])
async def test_failed_tool_turn_is_not_saved_as_success(comparison_setup, caplog, mode):
    client, session = comparison_setup
    agent = GroqAgent(Settings(), client)
    await seed_recommendations(agent, client)
    entry = agent.memory.entries["comparison"]
    before = list(entry.turns)
    if mode == "transport":
        session.call_tool.side_effect = RuntimeError("sensitive-error-body")
    else:
        session.call_tool.side_effect = None
        session.call_tool.return_value = CallToolResult(
            content=[],
            structuredContent={"source": "google_books", "items": [], "error": "authentication"},
        )
    client.complete.side_effect = [
        request_tool("search_books", {"title": "private-query"}, 1),
        completion(content="No pude verificar el libro"),
    ]
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        await agent.respond("private-user-input", "comparison")
    assert entry.turns == before
    assert entry.last_input == "Recomiéndame tres películas de fantasía"
    events = [json.loads(record.getMessage()) for record in caplog.records]
    assert events[-1]["code"] == "partial_tool_failure"
    assert events[-1]["memory_committed"] is False
    assert events[-2]["tool"] == "search_books"
    assert events[-2]["code"] == ("unexpected" if mode == "transport" else "catalog_authentication")
    assert "sensitive-error-body" not in caplog.text
    assert "private-query" not in caplog.text
    assert "private-user-input" not in caplog.text


@pytest.mark.parametrize(
    "code", ["timeout", "authentication", "rate_limit", "provider", "response"]
)
async def test_provider_failure_has_safe_diagnostics_without_saving_turn(
    comparison_setup, caplog, code
):
    client, _ = comparison_setup
    agent = GroqAgent(Settings(), client)
    await seed_recommendations(agent, client)
    status = {"authentication": 401, "rate_limit": 429, "provider": 400}.get(code)
    client.complete.side_effect = GroqClientError(
        code, "secret-exception-marker", status_code=status
    )
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        expected = RATE_LIMIT_ERROR if code == "rate_limit" else SAFE_ERROR
        assert await agent.respond("private-user-input", "comparison") == expected
    event = json.loads(caplog.records[-1].getMessage())
    assert event["code"] == f"groq_{code}"
    assert event["stage"] == "llm"
    assert event.get("status_code") == status
    assert len(agent.memory.entries["comparison"].turns) == 1
    assert "secret-exception-marker" not in caplog.text
    assert "private-user-input" not in caplog.text
    assert "comparison" not in caplog.text  # No raw conversation ID.


async def test_mcp_shutdown_error_does_not_commit_and_logs_safe_group_code(
    comparison_setup, caplog
):
    client, session = comparison_setup
    agent = GroqAgent(Settings(), client)
    await seed_recommendations(agent, client)

    @asynccontextmanager
    async def broken_close(settings):
        yield MCPTools(session)
        raise ExceptionGroup("private-group", [TimeoutError("private-child")])

    client.complete.side_effect = [completion(content="Comparación provisional")]
    with (
        patch("app.agents.groq_agent.open_catalog_tools", broken_close),
        caplog.at_level(logging.INFO, logger="uvicorn.error"),
    ):
        assert await agent.respond("Compara", "comparison") == SAFE_ERROR
    assert len(agent.memory.entries["comparison"].turns) == 1
    event = json.loads(caplog.records[-1].getMessage())
    assert event["stage"] == "mcp_close"
    assert event["code"] == "timeout"
    assert "private-group" not in caplog.text
    assert "private-child" not in caplog.text


async def test_unknown_tool_name_is_not_reflected_in_logs(comparison_setup, caplog):
    client, _ = comparison_setup
    agent = GroqAgent(Settings(), client)
    client.complete.side_effect = [
        request_tool("private-tool-name", {}, 0),
        completion(content="No pude verificar los datos"),
    ]
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        await agent.respond("private-user-input", "private-conversation-id")
    events = [json.loads(record.getMessage()) for record in caplog.records]
    assert events[0]["tool"] == "unknown"
    assert events[0]["code"] == "validation"
    assert events[-1]["memory_committed"] is False
    assert "private-tool-name" not in caplog.text
    assert "private-user-input" not in caplog.text
    assert "private-conversation-id" not in caplog.text
