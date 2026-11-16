"""Async Groq boundary; not yet wired into the chatbot or its agent."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
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
    omit,
)
from groq.types.chat import ChatCompletion, ChatCompletionMessageParam, ChatCompletionToolParam

from app.clients.rate_limits import LimitType, RequestBudget, read_rate_limit
from app.core.config import Settings

logger = logging.getLogger("uvicorn.error")


class GroqClientError(Exception):
    """Controlled provider failure with a safe message and machine-readable code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int | None = None,
        limit_type: LimitType = "unknown",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.limit_type = limit_type


class GroqClient:
    def __init__(self, settings: Settings, *, timeout_seconds: float = 10.0) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds debe ser positivo y finito.")
        if settings.groq_api_key is None or not settings.groq_api_key.get_secret_value().strip():
            raise GroqClientError("configuration", "GROQ_API_KEY no está configurada.")
        self._model = settings.groq_model
        self._timeout_seconds = timeout_seconds
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
        budget: RequestBudget | None = None,
    ) -> ChatCompletion:
        """Return the full completion, preserving tool calls for a future agent."""
        budget = budget or RequestBudget()
        attempts = 0
        request_chars = len(json.dumps(messages, ensure_ascii=False))
        schema_chars = len(json.dumps(tools or [], ensure_ascii=False))
        try:
            while True:
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
                            reasoning_effort="low"
                            if self._model in {"openai/gpt-oss-120b", "openai/gpt-oss-20b"}
                            else omit,
                        )
                    else:
                        response = await self._client.chat.completions.create(
                            model=self._model,
                            messages=messages,
                            stream=False,
                        )
                    break
                except RateLimitError as exc:
                    limit = read_rate_limit(exc)
                    delay = limit.retry_after
                    retry = (
                        limit.kind in {"rpm", "tpm"}
                        and delay is not None
                        and delay <= 8
                        and budget.retries_remaining > 0
                        and attempts < 1
                        and time.monotonic() + delay + self._timeout_seconds < budget.deadline
                    )
                    logger.warning(
                        json.dumps(
                            {
                                "event": "groq_rate_limited",
                                "limit_type": limit.kind,
                                "retry_after": delay,
                                "will_retry": retry,
                                "run_id": budget.run_id,
                                "status_code": 429,
                                "request_chars": request_chars,
                                "schema_chars": schema_chars,
                            }
                        )
                    )
                    if not retry:
                        raise GroqClientError(
                            "rate_limit",
                            "Groq alcanzó un límite de uso.",
                            status_code=429,
                            limit_type=limit.kind,
                        ) from None
                    budget.retries_remaining -= 1
                    attempts += 1
                    await asyncio.sleep(delay if delay is not None else 0)
        except APITimeoutError:
            raise GroqClientError("timeout", "Groq excedió el tiempo de espera.") from None
        except APIConnectionError:
            raise GroqClientError("connection", "No se pudo conectar con Groq.") from None
        except AuthenticationError as exc:
            raise GroqClientError(
                "authentication", "Groq rechazó la autenticación.", status_code=exc.status_code
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
        if response.usage:
            logger.info(
                json.dumps(
                    {
                        "event": "groq_usage",
                        "run_id": budget.run_id,
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "request_chars": request_chars,
                        "schema_chars": schema_chars,
                    }
                )
            )
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
