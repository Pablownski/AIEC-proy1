from __future__ import annotations

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.api.deps import get_chat_service
from app.schemas.chat import ChatRequestMessage
from app.services.chat_service import ChatService

router = APIRouter()


@router.websocket("/ws/chat")
async def chat_socket(
    websocket: WebSocket,
    service: ChatService = Depends(get_chat_service),
) -> None:
    await websocket.accept()
    try:
        while True:
            payload = await websocket.receive_json()
            conversation_id = payload.get("conversation_id", "")

            try:
                message = ChatRequestMessage(role="user", content=payload.get("content", ""))
            except ValidationError:
                await websocket.send_json({"type": "error", "detail": "Mensaje inválido."})
                continue

            await websocket.send_json({"type": "agent_start"})
            try:
                response = await service.handle_message(
                    conversation_id=conversation_id, message=message
                )
            except Exception:  # noqa: BLE001 - safe user-facing error over the socket
                await websocket.send_json(
                    {
                        "type": "error",
                        "detail": "No pudimos enviar tu mensaje. Intenta nuevamente.",
                    }
                )
                continue

            await websocket.send_json(
                {
                    "type": "agent_message",
                    "conversation_id": response.conversation_id,
                    "message": response.message.model_dump(mode="json"),
                }
            )
            await websocket.send_json({"type": "agent_end"})
    except WebSocketDisconnect:
        return
