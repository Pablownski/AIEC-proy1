from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_chat_service
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    try:
        return await service.handle_message(
            conversation_id=request.conversation_id,
            message=request.message,
        )
    except Exception as exc:  # noqa: BLE001 - translated to a safe user-facing error
        raise HTTPException(
            status_code=502,
            detail="No pudimos enviar tu mensaje. Intenta nuevamente.",
        ) from exc
