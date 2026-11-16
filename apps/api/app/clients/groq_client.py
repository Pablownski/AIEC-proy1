"""Async Groq boundary with safe errors and bounded, preventive token admission."""

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

from app.clients.rate_limits import LimitType, RequestBudget, estimate_tokens, read_rate_limit
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
        self._turn_limit = settings.groq_turn_token_budget
        self._minute_limit = int(settings.groq_tpm_budget * 0.9)
        # Shared by conversations using this client; reservations include in-flight requests.
        self._recent: list[list[float]] = []
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
        estimate = estimate_tokens(
            json.dumps([messages, tools or []], ensure_ascii=False, separators=(",", ":")),
            len(messages),
        )
        required = estimate + 1800  # Reserve the full maximum output, including reasoning.
        self._recent = [record for record in self._recent if record[0] > time.monotonic() - 60]

        def reject(reason: str) -> GroqClientError:
            logger.warning(
                json.dumps(
                    {
                        "event": "groq_budget_limited",
                        "reason": reason,
                        "run_id": budget.run_id,
                        "estimated_input_tokens": estimate,
                        "output_reserve": 1800,
                        "turn_tokens": budget.spent_tokens,
                        "recent_tokens": sum(r[1] for r in self._recent),
                    }
                )
            )
            return GroqClientError("budget", "Espera antes de consultar nuevamente.")

        if budget.spent_tokens + required > self._turn_limit or required > self._minute_limit:
            raise reject("turn_or_request")
        if sum(record[1] for record in self._recent) + required > self._minute_limit:
            window_delay = max(0.0, self._recent[0][0] + 60 - time.monotonic())
            if time.monotonic() + window_delay + self._timeout_seconds >= budget.deadline:
                raise reject("recent_window")
            logger.info(
                json.dumps(
                    {
                        "event": "groq_budget_wait",
                        "run_id": budget.run_id,
                        "wait_seconds": round(window_delay, 2),
                    }
                )
            )
            await asyncio.sleep(window_delay)
            self._recent = [r for r in self._recent if r[0] > time.monotonic() - 60]
            if sum(r[1] for r in self._recent) + required > self._minute_limit:
                raise reject("recent_window")
        if time.monotonic() + self._timeout_seconds >= budget.deadline:
            raise reject("deadline")
        reservation = [time.monotonic(), float(required)]
        self._recent.append(reservation)
        budget.estimated_tokens += estimate
        budget.spent_tokens += required
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
                            max_completion_tokens=1800,
                            reasoning_effort="low"
                            if self._model in {"openai/gpt-oss-120b", "openai/gpt-oss-20b"}
                            else omit,
                        )
                    break
                except RateLimitError as exc:
                    limit = read_rate_limit(exc)
                    delay = limit.retry_after
                    retry = (
                        limit.kind in {"rpm", "tpm"}
                        and delay is not None
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
            used = response.usage.prompt_tokens + response.usage.completion_tokens
            reservation[1] = float(used)
            budget.spent_tokens += used - required
            budget.prompt_tokens += response.usage.prompt_tokens
            budget.completion_tokens += response.usage.completion_tokens
            logger.info(
                json.dumps(
                    {
                        "event": "groq_usage",
                        "run_id": budget.run_id,
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "request_chars": request_chars,
                        "schema_chars": schema_chars,
                        "estimated_input_tokens": estimate,
                        "turn_tokens": budget.spent_tokens,
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
