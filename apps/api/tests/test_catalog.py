import json
import logging

import httpx
import pytest
from pydantic import ValidationError

from app.clients.catalog import CatalogClient
from app.core.config import Settings
from app.tools.models import INPUTS, Movie, ToolResult

MOVIE = {
    "id": 11,
    "title": "Obra de prueba",
    "overview": "Una aventura",
    "release_date": "2001-01-01",
    "genre_ids": [14],
    "vote_average": 7.5,
    "vote_count": 123,
    "poster_path": "/test.jpg",
    "imdb_id": "tt1234567",
    "keywords": {"keywords": [{"name": "based on novel"}]},
    "credits": {"crew": [{"name": "Autor Prueba", "job": "Novel"}]},
}
BOOK = {
    "id": "test_volume",
    "volumeInfo": {
        "title": "Libro de prueba",
        "authors": ["Autor Prueba"],
        "description": "<p>Una historia &amp; más</p>",
        "publishedDate": "1990",
        "industryIdentifiers": [{"type": "ISBN_13", "identifier": "1234567890123"}],
    },
}


@pytest.mark.parametrize(
    "name,args,path,payload",
    [
        (
            "search_movies",
            {"query": "Obra", "year": 2001},
            "/3/search/movie",
            {"results": [MOVIE] * 6},
        ),
        ("discover_movies", {"genre": "fantasía"}, "/3/discover/movie", {"results": [MOVIE]}),
        ("movie_details", {"movie_id": 11}, "/3/movie/11", MOVIE),
        (
            "search_books",
            {"title": "Libro", "author": "Autor"},
            "/books/v1/volumes",
            {"items": [BOOK]},
        ),
        ("book_details", {"volume_id": "test_volume"}, "/books/v1/volumes/test_volume", BOOK),
    ],
)
async def test_catalog_builds_requests_and_preserves_real_fields(name, args, path, payload):
    def handle(request):
        assert request.url.path == path
        assert request.extensions["timeout"]["read"] == 5.0
        if name == "discover_movies":
            assert request.url.params["with_genres"] == "14"
        if name == "search_movies":
            assert request.url.params["year"] == "2001"
            assert request.url.params["include_adult"] == "false"
        if name == "search_books":
            assert request.url.params["q"] == 'intitle:"Libro" inauthor:"Autor"'
            assert request.url.params["key"] == "test-books"
        return httpx.Response(200, json=payload)

    settings = Settings(tmdb_api_key="test-tmdb", google_books_api_key="test-books")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await CatalogClient(settings, http).execute(name, args)
    assert result.error is None
    assert 1 <= len(result.items) <= 5
    item = result.items[0]
    if isinstance(item, Movie):
        assert item.poster_url == "https://image.tmdb.org/t/p/w500/test.jpg"
        assert item.imdb_url == "https://www.imdb.com/title/tt1234567/"
        assert item.writing_credits[0].job == "Novel"
    else:
        assert item.description == "Una historia & más"
        assert item.authors == ["Autor Prueba"]
        assert item.source_url == "https://books.google.com/books?id=test_volume"


@pytest.mark.parametrize(
    "status,expected",
    [
        (401, "authentication"),
        (403, "authentication"),
        (429, "rate_limit"),
        (500, "unavailable"),
        (302, "unavailable"),
        (404, None),
    ],
)
@pytest.mark.parametrize(
    "name,args", [("search_movies", {"query": "x"}), ("search_books", {"author": "x"})]
)
async def test_safe_http_failures(status, expected, name, args):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(status, text="private-detail"))
    ) as http:
        result = await CatalogClient(Settings(tmdb_api_key="test-key"), http).execute(name, args)
    assert result.error == expected
    assert not result.items
    assert "private-detail" not in result.model_dump_json()
    assert "test-key" not in result.model_dump_json()


@pytest.mark.parametrize(
    "error,expected", [(httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "connection")]
)
async def test_transport_failures(error, expected):
    def fail(req):
        raise error("private-detail")

    async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as http:
        result = await CatalogClient(Settings(), http).execute("search_books", {"author": "x"})
    assert result.error == expected


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"results": None},
        {"results": [{"id": 11}]},
        {"results": [{**MOVIE, "vote_average": 99}]},
    ],
)
async def test_malformed_responses(payload):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=payload))
    ) as http:
        result = await CatalogClient(Settings(tmdb_api_key="test-key"), http).execute(
            "search_movies", {"query": "x"}
        )
    assert result.error == "invalid_response"


async def test_empty_missing_and_incomplete_results():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    ) as http:
        client = CatalogClient(Settings(), http)
        assert (await client.execute("search_movies", {"query": "x"})).error == "configuration"
        assert not (await client.execute("search_books", {"title": "x"})).items
    movie = CatalogClient._movie({"id": 11, "title": "x"})
    assert movie.poster_url is movie.imdb_url is movie.rating is None
    assert movie.overview is None
    assert not CatalogClient._movie(
        {**MOVIE, "imdb_id": "javascript:bad", "poster_path": "//evil.test/x"}
    ).imdb_url


@pytest.mark.parametrize(
    "name,args",
    [
        ("search_movies", {"query": " "}),
        ("search_movies", {"query": "x", "extra": True}),
        ("movie_details", {"movie_id": -1}),
        ("movie_details", {"movie_id": True}),
        ("discover_movies", {"genre": "unknown"}),
        ("search_books", {}),
        ("book_details", {"volume_id": "../../etc"}),
    ],
)
def test_argument_validation(name, args):
    with pytest.raises(ValidationError):
        INPUTS[name].model_validate(args)


def test_result_rejects_forged_sources():
    movie = CatalogClient._movie(MOVIE)
    with pytest.raises(ValidationError):
        ToolResult(source="google_books", items=[movie])
    with pytest.raises(ValidationError):
        ToolResult(source="tmdb", items=[movie], error="timeout")
    with pytest.raises(ValidationError):
        Movie(**{**movie.model_dump(), "source_url": "https://evil.test"})


@pytest.mark.parametrize(
    "status,reason,expected",
    [
        (429, "rateLimitExceeded", "rate_limit"),
        (429, "private-unknown-reason", "rate_limit"),
        (403, "dailyLimitExceeded", "rate_limit"),
        (403, "userRateLimitExceeded", "rate_limit"),
        (403, "API_KEY_INVALID", "authentication"),
        (401, "UNAUTHENTICATED", "authentication"),
        (500, "backendError", "unavailable"),
    ],
)
async def test_books_error_diagnostics_are_allowlisted_and_status_specific(
    caplog, status, reason, expected
):
    def handle(request):
        return httpx.Response(
            status,
            json={
                "error": {
                    "message": "private-body",
                    "status": "PERMISSION_DENIED",
                    "errors": [{"reason": reason}],
                }
            },
        )

    with caplog.at_level(logging.INFO):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            result = await CatalogClient(
                Settings(google_books_api_key="private-key"), http
            ).execute("search_books", {"title": "private-query"})
    assert result.error == expected
    event = json.loads(caplog.records[-1].getMessage())
    assert event["status_code"] == status
    assert event["source"] == "google_books"
    assert event["code"] == expected
    assert event["provider_reason"] == (
        "PERMISSION_DENIED" if reason == "private-unknown-reason" else reason
    )
    for private in ("private-body", "private-key", "private-query", "private-unknown-reason"):
        assert private not in caplog.text
