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

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CharacterSummary:
        return cls(
            id=str(payload.get("id", "")),
            name=str(payload.get("name", "")),
            has_avatar=bool(payload.get("has_avatar", False)),
        )


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
