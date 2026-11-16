from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.groq_agent import GroqAgent
from app.api.deps import get_chat_service
from app.api.routes import chat, health, websocket
from app.core.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    service = get_chat_service()
    try:
        yield
    finally:
        if isinstance(service.agent, GroqAgent):
            await service.agent.close()
        get_chat_service.cache_clear()


app = FastAPI(title="AGIChat API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(websocket.router)
