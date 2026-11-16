"""Allowlisted diagnostics: never log exception text, messages, arguments or credentials."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from uuid import uuid4

from jsonschema import ValidationError as SchemaError
from pydantic import ValidationError

from app.clients.groq_client import GroqClientError
from app.tools.models import INPUTS

logger = logging.getLogger("uvicorn.error")


class AgentFailure(Exception):
    """Internal failures carry only a controlled code, never provider details."""


def failure_code(exc: BaseException) -> str:
    if isinstance(exc, BaseExceptionGroup):
        return failure_code(exc.exceptions[0])
    if isinstance(exc, AgentFailure) and str(exc) in {
        "invalid_response",
        "tool_limit",
        "round_limit",
        "tools_after_limit",
        "books_unavailable",
    }:
        return str(exc)
    if isinstance(exc, GroqClientError) and exc.code in {
        "configuration",
        "timeout",
        "connection",
        "authentication",
        "rate_limit",
        "provider",
        "response",
    }:
        return f"groq_{exc.code}"
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, (ValidationError, SchemaError, ValueError)):
        return "validation"
    return "unexpected"


def provider_status(exc: BaseException) -> int | None:
    if isinstance(exc, BaseExceptionGroup):
        return provider_status(exc.exceptions[0])
    if isinstance(exc, GroqClientError) and isinstance(exc.status_code, int):
        if 100 <= exc.status_code <= 599:
            return exc.status_code
    return None


@dataclass
class TurnTrace:
    run_id: str = field(default_factory=lambda: uuid4().hex)
    started: float = field(default_factory=time.monotonic)
    stage: str = "memory"
    rounds: int = 0
    tool_calls: int = 0
    tool_failed: bool = False

    def emit(
        self,
        event: str,
        *,
        code: str = "ok",
        tool: str | None = None,
        memory_committed: bool = False,
        status_code: int | None = None,
    ) -> None:
        payload = {
            "event": event,
            "run_id": self.run_id,
            "stage": self.stage,
            "rounds": self.rounds,
            "tool_calls": self.tool_calls,
            "code": code,
            "elapsed_ms": round((time.monotonic() - self.started) * 1000),
            "memory_committed": memory_committed,
        }
        if tool is not None:
            payload["tool"] = tool if tool in INPUTS else "unknown"
        if status_code is not None:
            payload["status_code"] = status_code
        level = logging.INFO if code in {"ok", "no_results"} else logging.WARNING
        logger.log(level, json.dumps(payload, ensure_ascii=True))
