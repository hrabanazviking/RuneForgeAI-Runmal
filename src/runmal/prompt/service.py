"""Prompt manager resolution service (P-049).

Precedence for a composition is explicit (a layout supplied with
the request) > default -- there is deliberately no stored tier in
P-049: persisting a layout per owner or per chat is a named
follow-up slice that owns its own migration, and a service that
pretended to store one would be a lie. With no layout in play
:func:`resolve_layout` returns ``(None, "default")`` and the
pipeline composes exactly as it did before P-049.
"""

from __future__ import annotations

from runmal.prompt.manager import PromptLayout, default_layout, layout_from_data, layout_to_data


def resolve_layout(explicit: object | None) -> tuple[PromptLayout | None, str]:
    """Resolve the layout for a composition.

    Returns ``(layout, source)``: an explicit layout is validated
    (ValueError propagates to the caller, which maps it to 422)
    and returned with source ``"explicit"``; ``None`` yields
    ``(None, "default")`` -- no layout in play.
    """
    if explicit is not None:
        return layout_from_data(explicit), "explicit"
    return None, "default"


def layout_echo(layout: PromptLayout | None, source: str) -> dict:
    """The ``prompt_layout`` echo for an inspect result."""
    active = layout if layout is not None else default_layout()
    return {"blocks": layout_to_data(active)["blocks"], "source": source}
