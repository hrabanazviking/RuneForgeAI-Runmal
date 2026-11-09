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
from runmal.backends.events import Done, ErrorEvent, Event, ReasoningDelta, TextDelta, UsageUpdate
from runmal.backends.fake import FakeChatBackend
from runmal.backends.messages import ChatMessage
from runmal.backends.params import SamplingParams
from runmal.backends.retry import RetryPolicy, stream_with_retry

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


async def _dispatch_plugin(name, *, chat_id=None, message_id=None, data=None):
    """Fire-and-observe plugin dispatch (P-081): lazy import, never
    raises. Metadata only -- never prompt/message text (PLG-05)."""
    try:
        from runmal.plugins.service import dispatch_event

        await dispatch_event(name, chat_id=chat_id, message_id=message_id, data=data)
    except Exception:
        pass


def bridge_event(event: Event) -> dict | None:
    """Bridge one normalized backend event to the UI's SSE dict shape."""
    if isinstance(event, TextDelta):
        return {"type": "token", "text": event.text}
    if isinstance(event, ReasoningDelta):
        return {"type": "reasoning", "text": event.text}
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
    retry_policy: RetryPolicy | None = None,
    structured=None,
    chat_id: str | None = None,
    plugin_events: bool = True,
):
    """Yield UI-shaped SSE dicts for `request_id` through the backend seam.

    `prompt` is the legacy single-string form (wrapped as one user
    message); `messages` carries the full conversation when available.
    With `retry_policy` set, the stream runs through the S309 retry
    contract (§7): retries happen only before visible output, under the
    same request identity — the events seen here are still one turn.

    P-081: ``chat_id`` is threaded into the generation.* plugin
    payloads by callers that generate FOR a chat (the /generate
    router, the bridge); it stays None for chat-agnostic callers.
    ``plugin_events=False`` suppresses plugin dispatch entirely —
    the group-chat call sites pass it, because group chats are
    OUT of the v1 plugin catalogue (design section 3).
    """
    token = _cancel_tokens.setdefault(request_id, asyncio.Event())
    backend = backend or default_backend()
    # P-081 dispatch alias: the module helper, or a no-op when
    # this call site opted out (group chats). A distinct local
    # name -- shadowing the module helper conditionally would
    # make it function-local everywhere and break every call.
    if plugin_events:
        _dispatch = _dispatch_plugin
    else:
        async def _dispatch(name, *, chat_id=None, message_id=None, data=None):
            return None
    backend_key = getattr(backend, "backend_key", None) or "unknown"
    chat_messages = messages or [ChatMessage(role="user", content=prompt)]
    _model = getattr(backend, "default_model", None)
    # P-081 generation.before fires BEFORE the backend stream is
    # constructed/opened (design section 3 dispatch point).
    # model_id comes from the backend's declared default model --
    # the only model identity this seam honestly knows. chat_id
    # is whatever the caller threaded in (None for chat-agnostic
    # callers).
    await _dispatch(
        "generation.before",
        chat_id=chat_id,
        data={
            "request_id": request_id,
            "backend_key": backend_key,
            "model_id": _model.model_id if _model is not None else None,
            "chat_id": chat_id,
            "message_count": len(chat_messages),
        },
    )
    if retry_policy is not None:
        stream = stream_with_retry(
            backend, chat_messages, params or SamplingParams(), token,
            request_id=request_id, policy=retry_policy, structured=structured)
    elif structured is not None:
        stream = backend.chat_stream(
            chat_messages, params or SamplingParams(), token,
            structured=structured)
    else:
        stream = backend.chat_stream(chat_messages, params or SamplingParams(), token)
    saw_done = False
    last_usage: dict | None = None
    try:
        async for event in stream:
            bridged = bridge_event(event)
            if isinstance(event, UsageUpdate):
                last_usage = event.to_dict()
            elif isinstance(event, Done) and event.usage is not None:
                last_usage = event.usage.to_dict()
            if bridged is None:
                continue
            if bridged["type"] == "done":
                saw_done = True
                if isinstance(event, Done) and event.reason == "error":
                    await _dispatch(
                        "generation.failed",
                        chat_id=chat_id,
                        data={
                            "request_id": request_id,
                            "backend_key": backend_key,
                            "error_code": event.reason,
                            "retryable": False,
                        },
                    )
                if isinstance(event, Done) and event.reason != "error":
                    await _dispatch(
                        "generation.after",
                        chat_id=chat_id,
                        data={
                            "request_id": request_id,
                            "backend_key": backend_key,
                            "finish_reason": event.reason,
                            "usage": last_usage,
                        },
                    )
            yield bridged
        if token.is_set() and not saw_done:
            await _dispatch(
                "generation.after",
                chat_id=chat_id,
                data={
                    "request_id": request_id,
                    "backend_key": backend_key,
                    "finish_reason": "cancelled",
                    "usage": last_usage,
                },
            )
            yield {"type": "done", "finish_reason": "cancelled"}
    except GenerationCancelled:
        await _dispatch(
            "generation.after",
            chat_id=chat_id,
            data={
                "request_id": request_id,
                "backend_key": backend_key,
                "finish_reason": "cancelled",
                "usage": last_usage,
            },
        )
        yield {"type": "done", "finish_reason": "cancelled"}
    except BackendError as exc:
        await _dispatch(
            "generation.failed",
            chat_id=chat_id,
            data={
                "request_id": request_id,
                "backend_key": backend_key,
                "error_code": exc.code,
                "retryable": exc.retryable,
            },
        )
        yield {"type": "error", "code": exc.code, "message": str(exc),
               "retryable": exc.retryable}
        yield {"type": "done", "finish_reason": "error"}
    finally:
        await stream.aclose()
        _cancel_tokens.pop(request_id, None)
