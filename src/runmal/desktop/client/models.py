"""Typed view-models for the desktop client layer (R-04).

Each dataclass mirrors exactly one engine response shape (the same
dicts the engine routers return and the engine tests pin), parsed
tolerantly: unknown fields are ignored, missing optional fields fall
back to empty values, so an additive engine change never breaks the
shell. Parsing never raises on shape drift except where a field is
load-bearing (ids), and even there it degrades to an empty string
rather than crashing a widget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class HealthStatus:
    """``GET /healthz`` — public, unauthenticated liveness."""

    ok: bool
    status: str = ""
    version: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> HealthStatus:
        status = str(payload.get("status", ""))
        return cls(
            ok=status == "ok",
            status=status,
            version=str(payload.get("version", "")),
        )


@dataclass(frozen=True)
class BackendProfile:
    """One row of ``GET /api/v1/backend-profiles`` (R-02 shape).

    Secret *values* never exist in this shape — only the
    ``has_*_secret`` booleans and opaque references (INV-023).
    """

    id: str
    name: str
    chat_backend: str = ""
    chat_model: str = ""
    embedding_backend: str = ""
    embedding_model: str = ""
    has_chat_secret: bool = False
    has_embedding_secret: bool = False
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BackendProfile:
        config = payload.get("config")
        return cls(
            id=str(payload.get("id", "")),
            name=str(payload.get("name", "")),
            chat_backend=str(payload.get("chat_backend", "")),
            chat_model=str(payload.get("chat_model", "")),
            embedding_backend=str(payload.get("embedding_backend", "")),
            embedding_model=str(payload.get("embedding_model", "")),
            has_chat_secret=bool(payload.get("has_chat_secret", False)),
            has_embedding_secret=bool(payload.get("has_embedding_secret", False)),
            config=config if isinstance(config, dict) else {},
        )

    @property
    def label(self) -> str:
        """One-line human label: name, backend kind, model."""
        parts = [self.name or self.id]
        if self.chat_backend:
            parts.append(self.chat_backend)
        if self.chat_model:
            parts.append(self.chat_model)
        return " · ".join(parts)


@dataclass(frozen=True)
class ChatSummary:
    """One row of ``GET /api/v1/chats`` (chats ``chat_to_dict``)."""

    id: str
    title: str = ""
    character_id: str | None = None
    backend_profile_id: str | None = None
    preset_id: str | None = None
    message_count: int = 0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ChatSummary:
        count = payload.get("message_count", 0)
        return cls(
            id=str(payload.get("id", "")),
            title=str(payload.get("title", "")),
            character_id=payload.get("character_id") or None,
            backend_profile_id=payload.get("backend_profile_id") or None,
            preset_id=payload.get("preset_id") or None,
            message_count=count if isinstance(count, int) else 0,
        )


@dataclass(frozen=True)
class CharacterSummary:
    """One row of ``GET /api/v1/characters`` (``character_to_dict``)."""

    id: str
    name: str = ""
    has_avatar: bool = False
    version_no: int = 1
    lineage_id: str = ""
    avatar_asset: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CharacterSummary:
        version_no = payload.get("version_no", 1)
        return cls(
            id=str(payload.get("id", "")),
            name=str(payload.get("name", "")),
            has_avatar=bool(payload.get("has_avatar", False)),
            version_no=version_no if isinstance(version_no, int) else 1,
            lineage_id=str(payload.get("lineage_id", "") or ""),
            avatar_asset=payload.get("avatar_asset") or None,
        )


def card_data_of(card: dict[str, Any]) -> dict[str, Any]:
    """The field level of a stored card dict (R-08).

    Stored cards are the exporter's v2/v3 shape — fields live
    under ``data`` — but flat cards (v1-style, or a caller's raw
    dict) carry them at the top level. This returns the mapping
    that holds the card's fields, tolerantly."""
    data = card.get("data")
    if isinstance(data, dict):
        return data
    return card


def _str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if isinstance(v, str)]
    return []


@dataclass(frozen=True)
class CharacterCardView:
    """One character's FULL card (R-08), read through the roads
    that exist: the summary row (``GET /characters/{id}``) joined
    with the stored card carried by the version road
    (``GET /characters/{id}/versions/{n}`` — the only existing
    road that returns the whole card; there is no card-export
    route). ``raw_card`` is the stored dict verbatim, so an edit
    can overlay fields on it and unknown-but-valid fields survive
    the round trip (INV-009)."""

    id: str
    name: str = ""
    version_no: int = 1
    lineage_id: str = ""
    has_avatar: bool = False
    avatar_asset: str | None = None
    description: str = ""
    personality: str = ""
    scenario: str = ""
    system_prompt: str = ""
    mes_example: str = ""
    post_history_instructions: str = ""
    first_mes: str = ""
    alternate_greetings: list[str] = field(default_factory=list)
    creator_notes: str = ""
    tags: list[str] = field(default_factory=list)
    creator: str = ""
    character_version: str = ""
    nickname: str = ""
    group_only_greetings: list[str] = field(default_factory=list)
    character_book: dict[str, Any] = field(default_factory=dict)
    raw_card: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_parts(
        cls, summary: CharacterSummary, card: dict[str, Any]
    ) -> CharacterCardView:
        data = card_data_of(card)
        book = data.get("character_book")
        return cls(
            id=summary.id,
            name=str(data.get("name") or summary.name or ""),
            version_no=summary.version_no,
            lineage_id=summary.lineage_id,
            has_avatar=summary.has_avatar,
            avatar_asset=summary.avatar_asset,
            description=str(data.get("description") or ""),
            personality=str(data.get("personality") or ""),
            scenario=str(data.get("scenario") or ""),
            system_prompt=str(data.get("system_prompt") or ""),
            mes_example=str(data.get("mes_example") or ""),
            post_history_instructions=str(
                data.get("post_history_instructions") or ""
            ),
            first_mes=str(data.get("first_mes") or ""),
            alternate_greetings=_str_list(data.get("alternate_greetings")),
            creator_notes=str(data.get("creator_notes") or ""),
            tags=_str_list(data.get("tags")),
            creator=str(data.get("creator") or ""),
            character_version=str(data.get("character_version") or ""),
            nickname=str(data.get("nickname") or ""),
            group_only_greetings=_str_list(data.get("group_only_greetings")),
            character_book=book if isinstance(book, dict) else {},
            raw_card=card,
        )

    @property
    def book_entry_count(self) -> int:
        entries = self.character_book.get("entries")
        return len(entries) if isinstance(entries, list) else 0


def _int_or(value: Any, fallback: int) -> int:
    return value if isinstance(value, int) else fallback


@dataclass(frozen=True)
class LibraryCardView:
    """One row of ``GET /api/v1/library/cards`` (P-024): the
    library's own projection — name, tags, favourite, avatar."""

    id: str
    name: str = ""
    created_at: str = ""
    has_avatar: bool = False
    tags: list[str] = field(default_factory=list)
    is_favourite: bool = False

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> LibraryCardView:
        return cls(
            id=str(payload.get("id", "")),
            name=str(payload.get("name", "")),
            created_at=str(payload.get("created_at", "")),
            has_avatar=bool(payload.get("has_avatar", False)),
            tags=_str_list(payload.get("tags")),
            is_favourite=bool(payload.get("is_favourite", False)),
        )

    @property
    def label(self) -> str:
        """One dock line: name, favourite as a WORD, tags, avatar."""
        parts = [self.name or self.id]
        if self.is_favourite:
            parts.append("★ favourite")
        if self.tags:
            parts.append("tags: " + ", ".join(self.tags))
        if self.has_avatar:
            parts.append("avatar")
        return " · ".join(parts)


@dataclass(frozen=True)
class TagCountView:
    """One row of ``GET /api/v1/library/tags`` (P-024)."""

    tag: str
    tag_key: str = ""
    count: int = 0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TagCountView:
        return cls(
            tag=str(payload.get("tag", "")),
            tag_key=str(payload.get("tag_key", "")),
            count=_int_or(payload.get("count"), 0),
        )


@dataclass(frozen=True)
class OrganisationView:
    """``GET /api/v1/library/cards/{id}/organisation`` (P-024):
    the character's tags + favourite flag as the library keeps
    them (rows kept in step with the card's own tag list)."""

    character_id: str
    name: str = ""
    tags: list[str] = field(default_factory=list)
    is_favourite: bool = False

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> OrganisationView:
        return cls(
            character_id=str(payload.get("character_id", "")),
            name=str(payload.get("name", "")),
            tags=_str_list(payload.get("tags")),
            is_favourite=bool(payload.get("is_favourite", False)),
        )


@dataclass(frozen=True)
class CharacterVersionView:
    """One row of a character's version history (P-025)."""

    character_id: str
    version_no: int = 1
    lineage_id: str = ""
    name: str = ""
    content_hash: str = ""
    created_at: str = ""
    deleted: bool = False
    is_latest: bool = False

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CharacterVersionView:
        return cls(
            character_id=str(payload.get("character_id", "")),
            version_no=_int_or(payload.get("version_no"), 1),
            lineage_id=str(payload.get("lineage_id", "")),
            name=str(payload.get("name", "")),
            content_hash=str(payload.get("content_hash", "")),
            created_at=str(payload.get("created_at") or ""),
            deleted=bool(payload.get("deleted", False)),
            is_latest=bool(payload.get("is_latest", False)),
        )

    @property
    def label(self) -> str:
        words = f"v{self.version_no}"
        if self.is_latest:
            words += " · latest"
        if self.deleted:
            words += " · deleted"
        if self.created_at:
            words += f" · {self.created_at}"
        return words


@dataclass(frozen=True)
class VersionHistoryView:
    """``GET /api/v1/characters/{id}/versions`` (P-025)."""

    character_id: str
    lineage_id: str = ""
    name: str = ""
    latest_version_no: int = 1
    versions: list[CharacterVersionView] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> VersionHistoryView:
        rows = payload.get("versions")
        return cls(
            character_id=str(payload.get("character_id", "")),
            lineage_id=str(payload.get("lineage_id", "")),
            name=str(payload.get("name", "")),
            latest_version_no=_int_or(payload.get("latest_version_no"), 1),
            versions=[
                CharacterVersionView.from_dict(r)
                for r in rows
                if isinstance(r, dict)
            ]
            if isinstance(rows, list)
            else [],
        )


@dataclass(frozen=True)
class AssetView:
    """One row of ``GET /api/v1/characters/{id}/assets`` (P-023).
    Metadata only — bytes travel the content/thumbnail roads."""

    id: str
    character_id: str = ""
    kind: str = ""
    name: str = ""
    source_type: str = ""
    status: str = ""
    format: str = ""
    media_type: str = ""
    width: int | None = None
    height: int | None = None
    byte_size: int = 0
    has_thumbnail: bool = False
    thumbnail_status: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AssetView:
        width = payload.get("width")
        height = payload.get("height")
        return cls(
            id=str(payload.get("id", "")),
            character_id=str(payload.get("character_id", "")),
            kind=str(payload.get("kind", "")),
            name=str(payload.get("name", "")),
            source_type=str(payload.get("source_type", "")),
            status=str(payload.get("status", "")),
            format=str(payload.get("format", "")),
            media_type=str(payload.get("media_type", "")),
            width=width if isinstance(width, int) else None,
            height=height if isinstance(height, int) else None,
            byte_size=_int_or(payload.get("byte_size"), 0),
            has_thumbnail=bool(payload.get("has_thumbnail", False)),
            thumbnail_status=str(payload.get("thumbnail_status", "")),
        )

    @property
    def label(self) -> str:
        parts = [self.name or self.id]
        if self.kind:
            parts.append(self.kind)
        if self.status:
            parts.append(self.status)
        if self.width and self.height:
            parts.append(f"{self.width}×{self.height}")
        if self.byte_size:
            parts.append(f"{self.byte_size} bytes")
        return " · ".join(parts)


@dataclass(frozen=True)
class LorebookSummary:
    """One row of ``GET /api/v1/lorebooks`` (identity fields the
    binding picker needs; the full lorebook editor is R-10)."""

    id: str
    name: str = ""
    entry_count: int = 0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> LorebookSummary:
        return cls(
            id=str(payload.get("id", "")),
            name=str(payload.get("name", "")),
            entry_count=_int_or(payload.get("entry_count"), 0),
        )


@dataclass(frozen=True)
class BindingView:
    """``GET /api/v1/characters/{id}/lorebook-binding`` (P-039):
    bound or honestly unbound, with the book's name when known."""

    bound: bool
    character_id: str = ""
    lorebook_id: str | None = None
    precedence: str | None = None
    entry_count: int = 0
    lorebook_name: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BindingView:
        book = payload.get("lorebook")
        return cls(
            bound=bool(payload.get("bound", False)),
            character_id=str(payload.get("character_id", "")),
            lorebook_id=payload.get("lorebook_id") or None,
            precedence=payload.get("precedence") or None,
            entry_count=_int_or(payload.get("entry_count"), 0),
            lorebook_name=(
                str(book.get("name", ""))
                if isinstance(book, dict)
                else ""
            ),
        )

    @property
    def label(self) -> str:
        if not self.bound:
            return "No lorebook bound to this character."
        name = self.lorebook_name or self.lorebook_id or "lorebook"
        words = f"Bound lorebook: {name} · {self.entry_count} entr(ies)"
        if self.precedence:
            words += f" · precedence: {self.precedence}"
        return words + "."


@dataclass(frozen=True)
class FirstRunState:
    """First-run detection result (R-04; consumed by the R-05 wizard).

    First run means: no backend profile exists AND no character
    exists — the exact empty state every fresh install starts in
    (plan §1.3.4). Chats deliberately do not count: the old shell
    auto-created character-less chats, so a stray chat must not hide
    the unconfigured state.
    """

    is_first_run: bool
    profile_count: int
    character_count: int

    @property
    def label(self) -> str:
        if self.is_first_run:
            return "First run — nothing configured yet"
        return (
            f"Configured — {self.profile_count} backend profile(s), "
            f"{self.character_count} character(s)"
        )


def detect_first_run(
    profiles: list[BackendProfile], characters: list[CharacterSummary]
) -> FirstRunState:
    """Pure first-run rule over already-fetched lists (unit-testable
    without any HTTP)."""
    return FirstRunState(
        is_first_run=not profiles and not characters,
        profile_count=len(profiles),
        character_count=len(characters),
    )


@dataclass(frozen=True)
class MessageView:
    """One row of ``GET /api/v1/chats/{id}/messages`` (R-05; the
    swipe deck + pin state joined in R-07 — the engine's
    ``message_to_dict`` always carries them)."""

    id: str
    role: str = ""
    content: str = ""
    speaker_name: str | None = None
    swipes: list[str] = field(default_factory=list)
    swipe_id: int = 0
    pinned: bool = False

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> MessageView:
        deck = payload.get("swipes")
        swipes = (
            [str(s) for s in deck if isinstance(s, str)]
            if isinstance(deck, list)
            else []
        )
        swipe_id = payload.get("swipe_id", 0)
        return cls(
            id=str(payload.get("id", "")),
            role=str(payload.get("role", "")),
            content=str(payload.get("content", "")),
            speaker_name=payload.get("speaker_name") or None,
            swipes=swipes,
            swipe_id=swipe_id if isinstance(swipe_id, int) else 0,
            pinned=bool(payload.get("pinned", False)),
        )

    @property
    def swipe_count(self) -> int:
        """How many alternates this message's deck holds (the
        active content always counts as one, even before the
        engine materialises a deck)."""
        return max(len(self.swipes), 1)


@dataclass(frozen=True)
class AuthorsNoteView:
    """``GET /api/v1/chats/{id}/authors-note`` (P-056 shape: all
    five keys, always)."""

    text: str = ""
    depth: int = 4
    frequency: int = 1
    enabled: bool = True
    role: str = "system"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AuthorsNoteView:
        depth = payload.get("depth", 4)
        frequency = payload.get("frequency", 1)
        return cls(
            text=str(payload.get("text", "")),
            depth=depth if isinstance(depth, int) else 4,
            frequency=frequency if isinstance(frequency, int) else 1,
            enabled=bool(payload.get("enabled", True)),
            role=str(payload.get("role", "system")),
        )


@dataclass(frozen=True)
class CheckpointView:
    """One row of ``GET /api/v1/chats/{id}/checkpoints`` (P-067
    metadata projection: never message bodies)."""

    id: str
    name: str = ""
    created_at: str = ""
    message_count: int = 0
    chat_title: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CheckpointView:
        count = payload.get("message_count", 0)
        return cls(
            id=str(payload.get("id", "")),
            name=str(payload.get("name", "")),
            created_at=str(payload.get("created_at", "")),
            message_count=count if isinstance(count, int) else 0,
            chat_title=str(payload.get("chat_title", "")),
        )


@dataclass(frozen=True)
class UndoEntryView:
    """One row of a chat's undo journal (P-076 metadata projection:
    operation + detail words, never payloads)."""

    id: str
    operation: str = ""
    detail: str = ""
    created_at: str = ""
    message_count: int = 0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> UndoEntryView:
        count = payload.get("message_count", 0)
        return cls(
            id=str(payload.get("id", "")),
            operation=str(payload.get("operation", "")),
            detail=str(payload.get("detail", "")),
            created_at=str(payload.get("created_at", "")),
            message_count=count if isinstance(count, int) else 0,
        )

    @property
    def label(self) -> str:
        """One-line human label: what would be undone."""
        words = self.operation or "operation"
        if self.detail:
            words += f" — {self.detail}"
        return words


@dataclass(frozen=True)
class SearchHitView:
    """One result row of ``GET /api/v1/chats/search`` (P-072):
    which chat, which message, and the matched snippet."""

    chat_id: str
    chat_title: str = ""
    message_id: str = ""
    role: str = ""
    snippet: str = ""
    ordinal: int = 0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SearchHitView:
        ordinal = payload.get("ordinal", 0)
        return cls(
            chat_id=str(payload.get("chat_id", "")),
            chat_title=str(payload.get("chat_title", "")),
            message_id=str(payload.get("message_id", "")),
            role=str(payload.get("role", "")),
            snippet=str(payload.get("snippet", "")),
            ordinal=ordinal if isinstance(ordinal, int) else 0,
        )


@dataclass(frozen=True)
class GeneratedReply:
    """One collected ``POST /api/v1/generate`` SSE stream (R-05).

    The stream's token events are concatenated by the client; the
    backend key and generation mode come from the response headers
    the generation router sets (``X-Backend-Key`` /
    ``X-Generation-Mode``), so a caller can say honestly *which*
    backend answered and whether the prompt was composed.
    """

    text: str
    backend_key: str = ""
    mode: str = ""


@dataclass(frozen=True)
class ImportOutcome:
    """The wizard-relevant verdict of ``POST /api/v1/library/imports``.

    The bulk report accounts for every file; the wizard imports ONE
    card file, so this view collapses the report to: did a character
    land (created, repaired-in, or an exact duplicate of an existing
    one), which one, and a plain reason when nothing landed. File
    contents never appear here (the report never carries them).
    """

    ok: bool
    character_id: str = ""
    character_name: str = ""
    reason: str = ""

    @classmethod
    def from_report(cls, payload: dict[str, Any]) -> ImportOutcome:
        entries = payload.get("entries")
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                if entry.get("detected_kind") not in (None, "card"):
                    continue
                created_id = entry.get("created_id")
                if created_id:
                    return cls(
                        ok=True,
                        character_id=str(created_id),
                        character_name=str(entry.get("created_name") or ""),
                    )
                duplicate_of = entry.get("duplicate_of")
                if duplicate_of:
                    return cls(
                        ok=True,
                        character_id=str(duplicate_of),
                        character_name=str(entry.get("created_name") or ""),
                    )
            for entry in entries:
                if isinstance(entry, dict) and entry.get("reason"):
                    return cls(ok=False, reason=str(entry["reason"]))
        return cls(ok=False, reason="the file did not contain a usable card")


@dataclass(frozen=True)
class PresetSummary:
    """One row of ``GET /api/v1/presets`` (``preset_to_dict``).

    Only the identity fields the shell displays; the param bag
    itself is R-09's concern (the full editor), never rendered
    here."""

    id: str
    name: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PresetSummary:
        return cls(
            id=str(payload.get("id", "")),
            name=str(payload.get("name", "")),
        )


@dataclass(frozen=True)
class PersonaView:
    """``GET /api/v1/chats/{id}/persona`` (R-03): the chat's active
    persona, or no persona when the chat has no character."""

    chat_id: str
    character_id: str | None = None
    name: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PersonaView:
        persona = payload.get("persona")
        if isinstance(persona, dict):
            return cls(
                chat_id=str(payload.get("chat_id", "")),
                character_id=persona.get("character_id") or None,
                name=persona.get("name") or None,
            )
        return cls(chat_id=str(payload.get("chat_id", "")))

    @property
    def present(self) -> bool:
        return self.character_id is not None


@dataclass(frozen=True)
class StreamEvent:
    """One event of a ``POST /api/v1/generate`` SSE stream (R-06).

    ``kind`` is one of ``started`` (carries the response headers:
    ``backend_key`` + ``mode``), ``token`` / ``reasoning`` (carry
    ``text``), ``done`` (carries ``finish_reason``), or ``error``
    (carries a plain ``message`` — provider payloads never cross,
    INV-001/023). The client yields these in wire order; the chat
    flow reduces them into the visible draft."""

    kind: str
    text: str = ""
    finish_reason: str = ""
    message: str = ""
    backend_key: str = ""
    mode: str = ""


@dataclass(frozen=True)
class EngineSnapshot:
    """Everything the shell skeleton shows about the engine at once:
    health + the three lists + the derived first-run state. Fetched
    as one unit off the GUI thread (see ``core.fetch_snapshot``)."""

    health: HealthStatus
    profiles: list[BackendProfile] = field(default_factory=list)
    chats: list[ChatSummary] = field(default_factory=list)
    characters: list[CharacterSummary] = field(default_factory=list)
    first_run: FirstRunState = field(
        default_factory=lambda: FirstRunState(True, 0, 0)
    )
