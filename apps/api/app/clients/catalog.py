"""Fixed-host, read-only clients. No URLs or paths are supplied by the model."""

from __future__ import annotations

import html
import json
import logging
import re
from typing import Any, Literal

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.tools.models import (
    GENRES,
    INPUTS,
    Book,
    BookDetails,
    DiscoverMovies,
    Movie,
    MovieDetails,
    SearchBooks,
    SearchMovies,
    ToolResult,
    WritingCredit,
)

logger = logging.getLogger(__name__)
# MCP root logging is ERROR; keep safe catalog diagnostics visible.
logger.setLevel(logging.WARNING)
# httpx INFO includes query strings (API keys and user searches). Never emit those records.
logging.getLogger("httpx").setLevel(logging.WARNING)

QUOTA_REASONS = {
    "rateLimitExceeded",
    "userRateLimitExceeded",
    "dailyLimitExceeded",
    "quotaExceeded",
    "RATE_LIMIT_EXCEEDED",
    "QUOTA_EXCEEDED",
    "RESOURCE_EXHAUSTED",
}
SAFE_REASONS = QUOTA_REASONS | {
    "keyInvalid",
    "accessNotConfigured",
    "forbidden",
    "backendError",
    "API_KEY_INVALID",
    "SERVICE_DISABLED",
    "PERMISSION_DENIED",
    "UNAUTHENTICATED",
    "UNAVAILABLE",
}


def catalog_reason(response: httpx.Response | None) -> str:
    if response is None:
        return "unknown"
    try:
        error = response.json().get("error", {})
        candidates: list[object] = []
        for field in ("errors", "details"):
            entries = error.get(field, [])
            if isinstance(entries, list):
                candidates.extend(item.get("reason") for item in entries if isinstance(item, dict))
        candidates.append(error.get("status"))
        return next(
            (reason for reason in candidates if isinstance(reason, str) and reason in SAFE_REASONS),
            "unknown",
        )
    except (ValueError, TypeError, AttributeError):
        return "unknown"


class CatalogClient:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self.settings = settings
        self.http = http

    async def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        source: Literal["google_books", "tmdb"] = (
            "google_books" if name in {"search_books", "book_details"} else "tmdb"
        )
        response: httpx.Response | None = None

        def failure(code: str) -> ToolResult:
            result = ToolResult.model_validate({"source": source, "error": code})
            logger.warning(
                json.dumps(
                    {
                        "event": "catalog_request_failed",
                        "source": source,
                        "operation": name if name in INPUTS else "unknown",
                        "code": result.error,
                        "status_code": response.status_code if response is not None else None,
                        "provider_reason": catalog_reason(response),
                    }
                )
            )
            return result

        try:
            if source == "tmdb":
                if (
                    not self.settings.tmdb_api_key
                    or not self.settings.tmdb_api_key.get_secret_value()
                ):
                    return failure("configuration")
                path, params = self._movie_request(name, arguments)
                params["api_key"] = self.settings.tmdb_api_key.get_secret_value()
                params["language"] = "es-ES"
                url = f"https://api.themoviedb.org/3/{path}"
            else:
                path, params = self._book_request(name, arguments)
                if self.settings.google_books_api_key:
                    params["key"] = self.settings.google_books_api_key.get_secret_value()
                url = f"https://www.googleapis.com/books/v1/{path}"
            response = await self.http.get(url, params=params, timeout=5.0, follow_redirects=False)
            if response.status_code == 404:
                return ToolResult(source=source)
            if response.status_code in {401, 403}:
                if (
                    source == "google_books"
                    and response.status_code == 403
                    and catalog_reason(response) in QUOTA_REASONS
                ):
                    return failure("rate_limit")
                return failure("authentication")
            if response.status_code == 429:
                return failure("rate_limit")
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Invalid payload")
            if source == "tmdb":
                rows = [data] if name == "movie_details" else data.get("results", [])
                return ToolResult(source=source, items=[self._movie(row) for row in rows[:5]])
            rows = [data] if name == "book_details" else data.get("items", [])
            return ToolResult(source=source, items=[self._book(row) for row in rows[:5]])
        except httpx.TimeoutException:
            return failure("timeout")
        except httpx.RequestError:
            return failure("connection")
        except httpx.HTTPStatusError:
            return failure("unavailable")
        except (ValueError, TypeError, KeyError, AttributeError, ValidationError):
            return failure("invalid_response")

    def _movie_request(self, name: str, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        if name == "search_movies":
            search = SearchMovies.model_validate(args)
            params: dict[str, Any] = {"query": search.query, "include_adult": "false"}
            if search.year:
                params["year"] = search.year
            return "search/movie", params
        if name == "discover_movies":
            discover = DiscoverMovies.model_validate(args)
            return "discover/movie", {
                "with_genres": GENRES[discover.genre],
                "vote_average.gte": discover.min_rating,
                "vote_count.gte": 100,
                "include_adult": "false",
                "sort_by": "popularity.desc",
            }
        details = MovieDetails.model_validate(args)
        return f"movie/{details.movie_id}", {"append_to_response": "keywords,credits"}

    def _book_request(self, name: str, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        if name == "book_details":
            return f"volumes/{BookDetails.model_validate(args).volume_id}", {}
        search = SearchBooks.model_validate(args)
        # Quoted fields keep user text inside its intended search term.
        query = " ".join(
            f'{field}:"{value.replace(chr(34), " ")}"'
            for field, value in [("intitle", search.title), ("inauthor", search.author)]
            if value
        )
        return "volumes", {"q": query, "maxResults": 5, "printType": "books"}

    @staticmethod
    def _movie(row: dict[str, Any]) -> Movie:
        movie_id = int(row["id"])
        poster = row.get("poster_path")
        imdb = row.get("imdb_id")
        genres = row.get("genres") or [
            {"name": key} for key, value in GENRES.items() if value in row.get("genre_ids", [])
        ]
        keywords = row.get("keywords", {}).get("keywords", [])
        credits = row.get("credits", {}).get("crew", [])
        return Movie(
            id=movie_id,
            title=row["title"],
            overview=row.get("overview") or None,
            release_date=row.get("release_date") or None,
            genres=[g["name"] for g in genres[:20]],
            rating=row.get("vote_average"),
            vote_count=row.get("vote_count"),
            source_url=f"https://www.themoviedb.org/movie/{movie_id}",
            poster_url=f"https://image.tmdb.org/t/p/w500{poster}"
            if isinstance(poster, str) and re.fullmatch(r"/[A-Za-z0-9_.-]+", poster)
            else None,
            imdb_url=f"https://www.imdb.com/title/{imdb}/"
            if isinstance(imdb, str) and re.fullmatch(r"tt\d{5,12}", imdb)
            else None,
            keywords=[k["name"] for k in keywords[:30]],
            writing_credits=[
                WritingCredit(name=c["name"], job=c["job"])
                for c in credits
                if c.get("job") in {"Novel", "Writer", "Screenplay", "Original Story"}
            ][:20],
        )

    @staticmethod
    def _book(row: dict[str, Any]) -> Book:
        volume_id = BookDetails(volume_id=row["id"]).volume_id
        info = row["volumeInfo"]
        description = info.get("description")
        return Book(
            id=volume_id,
            title=info["title"],
            authors=info.get("authors", [])[:20],
            description=html.unescape(re.sub(r"<[^>]*>", "", description)) if description else None,
            published_date=info.get("publishedDate"),
            identifiers=[
                f"{item['type']}:{item['identifier']}"
                for item in info.get("industryIdentifiers", [])[:20]
            ],
            source_url=f"https://books.google.com/books?id={volume_id}",
        )
