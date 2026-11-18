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

from app.clients.groq_errors import classify_provider_error
from app.clients.rate_limits import LimitType, RequestBudget, estimate_tokens, read_rate_limit
from app.clients.token_budget import MAX_OUTPUT, MIN_OUTPUT, AdmissionDenied, Lease, TokenWindow
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
        retry_after: float | None = None,
        budget_reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.limit_type = limit_type
        self.retry_after, self.budget_reason = retry_after, budget_reason


class GroqClient:
    def __init__(self, settings: Settings, *, timeout_seconds: float = 10.0) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds debe ser positivo y finito.")
        if settings.groq_api_key is None or not settings.groq_api_key.get_secret_value().strip():
            raise GroqClientError("configuration", "GROQ_API_KEY no está configurada.")
        self._model = settings.groq_model
        self._timeout_seconds = timeout_seconds
        self._tokens = TokenWindow(
            settings.groq_turn_token_budget, int(settings.groq_tpm_budget * 0.9)
        )
        self._client = AsyncGroq(
            api_key=settings.groq_api_key.get_secret_value(),
            timeout=timeout_seconds,
            max_retries=0,
        )

    def _budget_failure(
        self,
        denied: AdmissionDenied,
        budget: RequestBudget,
        estimate: int,
        *,
        stage: str = "request",
    ) -> GroqClientError:
        logger.warning(
            json.dumps(
                {
                    "event": "groq_budget_limited",
                    "reason": denied.reason,
                    "run_id": budget.run_id,
                    "estimated_input_tokens": estimate,
                    "min_output_tokens": MIN_OUTPUT,
                    "stage": stage,
                    "available_turn_tokens": denied.turn,
                    "available_minute_tokens": denied.minute,
                    "turn_tokens": budget.spent_tokens,
                    "reserved_tokens": budget.reserved_tokens,
                    "recovery_seconds": denied.retry_after,
                    "turn_limit": self._tokens.turn_limit,
                    "minute_limit": self._tokens.minute_limit,
                    "recent_actual_tokens": sum(
                        u.tokens for u in self._tokens.usage if not u.estimated
                    ),
                    "recent_estimated_tokens": sum(
                        u.tokens for u in self._tokens.usage if u.estimated
                    ),
                    "in_flight_tokens": sum(p.tokens for p in self._tokens.pending),
                    "held_synthesis_tokens": sum(h[1] for h in self._tokens.holds.values()),
                }
            )
        )
        return GroqClientError(
            "budget",
            "Espera antes de consultar nuevamente.",
            retry_after=denied.retry_after,
            budget_reason=denied.reason,
        )

    async def _admit(self, budget: RequestBudget, estimate: int) -> Lease:
        try:
            lease = await self._tokens.admit(budget, estimate, self._timeout_seconds)
        except AdmissionDenied as denied:
            raise self._budget_failure(denied, budget, estimate) from None
        logger.info(
            json.dumps(
                {
                    "event": "groq_budget_admitted",
                    "run_id": budget.run_id,
                    "estimated_input_tokens": estimate,
                    "output_reserve": lease.output,
                    "turn_tokens": budget.spent_tokens,
                    "reserved_tokens": budget.reserved_tokens,
                }
            )
        )
        return lease

    async def reserve_synthesis(
        self,
        messages: Sequence[ChatCompletionMessageParam],
        budget: RequestBudget,
        *,
        tool_seconds: float = 8,
    ) -> None:
        # No schemas/trace in the final synthesis; allow estimated room for new evidence.
        estimate = (
            estimate_tokens(
                json.dumps(messages, ensure_ascii=False, separators=(",", ":")), len(messages)
            )
            + 600
        )
        try:
            await self._tokens.hold_synthesis(
                budget, estimate, self._timeout_seconds + tool_seconds
            )
        except AdmissionDenied as denied:
            raise self._budget_failure(denied, budget, estimate, stage="before_tools") from None

    async def release_budget(self, budget: RequestBudget) -> None:
        self._tokens.release_hold(budget)
        logger.info(
            json.dumps(
                {
                    "event": "groq_budget_released",
                    "run_id": budget.run_id,
                    "turn_tokens": budget.spent_tokens,
                    "reserved_tokens": budget.reserved_tokens,
                }
            )
        )

    def _charge_uncertain(self, lease: Lease) -> None:
        self._tokens.settle(lease, lease.tokens, estimated=True)
        logger.warning(
            json.dumps(
                {
                    "event": "groq_usage_uncertain",
                    "run_id": lease.budget.run_id,
                    "estimated_total_tokens": lease.tokens,
                    "reason": "delivery_or_billing_unknown",
                }
            )
        )

    def _record_usage(
        self,
        response: ChatCompletion,
        lease: Lease,
        budget: RequestBudget,
        estimate: int,
        request_chars: int,
        schema_chars: int,
    ) -> None:
        usage = response.usage
        used = (
            max(usage.total_tokens, usage.prompt_tokens + usage.completion_tokens)
            if usage
            else lease.tokens
        )
        self._tokens.settle(lease, used, estimated=usage is None)
        if usage:
            budget.prompt_tokens += usage.prompt_tokens
            budget.completion_tokens += usage.completion_tokens
        logger.info(
            json.dumps(
                {
                    "event": "groq_usage",
                    "run_id": budget.run_id,
                    "prompt_tokens": usage.prompt_tokens if usage else None,
                    "completion_tokens": usage.completion_tokens if usage else None,
                    "actual_total_tokens": used if usage else None,
                    "usage_estimated": usage is None,
                    "estimate_overrun": used > lease.tokens,
                    "estimated_input_tokens": estimate,
                    "output_reserve": lease.output,
                    "turn_tokens": budget.spent_tokens,
                    "request_chars": request_chars,
                    "schema_chars": schema_chars,
                }
            )
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
        try:
            while True:
                lease = await self._admit(budget, estimate)
                budget.estimated_tokens += estimate
                try:
                    if tools:
                        response = await self._client.chat.completions.create(
                            model=self._model,
                            messages=messages,
                            stream=False,
                            tools=tools,
                            tool_choice="auto" if allow_tools else "none",
                            parallel_tool_calls=False,
                            max_completion_tokens=lease.output,
                            reasoning_effort="low"
                            if self._model in {"openai/gpt-oss-120b", "openai/gpt-oss-20b"}
                            else omit,
                        )
                    else:
                        response = await self._client.chat.completions.create(
                            model=self._model,
                            messages=messages,
                            stream=False,
                            max_completion_tokens=lease.output,
                            reasoning_effort="low"
                            if self._model in {"openai/gpt-oss-120b", "openai/gpt-oss-20b"}
                            else omit,
                        )
                    self._record_usage(
                        response, lease, budget, estimate, request_chars, schema_chars
                    )
                    break
                except RateLimitError as exc:
                    self._tokens.release(lease)
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
                except APIStatusError as exc:
                    if exc.status_code >= 500 or classify_provider_error(exc)["error_class"] in {
                        "tool_generation",
                        "output_generation",
                    }:
                        self._charge_uncertain(lease)
                    raise
                except (APIConnectionError, asyncio.CancelledError):
                    # Delivery/billing is unknown: keep an explicitly estimated usage record,
                    # never a dangling reservation. Local/validation rejections release the lease.
                    self._charge_uncertain(lease)
                    raise
                finally:
                    self._tokens.release(lease)
        except APITimeoutError:
            raise GroqClientError("timeout", "Groq excedió el tiempo de espera.") from None
        except APIConnectionError:
            raise GroqClientError("connection", "No se pudo conectar con Groq.") from None
        except AuthenticationError as exc:
            raise GroqClientError(
                "authentication", "Groq rechazó la autenticación.", status_code=exc.status_code
            ) from None
        except APIStatusError as exc:
            tool_call_count = 0
            for outgoing_message in messages:
                calls = outgoing_message.get("tool_calls")
                if isinstance(calls, list):
                    tool_call_count += len(calls)
            logger.warning(
                json.dumps(
                    {
                        "event": "groq_request_failed",
                        "run_id": budget.run_id,
                        "status_code": exc.status_code,
                        **classify_provider_error(exc),
                        "message_count": len(messages),
                        "assistant_tool_calls": tool_call_count,
                        "tool_results": sum(m["role"] == "tool" for m in messages),
                        "has_tools": bool(tools),
                        "tool_choice": ("auto" if allow_tools else "none") if tools else "omitted",
                        "reasoning_effort": "low"
                        if self._model
                        in {
                            "openai/gpt-oss-120b",
                            "openai/gpt-oss-20b",
                        }
                        else "omitted",
                        "will_retry": False,
                    }
                )
            )
            raise GroqClientError(
                "provider", "No se pudo completar la solicitud a Groq.", status_code=exc.status_code
            ) from None
        except APIError:
            raise GroqClientError("provider", "No se pudo completar la solicitud a Groq.") from None

        if not response.choices:
            raise GroqClientError("response", "Groq devolvió una respuesta sin opciones.")
        if response.choices[0].finish_reason == "length":
            raise GroqClientError(
                "budget" if lease.output < MAX_OUTPUT else "response",
                "La respuesta no pudo completarse dentro del presupuesto.",
                budget_reason="output_limit",
            )
        message = response.choices[0].message
        if not (message.content and message.content.strip()) and not message.tool_calls:
            raise GroqClientError("response", "Groq devolvió una respuesta sin contenido.")
        return response

    async def close(self) -> None:
        try:
            await self._client.close()
        finally:
            for budget, _ in list(self._tokens.holds.values()):
                self._tokens.release_hold(budget)

    async def __aenter__(self) -> GroqClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()
