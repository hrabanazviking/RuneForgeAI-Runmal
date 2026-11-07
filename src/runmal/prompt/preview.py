"""Prompt preview (P-059): the exact final prompt, per backend rendering,
inspectable before send — the glass box the Part XIII Inspector also
uses. Built ONLY from the composed messages + the RenderedPrompt that
inspect_prompt already produced via render_prompt (the one renderer) —
this module never composes and never renders a second time, so preview
can never drift from the composition it previews (P-044
one-source-of-truth rule).

Honesty: every chat backend in this tree receives STRUCTURED messages
(wire payloads embed [m.to_dict()]); no backend receives the
instruct-rendered string — the provider applies its own chat template
server-side. The preview therefore shows BOTH forms and labels each:
messages/wire_messages = exact structured form; text = Rúnmál's
instruct rendering of the same messages, labelled as such. Where a
backend is unknown, say so in data (raise ValueError — the router maps
it to 422 — for an explicitly named unknown backend; do NOT invent a
rendering).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from runmal.prompt.render import RenderedPrompt
from runmal.tokens import estimate_tokens

#: Backend keys known to this tree, derived once at import from
#: capabilities' public surface -- never a hand-kept list of provider
#: names in domain code (S706: domain code does not depend on provider
#: identity; the capabilities registry is the one source of truth).
#: Empty only when that surface cannot be built at all, in which case
#: every explicitly named backend is refused as unknown (honest) rather
#: than guessed at.
KNOWN_BACKENDS: frozenset[str]


def _derive_backend_keys() -> frozenset[str]:
    """Backend keys from capabilities' public capability_matrix rows."""
    try:
        from runmal.backends.capabilities import capability_matrix

        return frozenset(
            str(row["backend_key"]) for row in capability_matrix()["backends"]
        )
    except Exception:
        return frozenset()


KNOWN_BACKENDS = _derive_backend_keys()


def known_backend_keys() -> frozenset[str]:
    """Backend keys known to this tree, derived fresh from capabilities.

    Falls back to the import-time derivation (:data:`KNOWN_BACKENDS`)
    when the surface cannot be built on this call.
    """
    return _derive_backend_keys() or KNOWN_BACKENDS


def _message_parts(message: Any) -> tuple[str, str, Any]:
    """(role, content, slot_id) for a duck-typed message."""
    if isinstance(message, dict):
        return (
            str(message.get("role", "user")),
            str(message.get("content", "")),
            message.get("slot_id"),
        )
    return (
        str(message.role),
        str(message.content),
        getattr(message, "slot_id", None),
    )


def build_preview(
    messages: Iterable[Any],
    rendered: RenderedPrompt,
    *,
    backend_key: str | None = None,
    model_id: str | None = None,
) -> dict:
    """Build the P-059 preview dict from composed messages + a render.

    ``messages`` is an iterable of duck-typed messages (objects or
    mappings with role/content, like render.py; ComposedMessage also
    carries slot_id, included when present, else None). ``rendered``
    is the RenderedPrompt inspect_prompt already produced via
    render_prompt — it is used as-is, never re-rendered.
    """
    if backend_key is not None and backend_key not in known_backend_keys():
        raise ValueError(f"unknown backend: {backend_key!r}")
    parts = [_message_parts(message) for message in messages]
    structured = [
        {"role": role, "content": content, "slot_id": slot_id}
        for role, content, slot_id in parts
    ]
    wire_messages = [
        {"role": role, "content": content} for role, content, _ in parts
    ]
    if backend_key is not None:
        note = (
            f"backend {backend_key!r} receives the structured messages "
            "above (wire_messages); the text field is Rúnmál's instruct "
            "rendering of the same messages - the provider applies its "
            "own chat template server-side."
        )
    else:
        note = (
            "backends receive the structured messages above "
            "(wire_messages); the text field is Rúnmál's instruct "
            "rendering of the same messages - the provider applies its "
            "own chat template server-side."
        )
    return {
        "available": True,
        "backend_key": backend_key,
        "model_id": model_id,
        "form": "structured_messages",
        "messages": structured,
        "wire_messages": wire_messages,
        "text": rendered.text,
        "template_name": rendered.template_name,
        "stop_strings": list(rendered.stop_strings),
        "rendered_tokens": estimate_tokens(rendered.text),
        "note": note,
    }


def preview_from_composed(composed: Any, rendered: RenderedPrompt, **kwargs: Any) -> dict:
    """Preview from a composed prompt: passes ``composed.messages``."""
    messages = composed["messages"] if isinstance(composed, dict) else composed.messages
    return build_preview(messages, rendered, **kwargs)
