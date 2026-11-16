import asyncio

import pytest

from app.agents.memory import Conversation, ConversationMemory


async def test_capacity_ttl_and_active_entries():
    memory = ConversationMemory(capacity=1, ttl_seconds=1)
    async with memory.turn("one") as entry:
        with pytest.raises(ValueError):
            async with memory.turn("two"):
                pass
    entry.touched -= 2
    async with memory.turn("two"):
        assert "one" not in memory.entries
    async with memory.turn("three"):
        assert "two" not in memory.entries


async def test_same_conversation_is_serialized_and_others_are_independent():
    memory = ConversationMemory()
    entered = asyncio.Event()

    async def second():
        async with memory.turn("one"):
            entered.set()

    async with memory.turn("one"):
        task = asyncio.create_task(second())
        await asyncio.sleep(0)
        assert not entered.is_set()
        async with memory.turn("two"):
            pass
    await task
    assert entered.is_set()
    assert memory.entries["one"].users == 0


async def test_request_limit_and_window_expiration():
    memory = ConversationMemory()
    for _ in range(10):
        async with memory.turn("one"):
            pass
    with pytest.raises(ValueError):
        async with memory.turn("one"):
            pass
    entry = memory.entries["one"]
    entry.requests = type(entry.requests)(time - 61 for time in entry.requests)
    async with memory.turn("one"):
        assert len(entry.requests) == 1


def test_memory_keeps_complete_bounded_turns_and_artifacts():
    entry = Conversation()
    for index in range(10):
        entry.commit(
            str(index),
            "reply",
            [{"role": "user", "content": str(index)}, {"role": "assistant", "content": "reply"}],
            [],
        )
    assert len(entry.turns) == 6
    assert entry.messages()[0]["content"] == "4"
    entry.commit("large", "reply", [{"role": "user", "content": "x" * 25000}], [])
    assert not entry.turns
