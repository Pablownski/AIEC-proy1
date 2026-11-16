import json

from jsonschema import validate

from app.agents.context import cache_key, compact_tools, dialogue, evidence_json, project_result
from app.agents.groq_agent import SYSTEM_PROMPT
from app.agents.memory import Conversation
from app.clients.catalog import CatalogClient
from app.tools.models import INPUTS, Book, ToolResult
from tests.test_catalog import MOVIE
from tests.test_groq_agent import agent_setup as agent_setup
from tests.test_groq_agent import tool_reply
from tests.test_groq_client import completion


def long_evidence():
    return ToolResult(
        source="tmdb",
        items=[
            CatalogClient._movie(
                {
                    **MOVIE,
                    "id": index,
                    "title": f"Película {index}",
                    "overview": "DESCRIPCIÓN " + "x" * 3900,
                }
            )
            for index in range(11, 16)
        ],
    )


def test_projection_reduces_payload_but_keeps_recommendation_evidence():
    original = long_evidence()
    projected = project_result(original)
    raw_size = len(original.model_dump_json())
    small_size = len(json.dumps(projected, ensure_ascii=False))
    assert small_size < raw_size * 0.3
    for full, short in zip(original.items, projected["items"], strict=True):
        assert full.id == short["id"]
        assert full.title == short["title"]
        assert full.rating == short["rating"]
        assert full.source_url == short["source_url"]
        assert full.keywords == short["keywords"]
        assert full.writing_credits[0].job == short["writing_credits"][0]["job"]
        assert len(short["overview"]) == 600
        assert short["truncated_fields"] == ["overview"]
        assert "poster_url" not in short and "imdb_url" not in short
    assert original.items[0].poster_url  # Full backend data is unchanged.
    print(f"Synthetic evidence chars: {raw_size} -> {small_size}")


def test_books_keep_authors_dates_identifiers_and_links_with_explicit_excerpt():
    book = Book(
        id="test",
        title="Libro",
        authors=["Autor"],
        description="x" * 4000,
        published_date="1990",
        identifiers=["ISBN_13:123"],
        source_url="https://books.google.com/books?id=test",
    )
    data = project_result(ToolResult(source="google_books", items=[book]))["items"][0]
    assert data["authors"] == ["Autor"]
    assert data["published_date"] == "1990"
    assert data["identifiers"] == ["ISBN_13:123"]
    assert data["source_url"] == book.source_url
    assert len(data["description"]) == 600
    assert data["truncated_fields"] == ["description"]


def test_evidence_is_consolidated_and_detail_fields_survive_search_rows():
    full = long_evidence()
    partial = ToolResult(
        source="tmdb", items=[CatalogClient._movie({"id": 11, "title": "Película 11"})]
    )
    data = json.loads(evidence_json([full, full, partial]))
    assert len(data["items"]) == 5
    assert data["items"][0]["writing_credits"]
    assert data["items"][0]["keywords"]
    assert not data["errors"]
    error = json.loads(evidence_json([ToolResult(source="google_books", error="timeout")]))
    assert error["errors"] == [{"source": "google_books", "error": "timeout"}]


def test_schemas_remove_annotations_without_removing_title_parameter():
    definitions = [
        {
            "type": "function",
            "function": {
                "name": "search_books",
                "parameters": INPUTS["search_books"].model_json_schema(),
            },
        }
    ]
    compact = compact_tools(definitions)
    schema = compact[0]["function"]["parameters"]
    assert "title" in schema["properties"]
    assert "title" not in schema
    validate({"title": "Libro"}, schema)
    assert len(json.dumps(compact)) < len(json.dumps(definitions))


def test_dialogue_omits_old_tool_traces_and_bounds_past_text():
    projected = dialogue(
        [
            {"role": "user", "content": "x" * 3000},
            {"role": "assistant", "tool_calls": [], "content": "Respuesta"},
            {"role": "tool", "tool_call_id": "old", "content": "large-result"},
        ]
    )
    assert len(projected[0]["content"]) == 1000
    assert "large-result" not in str(projected)
    assert cache_key("search_movies", '{"year":null,"query":"  Obra  "}') == cache_key(
        "search_movies", '{"query":"Obra"}'
    )


async def test_identical_tools_are_reused_within_conversation_but_not_across_users(agent_setup):
    agent, client, tools = agent_setup
    client.complete.side_effect = [
        tool_reply("search_movies"),
        completion(content="Primera"),
        tool_reply("search_movies"),
        completion(content="Segunda"),
        tool_reply("search_movies"),
        completion(content="Otra conversación"),
    ]
    await agent.respond("Recomienda", "one")
    await agent.respond("¿Y el libro?", "one")
    assert tools.call.await_count == 1
    context = client.complete.call_args.args[0]
    assert str(context).count("Obra de prueba") == 1
    assert context[0]["content"] == SYSTEM_PROMPT
    assert all(len(turn) == 2 for turn in agent.memory.entries["one"].turns)
    await agent.respond("Recomienda", "two")
    assert tools.call.await_count == 2


def test_cache_is_bounded_and_does_not_commit_failed_work():
    entry = Conversation()
    cache = {str(index): ToolResult(source="tmdb") for index in range(20)}
    entry.commit("x", "y", [{"role": "user", "content": "x"}], [], cache)
    assert len(entry.tool_cache) == 12
    assert "0" not in entry.tool_cache


def test_adaptation_evidence_beyond_prefix_and_latest_recommendations_are_not_lost():
    book = Book(
        id="test",
        title="Libro",
        authors=["Autor"],
        description="x" * 1800 + " Adapted into a film by Director. " + "y" * 1000,
        source_url="https://books.google.com/books?id=test",
    )
    data = project_result(ToolResult(source="google_books", items=[book]))["items"][0]
    assert "Adapted into a film by Director" in data["description"]
    assert len(data["description"]) <= 600
    latest = [
        {"role": "user", "content": "Recomienda tres"},
        {"role": "assistant", "content": "x" * 1500 + "Tercera película"},
    ]
    assert dialogue(latest)[1]["content"].endswith("Tercera película")
