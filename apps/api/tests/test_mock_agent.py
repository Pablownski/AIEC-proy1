import time

import pytest

from app.agents.base import Agent
from app.agents.mock import MockAgent


def test_mock_agent_satisfies_agent_protocol():
    assert isinstance(MockAgent(), Agent)


async def test_mock_agent_responds_with_markdown():
    agent = MockAgent(delay_seconds=0)

    reply = await agent.respond("Cuéntame sobre AGIChat", conversation_id="conv-1")

    assert "##" in reply or "**" in reply or "-" in reply


async def test_mock_agent_echoes_context_from_the_message():
    agent = MockAgent(delay_seconds=0)

    reply = await agent.respond("¿Qué es AGIChat?", conversation_id="conv-1")

    assert "AGIChat" in reply


async def test_mock_agent_greets_on_greeting():
    agent = MockAgent(delay_seconds=0)

    reply = await agent.respond("hola", conversation_id="conv-1")

    assert "Hola" in reply or "hola" in reply


async def test_mock_agent_respects_configured_delay():
    agent = MockAgent(delay_seconds=0.05)

    start = time.monotonic()
    await agent.respond("Hola", conversation_id="conv-1")
    elapsed = time.monotonic() - start

    assert elapsed >= 0.05


async def test_mock_agent_rejects_empty_message():
    agent = MockAgent(delay_seconds=0)

    with pytest.raises(ValueError):
        await agent.respond("   ", conversation_id="conv-1")
