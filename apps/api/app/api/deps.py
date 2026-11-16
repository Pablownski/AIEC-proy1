"""FastAPI dependency providers.

Kept separate from route modules so tests can override them with
``app.dependency_overrides`` without touching route code.
"""

from __future__ import annotations

from functools import lru_cache

from app.agents.base import Agent
from app.agents.groq_agent import GroqAgent
from app.agents.mock import MockAgent
from app.clients.groq_client import GroqClient
from app.core.config import get_settings
from app.services.chat_service import ChatService


@lru_cache
def get_chat_service() -> ChatService:
    settings = get_settings()
    agent: Agent
    if settings.agent_provider == "groq":
        agent = GroqAgent(settings, GroqClient(settings))
    else:
        agent = MockAgent(delay_seconds=settings.mock_agent_delay_seconds)
    return ChatService(agent=agent)
