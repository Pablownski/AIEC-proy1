"""Process-local admission: settled usage, in-flight leases and short-lived synthesis holds."""

import asyncio
import json
import logging
import time
from dataclasses import dataclass

from app.clients.rate_limits import RequestBudget

MAX_OUTPUT = 1800
MIN_OUTPUT = 768
WINDOW_SECONDS = 60


class AdmissionDenied(Exception):
    def __init__(self, reason: str, turn: int, minute: int, retry_after: float | None) -> None:
        super().__init__("Local token budget unavailable")
        self.reason, self.turn, self.minute, self.retry_after = reason, turn, minute, retry_after


@dataclass
class Usage:
    completed: float
    tokens: int
    estimated: bool = False


@dataclass(eq=False)
class Lease:
    budget: RequestBudget
    tokens: int
    output: int


class TokenWindow:
    def __init__(self, turn_limit: int, minute_limit: int) -> None:
        self.turn_limit, self.minute_limit = turn_limit, minute_limit
        self.usage: list[Usage] = []
        self.pending: list[Lease] = []
        self.holds: dict[int, tuple[RequestBudget, int]] = {}

    def available(self, budget: RequestBudget) -> tuple[int, int]:
        now = time.monotonic()
        self.usage = [u for u in self.usage if u.completed + WINDOW_SECONDS > now]
        own_hold = self.holds.get(id(budget), (budget, 0))[1]
        turn = self.turn_limit - budget.spent_tokens - budget.reserved_tokens + own_hold
        minute = self.minute_limit - sum(u.tokens for u in self.usage)
        minute -= sum(p.tokens for p in self.pending) + sum(h[1] for h in self.holds.values())
        return max(0, turn), max(0, minute + own_hold)

    def recovery(self, missing: int) -> float | None:
        recovered = 0
        for usage in sorted(self.usage, key=lambda u: u.completed):
            recovered += usage.tokens
            if recovered >= missing:
                return max(0.0, usage.completed + WINDOW_SECONDS - time.monotonic())
        # In-flight requests/holds have no known completion time; never invent one.
        return None

    async def _capacity(
        self,
        budget: RequestBudget,
        required: int,
        timeout: float,
    ) -> tuple[int, int]:
        for check in range(2):
            turn, minute = self.available(budget)
            delay = self.recovery(max(0, required - minute)) if minute < required else None
            if turn < required:
                raise AdmissionDenied("turn_budget", turn, minute, None)
            if required > self.minute_limit:
                raise AdmissionDenied("request_size", turn, minute, None)
            if time.monotonic() + timeout >= budget.deadline:
                raise AdmissionDenied("deadline", turn, minute, delay)
            if minute >= required:
                return turn, minute
            if check or delay is None or time.monotonic() + delay + timeout >= budget.deadline:
                raise AdmissionDenied("recent_window", turn, minute, delay)
            logging.getLogger("uvicorn.error").info(
                json.dumps(
                    {
                        "event": "groq_budget_wait",
                        "run_id": budget.run_id,
                        "reason": "recent_window",
                        "recovery_seconds": delay,
                        "available_minute_tokens": minute,
                        "required_tokens": required,
                    }
                )
            )
            await asyncio.sleep(delay)
        raise AssertionError("unreachable")

    async def admit(self, budget: RequestBudget, estimate: int, timeout: float) -> Lease:
        turn, minute = await self._capacity(budget, estimate + MIN_OUTPUT, timeout)
        output = min(MAX_OUTPUT, turn - estimate, minute - estimate)
        # No await between capacity check and reservation: atomic in this event loop.
        self.release_hold(budget)
        lease = Lease(budget, estimate + output, output)
        self.pending.append(lease)
        budget.reserved_tokens += lease.tokens
        return lease

    async def hold_synthesis(self, budget: RequestBudget, estimate: int, timeout: float) -> None:
        required = estimate + MIN_OUTPUT
        await self._capacity(budget, required, timeout)
        self.release_hold(budget)
        self.holds[id(budget)] = (budget, required)
        budget.reserved_tokens += required

    def release_hold(self, budget: RequestBudget) -> None:
        hold = self.holds.pop(id(budget), None)
        if hold:
            budget.reserved_tokens -= hold[1]

    def release(self, lease: Lease) -> None:
        if lease in self.pending:
            self.pending.remove(lease)
            lease.budget.reserved_tokens -= lease.tokens

    def settle(self, lease: Lease, tokens: int, *, estimated: bool = False) -> None:
        if lease not in self.pending:
            return
        self.release(lease)
        # Charge once, at completion. In-flight leases never expire prematurely.
        self.usage.append(Usage(time.monotonic(), tokens, estimated))
        lease.budget.spent_tokens += tokens
