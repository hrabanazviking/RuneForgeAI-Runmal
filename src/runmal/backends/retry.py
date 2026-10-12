"""Retry contract (S309) — BACKEND_CONTRACT §7, INV-004.

Automatic retry is allowed ONLY before visible output begins:

- A failed attempt that yielded NO event may be retried on the same
  backend (bounded by ``RetryPolicy.max_attempts``) or, when an explicit
  fallback backend is configured, continued on the fallback — again only
  while nothing has been yielded.
- Once ANY event has been yielded, a failure propagates immediately. The
  answer is NEVER silently restarted on another provider/model after
  visible output begins.
- Only errors flagged ``retryable`` are retried; cancellation
  (``GenerationCancelled``) is never retried and aborts backoff waits.
- Rate-limit backoff honors ``RateLimited.retry_after_s``, always capped
  by ``policy.max_delay_s``; every wait is cancellation-aware.
- Request identity: every attempt carries the SAME ``request_id`` (see
  ``AttemptRecord``). Because pre-output attempts yield nothing, a
  persisting consumer sees at most ONE assistant turn per request_id —
  retries can never duplicate a persisted turn.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from runmal.backends.base import ChatBackend
from runmal.backends.errors import BackendError, GenerationCancelled, RateLimited
from runmal.backends.events import Event
from runmal.backends.messages import ChatMessage
from runmal.backends.params import SamplingParams

MAX_ATTEMPTS_CAP = 10


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded retry configuration. Defaults: 3 attempts, short backoff."""

    max_attempts: int = 3
    base_delay_s: float = 0.25
    max_delay_s: float = 4.0
    backoff_factor: float = 2.0

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= MAX_ATTEMPTS_CAP:
            raise ValueError("max_attempts must be between 1 and 10")
        if self.base_delay_s < 0 or self.max_delay_s < 0:
            raise ValueError("delays must be >= 0")
        if self.max_delay_s < self.base_delay_s:
            raise ValueError("max_delay_s must be >= base_delay_s")
        if self.backoff_factor < 1:
            raise ValueError("backoff_factor must be >= 1")

    def delay_for(self, error: BackendError, attempt: int) -> float:
        """Delay before the next attempt (attempt is 1-based, just failed)."""
        if isinstance(error, RateLimited) and error.retry_after_s is not None:
            return min(max(error.retry_after_s, 0.0), self.max_delay_s)
        delay = self.base_delay_s * (self.backoff_factor ** (attempt - 1))
        return min(delay, self.max_delay_s)


@dataclass(frozen=True)
class AttemptRecord:
    """One attempt, tagged with the shared request identity."""

    request_id: str
    attempt: int
    backend_key: str
    phase: str  # "primary" | "fallback"

    def dedupe_key(self) -> str:
        """Persistence identity: identical across every attempt/phase."""
        return self.request_id


async def _wait(delay: float, cancel: asyncio.Event) -> None:
    """Cancellation-aware sleep: raises GenerationCancelled if set."""
    if cancel.is_set():
        raise GenerationCancelled("cancelled during retry backoff")
    if delay <= 0:
        return
    try:
        await asyncio.wait_for(cancel.wait(), timeout=delay)
    except TimeoutError:
        return
    raise GenerationCancelled("cancelled during retry backoff")


async def stream_with_retry(
    backend: ChatBackend,
    messages: list[ChatMessage],
    params: SamplingParams,
    cancel: asyncio.Event,
    *,
    request_id: str,
    policy: RetryPolicy | None = None,
    fallback: ChatBackend | None = None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    on_attempt: Callable[[AttemptRecord], None] | None = None,
) -> AsyncIterator[Event]:
    """Yield normalized events, retrying per the §7 contract above.

    ``sleep`` is injectable for tests; the default wait is
    cancellation-aware. ``on_attempt`` receives one AttemptRecord per
    attempt (all sharing ``request_id``).
    """
    policy = policy or RetryPolicy()
    phases: list[tuple[str, ChatBackend]] = [("primary", backend)]
    if fallback is not None:
        phases.append(("fallback", fallback))
    last_error: BackendError | None = None
    for phase, active in phases:
        for attempt in range(1, policy.max_attempts + 1):
            if on_attempt is not None:
                on_attempt(AttemptRecord(request_id, attempt,
                                         active.backend_key, phase))
            yielded = False
            try:
                stream = active.chat_stream(messages, params, cancel)
                try:
                    async for event in stream:
                        yielded = True
                        yield event
                finally:
                    await stream.aclose()
                return
            except GenerationCancelled:
                raise
            except BackendError as exc:
                last_error = exc
                if yielded:
                    # Visible output began: NEVER continue elsewhere (§7).
                    raise
                if not exc.retryable:
                    raise
                if attempt >= policy.max_attempts:
                    break  # bounded: move to fallback phase or give up
                delay = policy.delay_for(exc, attempt)
                if sleep is not None:
                    await sleep(delay)
                    if cancel.is_set():
                        raise GenerationCancelled(
                            "cancelled during retry backoff") from exc
                else:
                    await _wait(delay, cancel)
    if last_error is not None:
        raise last_error
    raise BackendError("retry loop ended without an attempt")  # unreachable
