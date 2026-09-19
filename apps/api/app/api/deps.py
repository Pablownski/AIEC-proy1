"""FastAPI dependency providers.

Kept separate from route modules so tests can override them with
``app.dependency_overrides`` without touching route code.
"""

from __future__ import annotations

from functools import lru_cache

from app.agents.mock import MockAgent
from app.core.config import get_settings
from app.services.chat_service import ChatService


@lru_cache
def get_chat_service() -> ChatService:
    settings = get_settings()
    agent = MockAgent(delay_seconds=settings.mock_agent_delay_seconds)
    return ChatService(agent=agent)
