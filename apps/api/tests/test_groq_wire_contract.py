"""Exercise the real Groq SDK serializer against strict, entirely offline HTTP fixtures."""

import json
import logging
from unittest.mock import patch

import httpx
import pytest
from groq import AsyncGroq
from jsonschema import ValidationError, validate

from app.agents.groq_agent import SAFE_ERROR, GroqAgent
from app.clients.groq_client import GroqClient
from app.core.config import Settings
from tests.test_comparison_regression import comparison_setup as comparison_setup
from tests.test_groq_client import completion

ASSISTANT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["role", "tool_calls"],
    "properties": {
        "role": {"const": "assistant"},
        "content": {"type": ["string", "null"]},
        "tool_calls": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "type", "function"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "type": {"const": "function"},
                    "function": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["name", "arguments"],
                        "properties": {
                            "name": {"type": "string"},
                            "arguments": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
}


def provider_response(calls=None):
    payload = completion(
        content=None
        if calls
        else json.dumps(
            {
                "content": "Obras consultadas; no invento diferencias de escenas.",
                "movie_ids": [11, 12, 13],
                "book_ids": [],
                "comparisons": [],
            }
        ),
        tool_calls=calls,
    ).model_dump(exclude_none=True)
    payload["usage"] = {"prompt_tokens": 800, "completion_tokens": 50, "total_tokens": 850}
    if calls:
        payload["choices"][0]["message"].update(
            {
                "reasoning": "private-response-reasoning",
                "internal_metadata": "private-metadata",
            }
        )
    return payload


def extended_call(name, arguments, index=0):
    return {
        "id": f"call-{index}",
        "type": "function",
        "index": index,
        "function": {
            "name": name,
            "arguments": json.dumps(arguments),
            "provider_metadata": "private-function-metadata",
        },
    }


@pytest.mark.parametrize("multiple", [False, True])
async def test_successful_discovery_followed_by_strict_wire_validation(comparison_setup, multiple):
    """Before the fix the second HTTP request is rejected with 400 after MCP succeeds."""
    _, session = comparison_setup
    calls = [extended_call("discover_movies", {"genre": "ciencia ficción"})]
    if multiple:
        calls.append(extended_call("movie_details", {"movie_id": 11}, 1))
    requests = []

    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return httpx.Response(200, json=provider_response(calls))
        assistant = next(m for m in body["messages"] if m.get("tool_calls"))
        try:
            validate(assistant, ASSISTANT_SCHEMA)
        except ValidationError:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "type": "invalid_request_error",
                        "code": "invalid_request_error",
                        "param": "messages.3.tool_calls.0.index",
                        "message": "Tool call contains an unsupported response-only field.",
                    }
                },
            )
        return httpx.Response(200, json=provider_response())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        sdk = AsyncGroq(api_key="test-key", http_client=http, max_retries=0)
        with patch("app.clients.groq_client.AsyncGroq", return_value=sdk):
            async with GroqClient(Settings(groq_api_key="test-key")) as client:
                agent = GroqAgent(Settings(), client)
                result = await agent.respond_with_metadata(
                    "Recomiéndame tres películas de ciencia ficción", "wire"
                )
    assert session.call_tool.await_count == len(calls)  # MCP finished before request two.
    assert result.content != SAFE_ERROR
    assert len(requests) == 2
    outgoing = requests[1]["messages"]
    assistant = next(m for m in outgoing if m.get("tool_calls"))
    results = [m for m in outgoing if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in results] == [c["id"] for c in calls]
    assert [c["id"] for c in assistant["tool_calls"]] == [c["id"] for c in calls]
    assert all(isinstance(m["content"], str) for m in results)
    assert all(set(m) == {"role", "tool_call_id", "content"} for m in results)
    assert [m["role"] for m in outgoing[-len(calls) - 1 :]] == ["assistant", *["tool"] * len(calls)]
    assert "private-" not in json.dumps(outgoing)
    assert requests[1]["tool_choice"] == "auto"
    assert requests[1]["reasoning_effort"] == "low"
    assert len(result.metadata.movies) == 3
    assert len(agent.memory.entries["wire"].turns) == 1


async def test_provider_generation_400_after_mcp_is_classified_without_retry_or_memory_commit(
    comparison_setup,
    caplog,
):
    _, session = comparison_setup
    requests = []
    private = "private-body-system-prompt-tool-result-api-key"

    def handle(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(
                200,
                json=provider_response(
                    [extended_call("discover_movies", {"genre": "ciencia ficción"})]
                ),
            )
        return httpx.Response(
            400,
            json={
                "error": {
                    "code": "tool_use_failed",
                    "type": "invalid_request_error",
                    "param": "tools",
                    "message": private,
                    "failed_generation": private,
                }
            },
        )

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            sdk = AsyncGroq(api_key="test-key", http_client=http, max_retries=0)
            with patch("app.clients.groq_client.AsyncGroq", return_value=sdk):
                async with GroqClient(Settings(groq_api_key="test-key")) as client:
                    agent = GroqAgent(Settings(), client)
                    reply = await agent.respond(
                        "Recomiéndame tres películas de ciencia ficción", "failure"
                    )
    assert reply == SAFE_ERROR
    assert len(requests) == 2 and session.call_tool.await_count == 1
    entry = agent.memory.entries["failure"]
    assert not entry.turns and not entry.artifacts and not entry.tool_cache
    events = [json.loads(r.getMessage()) for r in caplog.records if r.name == "uvicorn.error"]
    event = next(e for e in events if e["event"] == "groq_request_failed")
    assert event["status_code"] == 400 and event["will_retry"] is False
    assert event["error_class"] == "tool_generation"
    assert event["provider_code"] == "tool_use_failed"
    assert event["has_failed_generation"] is True
    assert event["parameter"] == "tools"
    assert event["assistant_tool_calls"] == 1 and event["tool_results"] == 1
    assert event["run_id"] == events[-1]["run_id"]
    assert private not in caplog.text and "private-response-reasoning" not in caplog.text
    assert "test-key" not in caplog.text


@pytest.mark.parametrize("call_ids", [["", "second"], ["duplicate", "duplicate"]])
async def test_invalid_call_ids_fail_before_executing_mcp(comparison_setup, call_ids):
    _, session = comparison_setup
    calls = [extended_call("movie_details", {"movie_id": 11}, i) for i in range(2)]
    for call, call_id in zip(calls, call_ids, strict=True):
        call["id"] = call_id
    requests = []

    def handle(request):
        requests.append(1)
        return httpx.Response(200, json=provider_response(calls))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        sdk = AsyncGroq(api_key="test-key", http_client=http, max_retries=0)
        with patch("app.clients.groq_client.AsyncGroq", return_value=sdk):
            async with GroqClient(Settings(groq_api_key="test-key")) as client:
                agent = GroqAgent(Settings(), client)
                assert await agent.respond("Consulta las películas", "invalid") == SAFE_ERROR
    assert len(requests) == 1
    session.call_tool.assert_not_awaited()
    assert not agent.memory.entries["invalid"].turns


async def test_comparison_synthesis_omits_the_entire_tool_exchange_and_schemas(comparison_setup):
    _, session = comparison_setup
    requests = []

    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(
            200,
            json=provider_response(
                [extended_call("compare_movies", {"movie_ids": [11, 12, 13]})]
                if len(requests) == 1
                else None
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        sdk = AsyncGroq(api_key="test-key", http_client=http, max_retries=0)
        with patch("app.clients.groq_client.AsyncGroq", return_value=sdk):
            async with GroqClient(Settings(groq_api_key="test-key")) as client:
                agent = GroqAgent(Settings(), client)
                result = await agent.respond_with_metadata(
                    "Compara las películas 11, 12 y 13", "wire"
                )
    assert result.content != SAFE_ERROR
    assert len(requests) == 2 and session.call_tool.await_count == 1
    final = requests[-1]
    assert not {"tools", "tool_choice", "parallel_tool_calls", "response_format"} & final.keys()
    assert final["reasoning_effort"] == "low" and final["max_completion_tokens"] == 1800
    assert all(m["role"] != "tool" and "tool_calls" not in m for m in final["messages"])
    assert "private-" not in json.dumps(final)
    assert len(result.metadata.movies) == 3
