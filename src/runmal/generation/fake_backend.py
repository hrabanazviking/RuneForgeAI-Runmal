"""Fake provider backend (S108).

Emits deliberately provider-shaped raw chunks (OpenAI wire-shape-like) so the
normalizer has something real to convert. Raw chunks must NEVER reach the API:
only normalized events leave this package's service layer.
"""

from __future__ import annotations

import asyncio

_CHUNK_DELAY_S = 0.01
_WORDS = ["Rúnmál", " hears", " you", ".", " This", " is", " a", " stub", "."]


def _raw_chunk(word: str) -> dict:
    return {
        "id": "fake-1",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {"content": word}, "finish_reason": None}],
    }


def _raw_stop_chunk() -> dict:
    return {
        "id": "fake-1",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }


async def fake_provider_stream(prompt: str, cancel: asyncio.Event):
    """Yield raw fake-provider chunks; stop early when `cancel` is set."""
    _ = prompt  # the stub ignores content; the shape is what matters
    for word in _WORDS:
        try:
            await asyncio.wait_for(cancel.wait(), timeout=_CHUNK_DELAY_S)
        except TimeoutError:
            pass
        else:
            return
        yield _raw_chunk(word)
    yield _raw_stop_chunk()


def normalize_chunk(raw: dict) -> dict | None:
    """Convert one raw provider chunk into a normalized Rúnmál event.

    Returns None for chunks carrying no user-visible signal. The output schema
    is ours alone: {"type": "token", "text"} / {"type": "done", "finish_reason"}.
    """
    choice = (raw.get("choices") or [{}])[0]
    text = (choice.get("delta") or {}).get("content")
    if text:
        return {"type": "token", "text": text}
    if choice.get("finish_reason"):
        return {"type": "done", "finish_reason": choice["finish_reason"]}
    return None
