"""Run with python -m app.mcp_server; stdout is reserved for MCP JSON-RPC."""

import asyncio
from typing import Annotated

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import Field

from app.clients.catalog import CatalogClient
from app.core.config import Settings
from app.tools.models import Genre, Query, ToolResult, VolumeID


def create_server(catalog: CatalogClient) -> FastMCP:
    server = FastMCP("Movie and book catalog", log_level="ERROR")

    @server.tool()
    async def search_movies(
        query: Query,
        year: Annotated[int | None, Field(ge=1870, le=2100)] = None,
    ) -> ToolResult:
        """Busca títulos en TMDB; devuelve hasta 5 candidatos, sin elegir entre ambiguos."""
        return await catalog.execute("search_movies", {"query": query, "year": year})

    @server.tool()
    async def discover_movies(
        genre: Genre,
        min_rating: Annotated[float, Field(ge=0, le=10)] = 6.0,
    ) -> ToolResult:
        """Recomienda candidatos de TMDB por género y calificación; no es búsqueda por título."""
        return await catalog.execute("discover_movies", {"genre": genre, "min_rating": min_rating})

    @server.tool()
    async def movie_details(movie_id: Annotated[int, Field(gt=0, le=2_147_483_647)]) -> ToolResult:
        """Consulta un ID de TMDB: sinopsis, géneros, IMDb, póster, palabras clave y escritores.

        Usar para investigar adaptaciones. Una palabra clave 'based on novel' confirma
        adaptación genérica, no identifica por sí sola un libro concreto.
        """
        return await catalog.execute("movie_details", {"movie_id": movie_id})

    @server.tool()
    async def search_books(title: Query | None = None, author: Query | None = None) -> ToolResult:
        """Busca en Google Books por título y/o autor; no confirma una adaptación por similitud."""
        return await catalog.execute("search_books", {"title": title, "author": author})

    @server.tool()
    async def book_details(volume_id: VolumeID) -> ToolResult:
        """Obtiene autores, descripción, fecha, identificadores y enlace de un volumen."""
        return await catalog.execute("book_details", {"volume_id": volume_id})

    return server


async def main() -> None:
    # Parent passes only catalog credentials; never load a local .env in this process.
    Settings.model_config["env_file"] = None
    settings = Settings()
    async with httpx.AsyncClient() as http:
        await create_server(CatalogClient(settings, http)).run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())
