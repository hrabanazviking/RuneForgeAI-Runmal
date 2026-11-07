"""Prompt resolution services (P-049 layout; P-050 instruct; P-051 context; P-058 governor).

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


# ---------------- P-051: context template resolution ----------------

from runmal.prompt.context import (  # noqa: E402
    ContextTemplate,
    context_from_data,
    context_template_from_preset,
    default_context_template,
    from_story_string,
    get_context_template,
)


def resolve_context_template(
    explicit: object | None = None, preset: object | None = None
) -> tuple[ContextTemplate | None, str]:
    """Resolve the context template for a composition.

    Precedence, explicit first (mirrors resolve_template):

    - ``explicit`` as a string containing ``{{`` is a story
      string, parsed by from_story_string;
    - ``explicit`` as any other string names a builtin context
      template (ValueError on an unknown name propagates);
    - ``explicit`` as a dict is a full custom template,
      validated by context_from_data;
    - otherwise a preset (an ImportedPreset or a stored preset
      dict) contributes the template its P-021 carriage implies
      (source "preset") when it carries one;
    - otherwise nothing is in play: ``(None, "default")`` (the
      P-049 resolve_layout shape), so the no-template pipeline
      stays byte-identical to pre-P-051; the caller echoes the
      default template, whose application is an exact identity
      on the baseline assembly anyway.

    Returns ``(template, source)`` with source one of
    "explicit" | "preset" | "default".
    """
    if isinstance(explicit, str):
        if "{{" in explicit:
            return from_story_string(explicit), "explicit"
        return get_context_template(explicit), "explicit"
    if explicit is not None:
        return context_from_data(explicit), "explicit"
    if preset is not None:
        derived = context_template_from_preset(preset)
        if derived is not None:
            return derived, "preset"
    return None, "default"


def context_echo(template: ContextTemplate | None, source: str) -> dict:
    """The ``context_template`` echo for an inspect result.

    Metadata only, whitelist-pinned: the source, one
    ``{anchor, enabled}`` row per segment in assembly order,
    and the derived stop strings. No prefix / suffix /
    separator literals and no slot content ever enter an
    inspect result (S214 trace safety contract). A ``None``
    template echoes the default template (the layout_echo
    precedent).
    """
    active = template if template is not None else default_context_template()
    return {
        "source": source,
        "segments": [
            {"anchor": seg.anchor, "enabled": seg.enabled}
            for seg in active.segments
        ],
        "stop_strings": list(active.stop_strings()),
    }


# ---------------- P-058: budget policy resolution ----------------

from runmal.prompt.governor import (  # noqa: E402
    BudgetPolicy,
    default_policy,
    policy_from_data,
    policy_to_data,
)


def resolve_policy(explicit: object | None) -> tuple[BudgetPolicy | None, str]:
    """Resolve the budget policy for a composition.

    Returns ``(policy, source)``: an explicit policy is validated
    by policy_from_data (ValueError propagates to the caller,
    which maps it to 422) and returned with source ``"explicit"``;
    ``None`` yields ``(None, "default")`` -- no policy in play, so
    the pipeline composes exactly as it did before P-058.
    """
    if explicit is not None:
        return policy_from_data(explicit), "explicit"
    return None, "default"


def policy_echo(policy: BudgetPolicy | None, source: str) -> dict:
    """The ``budget_governor`` policy echo for an inspect result."""
    return {
        "source": source,
        "policy": policy_to_data(policy if policy is not None else default_policy()),
    }


# ---------------- P-062: model profile resolution ----------------

from runmal.prompt.model_profiles import (  # noqa: E402
    ModelProfile,
    get_profile,
    partition_profile_sampler,
    profile_from_data,
)


def resolve_model_profile(
    explicit: object | None = None,
) -> tuple[ModelProfile | None, str]:
    """Resolve the model profile for a composition.

    - ``explicit`` as a string names a builtin profile
      (ValueError on an unknown name propagates to the caller,
      which maps it to 422);
    - ``explicit`` as a dict is full profile data, validated by
      profile_from_data;
    - otherwise no profile is in play: ``(None, "none")``.

    Returns ``(profile, source)`` with source "explicit" | "none"
    (a supplied profile is always an explicit act; there is no
    stored tier in P-062, so no other source exists yet).
    """
    if isinstance(explicit, str):
        return get_profile(explicit), "explicit"
    if explicit is not None:
        return profile_from_data(explicit), "explicit"
    return None, "none"


def model_profile_echo(
    profile: ModelProfile | None,
    source: str,
    *,
    field_sources: dict | None = None,
) -> dict:
    """The ``model_profile`` echo for an inspect result.

    Metadata only (S214): profile name/source, the effective
    model/backend NAMES, per-field resolution sources, extension
    KEY names, and the sampler partition as key names plus greyed
    truth rows. No prompt content, no sampler values and no
    extension values ever enter the echo.
    """
    if profile is None:
        return {
            "applied": False,
            "name": None,
            "source": source,
            "model_id": None,
            "backend_key": None,
            "fields": {},
            "extension_keys": [],
            "sampler": {
                "partitioned": False,
                "offered": [],
                "greyed": [],
                "carried_unknown": [],
                "unpartitioned": [],
            },
        }
    part = partition_profile_sampler(profile)
    return {
        "applied": True,
        "name": profile.name,
        "source": source,
        "model_id": profile.model_id,
        "backend_key": profile.backend_key,
        "fields": dict(field_sources or {}),
        "extension_keys": sorted(profile.extensions),
        "sampler": {
            "partitioned": part["partitioned"],
            "offered": part["offered"],
            "greyed": [
                {
                    "name": row["name"],
                    "reason_code": row["reason_code"],
                    "reason": row["reason"],
                }
                for row in part["greyed"]
            ],
            "carried_unknown": part["carried_unknown"],
            "unpartitioned": part["unpartitioned"],
        },
    }
