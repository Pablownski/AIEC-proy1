"""Async Groq boundary; not yet wired into the chatbot or its agent."""

from __future__ import annotations

import math
from collections.abc import Sequence
from types import TracebackType

from groq import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AsyncGroq,
    AuthenticationError,
    RateLimitError,
)
from groq.types.chat import ChatCompletion, ChatCompletionMessageParam, ChatCompletionToolParam

from app.core.config import Settings


class GroqClientError(Exception):
    """Controlled provider failure with a safe message and machine-readable code."""

    def __init__(self, code: str, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class GroqClient:
    def __init__(self, settings: Settings, *, timeout_seconds: float = 10.0) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds debe ser positivo y finito.")
        if settings.groq_api_key is None or not settings.groq_api_key.get_secret_value().strip():
            raise GroqClientError("configuration", "GROQ_API_KEY no está configurada.")
        self._model = settings.groq_model
        self._client = AsyncGroq(
            api_key=settings.groq_api_key.get_secret_value(),
            timeout=timeout_seconds,
            max_retries=0,
        )

    async def complete(
        self,
        messages: Sequence[ChatCompletionMessageParam],
        *,
        tools: list[ChatCompletionToolParam] | None = None,
        allow_tools: bool = True,
    ) -> ChatCompletion:
        """Return the full completion, preserving tool calls for a future agent."""
        try:
            if tools:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    stream=False,
                    tools=tools,
                    tool_choice="auto" if allow_tools else "none",
                    parallel_tool_calls=False,
                    max_completion_tokens=1800,
                )
            else:
                response = await self._client.chat.completions.create(
                    model=self._model, messages=messages, stream=False
                )
        except APITimeoutError:
            raise GroqClientError("timeout", "Groq excedió el tiempo de espera.") from None
        except APIConnectionError:
            raise GroqClientError("connection", "No se pudo conectar con Groq.") from None
        except AuthenticationError as exc:
            raise GroqClientError(
                "authentication", "Groq rechazó la autenticación.", status_code=exc.status_code
            ) from None
        except RateLimitError as exc:
            raise GroqClientError(
                "rate_limit", "Groq alcanzó el límite de solicitudes.", status_code=exc.status_code
            ) from None
        except APIStatusError as exc:
            raise GroqClientError(
                "provider", "No se pudo completar la solicitud a Groq.", status_code=exc.status_code
            ) from None
        except APIError:
            raise GroqClientError("provider", "No se pudo completar la solicitud a Groq.") from None

        if not response.choices:
            raise GroqClientError("response", "Groq devolvió una respuesta sin opciones.")
        message = response.choices[0].message
        if not (message.content and message.content.strip()) and not message.tool_calls:
            raise GroqClientError("response", "Groq devolvió una respuesta sin contenido.")
        return response

    async def close(self) -> None:
        await self._client.close()

    async def __aenter__(self) -> GroqClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()
