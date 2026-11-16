import json
import logging
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from mcp.types import CallToolResult, ListToolsResult, Tool

from app.agents.groq_agent import GroqAgent
from app.clients.catalog import CatalogClient
from app.clients.mcp_client import MCPTools
from app.core.config import Settings
from app.tools.models import INPUTS
from tests.test_catalog import BOOK
from tests.test_comparison_regression import request_tool
from tests.test_groq_client import completion


@pytest.mark.parametrize("operation", ["search_books", "book_details"])
@pytest.mark.parametrize("batched", [False, True])
async def test_books_429_stops_four_searches_without_more_groq_rounds(caplog, operation, batched):
    requests = []
    recovering = False

    def handle(request):
        requests.append(request)
        if recovering:
            return httpx.Response(
                200, json=BOOK if operation == "book_details" else {"items": [BOOK]}
            )
        return httpx.Response(
            429,
            json={
                "error": {"message": "private-body", "errors": [{"reason": "rateLimitExceeded"}]}
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        catalog = CatalogClient(Settings(google_books_api_key="private-key"), http)
        session = AsyncMock()
        session.list_tools.return_value = ListToolsResult(
            tools=[
                Tool(name=name, inputSchema=model.model_json_schema())
                for name, model in INPUTS.items()
            ]
        )

        async def call_tool(name, arguments):
            result = await catalog.execute(name, arguments)
            return CallToolResult(content=[], structuredContent=result.model_dump(mode="json"))

        session.call_tool.side_effect = call_tool

        @asynccontextmanager
        async def connect(settings):
            yield MCPTools(session)

        client = AsyncMock()
        agent = GroqAgent(Settings(), client)
        async with agent.memory.turn("one") as entry:
            entry.commit(
                "Recomienda",
                "Tres películas de TMDB",
                [
                    {"role": "user", "content": "Recomienda"},
                    {"role": "assistant", "content": "Tres películas de TMDB"},
                ],
                [],
            )
        before = list(entry.turns)
        arguments = (
            {"title": "private-query"}
            if operation == "search_books"
            else {"volume_id": "test_volume"}
        )
        calls = [request_tool(operation, arguments, index) for index in range(4)]
        if batched:
            calls = [
                completion(
                    content=None,
                    tool_calls=[
                        call.choices[0].message.tool_calls[0].model_dump() for call in calls
                    ],
                )
            ]
        client.complete.side_effect = [*calls, completion(content="Comparación inventada")]
        with (
            patch("app.agents.groq_agent.open_catalog_tools", connect),
            caplog.at_level(logging.INFO),
        ):
            reply = await agent.respond("Compara con sus libros", "one")
        assert "Google Books" in reply
        assert "no puedo verificar" in reply
        assert "inventada" not in reply
        assert len(requests) == 1
        assert client.complete.await_count == 1
        assert entry.turns == before
        assert not entry.artifacts and not entry.tool_cache
        assert "private-key" not in caplog.text
        assert "private-body" not in caplog.text
        assert "private-query" not in caplog.text
        events = [json.loads(record.getMessage()) for record in caplog.records]
        assert any(event.get("status_code") == 429 for event in events)
        assert events[-1]["code"] == "books_unavailable"
        # A later manual request can use Books after recovery: no persistent failure cache.
        recovering = True
        client.complete.side_effect = [
            request_tool(operation, arguments, 5),
            completion(content="Datos bibliográficos disponibles"),
        ]
        with patch("app.agents.groq_agent.open_catalog_tools", connect):
            reply = await agent.respond("Intenta verificar de nuevo", "one")
        assert "Datos bibliográficos" in reply
        assert len(requests) == 2
        assert len(entry.turns) == 2
        assert entry.artifacts and entry.tool_cache
