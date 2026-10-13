"""Backend modality profiles + secrets handling (S306).

BACKEND_CONTRACT §10: a *profile* composes a chat backend+model, an
embedding backend+model, and STT/TTS references. Profiles are independent
per modality — a profile may pair a cloud chat backend (OpenRouter) with a
local embedding backend (Ollama) (ADR-0001).

Secrets rule (INV-023): profile/config data stores ONLY secret references.
Values live in the server-side secrets store (``secrets`` table) and are
resolved only inside the server by :func:`build_chat_backend` /
:func:`build_embedding_backend`. ``profile_to_dict`` (the API/export shape)
contains references and ``has_*_secret`` booleans — never values.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.backends.aesir import AesirChatBackend
from runmal.backends.base import ChatBackend
from runmal.backends.embeddings import (
    AesirEmbeddingBackend,
    EmbeddingBackend,
    FakeEmbeddingBackend,
    OllamaEmbeddingBackend,
    UnavailableEmbeddingBackend,
)
from runmal.backends.fake import FakeChatBackend
from runmal.backends.ollama import OllamaChatBackend
from runmal.backends.openrouter import OpenRouterChatBackend
from runmal.db.models import BackendProfile, SecretEntry

CHAT_BACKENDS = ("fake", "ollama", "openrouter", "aesir")
EMBEDDING_BACKENDS = ("", "fake", "ollama", "aesir")


def _bad(message: str) -> ValueError:
    return ValueError(message)


async def put_secret(session: AsyncSession, user_id: str, value: str) -> str:
    """Store a secret server-side; returns the opaque reference."""
    if not value:
        raise _bad("secret value must be non-empty")
    ref = f"secret:{uuid.uuid4()}"
    session.add(SecretEntry(ref=ref, user_id=user_id, value=value))
    await session.commit()
    return ref


async def resolve_secret(session: AsyncSession, user_id: str, ref: str) -> str | None:
    """Server-side only: fetch a secret value by reference (owner-scoped)."""
    if not ref:
        return None
    row = await session.get(SecretEntry, ref)
    if row is None or row.user_id != user_id:
        return None
    return row.value


async def delete_secret(session: AsyncSession, user_id: str, ref: str) -> bool:
    row = await session.get(SecretEntry, ref)
    if row is None or row.user_id != user_id:
        return False
    await session.delete(row)
    await session.commit()
    return True


def profile_to_dict(profile: BackendProfile) -> dict:
    """API/export shape: references only, NEVER secret values (INV-023)."""
    try:
        config = json.loads(profile.config_json or "{}")
    except json.JSONDecodeError:
        config = {}
    return {
        "id": profile.id,
        "name": profile.name,
        "chat_backend": profile.chat_backend,
        "chat_model": profile.chat_model,
        "embedding_backend": profile.embedding_backend,
        "embedding_model": profile.embedding_model,
        "stt_ref": profile.stt_ref,
        "tts_ref": profile.tts_ref,
        "chat_secret_ref": profile.chat_secret_ref,
        "embedding_secret_ref": profile.embedding_secret_ref,
        "has_chat_secret": bool(profile.chat_secret_ref),
        "has_embedding_secret": bool(profile.embedding_secret_ref),
        "config": config if isinstance(config, dict) else {},
    }


async def create_profile(
    session: AsyncSession,
    user_id: str,
    *,
    name: str,
    chat_backend: str = "fake",
    chat_model: str = "",
    embedding_backend: str = "",
    embedding_model: str = "",
    stt_ref: str = "",
    tts_ref: str = "",
    chat_secret_ref: str = "",
    embedding_secret_ref: str = "",
    config: dict | None = None,
) -> BackendProfile:
    if not name.strip():
        raise _bad("profile name must be non-empty")
    if chat_backend not in CHAT_BACKENDS:
        raise _bad(f"unknown chat backend: {chat_backend}")
    if embedding_backend not in EMBEDDING_BACKENDS:
        raise _bad(f"unknown embedding backend: {embedding_backend}")
    for ref in (chat_secret_ref, embedding_secret_ref):
        if ref and await resolve_secret(session, user_id, ref) is None:
            raise _bad(f"unknown secret reference: {ref}")
    existing = await session.scalar(
        select(BackendProfile).where(BackendProfile.user_id == user_id, BackendProfile.name == name)
    )
    if existing is not None:
        raise _bad(f"profile name already exists: {name}")
    profile = BackendProfile(
        user_id=user_id,
        name=name,
        chat_backend=chat_backend,
        chat_model=chat_model,
        embedding_backend=embedding_backend,
        embedding_model=embedding_model,
        stt_ref=stt_ref,
        tts_ref=tts_ref,
        chat_secret_ref=chat_secret_ref,
        embedding_secret_ref=embedding_secret_ref,
        config_json=json.dumps(config or {}),
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile


async def get_profile(
    session: AsyncSession, user_id: str, profile_id: str
) -> BackendProfile | None:
    profile = await session.get(BackendProfile, profile_id)
    if profile is None or profile.user_id != user_id:
        return None
    return profile


async def list_profiles(session: AsyncSession, user_id: str) -> list[BackendProfile]:
    rows = await session.scalars(
        select(BackendProfile)
        .where(BackendProfile.user_id == user_id)
        .order_by(BackendProfile.name)
    )
    return list(rows)


async def delete_profile(session: AsyncSession, user_id: str, profile_id: str) -> bool:
    profile = await get_profile(session, user_id, profile_id)
    if profile is None:
        return False
    await session.delete(profile)
    await session.commit()
    return True


@dataclass
class ResolvedProfile:
    profile: BackendProfile
    chat: ChatBackend
    embedding: EmbeddingBackend


async def build_chat_backend(session: AsyncSession, profile: BackendProfile) -> ChatBackend:
    """Instantiate the profile's chat backend, resolving its secret ref."""
    secret = await resolve_secret(session, profile.user_id, profile.chat_secret_ref)
    if profile.chat_backend == "ollama":
        return OllamaChatBackend(model=profile.chat_model or "llama3.1")
    if profile.chat_backend == "openrouter":
        return OpenRouterChatBackend(
            model=profile.chat_model or "openai/gpt-4o-mini", api_key=secret or ""
        )
    if profile.chat_backend == "aesir":
        try:
            config = json.loads(profile.config_json or "{}")
        except json.JSONDecodeError:
            config = {}
        base_url = config.get("base_url") if isinstance(config, dict) else None
        return AesirChatBackend(
            model=profile.chat_model or "local-model",
            base_url=base_url or "http://127.0.0.1:8000/v1",
            api_key=secret,
        )
    return FakeChatBackend()


async def build_embedding_backend(
    session: AsyncSession, profile: BackendProfile
) -> EmbeddingBackend:
    if profile.embedding_backend == "ollama":
        return OllamaEmbeddingBackend(model=profile.embedding_model or "nomic-embed-text")
    if profile.embedding_backend == "aesir":
        secret = await resolve_secret(session, profile.user_id, profile.embedding_secret_ref)
        try:
            config = json.loads(profile.config_json or "{}")
        except json.JSONDecodeError:
            config = {}
        base_url = config.get("base_url") if isinstance(config, dict) else None
        kwargs = {"model": profile.embedding_model or "local-embed", "api_key": secret}
        if base_url:
            kwargs["base_url"] = base_url
        return AesirEmbeddingBackend(**kwargs)
    if profile.embedding_backend == "fake":
        return FakeEmbeddingBackend()
    return UnavailableEmbeddingBackend()


async def resolve_profile(session: AsyncSession, profile: BackendProfile) -> ResolvedProfile:
    return ResolvedProfile(
        profile=profile,
        chat=await build_chat_backend(session, profile),
        embedding=await build_embedding_backend(session, profile),
    )
