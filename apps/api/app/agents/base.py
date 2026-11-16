"""Agent abstraction. ChatService depends on this Protocol, never on a concrete agent."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.schemas.presentation import AgentReply


@runtime_checkable
class Agent(Protocol):
    async def respond(self, message: str, conversation_id: str) -> str:
        """Return the agent's reply text for a given user message."""
        ...


@runtime_checkable
class StructuredAgent(Protocol):
    async def respond_with_metadata(self, message: str, conversation_id: str) -> AgentReply:
        """Optional capability; existing Agent implementations stay unchanged."""
        ...
