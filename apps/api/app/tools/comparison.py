"""Bounded read-only catalog join, exposed through the real MCP server."""

import asyncio

from app.clients.catalog import CatalogClient
from app.tools.models import CompareMovies, Movie, ToolResult


async def compare_movies(catalog: CatalogClient, movie_ids: list[int]) -> ToolResult:
    ids = CompareMovies(movie_ids=movie_ids).movie_ids
    semaphore = asyncio.Semaphore(2)

    async def details(movie_id: int) -> ToolResult:
        async with semaphore:
            return await catalog.execute("movie_details", {"movie_id": movie_id})

    # gather preserves IDs/order; at most two independent TMDB requests in flight.
    results = await asyncio.gather(*(details(movie_id) for movie_id in ids))
    movies: list[Movie] = []
    books: list[ToolResult] = []
    for result in results:
        if result.error:
            # Preserve failure rather than presenting a partial join as complete.
            return result
        movies.extend(item for item in result.items if isinstance(item, Movie))
    for movie in movies:
        authors = [credit.name for credit in movie.writing_credits if credit.job == "Novel"]
        result = await catalog.execute(
            "search_books", {"title": movie.title, "author": authors[0] if authors else None}
        )
        books.append(result)
        # Do not vary the query or retry a quota failure (one Books request at a time).
        if result.error:
            break
    return ToolResult(source="tmdb", items=list(movies), related=books)
