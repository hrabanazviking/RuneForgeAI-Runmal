"""ORM models. DDL source of truth lives in the migrations; these classes
must match the migrated schema."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    card_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    avatar_asset: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    # Soft delete (S303): trashed characters are hidden but recoverable.
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True, default=None)


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    character_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )
    # Group-room transcript link (S210): set when this chat is a group's room.
    group_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("groups.id", ondelete="CASCADE"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # Applied sampling preset (S306); plain id, integrity kept by service.
    preset_id: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None)
    # Selected backend profile (S306/S307); plain id, integrity by service.
    backend_profile_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    chat_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Per-message speaker identity (S210): the speaking character's id and a
    # snapshot of its display name. The snapshot survives membership changes
    # and character renames -- history is never rewritten.
    speaker_id: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None)
    speaker_name: Mapped[str | None] = mapped_column(String(200), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, default=None)


class ChatEvent(Base):
    """Durable mutation event log per chat (S107): feeds future memory sync."""

    __tablename__ = "chat_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    chat_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    data: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)


class Lorebook(Base):
    """Lorebook (S201): owns book-level scanning/budget/default settings."""

    __tablename__ = "lorebooks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scan_depth: Mapped[int] = mapped_column(nullable=False, default=4)
    token_budget: Mapped[int | None] = mapped_column(nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)


class LoreEntry(Base):
    """Lore entry (S201): activation metadata, content, position/priority,
    enabled state. Keys are stored as JSON text."""

    __tablename__ = "lore_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    lorebook_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lorebooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    keys_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    secondary_keys_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    priority: Mapped[int] = mapped_column(nullable=False, default=100)
    position: Mapped[str] = mapped_column(String(40), nullable=False, default="before_char")
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    constant: Mapped[bool] = mapped_column(nullable=False, default=False)
    case_sensitive: Mapped[bool] = mapped_column(nullable=False, default=False)
    whole_word: Mapped[bool] = mapped_column(nullable=False, default=True)
    sticky_prompts: Mapped[int] = mapped_column(nullable=False, default=0)
    cooldown_prompts: Mapped[int] = mapped_column(nullable=False, default=0)
    delay_prompts: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, default=None)


class SamplingPreset(Base):
    """Sampling preset (S207): named canonical parameter bag + template ref."""

    __tablename__ = "sampling_presets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    params_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    template_ref: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, default=None)


class ConnectionProfile(Base):
    """Backend connection profile (S211). Secrets are never stored here."""

    __tablename__ = "connection_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    backend: Mapped[str] = mapped_column(String(40), nullable=False, default="fake")
    base_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, default=None)


class Group(Base):
    """A group-chat room (roadmap S210): references member characters; its
    transcript is a Chat whose group_id points here."""

    __tablename__ = "groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    # Speaker-policy configuration (S211): policy name + JSON parameters.
    speaker_policy: Mapped[str] = mapped_column(String(40), nullable=False, default="natural")
    speaker_config: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)


class GroupMember(Base):
    """One roster row: a character's membership in a group, in order."""

    __tablename__ = "group_members"

    group_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    character_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(nullable=False, default=0)
    # Speaker-policy knobs (S211): selection weight + absolute mute.
    talkativeness: Mapped[float] = mapped_column(nullable=False, default=0.5)
    muted: Mapped[bool] = mapped_column(nullable=False, default=False)


class BackendProfile(Base):
    """Backend modality profile (S306, BACKEND_CONTRACT §10).

    Composes a chat backend+model, an embedding backend+model, and STT/TTS
    references. Stores ONLY secret references — values live in SecretEntry.
    """

    __tablename__ = "backend_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    chat_backend: Mapped[str] = mapped_column(String(40), nullable=False, default="fake")
    chat_model: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    embedding_backend: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    embedding_model: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    stt_ref: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    tts_ref: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    chat_secret_ref: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    embedding_secret_ref: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, default=None)


class EmbeddingActivation(Base):
    """The owner's ACTIVE embedding profile (S311) — an axis independent
    of chat: switching it never touches chat backends or models."""

    __tablename__ = "embedding_activation"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    profile_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    provenance_key: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)


class ReembeddingJob(Base):
    """A scheduled re-embedding job (S311 migration hook ledger)."""

    __tablename__ = "reembedding_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_key: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    to_key: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled")
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)


class SecretEntry(Base):
    """Server-side secret value (S306). Referenced by profiles via ``ref``;
    values are never serialized into API responses, logs, or exports."""

    __tablename__ = "secrets"

    ref: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)


class Memory(Base):
    """Canonical living-memory record (Campaign IV, MEMORY_ARCH §2)."""

    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="semantic")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    subject: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    predicate: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    salience: Mapped[float] = mapped_column(nullable=False, default=0.5)
    stability: Mapped[float] = mapped_column(nullable=False, default=0.5)
    pinned: Mapped[bool] = mapped_column(nullable=False, default=False)
    confidence: Mapped[float] = mapped_column(nullable=False, default=1.0)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    witnesses_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    character_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    chat_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    valid_from: Mapped[datetime | None] = mapped_column(nullable=True, default=None)
    valid_until: Mapped[datetime | None] = mapped_column(nullable=True, default=None)
    last_confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True, default=None)
    recall_count: Mapped[int] = mapped_column(nullable=False, default=0)
    last_recalled_at: Mapped[datetime | None] = mapped_column(nullable=True, default=None)
    supersedes_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    extractor_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    embedding_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class MemorySource(Base):
    """Many-to-many evidence link: memory -> canonical source (MEMORY_ARCH §4)."""

    __tablename__ = "memory_sources"

    memory_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("memories.id", ondelete="CASCADE"), primary_key=True
    )
    source_kind: Mapped[str] = mapped_column(String(20), primary_key=True, default="message")
    source_id: Mapped[str] = mapped_column(String(200), primary_key=True, default="")
    chat_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class MemoryChunk(Base):
    """One embedded chunk of a memory, with full embedding provenance (S402)."""

    __tablename__ = "memory_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    memory_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("memories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    provider: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    dims: Mapped[int] = mapped_column(nullable=False, default=0)
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="")


class ChatSummary(Base):
    """Rolling conversation summary with source range + version (S404)."""

    __tablename__ = "chat_summaries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chat_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_first_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_last_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_count: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)


class CharacterVoiceProfile(Base):
    """Per-character TTS reference (S512): backend + voice + params.

    Deliberately NOT part of backend_profiles: a persona's voice switch
    must never move the chat/embedding composition (S512 acceptance).
    """

    __tablename__ = "character_voice_profiles"

    character_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tts_backend: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    voice_id: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    language: Mapped[str] = mapped_column(String(20), nullable=False, default="en-us")
    params_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
