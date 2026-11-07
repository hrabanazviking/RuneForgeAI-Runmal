"""Context templates (P-051): prompt assembly as a story string.

Until P-051 Rúnmál could reorder or disable the composer's
BLOCKS (P-049's prompt manager) and could say how a conversation
looks as raw text (P-050's instruct templates), but it had no
first-class thing that says how the preamble itself is ASSEMBLED:
which named pieces appear, in what order, wrapped in what literal
text, joined by what separators, and which separators double as
stop strings.

The public behaviour this slice models is census ST-32 (see
``docs/SILLYTAVERN_CENSUS_2026-10-30.md``): a context template /
story string assembling the preamble from named anchors -- the
system piece, character/persona fields, World Info before and
after, example dialogues, the chat history, the author's note and
the post-history instructions -- with an example separator, a
chat-start separator, and separators optionally acting as stop
strings. This module was built clean-room from that census line
and the in-tree patterns of P-049/P-050/P-021 only; no mirror
source was read for it.

A :class:`ContextTemplate` is data, like P-049's layout and
P-050's instruct templates:

- ``segments`` -- one :class:`ContextSegment` per anchor, in
  assembly order, each carrying only ``enabled``, ``prefix`` and
  ``suffix``: literal text wrapped around that anchor's content
  when the template is applied or assembled;
- ``separator`` -- text between segments in the story-string
  serialisation ONLY (apply never inserts it between slots);
- ``example_separator`` -- carried data only in P-051: it has
  NO apply effect (the examples slot arrives pre-joined;
  changing that is composer surgery, out of scope here);
- ``chat_start_separator`` -- text prepended (in apply only)
  before the history segment's own prefix;
- ``stops_from_separators`` -- when true, the template's
  non-empty separators are also its stop strings.

Segments are POSITION-FAITHFUL, like P-049's blocks: lore and
memory each occupy two baseline positions, so world info and
memory each get two anchors (``world_before`` / ``world_after``,
``memory_nucleus`` / ``memory_retrieved``), and the extra anchor
P-049 left unmanaged, ``post_history``, is a full segment here.
The default template lists every anchor in baseline order, all
enabled, and applying it reproduces the baseline assembly except
for any literal wrapping a segment declares (the default
declares none).

The story-string form is the interchange shape: a template
serialises to text with ``{{anchor}}`` placeholders (see
:func:`to_story_string`) and parses back from text whose
placeholders may also use the public alias spellings carried in
the in-tree census/fixtures (see :data:`STORY_ALIASES`).
:func:`context_template_from_preset` derives a template from an
imported preset (P-021): a carried ``context_template`` or
``story_string`` wins, otherwise the preset's ``prompt_order``
identifiers map onto anchors. A preset's prompt CONTENT is not
assembly data and is never copied into a template -- the prompt
manager owns content blocks; P-051 owns assembly shape only.

Scope: P-051 ships templates as data -- validated here and
applied to slot lists. There is no second render path:
story-string assembly IS apply + compose + the existing
P-050 render; this module never flattens content itself.
Persisting a
template per owner or per chat is a named follow-up slice that
owns its own migration; sampler wiring is P-052 and preset
bundles are P-054. Nothing in P-051 pretends to store one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from runmal.prompt.slots import BASELINE_INDEX, BASELINE_ORDER, Slot

#: Context segments in anchor form: anchor -> the slot kinds it
#: governs, exactly like P-049's ``BLOCK_KINDS`` but with anchors
#: named for the story string (``world_before`` / ``world_after``
#: for the lore positions) and with ``post_history`` included as
#: a full segment instead of an unmanaged tail kind.
SEGMENT_KINDS: dict[str, tuple[str, ...]] = {
    "system": ("main_system",),
    "persona": ("persona",),
    "memory_nucleus": ("memory_nucleus",),
    "world_before": ("lore_before",),
    "memory_retrieved": ("memory_retrieved",),
    "examples": ("examples",),
    "history": ("history",),
    "world_after": ("lore_after",),
    "authors_note": ("authors_note",),
    "post_history": ("post_history",),
}

#: Anchors in baseline (default template) order: sorted by the
#: smallest baseline index of the kinds each anchor governs.
SEGMENT_ORDER: tuple[str, ...] = tuple(
    sorted(
        SEGMENT_KINDS,
        key=lambda name: min(BASELINE_INDEX[k] for k in SEGMENT_KINDS[name]),
    )
)

#: Reverse map: slot kind -> the anchor governing it.
KIND_TO_SEGMENT: dict[str, str] = {
    kind: anchor for anchor, kinds in SEGMENT_KINDS.items() for kind in kinds
}

#: Trace discard reason for slots a disabled segment removed.
DISABLED_REASON = "context_template_disabled"


@dataclass(frozen=True)
class ContextSegment:
    anchor: str
    enabled: bool = True
    prefix: str = ""
    suffix: str = ""


@dataclass(frozen=True)
class ContextTemplate:
    name: str
    description: str = ""
    segments: tuple[ContextSegment, ...] = ()
    separator: str = ""
    example_separator: str = ""
    chat_start_separator: str = ""
    stops_from_separators: bool = False

    def segment(self, anchor: str) -> ContextSegment | None:
        for row in self.segments:
            if row.anchor == anchor:
                return row
        return None

    def position(self, anchor: str) -> int | None:
        for i, row in enumerate(self.segments):
            if row.anchor == anchor:
                return i
        return None

    def is_enabled(self, anchor: str) -> bool:
        row = self.segment(anchor)
        return row.enabled if row is not None else True

    def stop_strings(self) -> tuple[str, ...]:
        """Separator stops, when this template declares them.

        Unique non-empty separators, in separator /
        example_separator / chat_start_separator order; empty
        when ``stops_from_separators`` is false.
        """
        if not self.stops_from_separators:
            return ()
        stops: list[str] = []
        for text in (
            self.separator,
            self.example_separator,
            self.chat_start_separator,
        ):
            if text and text not in stops:
                stops.append(text)
        return tuple(stops)


#: The default template: every anchor enabled, in baseline
#: order, no literal wrapping, blank-line separator.
DEFAULT_TEMPLATE = ContextTemplate(
    name="default",
    description=(
        "Baseline assembly: every segment enabled in baseline "
        "order, no separators."
    ),
    segments=tuple(ContextSegment(anchor) for anchor in SEGMENT_ORDER),
)

#: Builtin registry, in presentation order.
BUILTIN_CONTEXT_TEMPLATES: tuple[ContextTemplate, ...] = (DEFAULT_TEMPLATE,)
CONTEXT_TEMPLATE_ORDER: tuple[str, ...] = tuple(
    t.name for t in BUILTIN_CONTEXT_TEMPLATES
)
_BY_NAME: dict[str, ContextTemplate] = {
    t.name: t for t in BUILTIN_CONTEXT_TEMPLATES
}


def default_context_template() -> ContextTemplate:
    """The baseline template: every segment enabled, in order."""
    return DEFAULT_TEMPLATE


def get_context_template(name: str) -> ContextTemplate:
    """The builtin template called ``name``; ValueError if none."""
    template = _BY_NAME.get(name)
    if template is None:
        raise ValueError(f"unknown context template: {name!r}")
    return template


def list_context_templates() -> tuple[ContextTemplate, ...]:
    return BUILTIN_CONTEXT_TEMPLATES


def _fill_segments(
    seen: list[ContextSegment], fill_enabled: bool
) -> tuple[ContextSegment, ...]:
    """Fill missing anchors at baseline-relative positions.

    The P-049 fill algorithm: insert each missing anchor just
    before the first present anchor that follows it in the
    default order (or at the end when none follows), so a
    partial structure still denotes a complete one and anchors
    a structure predates do not invalidate it.
    """
    filled = list(seen)
    present = {row.anchor for row in filled}
    for missing in SEGMENT_ORDER:
        if missing in present:
            continue
        at = len(filled)
        for i, row in enumerate(filled):
            if SEGMENT_ORDER.index(row.anchor) > SEGMENT_ORDER.index(missing):
                at = i
                break
        filled.insert(at, ContextSegment(missing, enabled=fill_enabled))
        present.add(missing)
    return tuple(filled)


_TEMPLATE_KEYS = frozenset({
    "name", "description", "segments", "separator",
    "example_separator", "chat_start_separator",
    "stops_from_separators",
})
_SEGMENT_KEYS = frozenset({"anchor", "enabled", "prefix", "suffix"})


def context_to_data(template: ContextTemplate) -> dict:
    return {
        "name": template.name,
        "description": template.description,
        "segments": [
            {
                "anchor": row.anchor,
                "enabled": row.enabled,
                "prefix": row.prefix,
                "suffix": row.suffix,
            }
            for row in template.segments
        ],
        "separator": template.separator,
        "example_separator": template.example_separator,
        "chat_start_separator": template.chat_start_separator,
        "stops_from_separators": template.stops_from_separators,
    }


def context_from_data(data: object) -> ContextTemplate:
    """Validate + build a template from API/stored data.

    Mirrors P-050's ``template_from_data`` and P-049's
    ``layout_from_data``: bad shapes raise ValueError (the API
    maps it to 422), unknown keys fail rather than being
    silently dropped, and anchors the data does not mention are
    filled in ENABLED at their baseline-relative positions, so
    a partial template still denotes a complete structure. A
    template with no ``segments`` key at all is the default
    all-enabled assembly; an empty segments list fails, as a
    layout must name at least one block (P-049).
    """
    if isinstance(data, list):
        data = {"name": "custom", "segments": data}
    if not isinstance(data, dict):
        raise ValueError("context template must be an object")
    unknown = set(data) - _TEMPLATE_KEYS
    if unknown:
        raise ValueError(f"unknown context template keys: {sorted(unknown)}")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("context template name must be a non-empty string")
    text: dict[str, str] = {}
    for key, default in (
        ("description", ""),
        ("separator", ""),
        ("example_separator", ""),
        ("chat_start_separator", ""),
    ):
        value = data.get(key, default)
        if not isinstance(value, str):
            raise ValueError(f"context template {key} must be a string")
        text[key] = value
    stops = data.get("stops_from_separators", False)
    if not isinstance(stops, bool):
        raise ValueError("context template stops_from_separators must be a boolean")
    if "segments" not in data:
        segments = tuple(ContextSegment(anchor) for anchor in SEGMENT_ORDER)
        return ContextTemplate(
            name=name, segments=segments,
            stops_from_separators=stops, **text,
        )
    raw_segments = data.get("segments")
    if not isinstance(raw_segments, list):
        raise ValueError("context template segments must be a list")
    seen: list[ContextSegment] = []
    names: set[str] = set()
    for entry in raw_segments:
        if not isinstance(entry, dict):
            raise ValueError("context template segments must be objects")
        seg_unknown = set(entry) - _SEGMENT_KEYS
        if seg_unknown:
            raise ValueError(
                f"unknown context segment keys: {sorted(seg_unknown)}"
            )
        anchor = entry.get("anchor")
        if anchor not in SEGMENT_KINDS:
            raise ValueError(f"unknown context segment anchor: {anchor!r}")
        if anchor in names:
            raise ValueError(f"duplicate context segment anchor: {anchor!r}")
        enabled = entry.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(
                f"context segment {anchor!r} enabled must be a boolean"
            )
        prefix, suffix = entry.get("prefix", ""), entry.get("suffix", "")
        if not isinstance(prefix, str) or not isinstance(suffix, str):
            raise ValueError(
                f"context segment {anchor!r} prefix/suffix must be strings"
            )
        names.add(anchor)
        seen.append(ContextSegment(anchor, enabled, prefix, suffix))
    if not seen:
        raise ValueError("context template must name at least one segment")
    return ContextTemplate(
        name=name, segments=_fill_segments(seen, True),
        stops_from_separators=stops, **text,
    )


#: Public alias spellings for story-string placeholders, from
#: the in-tree census/fixtures: alias -> canonical anchor.
#: Canonical anchor names are always accepted as well.
STORY_ALIASES: dict[str, str] = {
    "worldInfoBefore": "world_before",
    "worldInfoAfter": "world_after",
    "chatHistory": "history",
    "dialogueExamples": "examples",
    "mesExamples": "examples",
    "authorsNote": "authors_note",
    "main": "system",
}

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def _anchor_for_placeholder(name: str) -> str:
    if name in SEGMENT_KINDS:
        return name
    anchor = STORY_ALIASES.get(name)
    if anchor is None:
        raise ValueError(f"unknown story string placeholder: {name!r}")
    return anchor


def to_story_string(template: ContextTemplate) -> str:
    """Serialise a template to its story-string form.

    Enabled segments only, in template order, each rendered as
    its ``prefix`` + ``{{anchor}}`` + ``suffix``, joined by the
    template's separator.
    """
    pieces = [
        row.prefix + "{{" + row.anchor + "}}" + row.suffix
        for row in template.segments
        if row.enabled
    ]
    return template.separator.join(pieces)


def from_story_string(text: str, name: str = "story") -> ContextTemplate:
    """Parse a story string into a template.

    The string is the whole assembly: a literal before an
    anchor becomes that segment's prefix, a literal after the
    last anchor becomes that (last) segment's suffix, and
    anchors the string does not mention fill in DISABLED at
    their baseline-relative positions. Unknown placeholders,
    duplicate anchors (aliases resolve before the duplicate
    check, so ``{{examples}}`` and ``{{dialogueExamples}}``
    collide), and a string with no placeholders at all raise
    ValueError. The result's separator is empty: the literals
    themselves carry the spacing.
    """
    if not isinstance(text, str):
        raise ValueError("story string must be a string")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("context template name must be a non-empty string")
    matches = list(_PLACEHOLDER_RE.finditer(text))
    if not matches:
        raise ValueError("story string must contain at least one placeholder")
    seen: list[ContextSegment] = []
    anchors: set[str] = set()
    prev_end = 0
    for match in matches:
        literal = text[prev_end:match.start()]
        if "{{" in literal:
            raise ValueError(
                "story string contains an unrecognised handlebars form"
            )
        anchor = _anchor_for_placeholder(match.group(1))
        if anchor in anchors:
            raise ValueError(f"duplicate story string anchor: {anchor!r}")
        anchors.add(anchor)
        seen.append(ContextSegment(anchor, True, prefix=literal))
        prev_end = match.end()
    trailing = text[prev_end:]
    if "{{" in trailing:
        raise ValueError(
            "story string contains an unrecognised handlebars form"
        )
    if trailing:
        seen[-1] = replace(seen[-1], suffix=trailing)
    return ContextTemplate(
        name=name, segments=_fill_segments(seen, False), separator=""
    )


def _effective_prefix(template: ContextTemplate, row: ContextSegment) -> str:
    """A segment's apply/assemble prefix.

    The history segment's effective prefix carries the
    template's chat-start separator before its own prefix; no
    other segment is touched by it.
    """
    if row.anchor == "history":
        return template.chat_start_separator + row.prefix
    return row.prefix


def apply_context_template(
    slots: list[Slot], template: ContextTemplate
) -> tuple[list[Slot], list[Slot]]:
    """Rewrite ``slots`` through ``template`` for the composer.

    Mirrors P-049's ``apply_layout`` in structure. Returns
    ``(kept, dropped)``: a kept slot's ``order`` becomes
    ``segment_position * 100 + baseline_index(kind)``; dropped
    slots are the disabled segments' slots, in input order, so
    the caller can record them in the trace (with reason
    :data:`DISABLED_REASON`). Kinds no segment governs form the
    unmanaged tail: ``len(segments) * 100 + baseline_index``.

    Depth slots keep P-049's splice contract: a depth slot's
    order is ``max(assigned, history_assigned + 10)``, keyed on
    the history slot's ASSIGNED order, when the history segment
    is enabled and present.

    Wrapping is idempotent: a fragment already starting with
    the segment prefix (or ending with its suffix) is not
    wrapped again, so applying a template twice is stable.

    Kept slots are also wrapped in their segment's literal
    ``prefix`` / ``suffix`` (history slots get the chat-start
    separator before their segment prefix): a non-splittable
    slot's content is wrapped; a splittable slot's prefix is
    prepended to its first part and its suffix appended to its
    last part.
    """
    span = 100
    history_pos = template.position("history")
    history_enabled = template.is_enabled("history")
    history_assigned = (
        history_pos * span + BASELINE_INDEX["history"]
        if history_enabled and history_pos is not None
        else None
    )
    kept: list[Slot] = []
    dropped: list[Slot] = []
    for slot in slots:
        anchor = KIND_TO_SEGMENT.get(slot.kind)
        if anchor is None:
            kept.append(
                replace(
                    slot,
                    order=len(template.segments) * span
                    + BASELINE_INDEX.get(slot.kind, len(BASELINE_ORDER)),
                )
            )
            continue
        if not template.is_enabled(anchor):
            dropped.append(slot)
            continue
        pos = template.position(anchor)
        if pos is None:
            pos = SEGMENT_ORDER.index(anchor)
        order = pos * span + BASELINE_INDEX.get(slot.kind, 0)
        if slot.depth is not None and history_assigned is not None:
            order = max(order, history_assigned + 10)
        row = template.segment(anchor)
        prefix = _effective_prefix(template, row) if row is not None else ""
        suffix = row.suffix if row is not None else ""
        if not prefix and not suffix:
            kept.append(replace(slot, order=order))
        elif slot.splittable:
            parts = list(slot.parts)
            if prefix and not parts[0].startswith(prefix):
                parts[0] = prefix + parts[0]
            if suffix and not parts[-1].endswith(suffix):
                parts[-1] = parts[-1] + suffix
            kept.append(replace(slot, order=order, parts=tuple(parts)))
        else:
            content = slot.content
            if prefix and not content.startswith(prefix):
                content = prefix + content
            if suffix and not content.endswith(suffix):
                content = content + suffix
            kept.append(replace(slot, order=order, content=content))
    return kept, dropped


#: Preset prompt_order identifiers -> anchors (P-021 carriage).
#: Several character-field identifiers share the persona
#: anchor; the first occurrence of an anchor wins (see
#: :func:`context_template_from_preset`).
IDENTIFIER_TO_ANCHOR: dict[str, str] = {
    "main": "system",
    "worldInfoBefore": "world_before",
    "personaDescription": "persona",
    "charDescription": "persona",
    "charPersonality": "persona",
    "scenario": "persona",
    "worldInfoAfter": "world_after",
    "dialogueExamples": "examples",
    "chatHistory": "history",
    "jailbreak": "post_history",
}


def _preset_field(preset: object, key: str, default=None):
    if isinstance(preset, dict):
        return preset.get(key, default)
    return getattr(preset, key, default)


def context_template_from_preset(preset: object) -> ContextTemplate | None:
    """Derive a context template from an imported preset.

    Accepts an ImportedPreset-like object (attributes
    ``prompts`` / ``prompt_order`` / ``raw`` / ``name``, P-021)
    or a dict of the same shape (e.g. a ``preset_to_dict``
    result). Precedence:

    1. a carried ``context_template`` (a dict in
       :func:`context_from_data` shape, or a string parsed as
       a story string), looked for at the top level first,
       then inside the preset's ``raw`` carriage;
    2. a carried ``story_string`` string, same lookup order,
       parsed via :func:`from_story_string`;
    3. the preset's ``prompt_order``: identifiers map through
       :data:`IDENTIFIER_TO_ANCHOR` (entries are strings or
       ``{identifier, enabled}`` objects, enabled defaulting
       true), unmapped identifiers are skipped, the first
       occurrence of each anchor wins its position and enabled
flag, and anchors never mentioned fill in ENABLED at
       baseline-relative positions (the P-049 fill rule: a
       prompt_order may be partial, so an unmentioned anchor
       keeps its baseline place; fill-DISABLED belongs to
       story strings alone). When the flat order maps nothing,
       a grouped raw prompt_order is flattened and tried.
       When no identifier maps at all, the result is None.

    The template name is the preset's name, or ``imported``
    when it carries none. The preset's prompt CONTENT is never
    copied: it is not assembly data (see the module docstring).
    """
    name_value = _preset_field(preset, "name")
    preset_name = (
        name_value
        if isinstance(name_value, str) and name_value.strip()
        else "imported"
    )
    def _carried(container: object) -> ContextTemplate | None:
        if not isinstance(container, dict):
            return None
        if "context_template" in container:
            carried = container["context_template"]
            if isinstance(carried, str):
                return from_story_string(carried, name=preset_name)
            return context_from_data(carried)
        story = container.get("story_string")
        if isinstance(story, str):
            return from_story_string(story, name=preset_name)
        return None

    if isinstance(preset, dict):
        hit = _carried(preset)
        if hit is not None:
            return hit
    raw = _preset_field(preset, "raw")
    hit = _carried(raw)
    if hit is not None:
        return hit
    prompt_order = _preset_field(preset, "prompt_order") or []
    if not isinstance(prompt_order, (list, tuple)):
        return None
    def _flatten(order: list) -> list:
        flat: list = []
        for e in order:
            if isinstance(e, dict) and isinstance(e.get("order"), list):
                flat.extend(e["order"])
            else:
                flat.append(e)
        return flat

    entries = _flatten(list(prompt_order))
    if not any(
        isinstance(e, str) or (isinstance(e, dict) and "identifier" in e)
        for e in entries
    ) and isinstance(raw, dict):
        grouped = raw.get("prompt_order")
        if isinstance(grouped, list):
            flat = _flatten(grouped)
            if flat:
                entries = flat
    seen: list[ContextSegment] = []
    anchors: set[str] = set()
    for entry in entries:
        if isinstance(entry, str):
            identifier, enabled = entry, True
        elif isinstance(entry, dict):
            identifier = entry.get("identifier")
            raw_enabled = entry.get("enabled", True)
            enabled = raw_enabled if isinstance(raw_enabled, bool) else True
        else:
            continue
        if not isinstance(identifier, str):
            continue
        anchor = IDENTIFIER_TO_ANCHOR.get(identifier)
        if anchor is None or anchor in anchors:
            continue
        anchors.add(anchor)
        seen.append(ContextSegment(anchor, enabled))
    if not seen:
        return None
    return ContextTemplate(
        name=preset_name, segments=_fill_segments(seen, True)
    )
