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


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    character_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    chat_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
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
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True, default=None)
