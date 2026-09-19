"""Pydantic contracts shared by the REST and WebSocket chat endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

MessageRole = Literal["user", "assistant", "system"]


def _now() -> datetime:
    return datetime.now(UTC)


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    role: MessageRole
    content: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=_now)


class ChatRequestMessage(BaseModel):
    """Inbound message payload — id/created_at are assigned server-side."""

    role: MessageRole
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    conversation_id: str
    message: ChatRequestMessage


class ChatResponse(BaseModel):
    conversation_id: str
    message: ChatMessage


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
