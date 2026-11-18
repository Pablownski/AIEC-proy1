"""Local admission regressions: no provider calls; clocks and usage are simulated."""

import asyncio
import json
import logging
import time
from unittest.mock import patch

import httpx
import pytest
from groq import APIStatusError

from app.agents.diagnostics import TurnTrace
from app.agents.groq_agent import BUDGET_ERROR, GroqAgent
from app.clients.groq_client import GroqClient, GroqClientError
from app.clients.rate_limits import RequestBudget
from app.clients.token_budget import AdmissionDenied, TokenWindow, Usage
from app.core.config import Settings
from tests.test_comparison_regression import comparison_setup as comparison_setup
from tests.test_comparison_regression import request_tool
from tests.test_efficiency import counted
from tests.test_groq_agent import agent_setup as agent_setup
from tests.test_groq_client import completion
from tests.test_groq_client import sdk as sdk
from tests.test_rate_limits import limited


class Clock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    async def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(time, "monotonic", lambda: clock.now)
    monkeypatch.setattr(asyncio, "sleep", clock.sleep)
    monkeypatch.setattr("app.agents.groq_agent.TurnTrace", lambda: TurnTrace(started=clock.now))
    return clock


@pytest.mark.parametrize("spent", [2663, 2655])
async def test_observed_first_round_can_afford_a_bounded_final_response(sdk, spent):
    sdk[1].chat.completions.create.side_effect = [
        counted(completion(), spent - 63, 63),
        counted(completion(), 800, 200),
    ]
    budget = RequestBudget(deadline=time.monotonic() + 60)
    with patch("app.clients.groq_client.estimate_tokens", side_effect=[1200, 3000]):
        async with GroqClient(Settings(groq_api_key="test")) as client:
            await client.complete([{"role": "user", "content": "Plan"}], budget=budget)
            await client.complete(
                [{"role": "user", "content": "Final"}], allow_tools=False, budget=budget
            )
    assert sdk[1].chat.completions.create.await_count == 2
    assert (
        sdk[1].chat.completions.create.call_args.kwargs["max_completion_tokens"]
        == 7000 - spent - 3000
    )
    assert budget.spent_tokens == spent + 1000


async def test_rejected_http_request_does_not_poison_the_next_admission(sdk):
    sdk[1].chat.completions.create.side_effect = [
        APIStatusError(
            "safe",
            response=httpx.Response(400, request=httpx.Request("POST", "https://api.groq.test")),
            body={},
        ),
        counted(completion(), 80, 20),
    ]
    budget = RequestBudget()
    async with GroqClient(Settings(groq_api_key="test", groq_turn_token_budget=3000)) as client:
        with pytest.raises(GroqClientError):
            await client.complete([{"role": "user", "content": "a"}], budget=budget)
        await client.complete([{"role": "user", "content": "b"}], budget=budget)
    assert budget.spent_tokens == 100


async def test_sixty_seconds_expire_previous_usage_without_erasing_current_turn(sdk, clock):
    sdk[1].chat.completions.create.return_value = counted(completion(), 2600, 63)
    with patch("app.clients.groq_client.estimate_tokens", return_value=1200):
        async with GroqClient(Settings(groq_api_key="test")) as client:
            first = RequestBudget(deadline=clock.now + 60)
            await client.complete([{"role": "user", "content": "a"}], budget=first)
            clock.now += 60
            second = RequestBudget(deadline=clock.now + 60)
            await client.complete([{"role": "user", "content": "b"}], budget=second)
            assert len(client._tokens.usage) == 1
            assert first.spent_tokens == second.spent_tokens == 2663
            assert client._tokens.available(second)[1] == 7200 - 2663
    assert not clock.sleeps


async def test_search_after_previous_query_gets_an_economical_final_and_commits(
    comparison_setup,
    sdk,
    clock,
):
    _, session = comparison_setup
    sdk[1].chat.completions.create.side_effect = [
        counted(completion(), 800, 200),
        counted(request_tool("search_movies", {"query": "Obra"}, 1), 2600, 63),
        counted(
            completion(
                content=json.dumps(
                    {
                        "content": "Una obra consultada en TMDB.",
                        "movie_ids": [11],
                        "book_ids": [],
                        "comparisons": [],
                    }
                )
            ),
            800,
            200,
        ),
    ]
    with patch(
        "app.clients.groq_client.estimate_tokens", side_effect=[100, 1200, 1400, 4000, 3000]
    ):
        async with GroqClient(Settings(groq_api_key="test")) as client:
            await client.complete([{"role": "user", "content": "Consulta previa"}])
            clock.now += 60
            agent = GroqAgent(Settings(), client)
            reply = await agent.respond_with_metadata("Recomienda una película", "followup")
            assert "obra consultada" in reply.content
            assert reply.metadata.movies[0].id == 11
            assert len(agent.memory.entries["followup"].turns) == 1
            assert not client._tokens.pending and not client._tokens.holds
    assert session.call_tool.await_count == 1
    assert (
        sdk[1].chat.completions.create.await_count == 3
    )  # Prior + planning + final, not a local rejection.
    assert sdk[1].chat.completions.create.call_args.kwargs["max_completion_tokens"] == 1337


async def test_multiple_turns_share_usage_but_not_the_per_turn_ceiling(
    comparison_setup, sdk, clock
):
    sdk[1].chat.completions.create.return_value = counted(
        completion(content="Puedo comparar obras."), 250, 50
    )
    async with GroqClient(Settings(groq_api_key="test")) as client:
        agent = GroqAgent(Settings(), client)
        for number in range(4):
            assert "comparar" in await agent.respond(f"Pregunta {number}", "same")
        assert len(agent.memory.entries["same"].turns) == 4
        assert sum(u.tokens for u in client._tokens.usage) == 1200
        assert not client._tokens.pending and not client._tokens.holds


async def test_preflight_avoids_tool_calls_and_releases_holds_after_local_denial(
    comparison_setup,
    sdk,
    clock,
):
    _, session = comparison_setup
    sdk[1].chat.completions.create.return_value = counted(
        request_tool("search_movies", {"query": "Obra"}, 1), 2600, 63
    )
    with patch("app.clients.groq_client.estimate_tokens", return_value=1200):
        async with GroqClient(Settings(groq_api_key="test", groq_turn_token_budget=3500)) as client:
            agent = GroqAgent(Settings(), client)
            assert await agent.respond("Busca una película", "low") == BUDGET_ERROR
            session.call_tool.assert_not_awaited()
            assert not client._tokens.pending and not client._tokens.holds
            assert (
                sum(u.tokens for u in client._tokens.usage) == 2663
            )  # Real usage remains charged.
            assert not agent.memory.entries["low"].turns


async def test_recovery_waits_for_enough_records_not_only_the_first_expiry(clock):
    window = TokenWindow(7000, 7200)
    window.usage = [Usage(50, 500), Usage(70, 4500)]
    lease = await window.admit(RequestBudget(deadline=150), 3232, 10)
    assert clock.sleeps == [30]  # At 110 only 500 expire; at 130 both records have expired.
    assert clock.now == 130 and lease.output == 1800
    window.release(lease)
    assert not window.pending


async def test_near_limit_logs_available_capacity_and_recovery_without_reserving(
    sdk, clock, caplog
):
    async with GroqClient(Settings(groq_api_key="test")) as client:
        client._tokens.usage = [Usage(clock.now, 6500)]
        budget = RequestBudget(deadline=clock.now + 20)
        with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
            with pytest.raises(GroqClientError) as error:
                await client.complete(
                    [{"role": "user", "content": "private-content"}], budget=budget
                )
        assert error.value.retry_after == 60 and error.value.budget_reason == "recent_window"
        assert budget.spent_tokens == budget.reserved_tokens == 0
        assert not client._tokens.pending and not client._tokens.holds
    event = next(json.loads(r.getMessage()) for r in caplog.records if r.name == "uvicorn.error")
    assert event["available_minute_tokens"] == 700 and event["recovery_seconds"] == 60
    assert "private-content" not in caplog.text and "test" not in json.dumps(event)
    sdk[1].chat.completions.create.assert_not_awaited()


async def test_pending_leases_do_not_expire_and_settlement_is_counted_once(clock):
    window = TokenWindow(7000, 7200)
    budget = RequestBudget(deadline=300)
    lease = await window.admit(budget, 2000, 10)
    clock.now += 61
    with pytest.raises(AdmissionDenied):
        await window.admit(RequestBudget(deadline=300), 3000, 10)
    window.settle(lease, 2663)
    window.settle(lease, 2663)
    assert len(window.usage) == 1 and budget.spent_tokens == 2663
    clock.now += 59
    assert window.available(RequestBudget())[1] == 7200 - 2663
    clock.now += 1
    assert window.available(RequestBudget())[1] == 7200


async def test_synthesis_hold_cannot_be_stolen_by_another_conversation(clock):
    window = TokenWindow(7000, 7200)
    first = RequestBudget(deadline=200)
    await window.hold_synthesis(first, 2200, 10)
    other = await window.admit(RequestBudget(deadline=200), 1000, 10)
    with pytest.raises(AdmissionDenied):
        await window.admit(RequestBudget(deadline=110), 1000, 10)
    synthesis = await window.admit(first, 2200, 10)
    assert sum(p.tokens for p in window.pending) <= 7200
    window.release(other)
    window.settle(synthesis, 1000)
    assert first.reserved_tokens == 0 and not window.holds


async def test_concurrent_calls_share_atomic_reservations_and_recover_after_completion(sdk, clock):
    release = asyncio.Event()

    async def generate(**kwargs):
        await release.wait()
        return counted(completion(), 800, 200)

    sdk[1].chat.completions.create.side_effect = generate
    async with GroqClient(Settings(groq_api_key="test")) as client:
        with patch("app.clients.groq_client.estimate_tokens", return_value=1000):
            tasks = [
                asyncio.create_task(
                    client.complete(
                        [{"role": "user", "content": "a"}], budget=RequestBudget(deadline=150)
                    )
                )
                for _ in range(3)
            ]
            await asyncio.sleep(0)  # Fake sleep has no yield: explicitly let tasks run below.
            await asyncio.wait(tasks, timeout=0)
            assert len(client._tokens.pending) == 2
            assert sum(p.tokens for p in client._tokens.pending) <= 7200
            release.set()
            results = await asyncio.gather(*tasks, return_exceptions=True)
        assert sum(isinstance(r, GroqClientError) for r in results) == 1
        assert not client._tokens.pending and sum(u.tokens for u in client._tokens.usage) == 2000


async def test_429_retry_is_not_charged_twice_and_clears_each_lease(sdk, clock):
    sdk[1].chat.completions.create.side_effect = [
        limited(retry_after="12"),
        counted(completion(), 800, 200),
    ]
    budget = RequestBudget(deadline=clock.now + 60)
    async with GroqClient(Settings(groq_api_key="test")) as client:
        await client.complete([{"role": "user", "content": "a"}], budget=budget)
        assert budget.spent_tokens == 1000 and budget.prompt_tokens == 800
        assert budget.completion_tokens == 200 and budget.reserved_tokens == 0
        assert len(client._tokens.usage) == 1 and not client._tokens.pending
    assert sdk[1].chat.completions.create.await_count == 2 and clock.sleeps == [12]


async def test_budget_rejection_after_tools_releases_the_turn_hold(comparison_setup, sdk, clock):
    sdk[1].chat.completions.create.return_value = counted(
        request_tool("search_movies", {"query": "Obra"}, 1), 2600, 63
    )
    with patch("app.clients.groq_client.estimate_tokens", side_effect=[1200, 1400, 6000, 6000]):
        async with GroqClient(Settings(groq_api_key="test")) as client:
            agent = GroqAgent(Settings(), client)
            assert "presupuesto local" in await agent.respond("Busca Obra", "failed")
            assert not client._tokens.pending and not client._tokens.holds
            assert sum(u.tokens for u in client._tokens.usage) == 2663
            assert not agent.memory.entries["failed"].artifacts


async def test_cancelled_inflight_request_has_no_dangling_reservation(sdk, clock):
    started = asyncio.Event()

    async def generate(**kwargs):
        started.set()
        await asyncio.Event().wait()

    sdk[1].chat.completions.create.side_effect = generate
    budget = RequestBudget(deadline=200)
    async with GroqClient(Settings(groq_api_key="test")) as client:
        task = asyncio.create_task(
            client.complete([{"role": "user", "content": "a"}], budget=budget)
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not client._tokens.pending and budget.reserved_tokens == 0
        assert client._tokens.usage[0].estimated  # Billing uncertain; no dangling lease.
        clock.now += 60
        assert client._tokens.available(RequestBudget())[1] == 7200


async def test_truncated_economical_output_is_not_returned_as_a_complete_answer(sdk, clock):
    response = counted(completion(), 800, 200)
    response.choices[0].finish_reason = "length"
    sdk[1].chat.completions.create.return_value = response
    async with GroqClient(Settings(groq_api_key="test")) as client:
        client._tokens.usage = [Usage(clock.now, 6000)]
        budget = RequestBudget(deadline=200)
        with pytest.raises(GroqClientError) as error:
            await client.complete([{"role": "user", "content": "a"}], budget=budget)
        assert error.value.code == "budget" and error.value.budget_reason == "output_limit"
        assert budget.spent_tokens == 1000 and budget.reserved_tokens == 0


async def test_wait_message_survives_an_mcp_exception_group(agent_setup):
    agent, client, _ = agent_setup
    client.complete.side_effect = ExceptionGroup(
        "private",
        [
            GroqClientError("budget", "safe", retry_after=12, budget_reason="recent_window"),
        ],
    )
    message = await agent.respond("Una consulta", "wait")
    assert "presupuesto local" in message and "12 segundos" in message
    assert "private" not in message


async def test_per_turn_setting_cannot_override_the_minute_ceiling(clock):
    window = TokenWindow(100000, 7200)
    with pytest.raises(AdmissionDenied) as error:
        await window.admit(RequestBudget(deadline=200), 7000, 10)
    assert error.value.reason == "request_size"
    assert not window.pending and not window.usage


async def test_preflight_denies_extra_tools_but_requests_honest_synthesis(agent_setup):
    agent, client, tools = agent_setup
    client.complete.side_effect = [
        request_tool("search_movies", {"query": "Obra"}, 1),
        request_tool("movie_details", {"movie_id": 11}, 2),
        completion(content="Solo pude consultar la búsqueda; no puedo verificar más detalles."),
    ]
    client.reserve_synthesis.side_effect = [None, GroqClientError("budget", "safe")]
    reply = await agent.respond("Consulta la obra y su libro", "limited")
    assert "no puedo verificar" in reply
    assert tools.call.await_count == 1
    assert client.complete.call_args.kwargs["tools"] is None
    assert "sin nuevas búsquedas" in str(client.complete.call_args.args[0])
