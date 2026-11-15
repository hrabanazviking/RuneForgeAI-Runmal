"""Lorebook logic for the desktop shell (R-10) — Qt-free.

The lorebook editor is SCHEMA-DRIVEN: its book and entry forms
are generated from the engine's own editor census
(``GET /lorebooks/editor-schema``, P-042) — field order, kinds
and select options come from the census, and this module only
adds human labels and help per field name. One honest exception:
``activation_kind`` is a derived census field (computed from
``constant`` / ``vectorised``); the form shows it as read-only
words and a save never sends it.

Saves compose over the stored document, so fields the shell does
not know (forward-compatible entry data) survive verbatim — the
same open-bag discipline as R-09's presets. Scope assignments
(global / character / persona / chat) are their own mechanism,
distinct from the card editor's P-039 binding (R-08).

Preview verdicts (the activation preview and the layered
per-chat lore preview) are rendered as words here: every status
the engine reports gets a plain sentence. No Qt in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from runmal.desktop.client import RunmalClient
from runmal.desktop.client.errors import ClientError
from runmal.desktop.client.models import (
    LayerScopeSummary,
    LorebookView,
    LoreEntryView,
    LoreScopeView,
    PreviewRow,
)

# ------------------------------------------------------------- schema

KIND_TEXT = "text"
KIND_LONGTEXT = "longtext"
KIND_INT = "int"
KIND_INT_OR_NULL = "int_or_null"
KIND_KEYS = "keys"
KIND_BOOL = "bool"
KIND_SELECT = "select"

DERIVED_FIELDS = frozenset({"activation_kind"})

FIELD_LABELS: dict[str, str] = {
    # book
    "name": "Name",
    "description": "Description",
    "scan_depth": "Scan depth (recent messages examined)",
    "token_budget": "Token budget (blank = no limit)",
    "scan_mode": "Scan window",
    "scan_external_context": "Also scan external context",
    # entry
    "content": "Content (injected text)",
    "keys": "Keywords (one per line)",
    "secondary_keys": "Secondary keywords (one per line)",
    "selective_logic": "Secondary-key logic",
    "inclusion_group": "Inclusion group",
    "group_weight": "Group weight",
    "probability": "Probability (%)",
    "priority": "Priority (higher wins budget)",
    "position": "Injection position",
    "depth": "Depth (for at-depth position)",
    "role": "Injection role",
    "enabled": "Enabled",
    "constant": "Always on (constant)",
    "vectorised": "Vectorised (similarity match)",
    "activation_kind": "Activation kind",
    "case_sensitive": "Case-sensitive keywords",
    "whole_word": "Whole-word keywords",
    "sticky_prompts": "Sticky (prompts it stays active)",
    "cooldown_prompts": "Cooldown (prompts before it can refire)",
    "delay_prompts": "Delay (prompts before it can first fire)",
}

FIELD_HELP: dict[str, str] = {
    "scan_depth": "How many recent messages are scanned for keywords.",
    "scan_mode": "Depth = the last few messages; whole chat = everything.",
    "keys": "The entry fires when a message mentions one of these.",
    "secondary_keys": "Extra keywords combined by the secondary-key logic.",
    "selective_logic": "How secondary keywords gate the entry.",
    "constant": "Constant entries are always injected, keyword or not.",
    "vectorised": "Vectorised entries match by meaning, not exact words.",
    "activation_kind": "Derived from Always-on / Vectorised — shown, not edited.",
    "position": "Where the entry lands relative to the character's text.",
    "sticky_prompts": "Once fired, stays active for this many further prompts.",
    "cooldown_prompts": "After firing, cannot fire again for this many prompts.",
    "delay_prompts": "Cannot fire until this many prompts have passed.",
}


@dataclass(frozen=True)
class SchemaField:
    """One census field, ready for a generated form."""

    name: str
    kind: str
    options: list[str] = field(default_factory=list)
    derived: bool = False

    @property
    def label(self) -> str:
        return FIELD_LABELS.get(self.name, self.name.replace("_", " ").title())

    @property
    def help(self) -> str:
        return FIELD_HELP.get(self.name, "")


def schema_fields(schema: dict[str, Any], surface: str) -> list[SchemaField]:
    """The census fields for one surface ("book" / "entry"), in
    census order. An empty census yields no fields — the editor
    then honestly has nothing to generate."""
    surfaces = schema.get("surfaces") if isinstance(schema, dict) else None
    rows = surfaces.get(surface) if isinstance(surfaces, dict) else None
    out: list[SchemaField] = []
    for row in rows or []:
        if not isinstance(row, dict) or not row.get("name"):
            continue
        name = str(row["name"])
        kind = str(row.get("kind", KIND_TEXT) or KIND_TEXT)
        out.append(
            SchemaField(
                name=name,
                kind=kind,
                options=[str(o) for o in (row.get("options") or [])],
                derived=name in DERIVED_FIELDS or kind == "derived",
            )
        )
    return out


# ------------------------------------------------------- value codecs


def keys_to_text(keys: Any) -> str:
    if isinstance(keys, list):
        return "\n".join(str(k) for k in keys)
    return ""


def text_to_keys(text: str) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def activation_kind_words(values: dict[str, Any]) -> str:
    """The derived activation kind, in the engine's own terms."""
    if values.get("constant"):
        return "constant (always on)"
    if values.get("vectorised"):
        return "vectorised (similarity)"
    return "keyword"


def collect_fields(
    fields: list[SchemaField],
    values: dict[str, Any],
    base: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compose a save payload: start from the stored document
    (unknown fields survive verbatim), overlay every writable
    census field from ``values``, never send derived fields."""
    out: dict[str, Any] = dict(base or {})
    for f in fields:
        if f.derived:
            continue
        if f.name in values:
            out[f.name] = values[f.name]
    return out


def validate_book(values: dict[str, Any]) -> None:
    """Plain-words validation mirroring the book model's bounds."""
    if not str(values.get("name", "") or "").strip():
        raise ClientError("The lorebook needs a name.")
    depth = values.get("scan_depth")
    if depth is not None and (not isinstance(depth, int) or depth < 1):
        raise ClientError("Scan depth must be at least 1.")
    budget = values.get("token_budget")
    if budget is not None and (not isinstance(budget, int) or budget < 1):
        raise ClientError("Token budget must be at least 1, or blank.")


def validate_entry(values: dict[str, Any]) -> None:
    """Plain-words validation mirroring the entry model's bounds."""
    probability = values.get("probability")
    if probability is not None and (
        not isinstance(probability, int) or not 0 <= probability <= 100
    ):
        raise ClientError("Probability must be between 0 and 100.")
    for key in ("group_weight", "depth", "sticky_prompts",
                "cooldown_prompts", "delay_prompts"):
        value = values.get(key)
        if value is not None and (not isinstance(value, int) or value < 0):
            label = FIELD_LABELS.get(key, key)
            raise ClientError(f"{label} cannot be negative.")


# --------------------------------------------------------- scope words

SCOPE_KINDS = ["global", "character", "persona", "chat"]

SCOPE_LABELS = {
    "global": "Global (every chat)",
    "character": "Character (chats with this character)",
    "persona": "Persona (chats where you speak as this character)",
    "chat": "Chat (one chat only)",
}


def scope_words(scope: LoreScopeView, owner_name: str = "") -> str:
    label = SCOPE_LABELS.get(scope.scope_kind, scope.scope_kind)
    words = label
    if scope.owner_id:
        words += f" — {owner_name or scope.owner_id}"
    if scope.token_budget is not None:
        words += f" · budget {scope.token_budget} tokens"
    if scope.position:
        words += f" · position {scope.position}"
    return words


# ------------------------------------------------------- preview words

_STATUS_WORDS = {
    "included": "Included",
    "not_triggered": "Not triggered",
    "discarded": "Discarded",
    "disabled": "Disabled",
    "group_excluded": "Excluded by its inclusion group",
}


def verdict_words(row: PreviewRow) -> str:
    """One preview row as a plain sentence."""
    head = _STATUS_WORDS.get(row.status, row.status or "Unknown")
    name = row.name or row.entry_id or "entry"
    parts = [f"{name}: {head}"]
    if row.matched_primary:
        parts.append("matched " + ", ".join(row.matched_primary))
    if row.matched_secondary:
        parts.append("secondary " + ", ".join(row.matched_secondary))
    if row.scope:
        parts.append(f"scope: {row.scope}")
    if row.via:
        parts.append(f"via {row.via}")
    if row.tokens is not None and row.status in ("included", "discarded"):
        parts.append(f"{row.tokens} tokens")
    if row.status == "discarded" and row.discard_reason:
        parts.append(f"reason: {row.discard_reason}")
    return " · ".join(parts)


def layer_words(summary: LayerScopeSummary) -> str:
    """One layered-preview scope summary as a plain sentence."""
    label = SCOPE_LABELS.get(summary.scope, summary.scope)
    books = ", ".join(summary.books) if summary.books else "no books"
    parts = [f"{label}: {books}"]
    if summary.budget is not None:
        parts.append(f"budget {summary.budget}")
    parts.append(f"{summary.tokens_used} tokens used")
    parts.append(f"{summary.included} included")
    parts.append(f"{summary.discarded} discarded")
    return " · ".join(parts)


# ---------------------------------------------------------------- flow


class LoreFlow:
    """Lorebook operations over the typed client (R-10)."""

    def __init__(self, client: RunmalClient) -> None:
        self._client = client

    # ------------------------------------------------------------ books

    def schema(self) -> dict[str, Any]:
        return self._client.lorebook_editor_schema()

    def list_books(self) -> list[LorebookView]:
        return self._client.list_lorebook_views()

    def save_book(
        self,
        book_id: str | None,
        fields: list[SchemaField],
        values: dict[str, Any],
        base: LorebookView | None,
    ) -> LorebookView:
        validate_book(values)
        payload = collect_fields(
            fields, values, base.fields_dict() if base else None
        )
        if book_id is None:
            return self._client.create_lorebook(payload)
        changed = {
            key: value
            for key, value in payload.items()
            if base is None or base.fields_dict().get(key) != value
        }
        if not changed:
            assert base is not None
            return base
        return self._client.update_lorebook(book_id, changed)

    def delete_book(self, book_id: str) -> bool:
        return self._client.delete_lorebook(book_id)

    def import_book(self, document: dict[str, Any]) -> LorebookView:
        if not isinstance(document, dict) or not document:
            raise ClientError("That file is not a lorebook document.")
        return self._client.import_lorebook(document)

    def export_book(self, book_id: str) -> dict[str, Any]:
        return self._client.export_lorebook(book_id)

    # ---------------------------------------------------------- entries

    def list_entries(self, book_id: str) -> list[LoreEntryView]:
        return self._client.list_lore_entries(book_id)

    def save_entry(
        self,
        book_id: str,
        entry_id: str | None,
        fields: list[SchemaField],
        values: dict[str, Any],
        base: LoreEntryView | None,
    ) -> LoreEntryView:
        validate_entry(values)
        payload = collect_fields(
            fields, values, base.fields_dict() if base else None
        )
        # The stored document carries identity/read-only keys the
        # create/update models do not accept; never send them.
        for key in ("id", "lorebook_id", "created_at", "updated_at",
                    "activation_kind"):
            payload.pop(key, None)
        if entry_id is None:
            return self._client.create_lore_entry(book_id, payload)
        changed = {
            key: value
            for key, value in payload.items()
            if base is None or base.fields_dict().get(key) != value
        }
        if not changed:
            assert base is not None
            return base
        return self._client.update_lore_entry(book_id, entry_id, changed)

    def delete_entry(self, book_id: str, entry_id: str) -> bool:
        return self._client.delete_lore_entry(book_id, entry_id)

    # ----------------------------------------------------------- scopes

    def list_scopes(self, book_id: str) -> list[LoreScopeView]:
        return self._client.list_book_scopes(book_id)

    def assign_scope(
        self,
        book_id: str,
        scope_kind: str,
        owner_id: str | None,
        *,
        token_budget: int | None = None,
        position: int = 0,
    ) -> LoreScopeView:
        if scope_kind not in SCOPE_KINDS:
            raise ClientError(f"Unknown scope kind: {scope_kind}")
        if scope_kind != "global" and not owner_id:
            raise ClientError("That scope kind needs an owner.")
        return self._client.assign_book_scope(
            book_id,
            scope_kind,
            owner_id,
            token_budget=token_budget,
            position=position,
        )

    def unassign_scope(
        self, book_id: str, scope_kind: str, owner_id: str | None
    ) -> bool:
        return self._client.unassign_book_scope(book_id, scope_kind, owner_id)

    # ---------------------------------------------------------- preview

    def preview_book(
        self, book_id: str, messages: list[str]
    ) -> list[PreviewRow]:
        return self._client.preview_lorebook(book_id, messages)

    def preview_chat(
        self, chat_id: str, messages: list[str]
    ) -> tuple[list[PreviewRow], list[LayerScopeSummary], list[str]]:
        if not chat_id:
            raise ClientError("Open a chat before previewing its lore.")
        return self._client.preview_chat_lore(chat_id, messages)
