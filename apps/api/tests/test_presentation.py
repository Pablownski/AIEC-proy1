import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agents.presentation import build_metadata, parse_selection, reference_targets
from app.api.deps import get_chat_service
from app.clients.catalog import CatalogClient
from app.main import app
from app.schemas.chat import ChatMessage
from app.schemas.presentation import AgentReply, ChatMetadata, ExternalAction, PresentationSelection
from app.services.chat_service import ChatService
from app.tools.models import ToolResult
from tests.test_catalog import BOOK, MOVIE
from tests.test_comparison_regression import request_tool
from tests.test_groq_agent import agent_setup as agent_setup
from tests.test_groq_client import completion


def evidence(matching=True):
    book = {
        **BOOK,
        "volumeInfo": {
            **BOOK["volumeInfo"],
            "title": MOVIE["title"] if matching else "Otro título",
        },
    }
    return [
        ToolResult(source="tmdb", items=[CatalogClient._movie(MOVIE)]),
        ToolResult(source="google_books", items=[CatalogClient._book(book)]),
    ]


def selection():
    return PresentationSelection(
        content="Mi comparación",
        movie_ids=[11],
        book_ids=["test_volume"],
        comparisons=[
            {"movie_id": 11, "book_id": "test_volume", "opinion": "Vale la pena por su género."}
        ],
    )


def test_metadata_uses_verified_provider_fields_and_comparison_evidence():
    data = build_metadata(evidence(), selection(), "Compárala con su libro")
    assert data.movies[0].poster_url == "https://image.tmdb.org/t/p/w500/test.jpg"
    assert data.movies[0].imdb_id == "tt1234567"
    assert data.comparisons[0].relation == "confirmed"
    assert data.comparisons[0].differences
    assert "escenas" in data.comparisons[0].limitations[0]
    assert {action.target for action in data.actions} == {"imdb", "google_books"}
    assert ChatMetadata.model_validate_json(data.model_dump_json()) == data


def test_title_similarity_alone_does_not_verify_an_adaptation():
    data = build_metadata(evidence(False), selection(), "Compara")
    assert data.comparisons[0].relation == "unconfirmed"
    assert "No se puede confirmar" in data.comparisons[0].limitations[-1]
    results = evidence()
    results[0].items[0].writing_credits = []
    assert build_metadata(results, selection(), "Compara").comparisons[0].relation == "unconfirmed"


@pytest.mark.parametrize(
    "text,targets",
    [
        ("Hola", set()),
        ("Recomienda fantasía", set()),
        ("Compárala", {"imdb", "google_books"}),
        ("Ábreme IMDb", {"imdb"}),
        ("Abre Google Books", {"google_books"}),
        ("Abre referencias", {"imdb", "google_books"}),
        ("No quiero abrir IMDb", set()),
    ],
)
def test_actions_require_explicit_user_intent(text, targets):
    assert reference_targets(text) == targets
    data = build_metadata(evidence(), selection(), text)
    assert {action.target for action in data.actions} == targets


def test_unknown_ids_and_absent_fields_do_not_create_fake_cards_or_actions():
    chosen = PresentationSelection(
        content="Texto",
        movie_ids=[999],
        book_ids=["unknown"],
        comparisons=[{"movie_id": 999, "book_id": "unknown"}],
    )
    assert build_metadata(evidence(), chosen, "Compara") is None
    minimal = ToolResult(
        source="tmdb", items=[CatalogClient._movie({"id": 1, "title": "Solo título"})]
    )
    data = build_metadata([minimal], None, "Abre IMDb")
    assert data.movies[0].poster_url is None and not data.actions
    assert not data.comparisons


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "https://www.imdb.com.evil/title/tt1234567/",
        "https://user:pass@www.imdb.com/title/tt1234567/",
        "https://www.imdb.com/title/tt1234567/?x=1",
    ],
)
def test_external_actions_reject_arbitrary_destinations(url):
    with pytest.raises(ValidationError):
        ExternalAction(id="a", target="imdb", reference_id="tt1234567", url=url)


def test_metadata_rejects_unbound_comparisons_and_actions():
    with pytest.raises(ValidationError):
        ChatMetadata(comparisons=[{"movie_id": 11, "book_id": "unknown", "relation": "confirmed"}])
    with pytest.raises(ValidationError):
        ChatMetadata(
            actions=[
                ExternalAction(
                    id="a",
                    target="google_books",
                    reference_id="unknown",
                    url="https://books.google.com/books?id=unknown",
                )
            ]
        )
    assert ChatMessage(role="assistant", content="Texto antiguo").metadata is None
    assert parse_selection("Texto antiguo") == ("Texto antiguo", None)
    good = build_metadata(evidence(), selection(), "Compara").model_dump()
    for field, key, wrong in [
        ("movies", "source_url", "https://www.themoviedb.org/movie/99"),
        ("movies", "imdb_url", "https://www.imdb.com/title/tt7654321/"),
        ("books", "source_url", "https://books.google.com/books?id=wrong"),
    ]:
        bad = json.loads(json.dumps(good))
        bad[field][0][key] = wrong
        with pytest.raises(ValidationError):
            ChatMetadata.model_validate(bad)


async def test_real_agent_returns_atomic_metadata_and_reuses_action_ids_on_retry(agent_setup):
    agent, client, tools = agent_setup
    tools.call.side_effect = evidence()
    client.complete.side_effect = [
        request_tool("movie_details", {"movie_id": 11}, 1),
        request_tool("book_details", {"volume_id": "test_volume"}, 2),
        completion(content=selection().model_dump_json()),
    ]
    reply = await agent.respond_with_metadata("Compárala con su libro", "rich")
    assert reply.content == "Mi comparación"
    assert reply.metadata.comparisons[0].relation == "confirmed"
    again = await agent.respond_with_metadata("Compárala con su libro", "rich")
    assert again.metadata.actions == reply.metadata.actions
    assert client.complete.await_count == 3
    assert agent.memory.entries["rich"].last_reply == "Mi comparación"


class RichStub:
    async def respond(self, message, conversation_id):
        return "Texto"

    async def respond_with_metadata(self, message, conversation_id):
        return AgentReply(
            content="Comparación", metadata=build_metadata(evidence(), selection(), message)
        )


async def test_http_contract_serializes_optional_metadata(client):
    app.dependency_overrides[get_chat_service] = lambda: ChatService(RichStub())
    response = await client.post(
        "/api/v1/chat",
        json={"conversation_id": "rich", "message": {"role": "user", "content": "Compara"}},
    )
    assert response.status_code == 200
    message = response.json()["message"]
    assert message["content"] == "Comparación"
    assert message["metadata"]["movies"][0]["id"] == 11
    assert len(message["metadata"]["actions"]) == 2


def test_websocket_contract_serializes_same_metadata():
    app.dependency_overrides[get_chat_service] = lambda: ChatService(RichStub())
    with TestClient(app) as client, client.websocket_connect("/ws/chat") as socket:
        socket.send_json({"conversation_id": "rich", "content": "Compara"})
        assert socket.receive_json()["type"] == "agent_start"
        message = socket.receive_json()["message"]
        assert message["metadata"]["books"][0]["id"] == "test_volume"
        assert message["metadata"]["comparisons"][0]["relation"] == "confirmed"
        assert socket.receive_json()["type"] == "agent_end"
