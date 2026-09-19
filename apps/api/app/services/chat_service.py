"""Application-level use case for handling a chat turn.

Depends only on the ``Agent`` protocol so the concrete agent (mock today,
a real agent in Proyecto 2) can be swapped without touching this service.
"""

from __future__ import annotations

from app.agents.base import Agent
from app.schemas.chat import ChatMessage, ChatRequestMessage, ChatResponse


class ChatService:
    def __init__(self, agent: Agent) -> None:
        self.agent = agent

    async def handle_message(
        self, conversation_id: str, message: ChatRequestMessage
    ) -> ChatResponse:
        reply_content = await self.agent.respond(
            message=message.content, conversation_id=conversation_id
        )
        return ChatResponse(
            conversation_id=conversation_id,
            message=ChatMessage(role="assistant", content=reply_content),
        )
