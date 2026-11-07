"""ORM models. DDL source of truth lives in the migrations; these classes
must match the migrated schema."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import ForeignKey, Integer, String, Text
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
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    lineage_id: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    provenance_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


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
    backend_profile_id: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None)
    # Author's note (P-056, PROVISIONAL 0034); one validated JSON document.
    authors_note_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # Post-history instructions (P-057, PROVISIONAL 0035); one validated JSON document.
    post_history_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # Swipe-regen settings (P-065, PROVISIONAL 0036); one validated JSON document.
    swipe_settings_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # Branch lineage (P-066, PROVISIONAL 0037). branch_parent_id is a
    # plain id, deliberately NOT a foreign key: deleting a parent must
    # never cascade into a branch (branching is never destructive).
    branch_parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None)
    branch_fork_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True, default=None)
    branch_fork_index: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    branch_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="root")
    branch_merge_of_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    chat_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Swipe deck (P-065, PROVISIONAL 0036): ordered alternates; content == swipes[swipe_id].
    swipes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    swipe_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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
    # Scan windows (P-037): which context window the scanner sees, as
    # data -- scan_mode is the windows.py vocabulary ('depth' scans the
    # last scan_depth messages, 'whole_chat' scans them all) and
    # scan_external_context admits caller-supplied external context
    # into the window as its own segment.
    scan_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="depth")
    scan_external_context: Mapped[bool] = mapped_column(nullable=False, default=False)
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
    selective_logic: Mapped[str] = mapped_column(String(20), nullable=False, default="and_any")
    # Inclusion groups (P-034): one group label ('' = ungrouped) +
    # the weight that ranks the entry inside its group.
    inclusion_group: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    group_weight: Mapped[int] = mapped_column(nullable=False, default=100)
    # Probability (P-036): integer percent 0..100; 100 = gate off.
    # The seeded, inspectable roll lives in lorebooks/rng.py.
    probability: Mapped[int] = mapped_column(nullable=False, default=100)
    priority: Mapped[int] = mapped_column(nullable=False, default=100)
    position: Mapped[str] = mapped_column(String(40), nullable=False, default="before_char")
    # Placement (P-038): the at-depth companions. depth is the S206
    # splice count (NULL = undeclared; placement materialises the
    # default at compose time); role is the chat role an at_depth
    # entry is injected as. Both are stored for every entry and
    # consulted only when position == "at_depth".
    depth: Mapped[int | None] = mapped_column(nullable=True, default=None)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="system"
    )
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    constant: Mapped[bool] = mapped_column(nullable=False, default=False)
    # Entry states (P-035): vectorised kind flag; the kind itself is derived (runmal.lorebooks.states), never stored.
    vectorised: Mapped[bool] = mapped_column(nullable=False, default=False)
    case_sensitive: Mapped[bool] = mapped_column(nullable=False, default=False)
    whole_word: Mapped[bool] = mapped_column(nullable=False, default=True)
    sticky_prompts: Mapped[int] = mapped_column(nullable=False, default=0)
    cooldown_prompts: Mapped[int] = mapped_column(nullable=False, default=0)
    delay_prompts: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, default=None)


class CharacterBookBinding(Base):
    """Character-book binding (P-039): one character bound to one lorebook,
    with the precedence that orders the character book against other
    lore sources."""

    __tablename__ = "character_book_bindings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    character_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    lorebook_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lorebooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    precedence: Mapped[str] = mapped_column(String(40), nullable=False, default="character_first")
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, default=None)


class LorebookScope(Base):
    """Lorebook scope assignment (P-040): one lorebook assigned to a
    layer of a chat's world -- global (owner ''), character or persona
    (owner = character id), or chat (owner = chat id) -- with an
    optional per-scope token budget (NULL = unlimited, 0 = muted) and
    a position inside the layer. The (lorebook, kind, owner) triple
    is unique."""

    __tablename__ = "lorebook_scopes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lorebook_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lorebooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="global")
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    token_budget: Mapped[int | None] = mapped_column(nullable=True, default=None)
    position: Mapped[int] = mapped_column(nullable=False, default=0)
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
    # Preset interop carriage (P-021): origin format + lossless original.
    source_format: Mapped[str] = mapped_column(String(40), nullable=False, default="native")
    interop_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, default=None)


class PresetBundle(Base):
    """Preset bundle (P-054): sampler + prompt selections as one unit.

    The whole validated bundle lives in ``bundle_json`` (canonical
    JSON): the bundle is an aggregate and splitting it across
    columns would invite partial writes that lose carried fields.
    """

    __tablename__ = "preset_bundles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    bundle_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, default=None)


class PresetOverride(Base):
    """Preset override (P-054): one bundle assigned to one character
    or chat, with a partial delta. Unique per (scope_kind, owner_id)."""

    __tablename__ = "preset_overrides"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bundle_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("preset_bundles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="chat")
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    overrides_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
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


class ChatLoreEntryState(Base):
    """Runtime timed-effect counters for one lore entry in one chat
    (P-033). Separate from the canonical LoreEntry definition per
    DATA_MODEL.md: the entry row holds sticky/cooldown/delay CONFIG;
    this row holds the live counters. Absence of a row means the
    default (all-zero, unarmed) state."""

    __tablename__ = "chat_lore_entry_states"

    chat_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chats.id", ondelete="CASCADE"), primary_key=True
    )
    entry_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lore_entries.id", ondelete="CASCADE"),
        primary_key=True, index=True,
    )
    sticky_remaining: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cooldown_remaining: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delay_remaining: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delay_armed: Mapped[bool] = mapped_column(nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)


class BridgeCredential(Base):
    """Per-bridge scoped credential (S601, BRIDGE_PROTOCOL §2).

    Only the SHA-256 hash of the token is stored; the plaintext is
    shown once at creation and never persisted (INV-023/INV-029).
    Revocation is a timestamp — a revoked credential authenticates
    nothing, but its row remains as the audit record.
    """

    __tablename__ = "bridge_credentials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    scopes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    revoked_at: Mapped[str | None] = mapped_column(String(40), nullable=True, default=None)
    last_used_at: Mapped[str | None] = mapped_column(String(40), nullable=True, default=None)


class BridgeEvent(Base):
    """One durable outbox event in a chat's bridge stream (S609).

    Ids are database AUTOINCREMENT integers: strictly monotonic, so
    a consumer's position is a single integer (its checkpoint).
    """

    __tablename__ = "bridge_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    data_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")


class BridgeCheckpoint(Base):
    """A bridge credential's acknowledged position in one chat's
    outbox stream (S609). Acknowledged events are never re-delivered
    to that credential; the checkpoint only moves forward."""

    __tablename__ = "bridge_checkpoints"

    credential_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    chat_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    last_event_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")


class BridgeIdempotencyKey(Base):
    """Stored result of one idempotent bridge write (S610).

    Primary key (credential, operation, key): replaying the same
    logical request returns `response_json`; a different request
    under the same key is a 409 conflict (INV-030).
    """

    __tablename__ = "bridge_idempotency_keys"

    credential_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    operation: Mapped[str] = mapped_column(String(40), primary_key=True)
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    response_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")


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


class CharacterAsset(Base):
    """One asset belonging to a character (P-023): card art,
    expression, background, embedded image or pack. Provenance +
    sniffed image facts + relative storage paths; the bytes live on
    disk, never in the row."""

    __tablename__ = "character_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    character_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False, default="embedded")
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    source_uri: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_ext: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="stored")
    detail: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    format: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    media_type: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    storage_relpath: Mapped[str | None] = mapped_column(String(300), nullable=True)
    thumbnail_relpath: Mapped[str | None] = mapped_column(String(300), nullable=True)
    thumbnail_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="not_applicable"
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)


class CharacterOrganisation(Base):
    """Per-user library organisation for one character (P-024).

    One row per character: the owning user's favourite flag and when
    it last changed. Absence of a row means not a favourite.
    """

    __tablename__ = "character_organisation"

    character_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_favourite: Mapped[bool] = mapped_column(nullable=False, default=False)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, default=None)


class CharacterTag(Base):
    """One user-applied tag on a character (P-024).

    ``tag`` is the display form; ``tag_key`` is its normalised lookup
    form and, with the character, the primary key - so the same tag
    cannot be applied twice to one character.
    """

    __tablename__ = "character_tags"

    character_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True
    )
    tag_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tag: Mapped[str] = mapped_column(String(80), nullable=False)
