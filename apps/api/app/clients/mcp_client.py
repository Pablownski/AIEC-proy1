"""Real MCP discovery and calls through an owned, fixed STDIO subprocess."""

from __future__ import annotations

import json
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from groq.types.chat import ChatCompletionToolParam
from jsonschema import validate
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.core.config import Settings
from app.tools.models import INPUTS, ToolResult


class MCPTools:
    def __init__(self, session: ClientSession) -> None:
        self.session = session
        self.schemas: dict[str, dict[str, Any]] = {}

    async def discover(self) -> list[ChatCompletionToolParam]:
        response = await self.session.list_tools()
        tools: list[ChatCompletionToolParam] = []
        for tool in response.tools:
            if tool.name in INPUTS:
                self.schemas[tool.name] = tool.inputSchema
                tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description or tool.name,
                            "parameters": tool.inputSchema,
                        },
                    }
                )
        if not tools:
            raise ValueError("No hay herramientas MCP disponibles")
        return tools

    async def call(self, name: str, arguments: str) -> ToolResult:
        if name not in self.schemas or len(arguments) > 4000:
            raise ValueError("Herramienta o argumentos inválidos")
        parsed = json.loads(arguments)
        validate(parsed, self.schemas[name])
        validated = INPUTS[name].model_validate(parsed).model_dump()
        response = await self.session.call_tool(name, validated)
        if response.isError or response.structuredContent is None:
            raise ValueError("La herramienta MCP no pudo completar la consulta")
        if len(json.dumps(response.structuredContent)) > 30000:
            raise ValueError("Resultado MCP demasiado grande")
        return ToolResult.model_validate(response.structuredContent)


@asynccontextmanager
async def open_catalog_tools(settings: Settings) -> AsyncIterator[MCPTools]:
    env: dict[str, str] = {}
    for name, value in [
        ("TMDB_API_KEY", settings.tmdb_api_key),
        ("GOOGLE_BOOKS_API_KEY", settings.google_books_api_key),
    ]:
        if value:
            env[name] = value.get_secret_value()
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_server"],
        env=env,
    )
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield MCPTools(session)
