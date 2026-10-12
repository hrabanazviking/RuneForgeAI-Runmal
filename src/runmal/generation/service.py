"""Generation orchestration (S108): normalized event stream + cancellation tokens.

The fake backend runs INLINE in the response generator — there is deliberately
no background task, so cancellation/disconnect cannot orphan anything. The
per-request registry entry is removed in a finally block on every exit path.
"""

from __future__ import annotations

import asyncio
import uuid

from runmal.generation import fake_backend

_cancel_tokens: dict[str, asyncio.Event] = {}


def new_request_id() -> str:
    return uuid.uuid4().hex


def cancel_request(request_id: str) -> bool:
    """Signal cancellation for an in-flight generation. Returns False if unknown."""
    token = _cancel_tokens.get(request_id)
    if token is None:
        return False
    token.set()
    return True


async def generate_events(request_id: str, prompt: str):
    """Yield normalized events for `request_id`; honor its cancellation token."""
    token = _cancel_tokens.setdefault(request_id, asyncio.Event())
    stream = fake_backend.fake_provider_stream(prompt, token)
    saw_done = False
    try:
        async for raw in stream:
            event = fake_backend.normalize_chunk(raw)
            if event is None:
                continue
            if event["type"] == "done":
                saw_done = True
            yield event
        if token.is_set() and not saw_done:
            yield {"type": "done", "finish_reason": "cancelled"}
    finally:
        await stream.aclose()
        _cancel_tokens.pop(request_id, None)
