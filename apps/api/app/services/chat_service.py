"""Application-level use case for handling a chat turn.

Depends only on the ``Agent`` protocol so the concrete agent (mock today,
a real agent in Proyecto 2) can be swapped without touching this service.
"""

from __future__ import annotations

from app.agents.base import Agent, StructuredAgent
from app.schemas.chat import ChatMessage, ChatRequestMessage, ChatResponse
from app.schemas.presentation import AgentReply


class ChatService:
    def __init__(self, agent: Agent) -> None:
        self.agent = agent

    async def handle_message(
        self, conversation_id: str, message: ChatRequestMessage
    ) -> ChatResponse:
        if isinstance(self.agent, StructuredAgent):
            reply = await self.agent.respond_with_metadata(message.content, conversation_id)
        else:
            reply = AgentReply(content=await self.agent.respond(message.content, conversation_id))
        return ChatResponse(
            conversation_id=conversation_id,
            message=ChatMessage(role="assistant", content=reply.content, metadata=reply.metadata),
        )
