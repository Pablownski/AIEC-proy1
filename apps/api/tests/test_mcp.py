import asyncio
import json
import sys
from unittest.mock import AsyncMock

import pytest
from jsonschema import ValidationError as SchemaError
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, ListToolsResult, Tool

from app.clients.mcp_client import MCPTools, open_catalog_tools
from app.core.config import Settings


async def test_real_stdio_discovery_and_all_tools():
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "tests.mcp_fixture_server"], env={}
    )
    async with asyncio.timeout(30):
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                client = MCPTools(session)
                tools = await client.discover()
                assert len(tools) == 5
                for name, args in [
                    ("search_movies", {"query": "x"}),
                    ("discover_movies", {"genre": "fantasía"}),
                    ("movie_details", {"movie_id": 11}),
                    ("search_books", {"title": "x"}),
                    ("book_details", {"volume_id": "volume_test"}),
                ]:
                    result = await client.call(name, json.dumps(args))
                    assert result.items
                invalid = await session.call_tool("movie_details", {"movie_id": -1})
                assert invalid.isError
                with pytest.raises(SchemaError):
                    await client.call("movie_details", '{"movie_id":-1}')
                with pytest.raises(ValueError):
                    await client.call("shell", "{}")


async def test_production_stdio_server_starts_without_reading_dotenv():
    async with asyncio.timeout(30):
        async with open_catalog_tools(Settings()) as client:
            tools = await client.discover()
            assert len(tools) == 5
            result = await client.call("search_movies", '{"query":"x"}')
            assert result.error == "configuration"


async def test_mcp_client_rejects_missing_tools_and_invalid_output():
    session = AsyncMock()
    session.list_tools.return_value = ListToolsResult(
        tools=[Tool(name="shell", inputSchema={"type": "object"})]
    )
    client = MCPTools(session)
    with pytest.raises(ValueError):
        await client.discover()
    client.schemas["search_movies"] = {"type": "object"}
    with pytest.raises(ValueError):
        await client.call("search_movies", "x" * 4001)
    for result in [
        CallToolResult(content=[], isError=True),
        CallToolResult(content=[], structuredContent={"source": "bad"}),
        CallToolResult(content=[], structuredContent={"x": "a" * 30001}),
    ]:
        session.call_tool.return_value = result
        with pytest.raises(ValueError):
            await client.call("search_movies", '{"query":"x"}')
