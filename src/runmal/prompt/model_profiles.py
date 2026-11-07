"""Multi-model prompt profiles (P-062): one chat, swappable profiles.

Roadmap line: *Multi-model prompt profiles: one chat, swappable
model profiles with their own templates/samplers (the mirrors'
connection profiles, sovereign-shaped).*

Until P-062 the pieces of "which model, shaped how" lived apart:
a model was a bare ``model_id`` string on a request, its instruct
template was resolved per request (P-050), its context template
likewise (P-051), its layout likewise (P-049), and its sampler set
was a preset's bag (S207/P-052) with no model attached. Nothing in
the tree was the unit a user actually thinks in: *this chat runs
on that model, with that model's framing and that model's
samplers — and I can swap the whole unit without losing my chat.*

A :class:`ModelProfile` is that unit, as data:

- ``model_id`` / ``backend_key`` -- the model this profile runs,
  and optionally the backend that serves it (the backend is what
  makes sampler truth judgable, P-053; without one, support is
  undeclared and nothing here guesses);
- ``instruct_template`` / ``context_template`` -- SELECTIONS in
  the P-054 bundle shape (``{"kind": "builtin", "name": ...}``,
  ``{"kind": "custom", "template": {...}}``, plus
  ``story_string`` for context): the registry stays the truth for
  a builtin's data; only the name is carried;
- ``prompt_layout`` -- a P-049 layout in its normalised data form,
  or None;
- ``sampler`` -- the S207/P-052 parameter bag, validated by
  :func:`runmal.presets.service.validate_params` (canonical keys
  type/range-checked; unknown keys preserved verbatim);
- ``extensions`` -- every OTHER top-level key of an incoming
  profile, preserved verbatim (the P-054 honesty rule: foreign
  fields are carried, never silently dropped).

Malformed KNOWN sections refuse cleanly (ValueError): a bad
sampler value, an unknown layout block, an unknown builtin name
or a malformed custom template is a profile that would lie about
what it carries. Normalisation is a fixed point: validating a
validated profile returns it unchanged.

Switching is honest about what changes and what carries:
:func:`diff_profiles` reports per-field changes (and per-key
sampler changes) between two profiles, and the fixed
:data:`CARRIES` list -- chat state a profile never governs
(history, character, lorebooks, author's note, post-history
instructions), which a switch therefore never touches.

Sampler honesty (P-053): :func:`partition_profile_sampler` splits
a profile's canonical sampler keys against the truth of the
backend the profile names, judged by that backend's DECLARED
sampler set. Offered keys pass; greyed keys come back as truth
rows (never silently kept, never pretended honoured);
non-canonical keys are reported as carried-unknown and are never
offered at all. With no backend named, no partition is claimed.

Scope: P-062 ships profiles as data -- validated here, supplied
per request through the inspector, honoured by the composition
path that exists. Generation does not route through the composer
in this tree (the P-059 scout finding, re-verified for P-062), so
profiles govern composition/inspection, not live generation;
wiring generation is a separate future slice. Persisting a
profile per owner or per chat is likewise a named follow-up slice
owning its own migration; nothing in P-062 pretends to store one.
No mirror source was read for this slice (clean-room log, P-062).
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field

from runmal.presets.service import validate_params
from runmal.prompt.context import (
    ContextTemplate,
    context_from_data,
    context_to_data,
    from_story_string,
    get_context_template,
)
from runmal.prompt.instruct import (
    InstructTemplate,
    get_template,
    template_from_data,
    template_to_data,
)
from runmal.prompt.manager import (
    PromptLayout,
    layout_from_data,
    layout_to_data,
)

__all__ = [
    "CARRIES",
    "PROFILE_SCHEMA",
    "BUILTIN_PROFILES",
    "PROFILE_ORDER",
    "ModelProfile",
    "profile_to_data",
    "profile_from_data",
    "get_profile",
    "list_profiles",
    "selection_to_template",
    "selection_to_context_template",
    "partition_profile_sampler",
    "diff_profiles",
]

PROFILE_SCHEMA = "runmal-p062-model-profile-v1"

#: Chat state a profile switch never touches: a profile governs
#: model + templates + layout + samplers, and nothing else in a
#: chat, so everything else carries across a switch by definition.
CARRIES: tuple[str, ...] = (
    "history",
    "character",
    "lorebooks",
    "authors_note",
    "post_history",
)

_KNOWN_KEYS = frozenset({
    "name", "description", "model_id", "backend_key",
    "instruct_template", "context_template", "prompt_layout",
    "sampler", "extensions",
})


@dataclass(frozen=True)
class ModelProfile:
    name: str
    description: str = ""
    model_id: str | None = None
    backend_key: str | None = None
    instruct_template: dict | None = None
    context_template: dict | None = None
    prompt_layout: dict | None = None
    sampler: dict = field(default_factory=dict)
    extensions: dict = field(default_factory=dict)


# ---------------- selections (the P-054 shapes) ----------------


def _validate_selection(value: object, kind_label: str) -> dict | None:
    """Validate one template selection; None passes through.

    Mirrors P-054's ``_validate_selection`` exactly in shape and
    strictness (unknown keys inside a selection refuse), but
    raises plain ValueError: profiles are a prompt-layer concept
    and carry no bundle error type.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{kind_label} selection must be an object or null")
    kind = value.get("kind")
    if kind == "builtin":
        name = value.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(f"{kind_label} builtin selection needs a name")
        if kind_label == "instruct_template":
            get_template(name)
        else:
            get_context_template(name)
        extra = set(value) - {"kind", "name"}
        if extra:
            raise ValueError(
                f"{kind_label} builtin selection has unknown keys: {sorted(extra)}")
        return {"kind": "builtin", "name": name}
    if kind == "custom":
        template = value.get("template")
        extra = set(value) - {"kind", "template"}
        if extra:
            raise ValueError(
                f"{kind_label} custom selection has unknown keys: {sorted(extra)}")
        if kind_label == "instruct_template":
            return {"kind": "custom",
                    "template": template_to_data(template_from_data(template))}
        return {"kind": "custom",
                "template": context_to_data(context_from_data(template))}
    if kind == "story_string" and kind_label == "context_template":
        text = value.get("text")
        if not isinstance(text, str) or "{{" not in text:
            raise ValueError(
                "context story_string selection needs text with a {{placeholder}}")
        extra = set(value) - {"kind", "text"}
        if extra:
            raise ValueError(
                f"{kind_label} story_string selection has unknown keys: {sorted(extra)}")
        from_story_string(text)
        return {"kind": "story_string", "text": text}
    raise ValueError(f"{kind_label} selection kind is unknown: {kind!r}")


def selection_to_template(selection: dict | None) -> InstructTemplate | None:
    """The instruct template a selection denotes; None if no selection."""
    if selection is None:
        return None
    if selection["kind"] == "builtin":
        return get_template(selection["name"])
    return template_from_data(selection["template"])


def selection_to_context_template(
    selection: dict | None,
) -> ContextTemplate | None:
    """The context template a selection denotes; None if no selection."""
    if selection is None:
        return None
    if selection["kind"] == "builtin":
        return get_context_template(selection["name"])
    if selection["kind"] == "story_string":
        return from_story_string(selection["text"])
    return context_from_data(selection["template"])


# ---------------- data form ----------------


def _json_safe(value: object, what: str) -> object:
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{what} is not JSON-serializable") from exc
    return copy.deepcopy(value)


def profile_to_data(profile: ModelProfile) -> dict:
    return {
        "name": profile.name,
        "description": profile.description,
        "model_id": profile.model_id,
        "backend_key": profile.backend_key,
        "instruct_template": copy.deepcopy(profile.instruct_template),
        "context_template": copy.deepcopy(profile.context_template),
        "prompt_layout": copy.deepcopy(profile.prompt_layout),
        "sampler": copy.deepcopy(profile.sampler),
        "extensions": copy.deepcopy(profile.extensions),
    }


def profile_from_data(data: object) -> ModelProfile:
    """Validate + normalise a profile; return the ModelProfile.

    Fixed point: ``profile_from_data(profile_to_data(p)) == p``
    for every valid ``p``, and re-validating the data form of a
    validated profile returns the identical data form. Unknown
    top-level keys are preserved under ``extensions`` (an explicit
    ``extensions`` object wins on a key clash, the P-054 rule).
    """
    if not isinstance(data, dict):
        raise ValueError("model profile must be an object")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("model profile name must be a non-empty string")
    description = data.get("description", "")
    if not isinstance(description, str):
        raise ValueError("model profile description must be a string")
    model_id = data.get("model_id")
    if model_id is not None and (
        not isinstance(model_id, str) or not model_id.strip()
    ):
        raise ValueError("model profile model_id must be a non-empty string or null")
    backend_key = data.get("backend_key")
    if backend_key is not None and (
        not isinstance(backend_key, str) or not backend_key.strip()
    ):
        raise ValueError("model profile backend_key must be a non-empty string or null")
    instruct = _validate_selection(
        data.get("instruct_template"), "instruct_template")
    context = _validate_selection(
        data.get("context_template"), "context_template")
    layout = data.get("prompt_layout")
    if layout is not None:
        layout = layout_to_data(layout_from_data(layout))
    sampler = validate_params(data.get("sampler") or {})
    extensions: dict = {}
    raw_ext = data.get("extensions", {})
    if not isinstance(raw_ext, dict):
        raise ValueError("model profile extensions must be an object")
    extensions.update(_json_safe(raw_ext, "extensions"))
    for key, value in data.items():
        if key not in _KNOWN_KEYS:
            extensions[key] = _json_safe(value, f"extension {key!r}")
    return ModelProfile(
        name=name,
        description=description,
        model_id=model_id,
        backend_key=backend_key,
        instruct_template=instruct,
        context_template=context,
        prompt_layout=layout,
        sampler=sampler,
        extensions=extensions,
    )


# ---------------- builtins ----------------

#: Builtin profiles, in presentation order. Honest by construction:
#: none invents a model id -- a builtin either names no model at
#: all (the caller's current model, with these templates/samplers)
#: or binds templates a model family is publicly known to use via
#: the P-050 per-model defaults. Binding a concrete deployment
#: model is what user-authored profile data is for.
DEFAULT_PROFILE = ModelProfile(
    name="default",
    description=(
        "No model, no selections, no samplers: switching to this "
        "profile changes nothing but the profile name."),
)

CHATML_GENERAL = ModelProfile(
    name="chatml-general",
    description=(
        "ChatML framing with the baseline context assembly, for "
        "the caller's current model."),
    instruct_template={"kind": "builtin", "name": "chatml"},
    context_template={"kind": "builtin", "name": "default"},
    sampler={"temperature": 0.7, "top_p": 0.9},
)

LLAMA3_INSTRUCT = ModelProfile(
    name="llama3-instruct",
    description=(
        "Llama-3 instruct framing with the baseline context "
        "assembly, for the caller's current model."),
    instruct_template={"kind": "builtin", "name": "llama3"},
    context_template={"kind": "builtin", "name": "default"},
    sampler={"temperature": 0.7, "top_p": 0.9, "top_k": 40},
)

BUILTIN_PROFILES: tuple[ModelProfile, ...] = (
    DEFAULT_PROFILE, CHATML_GENERAL, LLAMA3_INSTRUCT,
)
PROFILE_ORDER: tuple[str, ...] = tuple(p.name for p in BUILTIN_PROFILES)
_BY_NAME: dict[str, ModelProfile] = {p.name: p for p in BUILTIN_PROFILES}


def get_profile(name: str) -> ModelProfile:
    """The builtin profile called ``name``; ValueError if none."""
    profile = _BY_NAME.get(name)
    if profile is None:
        raise ValueError(f"unknown model profile: {name!r}")
    return profile


def list_profiles() -> tuple[ModelProfile, ...]:
    return BUILTIN_PROFILES


# ---------------- sampler truth (P-053) ----------------


def partition_profile_sampler(profile: ModelProfile) -> dict:
    """Partition a profile's sampler bag against its backend's truth.

    Returns a metadata dict (key names and truth rows only, never
    sampler values):

    - no backend named: ``{"backend_key": None, "model_id": ...,
      "partitioned": False, "offered": [], "greyed": [],
      "carried_unknown": [...]}`` -- every canonical key is
      unpartitioned and nothing is claimed about support;
    - backend named: the backend must be a known chat backend
      (ValueError otherwise -- an unknown backend is refused, not
      guessed at); canonical keys split into ``offered`` (the
      backend declares them) and ``greyed`` (truth rows as dicts);
      non-canonical keys are ``carried_unknown`` -- preserved in
      the profile, never offered.
    """
    from runmal.backends.samplers import SAMPLER_NAMES

    canonical = frozenset(SAMPLER_NAMES)
    keys = sorted(profile.sampler)
    carried_unknown = [k for k in keys if k not in canonical]
    if profile.backend_key is None:
        return {
            "backend_key": None,
            "model_id": profile.model_id,
            "partitioned": False,
            "offered": [],
            "greyed": [],
            "carried_unknown": carried_unknown,
            "unpartitioned": [k for k in keys if k in canonical],
        }
    from runmal.backends.capabilities import declared_samplers, partition_bag
    from runmal.backends.models import Capabilities, ModelInfo

    declared = declared_samplers(profile.backend_key)
    model = ModelInfo(
        model_id=profile.model_id or "",
        display_name=profile.model_id or "",
        backend_key=profile.backend_key,
        capabilities=Capabilities(supported_samplers=declared),
    )
    bag = {k: profile.sampler[k] for k in keys if k in canonical}
    offered, greyed = partition_bag(bag, model)
    return {
        "backend_key": profile.backend_key,
        "model_id": profile.model_id,
        "partitioned": True,
        "offered": sorted(offered),
        "greyed": [row.to_dict() for row in greyed],
        "carried_unknown": carried_unknown,
        "unpartitioned": [],
    }


# ---------------- switching ----------------


def _selection_label(selection: dict | None) -> str | None:
    if selection is None:
        return None
    if selection["kind"] == "builtin":
        return f"builtin:{selection['name']}"
    if selection["kind"] == "story_string":
        return "story_string"
    template = selection.get("template") or {}
    return f"custom:{template.get('name', '')}"


def diff_profiles(before: ModelProfile, after: ModelProfile) -> dict:
    """What switching ``before`` -> ``after`` changes, and what carries.

    ``changes`` holds one row per governed field whose value
    differs (``{"field", "from", "to"}``; template fields report
    selection labels, the layout reports presence by block count,
    and the sampler expands to one row per differing key with the
    key's values -- sampler values are the profile's own declared
    numbers, not chat content). ``carries`` is always the fixed
    :data:`CARRIES` list: the chat state no profile governs.
    """
    changes: list[dict] = []
    if before.name != after.name:
        changes.append(
            {"field": "name", "from": before.name, "to": after.name})
    if before.model_id != after.model_id:
        changes.append(
            {"field": "model_id", "from": before.model_id,
             "to": after.model_id})
    if before.backend_key != after.backend_key:
        changes.append(
            {"field": "backend_key", "from": before.backend_key,
             "to": after.backend_key})
    for field_name in ("instruct_template", "context_template"):
        old = _selection_label(getattr(before, field_name))
        new = _selection_label(getattr(after, field_name))
        if old != new:
            changes.append({"field": field_name, "from": old, "to": new})
    old_layout = (
        None if before.prompt_layout is None
        else len(before.prompt_layout.get("blocks", []))
    )
    new_layout = (
        None if after.prompt_layout is None
        else len(after.prompt_layout.get("blocks", []))
    )
    if before.prompt_layout != after.prompt_layout:
        changes.append(
            {"field": "prompt_layout",
             "from": None if old_layout is None else f"{old_layout} blocks",
             "to": None if new_layout is None else f"{new_layout} blocks"})
    for key in sorted(set(before.sampler) | set(after.sampler)):
        old = before.sampler.get(key)
        new = after.sampler.get(key)
        if old != new:
            changes.append(
                {"field": f"sampler.{key}", "from": old, "to": new})
    return {
        "from_profile": before.name,
        "to_profile": after.name,
        "changes": changes,
        "carries": list(CARRIES),
    }


def layout_for_profile(profile: ModelProfile) -> PromptLayout | None:
    """The layout a profile carries; None when it carries none."""
    if profile.prompt_layout is None:
        return None
    return layout_from_data(profile.prompt_layout)
