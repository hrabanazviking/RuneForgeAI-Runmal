"""Prompt resolution services (P-049 layout; P-050 instruct).

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


# ---------------- P-050: instruct template resolution ----------------

from runmal.prompt.instruct import (  # noqa: E402
    InstructTemplate,
    default_template_for_model,
    get_template,
    template_from_data,
)


def resolve_template(
    explicit: object | None = None, model_id: str | None = None
) -> tuple[InstructTemplate, str]:
    """Resolve the instruct template for a render.

    Precedence, explicit first (mirrors resolve_layout):

    - ``explicit`` as a string names a builtin template
      (ValueError on an unknown name propagates to the caller,
      which maps it to 422);
    - ``explicit`` as a dict is a full custom template, validated
      by template_from_data;
    - otherwise the per-model default from
      MODEL_TEMPLATE_DEFAULTS (source "model_default" when a
      pattern matched, i.e. the result is not PLAIN-by-fallback);
    - otherwise PLAIN (source "default") -- the honest default
      that invents no framing.

    Returns ``(template, source)`` with source one of
    "explicit" | "model_default" | "default".
    """
    if isinstance(explicit, str):
        return get_template(explicit), "explicit"
    if explicit is not None:
        return template_from_data(explicit), "explicit"
    template = default_template_for_model(model_id)
    if model_id and template.name != "plain":
        return template, "model_default"
    return template, "default"


def template_echo(template: InstructTemplate, source: str) -> dict:
    """The ``instruct_template`` echo for an inspect result.

    Metadata only -- name, source, stop behaviour. The rendered
    text itself never enters an inspect result (S214 trace safety
    contract: traces carry no prompt content).
    """
    return {
        "name": template.name,
        "source": source,
        "stop_strings": list(template.stop_strings),
    }
