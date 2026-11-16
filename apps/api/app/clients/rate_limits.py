"""Conservative interpretation of Groq signals; no raw provider data leaves this module."""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Literal

from groq import RateLimitError

LimitType = Literal["rpm", "tpm", "rpd", "tpd", "daily", "unknown"]


@dataclass
class RequestBudget:
    deadline: float = field(default_factory=lambda: time.monotonic() + 20)
    retries_remaining: int = 1
    run_id: str | None = None
    spent_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_tokens: int = 0


def estimate_tokens(payload: str, message_count: int) -> int:
    """Planning heuristic, NOT a tokenizer or a guaranteed upper bound for GPT-OSS.

    UTF-8 bytes / 3 plus message framing is deliberately more cautious than the
    common English four-characters heuristic. Actual provider usage replaces it.
    """
    return math.ceil(len(payload.encode("utf-8")) / 3) + 12 * message_count + 32


@dataclass(frozen=True)
class RateLimit:
    kind: LimitType
    retry_after: float | None


def read_rate_limit(exc: RateLimitError) -> RateLimit:
    headers = exc.response.headers
    body = exc.body if isinstance(exc.body, dict) else {}
    error = body.get("error", body)
    message = error.get("message", "") if isinstance(error, dict) else ""
    message = message.lower() if isinstance(message, str) else ""
    # Groq documents remaining-requests as RPD, not RPM. Daily signals take precedence.
    kind: LimitType = "unknown"
    if headers.get("x-ratelimit-remaining-requests") == "0" or re.search(
        r"\brpd\b|requests per day", message
    ):
        kind = "rpd"
    elif re.search(r"\btpd\b|tokens per day", message):
        kind = "tpd"
    elif "daily" in message:
        kind = "daily"
    elif headers.get("x-ratelimit-remaining-tokens") == "0" or re.search(
        r"\btpm\b|tokens per minute", message
    ):
        kind = "tpm"
    elif re.search(r"\brpm\b|requests per minute", message):
        kind = "rpm"
    raw = headers.get("retry-after")
    delay = None
    if raw is not None:
        try:
            delay = float(raw)
        except ValueError:
            try:
                date = parsedate_to_datetime(raw)
                delay = max(0.0, (date - datetime.now(UTC)).total_seconds())
            except (ValueError, TypeError, OverflowError):
                pass
        if delay is not None and (not math.isfinite(delay) or delay < 0):
            delay = None
    return RateLimit(kind, delay)
