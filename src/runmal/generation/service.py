"""Generation orchestration (S108, rewired through the backend seam in S307).

Generation now streams through a ``ChatBackend`` (S301): the service takes
the backend's NORMALIZED events and bridges them to the SSE dict shape the
web UI consumes ({"type": "token"} / {"type": "done"} / {"type": "usage"} /
{"type": "error"}). The default backend is the deterministic
``FakeChatBackend`` scripted with the historical stub text, so the ordinary
test suite passes with no Ollama/OpenRouter present.

Cancellation: the per-request registry maps request_id -> asyncio.Event;
the SAME event is handed to the backend, so Stop/disconnect propagates into
the provider stream (INV-003). Backends run INLINE in the response
generator — no background task — so a disconnect cannot orphan anything.
The registry entry is removed in a finally block on every exit path.
"""

from __future__ import annotations

import asyncio
import uuid

from runmal.backends.base import ChatBackend
from runmal.backends.errors import BackendError, GenerationCancelled
from runmal.backends.events import Done, ErrorEvent, Event, TextDelta, UsageUpdate
from runmal.backends.fake import FakeChatBackend
from runmal.backends.messages import ChatMessage
from runmal.backends.params import SamplingParams

_cancel_tokens: dict[str, asyncio.Event] = {}

_STUB_CHUNKS = ("Rúnmál", " hears", " you", ".", " This", " is", " a", " stub", ".")


def new_request_id() -> str:
    return uuid.uuid4().hex


def cancel_request(request_id: str) -> bool:
    """Signal cancellation for an in-flight generation. Returns False if unknown."""
    token = _cancel_tokens.get(request_id)
    if token is None:
        return False
    token.set()
    return True


def default_backend() -> ChatBackend:
    """The offline default: deterministic fake, scripted with the stub text."""
    return FakeChatBackend(chunks=_STUB_CHUNKS)


def bridge_event(event: Event) -> dict | None:
    """Bridge one normalized backend event to the UI's SSE dict shape."""
    if isinstance(event, TextDelta):
        return {"type": "token", "text": event.text}
    if isinstance(event, Done):
        return {"type": "done", "finish_reason": event.reason}
    if isinstance(event, UsageUpdate):
        return {"type": "usage", "prompt_tokens": event.prompt_tokens,
                "completion_tokens": event.completion_tokens,
                "total_tokens": event.total_tokens}
    if isinstance(event, ErrorEvent):
        return {"type": "error", "code": event.code, "message": event.message,
                "retryable": event.retryable}
    return None


async def generate_events(
    request_id: str,
    prompt: str = "",
    *,
    messages: list[ChatMessage] | None = None,
    backend: ChatBackend | None = None,
    params: SamplingParams | None = None,
):
    """Yield UI-shaped SSE dicts for `request_id` through the backend seam.

    `prompt` is the legacy single-string form (wrapped as one user
    message); `messages` carries the full conversation when available.
    """
    token = _cancel_tokens.setdefault(request_id, asyncio.Event())
    backend = backend or default_backend()
    chat_messages = messages or [ChatMessage(role="user", content=prompt)]
    stream = backend.chat_stream(chat_messages, params or SamplingParams(), token)
    saw_done = False
    try:
        async for event in stream:
            bridged = bridge_event(event)
            if bridged is None:
                continue
            if bridged["type"] == "done":
                saw_done = True
            yield bridged
        if token.is_set() and not saw_done:
            yield {"type": "done", "finish_reason": "cancelled"}
    except GenerationCancelled:
        yield {"type": "done", "finish_reason": "cancelled"}
    except BackendError as exc:
        yield {"type": "error", "code": exc.code, "message": str(exc),
               "retryable": exc.retryable}
        yield {"type": "done", "finish_reason": "error"}
    finally:
        await stream.aclose()
        _cancel_tokens.pop(request_id, None)
