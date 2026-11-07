"""Instruct rendering (P-050): messages -> one model-facing string.

The composer and the backends speak structured messages; a model
consuming raw text needs those messages flattened through the
selected :class:`~runmal.prompt.instruct.InstructTemplate`. This
is the rendering path that honours the selection: it applies the
template's ``bos``, per-role wrappers and separator in order,
uses the template's ``preamble`` as the system text when the
conversation carries no system message and the template declares
one, and closes with the template's ``generation_prefix`` so the
string ends open at the assistant's turn. The returned
:class:`RenderedPrompt` also carries the template's stop strings:
stop behaviour travels with the render, as data, never as a
backend-side guess.

Messages are duck-typed: anything with ``role`` / ``content``
attributes (the composer's ComposedMessage, the backends'
ChatMessage) or a mapping with those keys renders the same.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from runmal.prompt.instruct import InstructTemplate


@dataclass(frozen=True)
class RenderedPrompt:
    text: str
    template_name: str
    stop_strings: tuple[str, ...]


def _role_content(message) -> tuple[str, str]:
    if isinstance(message, dict):
        return str(message.get("role", "user")), str(message.get("content", ""))
    return str(message.role), str(message.content)


def render_prompt(messages: Iterable, template: InstructTemplate) -> RenderedPrompt:
    """Render ``messages`` through ``template`` to a single string."""
    rows = [_role_content(m) for m in messages]
    if template.preamble and not any(role == "system" for role, _ in rows):
        rows.insert(0, ("system", template.preamble))
    parts: list[str] = []
    for role, content in rows:
        wrapper = template.wrapper_for(role)
        prefix = wrapper.prefix.replace("{role}", role)
        suffix = wrapper.suffix.replace("{role}", role)
        parts.append(prefix + content + suffix)
    text = template.bos + template.separator.join(parts)
    text += template.generation_prefix.replace("{role}", "assistant")
    return RenderedPrompt(
        text=text, template_name=template.name,
        stop_strings=template.stop_strings,
    )
