import json
import logging
import time
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from groq import RateLimitError
from groq.types.chat import ChatCompletion
from groq.types.completion_usage import CompletionUsage

from app.agents.groq_agent import DAILY_LIMIT_ERROR, GroqAgent
from app.clients.groq_client import GroqClient, GroqClientError
from app.clients.rate_limits import RequestBudget, read_rate_limit
from app.core.config import Settings
from tests.test_comparison_regression import (
    comparison_setup as comparison_setup,
)
from tests.test_comparison_regression import (
    request_tool,
)
from tests.test_groq_client import completion
from tests.test_groq_client import sdk as sdk


def limited(message="tokens per minute (TPM)", retry_after="2", **headers):
    if retry_after is not None:
        headers["retry-after"] = retry_after
    return RateLimitError(
        "private-provider-detail",
        response=httpx.Response(
            429,
            headers=headers,
            request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
        ),
        body={"error": {"message": message}},
    )


@pytest.mark.parametrize(
    "message,headers,expected",
    [
        ("tokens per minute (TPM)", {}, "tpm"),
        ("requests per minute (RPM)", {}, "rpm"),
        ("requests per day (RPD)", {}, "rpd"),
        ("tokens per day (TPD)", {}, "tpd"),
        ("daily quota exhausted", {}, "daily"),
        ("private message", {}, "unknown"),
        ("tokens per minute", {"x-ratelimit-remaining-requests": "0"}, "rpd"),
        ("private message", {"x-ratelimit-remaining-tokens": "0"}, "tpm"),
    ],
)
def test_only_safe_limit_types_are_extracted(message, headers, expected):
    info = read_rate_limit(limited(message, **headers))
    assert info.kind == expected
    assert info.retry_after == 2


async def test_minute_limit_retries_once_respecting_retry_after(sdk, caplog):
    sdk[1].chat.completions.create.side_effect = [limited(), completion()]
    with (
        patch("app.clients.groq_client.asyncio.sleep", new_callable=AsyncMock) as sleep,
        caplog.at_level(logging.INFO, logger="uvicorn.error"),
    ):
        async with GroqClient(Settings(groq_api_key="test-key")) as client:
            reply = await client.complete([{"role": "user", "content": "private-prompt"}])
    assert reply.choices
    sleep.assert_awaited_once_with(2)
    assert sdk[1].chat.completions.create.await_count == 2
    assert "private-provider-detail" not in caplog.text
    assert "private-prompt" not in caplog.text
    assert "test-key" not in caplog.text
    event = next(
        json.loads(r.getMessage())
        for r in caplog.records
        if json.loads(r.getMessage()).get("event") == "groq_rate_limited"
    )
    assert event["limit_type"] == "tpm" and event["will_retry"] is True


@pytest.mark.parametrize(
    "message,delay,headers",
    [
        ("tokens per day", "1", {}),
        ("requests per day", "1", {}),
        ("daily quota", "1", {}),
        ("unknown", "1", {}),
        ("tokens per minute", "1", {"x-ratelimit-remaining-requests": "0"}),
        ("tokens per minute", "30", {}),
        ("tokens per minute", None, {}),
        ("tokens per minute", "invalid", {}),
        ("tokens per minute", "nan", {}),
        ("tokens per minute", "-1", {}),
    ],
)
async def test_daily_unknown_long_or_invalid_wait_never_retries(sdk, message, delay, headers):
    sdk[1].chat.completions.create.side_effect = limited(message, delay, **headers)
    with patch("app.clients.groq_client.asyncio.sleep", new_callable=AsyncMock) as sleep:
        async with GroqClient(Settings(groq_api_key="test-key")) as client:
            with pytest.raises(GroqClientError) as caught:
                await client.complete([{"role": "user", "content": "x"}])
    assert caught.value.code == "rate_limit"
    sdk[1].chat.completions.create.assert_awaited_once()
    sleep.assert_not_called()


async def test_retry_budget_is_shared_by_all_rounds_and_stops_after_one(sdk):
    sdk[1].chat.completions.create.side_effect = [limited(), completion(), limited()]
    budget = RequestBudget()
    with patch("app.clients.groq_client.asyncio.sleep", new_callable=AsyncMock) as sleep:
        async with GroqClient(Settings(groq_api_key="test-key")) as client:
            await client.complete([{"role": "user", "content": "x"}], budget=budget)
            with pytest.raises(GroqClientError):
                await client.complete([{"role": "user", "content": "y"}], budget=budget)
    assert budget.retries_remaining == 0
    assert sdk[1].chat.completions.create.await_count == 3
    sleep.assert_awaited_once()


async def test_no_wait_when_turn_deadline_has_insufficient_room(sdk):
    sdk[1].chat.completions.create.side_effect = limited()
    with patch("app.clients.groq_client.asyncio.sleep", new_callable=AsyncMock) as sleep:
        async with GroqClient(Settings(groq_api_key="test-key")) as client:
            with pytest.raises(GroqClientError):
                await client.complete(
                    [{"role": "user", "content": "x"}],
                    budget=RequestBudget(deadline=time.monotonic() + 3),
                )
    sleep.assert_not_called()


async def test_twelve_second_wait_recovers_when_turn_budget_allows_it(sdk):
    sdk[1].chat.completions.create.side_effect = [limited(retry_after="12"), completion()]
    with patch("app.clients.groq_client.asyncio.sleep", new_callable=AsyncMock) as sleep:
        async with GroqClient(Settings(groq_api_key="test-key")) as client:
            result = await client.complete(
                [{"role": "user", "content": "Compara"}],
                budget=RequestBudget(deadline=time.monotonic() + 60),
            )
    assert result.choices
    sleep.assert_awaited_once_with(12)
    assert sdk[1].chat.completions.create.await_count == 2


async def test_twelve_second_wait_does_not_start_when_deadline_is_too_close(sdk):
    sdk[1].chat.completions.create.side_effect = limited(retry_after="12")
    with patch("app.clients.groq_client.asyncio.sleep", new_callable=AsyncMock) as sleep:
        async with GroqClient(Settings(groq_api_key="test-key")) as client:
            with pytest.raises(GroqClientError):
                await client.complete(
                    [{"role": "user", "content": "Compara"}],
                    budget=RequestBudget(deadline=time.monotonic() + 15),
                )
    sleep.assert_not_called()
    sdk[1].chat.completions.create.assert_awaited_once()


def test_http_date_retry_after_is_supported():
    value = format_datetime(datetime.now(UTC) + timedelta(seconds=5), usegmt=True)
    delay = read_rate_limit(limited(retry_after=value)).retry_after
    assert 3 <= delay <= 5


async def test_observed_third_round_429_retries_without_reexecuting_tools(comparison_setup, sdk):
    _, session = comparison_setup
    sdk[1].chat.completions.create.side_effect = [
        request_tool("discover_movies", {"genre": "fantasía"}, 0),
        completion(content="Fantasía 11, Fantasía 12 y Fantasía 13"),
        request_tool("movie_details", {"movie_id": 11}, 1),
        request_tool("movie_details", {"movie_id": 12}, 2),
        limited(),
        completion(content="Puedo comparar solo lo confirmado por las fuentes"),
    ]
    # Successful production completions include usage; account for it rather than
    # reserving the maximum forever when a mock omits the provider counters.
    responses = list(sdk[1].chat.completions.create.side_effect)
    for response in responses:
        if isinstance(response, ChatCompletion):
            response.usage = CompletionUsage(
                prompt_tokens=100, completion_tokens=20, total_tokens=120
            )
    sdk[1].chat.completions.create.side_effect = responses
    with patch("app.clients.groq_client.asyncio.sleep", new_callable=AsyncMock) as sleep:
        async with GroqClient(Settings(groq_api_key="test-key")) as client:
            agent = GroqAgent(Settings(), client)
            await agent.respond("Recomiéndame tres películas", "one")
            reply = await agent.respond("Compara con sus libros", "one")
    assert "comparar" in reply
    assert len(agent.memory.entries["one"].turns) == 2
    assert session.call_tool.await_count == 3
    assert sdk[1].chat.completions.create.await_count == 6
    calls = sdk[1].chat.completions.create.await_args_list
    assert calls[-1].kwargs["messages"] == calls[-2].kwargs["messages"]
    sleep.assert_awaited_once_with(2)


async def test_daily_limit_is_understandable_and_preserves_memory(comparison_setup, sdk):
    sdk[1].chat.completions.create.side_effect = limited("tokens per day")
    async with GroqClient(Settings(groq_api_key="test-key")) as client:
        agent = GroqAgent(Settings(), client)
        assert await agent.respond("Compara", "one") == DAILY_LIMIT_ERROR
        assert not agent.memory.entries["one"].turns
        assert not agent.memory.entries["one"].tool_cache


async def test_usage_diagnostics_log_counts_without_prompt_or_key(sdk, caplog):
    sdk[1].chat.completions.create.return_value = ChatCompletion.model_validate(
        {
            **completion().model_dump(),
            "usage": {"prompt_tokens": 321, "completion_tokens": 17, "total_tokens": 338},
        }
    )
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        async with GroqClient(Settings(groq_api_key="test-key")) as client:
            await client.complete([{"role": "user", "content": "private-prompt"}])
    event = json.loads(caplog.records[-1].getMessage())
    assert event["event"] == "groq_usage"
    assert event["prompt_tokens"] == 321
    assert event["completion_tokens"] == 17
    assert event["request_chars"] > 0
    assert "private-prompt" not in caplog.text
    assert "test-key" not in caplog.text
