"""Characters logic (R-08) — Qt-free view-model layer.

The Characters *widgets* live in ``runmal.desktop.window``; every
decision they render lives here, so the whole library + editor is
unit-testable on hosts with no PySide6 (the R-04…R-07 pattern).
This module talks to the engine ONLY through ``RunmalClient`` —
no engine imports, no SQL, no prompt logic.

Roads composed here, honestly (no new engine routes in R-08):

- **Full card read.** ``GET /characters/{id}`` returns only the
  summary row; the whole stored card rides the version road
  (``GET /characters/{id}/versions/{n}`` → ``card``). The client
  joins the two; this flow never sees a partial card.
- **Card save.** The editor overlays its fields onto the STORED
  card dict (at whichever level — ``data`` or flat — the stored
  shape keeps them), so unknown-but-valid fields and extensions
  survive untouched (INV-009), then PATCHes the result. Tags are
  saved through the library organisation road instead (it keeps
  the tag rows and the card's own tag list in step), after the
  card PATCH, and only when they changed.
- **Version restore.** There is no restore-version route; a
  restore is the version's stored card PATCHed back as the
  character's current card — the same lossless composition
  R-07's Regenerate uses for its missing route.
- **Export.** There is no character-export route; export is the
  stored card dict (read via the version road) serialised to a
  JSON file by the caller — exactly the bytes a re-import reads.
- **Delete is the engine's soft delete** (S303): the row and its
  assets are retained and ``restore`` undoes it. The window says
  so, in those words.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any

from runmal.desktop.client import RunmalClient
from runmal.desktop.client.errors import ClientError
from runmal.desktop.client.models import (
    AssetView,
    BindingView,
    CharacterCardView,
    CharacterSummary,
    LibraryCardView,
    LorebookSummary,
    OrganisationView,
    TagCountView,
    VersionHistoryView,
    card_data_of,
)

#: Card text fields the editor edits, in dialog order. ``name``
#: travels separately (it is also the row's name), ``tags`` travel
#: the organisation road, greetings are lists, and
#: ``character_book`` is displayed + bound, not text-edited (the
#: lorebook entry editor is R-10).
CARD_TEXT_FIELDS = (
    "description",
    "personality",
    "scenario",
    "system_prompt",
    "mes_example",
    "post_history_instructions",
    "first_mes",
    "creator_notes",
    "creator",
    "character_version",
    "nickname",
)


def parse_tags(text: str) -> list[str]:
    """Parse the editor's tag line: comma- or newline-separated,
    trimmed, empties dropped, duplicates removed keeping order."""
    out: list[str] = []
    for chunk in (text or "").replace("\n", ",").split(","):
        tag = chunk.strip()
        if tag and tag not in out:
            out.append(tag)
    return out


def tags_text(tags: list[str]) -> str:
    return ", ".join(tags)


def apply_card_edits(
    raw_card: dict[str, Any], edits: dict[str, Any]
) -> dict[str, Any]:
    """Overlay editor fields onto a stored card dict (pure).

    Fields land at the level the stored shape keeps them —
    ``data`` for the wrapped v2/v3 shape, top level for flat
    cards — and ONLY the named fields change: every other key,
    at either level, is carried over verbatim (INV-009). The
    input dict is never mutated."""
    result = copy.deepcopy(raw_card)
    data = result.get("data")
    level = data if isinstance(data, dict) else result
    for key, value in edits.items():
        level[key] = copy.deepcopy(value)
    return result


def blank_card_edits() -> dict[str, Any]:
    """The editor's field bag for a character made from scratch:
    every edited field present and empty, so a create and a save
    share one shape."""
    edits: dict[str, Any] = {name: "" for name in CARD_TEXT_FIELDS}
    edits["alternate_greetings"] = []
    edits["group_only_greetings"] = []
    return edits


@dataclass(frozen=True)
class EditorBundle:
    """Everything the card editor dialog shows for one character,
    fetched as one unit off the GUI thread."""

    card: CharacterCardView
    organisation: OrganisationView
    binding: BindingView
    book: dict[str, Any]
    assets: list[AssetView] = field(default_factory=list)
    versions: VersionHistoryView | None = None
    lorebooks: list[LorebookSummary] = field(default_factory=list)

    @property
    def book_entry_count(self) -> int:
        entries = self.book.get("entries")
        if isinstance(entries, list):
            return len(entries)
        return self.card.book_entry_count

    @property
    def book_label(self) -> str:
        count = self.book_entry_count
        if count == 0:
            return "Character book: no entries travel with this card."
        return f"Character book: {count} entr(ies) travel with this card."


@dataclass(frozen=True)
class BulkImportOutcome:
    """The library bulk report (P-022) collapsed to verdicts:
    totals + one line per file. Refusals are data, with reasons."""

    total: int = 0
    accepted: int = 0
    repaired: int = 0
    refused: int = 0
    skipped: int = 0
    lines: list[str] = field(default_factory=list)
    created_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_report(cls, report: dict[str, Any]) -> BulkImportOutcome:
        totals = report.get("totals")
        totals = totals if isinstance(totals, dict) else {}

        def _n(key: str) -> int:
            value = totals.get(key)
            return value if isinstance(value, int) else 0

        lines: list[str] = []
        created: list[str] = []
        entries = report.get("entries")
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                name = str(
                    entry.get("filename") or entry.get("relpath") or "file"
                )
                outcome = str(entry.get("outcome") or entry.get("status") or "")
                if entry.get("created_id"):
                    created.append(str(entry["created_id"]))
                    shown = entry.get("created_name") or entry["created_id"]
                    lines.append(f"{name}: imported as “{shown}”")
                elif entry.get("duplicate_of"):
                    lines.append(f"{name}: already in the library (exact duplicate)")
                elif outcome:
                    reason = str(entry.get("reason") or entry.get("detail") or "")
                    lines.append(
                        f"{name}: {outcome}" + (f" — {reason}" if reason else "")
                    )
        return cls(
            total=_n("total_seen") or _n("seen"),
            accepted=_n("accepted"),
            repaired=_n("repaired"),
            refused=_n("refused"),
            skipped=_n("skipped") or _n("total_skipped"),
            lines=lines,
            created_ids=created,
        )

    @property
    def status_words(self) -> str:
        landed = self.accepted + self.repaired
        words = f"Import finished: {landed} character(s) landed"
        if self.refused:
            words += f", {self.refused} refused"
        if self.skipped:
            words += f", {self.skipped} skipped"
        return words + "."


class CharacterFlow:
    """Stateful driver for the Characters library + editor, over
    one client. Holds no card text beyond what a call returns."""

    def __init__(self, client: RunmalClient) -> None:
        self._client = client

    # ----------------------------------------------------------- library

    def library(
        self,
        *,
        q: str = "",
        tags: list[str] | None = None,
        tag_mode: str = "any",
        favourites_only: bool = False,
        sort: str = "name",
    ) -> tuple[int, list[LibraryCardView]]:
        return self._client.list_library_cards(
            q=q,
            tags=tags,
            tag_mode=tag_mode,
            favourites_only=favourites_only,
            sort=sort,
        )

    def library_tags(self) -> list[TagCountView]:
        return self._client.list_library_tags()

    def set_favourite(
        self, character_id: str, is_favourite: bool
    ) -> OrganisationView:
        return self._client.set_character_favourite(character_id, is_favourite)

    def organisation(self, character_id: str) -> OrganisationView:
        return self._client.get_organisation(character_id)

    # ------------------------------------------------------------- editor

    def open_editor(self, character_id: str) -> EditorBundle:
        """Fetch everything the editor dialog renders, as one unit."""
        card = self._client.get_character_card(character_id)
        organisation = self._client.get_organisation(character_id)
        binding = self._client.get_lorebook_binding(character_id)
        book = self._client.get_character_book(character_id)
        assets = self._client.list_assets(character_id)
        versions = self._client.get_character_versions(character_id)
        lorebooks = self._client.list_lorebooks()
        return EditorBundle(
            card=card,
            organisation=organisation,
            binding=binding,
            book=book,
            assets=assets,
            versions=versions,
            lorebooks=lorebooks,
        )

    def create_character(
        self, edits: dict[str, Any], tags: list[str]
    ) -> CharacterSummary:
        """Create a character from scratch: the editor's fields as
        a flat card dict (the engine's importer normalises it),
        then its tags through the organisation road."""
        name = str(edits.get("name") or "").strip()
        if not name:
            raise ClientError("the character needs a name")
        card: dict[str, Any] = {"name": name}
        for key in CARD_TEXT_FIELDS:
            card[key] = edits.get(key, "")
        card["alternate_greetings"] = list(edits.get("alternate_greetings") or [])
        card["group_only_greetings"] = list(
            edits.get("group_only_greetings") or []
        )
        card["tags"] = list(tags)
        created = self._client.create_character(card, name=name)
        if tags:
            self._client.set_character_tags(created.id, list(tags))
        return created

    def save_character(
        self, bundle_card: CharacterCardView, edits: dict[str, Any], tags: list[str]
    ) -> CharacterCardView:
        """Save the editor's changes: overlay onto the stored card
        (unknown fields survive), PATCH, then the tags through
        the organisation road when they changed. Returns the
        re-read card, so the dialog shows what the engine stored."""
        name = str(edits.get("name") or "").strip()
        if not name:
            raise ClientError("the character needs a name")
        overlay = {
            key: edits.get(key, getattr(bundle_card, key))
            for key in CARD_TEXT_FIELDS
        }
        overlay["alternate_greetings"] = list(
            edits.get("alternate_greetings") or []
        )
        overlay["group_only_greetings"] = list(
            edits.get("group_only_greetings")
            if edits.get("group_only_greetings") is not None
            else bundle_card.group_only_greetings
        )
        new_card = apply_card_edits(bundle_card.raw_card, overlay)
        self._client.update_character(bundle_card.id, new_card, name=name)
        if list(tags) != list(bundle_card.tags):
            self._client.set_character_tags(bundle_card.id, list(tags))
        return self._client.get_character_card(bundle_card.id)

    # ------------------------------------------------------ avatar/assets

    def set_avatar(
        self, character_id: str, filename: str, data: bytes
    ) -> str:
        if not data:
            raise ClientError("that avatar file is empty")
        return self._client.upload_avatar(character_id, filename, data)

    def avatar_bytes(self, character_id: str) -> tuple[bytes, str] | None:
        return self._client.get_avatar_bytes(character_id)

    def assets(self, character_id: str) -> list[AssetView]:
        return self._client.list_assets(character_id)

    def add_asset(
        self, character_id: str, filename: str, data: bytes
    ) -> AssetView:
        if not data:
            raise ClientError("that asset file is empty")
        return self._client.upload_asset(
            character_id, filename, data, name=filename
        )

    # ------------------------------------------------------------ versions

    def versions(self, character_id: str) -> VersionHistoryView:
        return self._client.get_character_versions(character_id)

    def restore_version(
        self, character_id: str, version_no: int
    ) -> CharacterCardView:
        """Restore one version as the character's current card
        (composed: the version's stored card, PATCHed back — no
        restore-version route exists). The character keeps its
        id, avatar, assets, tags and binding; only the card's
        fields go back."""
        card = self._client.get_character_version_card(character_id, version_no)
        if not card:
            raise ClientError(f"version {version_no} has no stored card")
        data = card_data_of(card)
        name = str(data.get("name") or "") or None
        self._client.update_character(character_id, card, name=name)
        return self._client.get_character_card(character_id)

    # ------------------------------------------------- duplicate / delete

    def duplicate(self, character_id: str) -> CharacterSummary:
        return self._client.duplicate_character(character_id)

    def delete(self, character_id: str) -> bool:
        """The engine's soft delete: hidden but retained, and
        :meth:`undo_delete` brings the character straight back."""
        return self._client.delete_character(character_id)

    def undo_delete(self, character_id: str) -> CharacterSummary:
        return self._client.restore_character(character_id)

    # ------------------------------------------------------ import/export

    def export_text(self, character_id: str) -> str:
        """The character's portable card as JSON text: the stored
        card dict serialised — exactly what a re-import reads
        (INV-025). No export route exists; none is needed."""
        card = self._client.get_character_card(character_id)
        if not card.raw_card:
            raise ClientError("that character has no stored card to export")
        return json.dumps(card.raw_card, indent=2, ensure_ascii=False)

    def export_filename(self, card: CharacterCardView) -> str:
        slug = "".join(
            ch if ch.isalnum() or ch in "-_" else "-" for ch in (card.name or "")
        ).strip("-")
        return f"runmal-character-{slug or card.id}.json"

    def import_files(
        self, files: list[tuple[str, bytes]]
    ) -> BulkImportOutcome:
        if not files:
            raise ClientError("pick at least one card file to import")
        report = self._client.import_character_files(files)
        return BulkImportOutcome.from_report(report)

    # -------------------------------------------------------------- binding

    def bind(
        self, character_id: str, lorebook_id: str, precedence: str = ""
    ) -> BindingView:
        if not lorebook_id:
            raise ClientError("pick a lorebook to bind first")
        return self._client.bind_lorebook(
            character_id, lorebook_id, precedence=precedence or None
        )

    def unbind(self, character_id: str) -> bool:
        return self._client.unbind_lorebook(character_id)

    def set_precedence(
        self, character_id: str, precedence: str
    ) -> BindingView:
        return self._client.set_binding_precedence(character_id, precedence)


__all__ = [
    "CARD_TEXT_FIELDS",
    "BulkImportOutcome",
    "CharacterFlow",
    "EditorBundle",
    "apply_card_edits",
    "blank_card_edits",
    "parse_tags",
    "tags_text",
]
