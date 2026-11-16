import traceback
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from groq import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)
from groq.types.chat import ChatCompletion

from app.clients.groq_client import GroqClient, GroqClientError
from app.core.config import Settings


def completion(*, content="Una recomendación", tool_calls=None):
    return ChatCompletion.model_validate(
        {
            "id": "completion-test",
            "object": "chat.completion",
            "created": 0,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls" if tool_calls else "stop",
                    "message": {
                        "role": "assistant",
                        "content": content,
                        "tool_calls": tool_calls,
                    },
                }
            ],
        }
    )


@pytest.fixture
def sdk():
    with patch("app.clients.groq_client.AsyncGroq") as factory:
        client = factory.return_value
        client.chat.completions.create = AsyncMock(return_value=completion())
        client.close = AsyncMock()
        yield factory, client


@pytest.mark.parametrize("key", [None, "", "   "])
def test_missing_credentials_fail_only_when_client_is_created(sdk, key):
    settings = Settings(groq_api_key=key)
    with pytest.raises(GroqClientError, match="GROQ_API_KEY") as caught:
        GroqClient(settings)
    assert caught.value.code == "configuration"
    sdk[0].assert_not_called()


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_timeout_is_rejected(sdk, timeout):
    with pytest.raises(ValueError, match="timeout"):
        GroqClient(Settings(groq_api_key="test-key"), timeout_seconds=timeout)
    sdk[0].assert_not_called()


async def test_default_model_request_response_and_close(sdk):
    factory, backend = sdk
    messages = [
        {"role": "system", "content": "Recomienda películas"},
        {"role": "user", "content": "Una comedia"},
    ]
    async with GroqClient(Settings(groq_api_key="test-key")) as client:
        result = await client.complete(messages)
    factory.assert_called_once_with(api_key="test-key", timeout=10.0, max_retries=0)
    backend.chat.completions.create.assert_awaited_once_with(
        model="openai/gpt-oss-120b", messages=messages, stream=False
    )
    assert result.choices[0].message.content == "Una recomendación"
    backend.close.assert_awaited_once()


async def test_custom_model_and_timeout(sdk):
    client = GroqClient(
        Settings(groq_api_key="test-key", groq_model="custom-model"), timeout_seconds=5.0
    )
    await client.complete([{"role": "user", "content": "Hola"}])
    assert sdk[0].call_args.kwargs["timeout"] == 5.0
    assert sdk[1].chat.completions.create.call_args.kwargs["model"] == "custom-model"
    await client.close()


async def test_tool_definitions_enable_sequential_function_calling(sdk):
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_movies",
                "description": "Busca películas",
                "parameters": {"type": "object"},
            },
        }
    ]
    async with GroqClient(Settings(groq_api_key="test-key")) as client:
        await client.complete([{"role": "user", "content": "Hola"}], tools=tools)
    kwargs = sdk[1].chat.completions.create.call_args.kwargs
    assert kwargs["tools"] == tools
    assert kwargs["tool_choice"] == "auto"
    assert kwargs["parallel_tool_calls"] is False
    assert kwargs["max_completion_tokens"] == 1800


async def test_response_preserves_tool_calls_without_executing_them(sdk):
    tool_calls = [
        {
            "id": "call-test",
            "type": "function",
            "function": {"name": "search", "arguments": '{"query":"movie"}'},
        }
    ]
    sdk[1].chat.completions.create.return_value = completion(content=None, tool_calls=tool_calls)
    async with GroqClient(Settings(groq_api_key="test-key")) as client:
        result = await client.complete([{"role": "user", "content": "Hola"}])
    assert result.choices[0].message.content is None
    assert result.choices[0].message.tool_calls[0].function.name == "search"


def provider_error(kind):
    request = httpx.Request("POST", "https://api.groq.com")
    if kind == "timeout":
        return APITimeoutError(request=request)
    if kind == "connection":
        return APIConnectionError(message="provider-private-detail", request=request)
    exception, status = {
        "authentication": (AuthenticationError, 401),
        "rate_limit": (RateLimitError, 429),
        "provider": (APIStatusError, 500),
    }[kind]
    return exception(
        "provider-private-detail",
        response=httpx.Response(status, request=request),
        body={"detail": "provider-private-detail"},
    )


@pytest.mark.parametrize(
    "kind", ["timeout", "connection", "authentication", "rate_limit", "provider"]
)
async def test_provider_errors_are_controlled_and_sanitized(sdk, kind):
    sdk[1].chat.completions.create.side_effect = provider_error(kind)
    async with GroqClient(Settings(groq_api_key="test-key")) as client:
        with pytest.raises(GroqClientError) as caught:
            await client.complete([{"role": "user", "content": "Hola"}])
    assert caught.value.code == kind
    rendered = "".join(traceback.format_exception(caught.value))
    assert "provider-private-detail" not in rendered
    assert "test-key" not in rendered
    sdk[1].chat.completions.create.assert_awaited_once()
    sdk[1].close.assert_awaited_once()


async def test_empty_choices_are_a_controlled_response_error(sdk):
    sdk[1].chat.completions.create.return_value = completion().model_copy(update={"choices": []})
    async with GroqClient(Settings(groq_api_key="test-key")) as client:
        with pytest.raises(GroqClientError) as caught:
            await client.complete([{"role": "user", "content": "Hola"}])
    assert caught.value.code == "response"


@pytest.mark.parametrize("content", [None, "", "   "])
async def test_missing_text_without_tool_calls_is_a_response_error(sdk, content):
    sdk[1].chat.completions.create.return_value = completion(content=content)
    async with GroqClient(Settings(groq_api_key="test-key")) as client:
        with pytest.raises(GroqClientError) as caught:
            await client.complete([{"role": "user", "content": "Hola"}])
    assert caught.value.code == "response"
