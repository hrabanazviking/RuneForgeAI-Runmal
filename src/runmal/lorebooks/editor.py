"""P-042 lorebook editor census: every field the engine honours,
reachable through the editor.

The lorebook engine grew field by field across Part III (P-031
recursion, P-032 selective logic, P-033 timed effects, P-034
inclusion groups, P-035 entry states, P-036 probability, P-037
scan windows, P-038 position/depth, P-040 scopes, P-041
vectorised lore) while the editor page (``web/templates/
lorebooks.html`` + ``web/static/lorebooks.js``) stayed at its
S304 shape: it could edit ten entry fields, offered only two of
the three positions, and had no book-settings form, no scope
controls and a preview panel that reached only three of the
preview engine's controls. Two preview controls were worse than
UI-missing: ``recursive_scan`` / ``max_recursion_depth`` existed
only inside :func:`runmal.lorebooks.preview.preview_activation`
-- no API shape carried them at all.

This module is the census that closes the gap, as data. For each
surface the editor owns (book, entry, scope assignment, preview)
it declares every engine-honoured field, the API shape that
carries it, and the editor element that edits it. The P-042
battery derives the engine's field set independently -- from the
SQLAlchemy models, the engine views (scan / activation /
placement / budget), the service dicts and the router models --
and fails if any field is missing here, missing from the API, or
missing from the page/JS. A future slice that adds an engine
field must extend this census (and the editor) or the battery
goes red: no engine-only settings, by construction.

Out of census, deliberately: the P-039 character-book binding
(``precedence``) is a field of the *character* aggregate, edited
through the characters API surface that P-039 shipped; it is not
a lorebook or lore-entry field. Per-chat timed-effect runtime
state (P-033 counters) is engine state, not an authored field.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "EditorField",
    "BOOK_FIELDS",
    "ENTRY_FIELDS",
    "SCOPE_FIELDS",
    "PREVIEW_FIELDS",
    "SURFACES",
    "editor_schema",
    "field_names",
]


@dataclass(frozen=True)
class EditorField:
    """One engine-honoured field and its editor reachability."""

    name: str
    surface: str  # book | entry | scope | preview
    kind: str  # text | longtext | int | int_or_null | bool | select | keys | lines | derived
    element_id: str  # element id in lorebooks.html that edits/shows it
    options: tuple[str, ...] = ()  # select vocabulary, when kind == select
    api_model: str = ""  # router model carrying the field


def _f(name, surface, kind, element_id, options=(), api_model=""):
    return EditorField(name, surface, kind, element_id, tuple(options), api_model)


#: Book-level fields (Lorebook model; service.lorebook_to_dict).
BOOK_FIELDS: tuple[EditorField, ...] = (
    _f("name", "book", "text", "b-name", api_model="LorebookCreate"),
    _f("description", "book", "longtext", "b-description", api_model="LorebookCreate"),
    _f("scan_depth", "book", "int", "b-scan-depth", api_model="LorebookCreate"),
    _f("token_budget", "book", "int_or_null", "b-token-budget", api_model="LorebookCreate"),
    _f("scan_mode", "book", "select", "b-scan-mode", ("depth", "whole_chat"), "LorebookCreate"),
    _f("scan_external_context", "book", "bool", "b-scan-external", api_model="LorebookCreate"),
)

#: Entry-level authored fields (LoreEntry model; service.entry_to_dict).
#: ``activation_kind`` is derived (P-035: constant > vectorised >
#: selective) -- never stored, shown read-only so the author sees
#: the kind the engine will use.
ENTRY_FIELDS: tuple[EditorField, ...] = (
    _f("name", "entry", "text", "e-name", api_model="EntryCreate"),
    _f("content", "entry", "longtext", "e-content", api_model="EntryCreate"),
    _f("keys", "entry", "keys", "e-keys", api_model="EntryCreate"),
    _f("secondary_keys", "entry", "keys", "e-secondary", api_model="EntryCreate"),
    _f("selective_logic", "entry", "select", "e-selective-logic", ("and_any", "and_all", "not_any", "not_all"), "EntryCreate"),
    _f("inclusion_group", "entry", "text", "e-inclusion-group", api_model="EntryCreate"),
    _f("group_weight", "entry", "int", "e-group-weight", api_model="EntryCreate"),
    _f("probability", "entry", "int", "e-probability", api_model="EntryCreate"),
    _f("priority", "entry", "int", "e-priority", api_model="EntryCreate"),
    _f("position", "entry", "select", "e-position", ("before_char", "after_char", "at_depth"), "EntryCreate"),
    _f("depth", "entry", "int_or_null", "e-depth", api_model="EntryCreate"),
    _f("role", "entry", "select", "e-role", ("system", "user", "assistant"), "EntryCreate"),
    _f("enabled", "entry", "bool", "e-enabled", api_model="EntryCreate"),
    _f("constant", "entry", "bool", "e-constant", api_model="EntryCreate"),
    _f("vectorised", "entry", "bool", "e-vectorised", api_model="EntryCreate"),
    _f("activation_kind", "entry", "derived", "e-activation-kind", ("constant", "selective", "vectorised")),
    _f("case_sensitive", "entry", "bool", "e-case-sensitive", api_model="EntryCreate"),
    _f("whole_word", "entry", "bool", "e-whole-word", api_model="EntryCreate"),
    _f("sticky_prompts", "entry", "int", "e-sticky", api_model="EntryCreate"),
    _f("cooldown_prompts", "entry", "int", "e-cooldown", api_model="EntryCreate"),
    _f("delay_prompts", "entry", "int", "e-delay", api_model="EntryCreate"),
)

#: Scope-assignment fields (LorebookScope model, P-040;
#: scopes.scope_to_dict). Edited from the editor's scope panel
#: against the lorebooks router scope endpoints.
SCOPE_FIELDS: tuple[EditorField, ...] = (
    _f("scope_kind", "scope", "select", "s-kind", ("global", "character", "persona", "chat"), "ScopeAssign"),
    _f("owner_id", "scope", "text", "s-owner", api_model="ScopeAssign"),
    _f("token_budget", "scope", "int_or_null", "s-budget", api_model="ScopeAssign"),
    _f("position", "scope", "int", "s-position", api_model="ScopeAssign"),
)

#: Preview controls (PreviewRequest -> preview_activation). The
#: preview panel is part of the editor: every control the engine
#: honours is reachable there, including the P-031 recursion
#: opt-in this slice wires through the API for the first time.
PREVIEW_FIELDS: tuple[EditorField, ...] = (
    _f("messages", "preview", "lines", "p-messages", api_model="PreviewRequest"),
    _f("scan_depth", "preview", "int_or_null", "p-depth", api_model="PreviewRequest"),
    _f("token_budget", "preview", "int_or_null", "p-budget", api_model="PreviewRequest"),
    _f("seed", "preview", "int_or_null", "p-seed", api_model="PreviewRequest"),
    _f("roll_context", "preview", "text", "p-roll-context", api_model="PreviewRequest"),
    _f("scan_mode", "preview", "select", "p-scan-mode", ("depth", "whole_chat"), "PreviewRequest"),
    _f("scan_external_context", "preview", "bool", "p-scan-external", api_model="PreviewRequest"),
    _f("external_context", "preview", "lines", "p-external", api_model="PreviewRequest"),
    _f("recursive_scan", "preview", "bool", "p-recursive", api_model="PreviewRequest"),
    _f("max_recursion_depth", "preview", "int_or_null", "p-max-recursion", api_model="PreviewRequest"),
    _f("vector_hit_ids", "preview", "keys", "p-vector-hits", api_model="PreviewRequest"),
    _f("vector_threshold", "preview", "int_or_null", "p-vector-threshold", api_model="PreviewRequest"),
    _f("vector_max_entries", "preview", "int_or_null", "p-vector-max", api_model="PreviewRequest"),
)

SURFACES: dict[str, tuple[EditorField, ...]] = {
    "book": BOOK_FIELDS,
    "entry": ENTRY_FIELDS,
    "scope": SCOPE_FIELDS,
    "preview": PREVIEW_FIELDS,
}


def field_names(surface: str) -> tuple[str, ...]:
    return tuple(f.name for f in SURFACES[surface])


def editor_schema() -> dict:
    """The census as JSON-shaped data (the editor-schema endpoint)."""
    return {
        "slice": "P-042",
        "surfaces": {
            surface: [
                {
                    "name": f.name,
                    "kind": f.kind,
                    "element_id": f.element_id,
                    "options": list(f.options),
                    "api_model": f.api_model,
                }
                for f in fields
            ]
            for surface, fields in SURFACES.items()
        },
    }
