"""Bounded in-process memory. Completed turns only; replaceable storage boundary."""

from __future__ import annotations

import asyncio
import json
import time
from collections import OrderedDict, deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from groq.types.chat import ChatCompletionMessageParam

from app.tools.models import ToolResult


@dataclass
class Conversation:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    turns: list[list[ChatCompletionMessageParam]] = field(default_factory=list)
    artifacts: list[ToolResult] = field(default_factory=list)
    requests: deque[float] = field(default_factory=deque)
    touched: float = field(default_factory=time.monotonic)
    last_input: str | None = None
    last_reply: str | None = None
    users: int = 0

    def messages(self) -> list[ChatCompletionMessageParam]:
        return [message for turn in self.turns for message in turn]

    def commit(
        self,
        text: str,
        reply: str,
        turn: list[ChatCompletionMessageParam],
        artifacts: list[ToolResult],
    ) -> None:
        self.turns.append(turn)
        while len(self.turns) > 6 or len(json.dumps(self.turns)) > 24000:
            self.turns.pop(0)
        self.artifacts = (self.artifacts + artifacts)[-12:]
        self.last_input, self.last_reply = text, reply
        self.touched = time.monotonic()


class ConversationMemory:
    def __init__(self, capacity: int = 128, ttl_seconds: float = 900) -> None:
        self.capacity, self.ttl_seconds = capacity, ttl_seconds
        self.entries: OrderedDict[str, Conversation] = OrderedDict()

    @asynccontextmanager
    async def turn(self, conversation_id: str) -> AsyncIterator[Conversation]:
        now = time.monotonic()
        for key, entry in list(self.entries.items()):
            if entry.users == 0 and now - entry.touched > self.ttl_seconds:
                del self.entries[key]
        if conversation_id not in self.entries:
            if len(self.entries) >= self.capacity:
                victim = next(
                    (key for key, entry in self.entries.items() if entry.users == 0), None
                )
                if victim is None:
                    raise ValueError("Memoria ocupada; intenta nuevamente")
                del self.entries[victim]
            self.entries[conversation_id] = Conversation()
        entry = self.entries[conversation_id]
        self.entries.move_to_end(conversation_id)
        entry.users += 1
        try:
            async with entry.lock:
                now = time.monotonic()
                while entry.requests and now - entry.requests[0] >= 60:
                    entry.requests.popleft()
                if len(entry.requests) >= 10:
                    raise ValueError("Límite de solicitudes; intenta más tarde")
                entry.requests.append(now)
                yield entry
        finally:
            entry.users -= 1
            entry.touched = time.monotonic()
