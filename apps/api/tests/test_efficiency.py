"""Offline regressions: real MCP in test_mcp; providers here are always mocked.

Usage counters in benchmark responses are ASSIGNED simulation inputs. They test
accounting, not GPT-OSS tokenization or achieved production savings.
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from groq.types.completion_usage import CompletionUsage

from app.agents.context import cache_key, compact_tools, evidence_json
from app.agents.groq_agent import (
    BOOKS_UNAVAILABLE,
    BUDGET_ERROR,
    RATE_LIMIT_ERROR,
    SAFE_ERROR,
    GroqAgent,
)
from app.clients.catalog import CatalogClient
from app.clients.groq_client import GroqClient, GroqClientError
from app.clients.rate_limits import RequestBudget, estimate_tokens
from app.core.config import Settings
from app.tools.comparison import compare_movies
from app.tools.models import INPUTS, Book, ToolResult
from tests.test_catalog import BOOK, MOVIE
from tests.test_comparison_regression import (
    comparison_setup as comparison_setup,
)
from tests.test_comparison_regression import comparison_steps, request_tool, seed_recommendations
from tests.test_groq_agent import agent_setup as agent_setup
from tests.test_groq_client import completion
from tests.test_groq_client import sdk as sdk


def counted(response, prompt=1800, output=50):
    response.usage = CompletionUsage(
        prompt_tokens=prompt, completion_tokens=output, total_tokens=prompt + output
    )
    return response


async def test_comparison_join_two_rounds_with_memory_metadata_and_no_schemas(comparison_setup):
    client, session = comparison_setup
    agent = GroqAgent(Settings(), client)
    await seed_recommendations(agent, client)
    client.complete.reset_mock()
    session.call_tool.reset_mock()
    final = json.dumps(
        {
            "content": "No puedo confirmar la relación. Como opinión, interesa por su género.",
            "movie_ids": [11],
            "book_ids": [BOOK["id"]],
            "comparisons": [
                {"movie_id": 11, "book_id": BOOK["id"], "opinion": "Opinión limitada."}
            ],
        }
    )
    client.complete.side_effect = [
        request_tool("compare_movies", {"movie_ids": [13, 11, 12]}, 1),
        completion(content=final),
    ]
    result = await agent.respond_with_metadata(
        "Compara las tres y abre sus referencias", "comparison"
    )
    assert result.content != SAFE_ERROR
    assert client.complete.await_count == 2
    assert session.call_tool.await_count == 1  # One genuine MCP operation, six bounded HTTP reads.
    assert client.complete.call_args.kwargs["tools"] is None
    assert client.complete.call_args.kwargs["allow_tools"] is False
    assert not any(m["role"] == "tool" for m in client.complete.call_args.args[0])
    assert "Fantasía 13" in str(client.complete.call_args.args[0])
    assert result.metadata.movies[0].poster_url == "https://image.tmdb.org/t/p/w500/test.jpg"
    assert result.metadata.books[0].id == BOOK["id"]
    assert result.metadata.comparisons[0].relation == "unconfirmed"
    assert {a.target for a in result.metadata.actions} == {"imdb", "google_books"}
    assert len(agent.memory.entries["comparison"].turns) == 2
    # Different ordering/duplicates reuse the entire validated bundle across a follow-up.
    client.complete.side_effect = [
        request_tool("compare_movies", {"movie_ids": [12, 13, 11, 11][:3]}, 2),
        completion(content=final),
    ]
    await agent.respond("Retoma la comparación", "comparison")
    assert session.call_tool.await_count == 1
    client.complete.side_effect = [request_tool("movie_details", {"movie_id": 11}, 3), completion()]
    await agent.respond("Recuerda los detalles de la primera", "comparison")
    assert session.call_tool.await_count == 1


async def test_independent_calls_concurrent_bounded_ordered_and_deduplicated(agent_setup):
    agent, client, tools = agent_setup
    active = peak = 0

    async def execute(name, arguments):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return ToolResult(source="tmdb", items=[CatalogClient._movie(MOVIE)])

    tools.call.side_effect = execute
    calls = [
        request_tool("movie_details", {"movie_id": i}, i).choices[0].message.tool_calls[0]
        for i in (11, 12, 13)
    ]
    calls.append(
        request_tool("movie_details", {"movie_id": 11}, 14).choices[0].message.tool_calls[0]
    )
    client.complete.side_effect = [
        completion(content=None, tool_calls=[call.model_dump() for call in calls]),
        completion(),
    ]
    await agent.respond("Consulta las películas", "batch")
    assert tools.call.await_count == 3 and peak == 2
    messages = client.complete.call_args.args[0]
    assert [m["tool_call_id"] for m in messages if m["role"] == "tool"] == [c.id for c in calls]
    assert client.complete.await_count == 2


async def test_dependent_search_then_detail_still_has_three_rounds(comparison_setup):
    client, session = comparison_setup
    client.complete.side_effect = [
        request_tool("search_movies", {"query": "Obra"}, 0),
        request_tool("movie_details", {"movie_id": 11}, 1),
        completion(),
    ]
    reply = await GroqAgent(Settings(), client).respond("Busca Obra y su IMDb", "dependent")
    assert reply != SAFE_ERROR
    assert client.complete.await_count == 3 and session.call_tool.await_count == 2


@pytest.mark.parametrize("error", ["rate_limit", "timeout", None])
async def test_join_stops_books_on_failure_and_preserves_partial_sources(error):
    catalog = AsyncMock()
    movies = ToolResult(source="tmdb", items=[CatalogClient._movie(MOVIE)])
    books = ToolResult(source="google_books", error=error)

    async def execute(name, args):
        return movies if name == "movie_details" else books

    catalog.execute.side_effect = execute
    result = await compare_movies(catalog, [11, 12, 13])
    assert len(result.related) == (1 if error else 3)
    assert result.related[0].error == error
    assert not result.related[0].items  # No invented book for an empty or failed lookup.


async def test_join_quota_failure_never_commits_or_returns_metadata(agent_setup):
    agent, client, tools = agent_setup
    tools.call.return_value = ToolResult(
        source="tmdb",
        items=[CatalogClient._movie(MOVIE)],
        related=[ToolResult(source="google_books", error="rate_limit")],
    )
    client.complete.return_value = request_tool("compare_movies", {"movie_ids": [11]}, 0)
    result = await agent.respond_with_metadata("Compara", "quota")
    assert result.content == BOOKS_UNAVAILABLE and result.metadata is None
    assert client.complete.await_count == 1
    assert not agent.memory.entries["quota"].turns
    assert not agent.memory.entries["quota"].artifacts


async def test_join_tmdb_failure_does_not_query_books():
    catalog = AsyncMock()
    catalog.execute.return_value = ToolResult(source="tmdb", error="authentication")
    result = await compare_movies(catalog, [11])
    assert result.error == "authentication"
    catalog.execute.assert_awaited_once_with("movie_details", {"movie_id": 11})


async def test_incomplete_join_allows_a_justified_dependent_round(agent_setup):
    agent, client, tools = agent_setup
    incomplete = Book(
        id="test_volume", title="Libro", source_url="https://books.google.com/books?id=test_volume"
    )
    tools.call.side_effect = [
        ToolResult(
            source="tmdb",
            items=[CatalogClient._movie(MOVIE)],
            related=[ToolResult(source="google_books", items=[incomplete])],
        ),
        ToolResult(
            source="google_books",
            items=[
                incomplete.model_copy(
                    update={
                        "authors": ["Autor"],
                        "description": "Una historia",
                        "published_date": "1990",
                    }
                )
            ],
        ),
    ]
    client.complete.side_effect = [
        request_tool("compare_movies", {"movie_ids": [11]}, 0),
        request_tool("book_details", {"volume_id": "test_volume"}, 1),
        completion(content="No puedo confirmar la relación con estos datos."),
    ]
    assert await agent.respond("Compara con datos bibliográficos", "incomplete") != SAFE_ERROR
    assert tools.call.await_count == 2 and client.complete.await_count == 3


async def test_admission_can_fall_back_to_synthesis_without_an_extra_planning_request(agent_setup):
    agent, client, _ = agent_setup
    client.complete.side_effect = [
        request_tool("movie_details", {"movie_id": 11}, 0),
        GroqClientError("budget", "safe"),
        completion(content="No pude consultar el libro; solo dispongo de la información de TMDB."),
    ]
    reply = await agent.respond("Compara con el libro", "fallback")
    assert "No pude consultar el libro" in reply
    assert client.complete.call_args.kwargs["tools"] is None
    assert client.complete.call_args.kwargs["allow_tools"] is False
    assert not any(m["role"] == "tool" for m in client.complete.call_args.args[0])


async def test_oversized_request_rejected_before_sdk_and_logs_no_payload(sdk, caplog):
    async with GroqClient(Settings(groq_api_key="test")) as client:
        with pytest.raises(GroqClientError) as error:
            await client.complete([{"role": "user", "content": "private-detail" * 3000}])
    assert error.value.code == "budget"
    sdk[1].chat.completions.create.assert_not_awaited()
    assert "private-detail" not in caplog.text and "groq_budget_limited" in caplog.text


async def test_fifteen_books_keep_identities_but_fit_two_round_budget(agent_setup, sdk):
    agent, _, tools = agent_setup
    related = [
        ToolResult(
            source="google_books",
            items=[
                Book(
                    id=f"book_{movie}_{i}",
                    title=f"Película {movie}" if i == 1 else f"Otra edición {i}",
                    authors=["Autor Prueba"],
                    description="Una historia larga. " * 200,
                    published_date="1990",
                    source_url=f"https://books.google.com/books?id=book_{movie}_{i}",
                )
                for i in range(5)
            ],
        )
        for movie in (11, 12, 13)
    ]
    movies = [
        CatalogClient._movie(
            {**MOVIE, "id": i, "title": f"Película {i}", "overview": "Una aventura larga. " * 200}
        )
        for i in (11, 12, 13)
    ]
    tools.call.return_value = ToolResult(source="tmdb", items=movies, related=related)
    tools.discover.return_value = compact_tools(
        [
            {
                "type": "function",
                "function": {"name": name, "parameters": model.model_json_schema()},
            }
            for name, model in INPUTS.items()
        ]
    )
    sdk[1].chat.completions.create.side_effect = [
        counted(request_tool("compare_movies", {"movie_ids": [11, 12, 13]}, 0)),
        counted(completion(content="Solo puedo comparar los datos disponibles."), 2200, 400),
    ]
    async with GroqClient(Settings(groq_api_key="test")) as client:
        agent.client = client
        result = await agent.respond_with_metadata("Compara las tres", "many")
    assert result.content not in {SAFE_ERROR, RATE_LIMIT_ERROR}
    assert sdk[1].chat.completions.create.await_count == 2
    facts = json.loads(evidence_json([*related, ToolResult(source="tmdb", items=movies)]))
    books = [item for item in facts["items"] if item["kind"] == "book"]
    assert len(books) == 15
    assert sum("description" in book for book in books) == 3
    assert all(book["id"].endswith("_1") for book in books if "description" in book)
    assert len(related[0].items[0].description) > 350
    assert result.metadata.movies[0].poster_url


def test_equivalent_queries_and_join_ids_have_identical_cache_keys():
    assert cache_key("search_books", '{"title":"  OBRA   original "}') == cache_key(
        "search_books", '{"title":"obra original","author":null}'
    )
    assert cache_key("compare_movies", '{"movie_ids":[12,11,11]}') == cache_key(
        "compare_movies", '{"movie_ids":[11,12]}'
    )


async def test_turn_budget_uses_actual_usage_and_reserves_output(sdk):
    sdk[1].chat.completions.create.side_effect = [
        counted(completion(), prompt=5000, output=100),
        counted(completion(), prompt=300, output=100),
    ]
    budget = RequestBudget()
    async with GroqClient(Settings(groq_api_key="test", groq_turn_token_budget=7000)) as client:
        await client.complete([{"role": "user", "content": "a"}], budget=budget)
        assert budget.prompt_tokens == 5000 and budget.completion_tokens == 100
        assert budget.spent_tokens == 5100
        await client.complete([{"role": "user", "content": "x" * 1000}], budget=budget)
        assert budget.spent_tokens == 5500 and budget.reserved_tokens == 0
    assert sdk[1].chat.completions.create.await_count == 2
    assert sdk[1].chat.completions.create.call_args.kwargs["max_completion_tokens"] < 1800


async def test_rolling_usage_shared_across_conversations_and_missing_usage_is_reserved(sdk):
    sdk[1].chat.completions.create.return_value = counted(completion(), prompt=6000, output=100)
    async with GroqClient(Settings(groq_api_key="test")) as client:
        await client.complete([{"role": "user", "content": "a"}])
        with pytest.raises(GroqClientError, match="Espera"):
            await client.complete([{"role": "user", "content": "b" * 2000}])
    async with GroqClient(Settings(groq_api_key="test")) as client:
        sdk[1].chat.completions.create.return_value = completion()  # No usage signals.
        budget = RequestBudget()
        await client.complete([{"role": "user", "content": "c"}], budget=budget)
        assert budget.spent_tokens >= 1800 and budget.prompt_tokens == 0


async def test_window_wait_is_bounded_and_can_recover(sdk):
    clock = [100.0]

    async def advance(delay):
        clock[0] += delay + 0.01

    with (
        patch("app.clients.groq_client.time.monotonic", side_effect=lambda: clock[0]),
        patch("app.clients.groq_client.asyncio.sleep", side_effect=advance) as sleep,
    ):
        async with GroqClient(Settings(groq_api_key="test")) as client:
            from app.clients.token_budget import Usage

            client._tokens.usage = [Usage(50.0, 6500)]
            await client.complete(
                [{"role": "user", "content": "a"}], budget=RequestBudget(deadline=140)
            )
            sleep.assert_awaited_once_with(10)


async def test_insufficient_budget_safe_message_and_memory_rollback(agent_setup):
    agent, client, _ = agent_setup
    client.complete.side_effect = GroqClientError("budget", "safe")
    assert await agent.respond("Compara", "budget") == BUDGET_ERROR
    assert not agent.memory.entries["budget"].turns


@pytest.mark.parametrize("grouped", [False, True])
async def test_comparable_transcript_metrics(comparison_setup, sdk, grouped, capsys):
    """Baseline = same catalog/query, granular scripted selection, NOT an old binary.

    All planning calls receive assigned usage 1800/50, synthesis 2200/400.
    The baseline bypasses admission solely to measure a completed transcript.
    """
    _, session = comparison_setup
    steps = (
        [request_tool("compare_movies", {"movie_ids": [11, 12, 13]}, 0)]
        if grouped
        else comparison_steps()
    )
    sdk[1].chat.completions.create.side_effect = [
        *(counted(step) for step in steps),
        counted(completion(), prompt=2200, output=400),
    ]
    settings = Settings(
        groq_api_key="test",
        groq_turn_token_budget=7000 if grouped else 100000,
        groq_tpm_budget=8000 if grouped else 100000,
    )
    async with GroqClient(settings) as client:
        result = await GroqAgent(settings, client).respond_with_metadata(
            "Compara TMDB 11, 12 y 13 con sus libros", "metric"
        )
    assert result.content not in {SAFE_ERROR, RATE_LIMIT_ERROR}
    assert {movie.id for movie in result.metadata.movies} == {11, 12, 13}
    assert {book.id for book in result.metadata.books} == {BOOK["id"]}
    assert all(movie.poster_url and movie.imdb_url for movie in result.metadata.movies)
    requests = sdk[1].chat.completions.create.await_args_list
    chars = sum(
        len(json.dumps([r.kwargs["messages"], r.kwargs.get("tools", [])], ensure_ascii=False))
        for r in requests
    )
    metrics = {
        "grouped": grouped,
        "llm_rounds": len(requests),
        "mcp_calls": session.call_tool.await_count,
        "simulated_prompt_tokens": 1800 * len(steps) + 2200,
        "simulated_completion_tokens": 50 * len(steps) + 400,
        "context_characters_total": chars,
        "estimated_input_tokens": sum(
            estimate_tokens(
                json.dumps(
                    [r.kwargs["messages"], r.kwargs.get("tools", [])],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                len(r.kwargs["messages"]),
            )
            for r in requests
        ),
    }
    assert len(requests) == (2 if grouped else 8)
    assert metrics["simulated_prompt_tokens"] == (4000 if grouped else 14800)
    print("BENCHMARK " + json.dumps(metrics))
    # Keep output visible with pytest -s, without logging user text or source data.
    with capsys.disabled():
        print("BENCHMARK " + json.dumps(metrics))


@pytest.mark.parametrize(
    "scenario,steps,expected_calls",
    [
        ("recommendation", [("discover_movies", {"genre": "fantasía"})], 1),
        (
            "independent",
            [("movie_details", {"movie_id": 11}), ("movie_details", {"movie_id": 12})],
            2,
        ),
        (
            "dependent",
            [("search_movies", {"query": "Obra"}), ("movie_details", {"movie_id": 11})],
            2,
        ),
    ],
)
async def test_scenario_metrics(comparison_setup, sdk, scenario, steps, expected_calls, capsys):
    _, session = comparison_setup
    responses = [request_tool(name, args, i) for i, (name, args) in enumerate(steps)]
    if scenario == "independent":
        calls = [response.choices[0].message.tool_calls[0].model_dump() for response in responses]
        responses = [completion(content=None, tool_calls=calls)]
    sdk[1].chat.completions.create.side_effect = [
        *(counted(r) for r in responses),
        counted(completion(), prompt=2200, output=400),
    ]
    async with GroqClient(Settings(groq_api_key="test")) as client:
        reply = await GroqAgent(Settings(), client).respond("Consulta el catálogo", scenario)
    assert reply not in {SAFE_ERROR, RATE_LIMIT_ERROR}
    assert session.call_tool.await_count == expected_calls
    requests = sdk[1].chat.completions.create.await_args_list
    assert len(requests) == (3 if scenario == "dependent" else 2)
    with capsys.disabled():
        print(
            "BENCHMARK "
            + json.dumps(
                {
                    "scenario": scenario,
                    "llm_rounds": len(requests),
                    "mcp_calls": expected_calls,
                    "simulated_prompt_tokens": 1800 * len(responses) + 2200,
                    "simulated_completion_tokens": 50 * len(responses) + 400,
                    "context_characters_total": sum(
                        len(json.dumps(r.kwargs["messages"])) for r in requests
                    ),
                }
            )
        )


def test_estimate_is_explicitly_not_a_character_count():
    estimate = estimate_tokens("Título 🐉", 2)
    assert estimate != len("Título 🐉")
    assert estimate >= 24
    original = ToolResult(
        source="tmdb", items=[CatalogClient._movie({**MOVIE, "overview": "x" * 4000})]
    )
    assert len(evidence_json([original])) < len(original.model_dump_json())
    assert len(original.items[0].overview) == 4000
