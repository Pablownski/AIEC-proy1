"""Test-only subprocess: real MCP, external HTTP replaced by MockTransport."""

import asyncio

import httpx

from app.clients.catalog import CatalogClient
from app.core.config import Settings
from app.mcp_server import create_server


async def main():
    Settings.model_config["env_file"] = None

    def handle(request):
        if request.url.host == "api.themoviedb.org":
            row = {"id": 11, "title": "Película de prueba"}
            return httpx.Response(
                200, json=row if request.url.path.endswith("/11") else {"results": [row]}
            )
        row = {"id": "volume_test", "volumeInfo": {"title": "Libro de prueba"}}
        return httpx.Response(
            200, json=row if request.url.path.endswith("/volume_test") else {"items": [row]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        server = create_server(CatalogClient(Settings(tmdb_api_key="test-key"), http))
        await server.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())
