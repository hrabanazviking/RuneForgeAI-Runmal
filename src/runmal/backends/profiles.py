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

R-02 (2026-11-14): this module is the profile system generation actually
resolves through (generation, chats, and the bridge all call
:func:`get_profile` / :func:`build_chat_backend` here), and it is now
exposed over HTTP by ``runmal.backends.router``
(``/api/v1/backend-profiles``). The legacy S211 ``connections`` profiles
(``runmal.connections``) are a separate, retired system: their data never
drove generation, there is nothing to migrate, and their rows/routes are
left readable only so existing data is not destroyed — see the retirement
note in ``runmal/connections/service.py``.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.backends.aesir import DEFAULT_BASE_URL as AESIR_DEFAULT_BASE_URL
from runmal.backends.aesir import AesirChatBackend
from runmal.backends.base import ChatBackend
from runmal.backends.embeddings import (
    AesirEmbeddingBackend,
    EmbeddingBackend,
    FakeEmbeddingBackend,
    OllamaEmbeddingBackend,
    OpenAICompatibleEmbeddingBackend,
    UnavailableEmbeddingBackend,
)
from runmal.backends.fake import FakeChatBackend
from runmal.backends.ollama import OllamaChatBackend
from runmal.backends.openai_compat import OpenAICompatibleChatBackend
from runmal.backends.openrouter import OpenRouterChatBackend
from runmal.db.models import BackendProfile, SecretEntry

CHAT_BACKENDS = ("fake", "ollama", "openrouter", "aesir", "openai")
EMBEDDING_BACKENDS = ("", "fake", "ollama", "aesir", "openai")


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


def _profile_config(profile: BackendProfile) -> dict:
    """The profile's config document (``{}`` when absent/malformed)."""
    try:
        config = json.loads(profile.config_json or "{}")
    except json.JSONDecodeError:
        return {}
    return config if isinstance(config, dict) else {}


def _config_base_url(profile: BackendProfile) -> str | None:
    base_url = _profile_config(profile).get("base_url")
    return base_url if isinstance(base_url, str) and base_url else None


async def _secret_still_referenced(
    session: AsyncSession, user_id: str, ref: str, *, exclude_profile_id: str
) -> bool:
    """True when another profile of this owner still references ``ref``."""
    if not ref:
        return False
    rows = await session.scalars(
        select(BackendProfile).where(
            BackendProfile.user_id == user_id,
            BackendProfile.id != exclude_profile_id,
        )
    )
    return any(
        ref in (row.chat_secret_ref, row.embedding_secret_ref) for row in rows
    )


async def _drop_secret_if_unreferenced(
    session: AsyncSession, user_id: str, ref: str, *, exclude_profile_id: str
) -> None:
    """Delete a secret row once no other profile references it."""
    if not ref:
        return
    if await _secret_still_referenced(
        session, user_id, ref, exclude_profile_id=exclude_profile_id
    ):
        return
    await delete_secret(session, user_id, ref)


def profile_to_dict(profile: BackendProfile) -> dict:
    """API/export shape: references only, NEVER secret values (INV-023)."""
    config = _profile_config(profile)
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


async def update_profile(
    session: AsyncSession,
    user_id: str,
    profile_id: str,
    *,
    name: str | None = None,
    chat_backend: str | None = None,
    chat_model: str | None = None,
    embedding_backend: str | None = None,
    embedding_model: str | None = None,
    stt_ref: str | None = None,
    tts_ref: str | None = None,
    config: dict | None = None,
) -> BackendProfile | None:
    """Partial update (R-02). ``None`` fields are left untouched; secret
    references are never changed here — use :func:`set_profile_secret` /
    :func:`clear_profile_secret` so values stay write-only (INV-023)."""
    profile = await get_profile(session, user_id, profile_id)
    if profile is None:
        return None
    if name is not None:
        if not name.strip():
            raise _bad("profile name must be non-empty")
        if name != profile.name:
            existing = await session.scalar(
                select(BackendProfile).where(
                    BackendProfile.user_id == user_id,
                    BackendProfile.name == name,
                )
            )
            if existing is not None:
                raise _bad(f"profile name already exists: {name}")
        profile.name = name
    if chat_backend is not None:
        if chat_backend not in CHAT_BACKENDS:
            raise _bad(f"unknown chat backend: {chat_backend}")
        profile.chat_backend = chat_backend
    if chat_model is not None:
        profile.chat_model = chat_model
    if embedding_backend is not None:
        if embedding_backend not in EMBEDDING_BACKENDS:
            raise _bad(f"unknown embedding backend: {embedding_backend}")
        profile.embedding_backend = embedding_backend
    if embedding_model is not None:
        profile.embedding_model = embedding_model
    if stt_ref is not None:
        profile.stt_ref = stt_ref
    if tts_ref is not None:
        profile.tts_ref = tts_ref
    if config is not None:
        profile.config_json = json.dumps(config)
    profile.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(profile)
    return profile


#: Secret slots a profile carries (R-02): ``chat`` feeds the chat backend,
#: ``embedding`` feeds the embedding backend. Independent by design (ADR-0001).
SECRET_KINDS = ("chat", "embedding")


def _secret_attr(kind: str) -> str:
    if kind == "chat":
        return "chat_secret_ref"
    if kind == "embedding":
        return "embedding_secret_ref"
    raise _bad(f"unknown secret kind: {kind}")


async def set_profile_secret(
    session: AsyncSession,
    user_id: str,
    profile_id: str,
    kind: str,
    value: str,
) -> BackendProfile | None:
    """Store ``value`` in the secret store and point the profile's ``kind``
    slot at it (R-02, write-only). The replaced secret row is deleted once
    no other profile references it. The value itself is never returned,
    logged, or serialized (INV-023)."""
    attr = _secret_attr(kind)
    if not value:
        raise _bad("secret value must be non-empty")
    profile = await get_profile(session, user_id, profile_id)
    if profile is None:
        return None
    old_ref = getattr(profile, attr)
    new_ref = await put_secret(session, user_id, value)
    # put_secret committed; re-load the profile in this session's identity map.
    profile = await get_profile(session, user_id, profile_id)
    if profile is None:  # deleted concurrently: do not orphan the new secret
        await delete_secret(session, user_id, new_ref)
        return None
    setattr(profile, attr, new_ref)
    profile.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(profile)
    if old_ref and old_ref != new_ref:
        await _drop_secret_if_unreferenced(
            session, user_id, old_ref, exclude_profile_id=profile.id
        )
    return profile


async def clear_profile_secret(
    session: AsyncSession,
    user_id: str,
    profile_id: str,
    kind: str,
) -> BackendProfile | None:
    """Clear the profile's ``kind`` secret slot and delete the secret row
    once no other profile references it (R-02). Idempotent: clearing an
    already-empty slot succeeds and changes nothing."""
    attr = _secret_attr(kind)
    profile = await get_profile(session, user_id, profile_id)
    if profile is None:
        return None
    old_ref = getattr(profile, attr)
    if old_ref:
        setattr(profile, attr, "")
        profile.updated_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(profile)
        await _drop_secret_if_unreferenced(
            session, user_id, old_ref, exclude_profile_id=profile.id
        )
    return profile


async def delete_profile(session: AsyncSession, user_id: str, profile_id: str) -> bool:
    profile = await get_profile(session, user_id, profile_id)
    if profile is None:
        return False
    chat_ref, embedding_ref = profile.chat_secret_ref, profile.embedding_secret_ref
    await session.delete(profile)
    await session.commit()
    # A deleted profile must not leave its secret values behind (INV-023
    # hygiene): drop each row once no surviving profile references it.
    for ref in (chat_ref, embedding_ref):
        if ref:
            await _drop_secret_if_unreferenced(
                session, user_id, ref, exclude_profile_id=profile_id
            )
    return True


@dataclass
class ResolvedProfile:
    profile: BackendProfile
    chat: ChatBackend
    embedding: EmbeddingBackend


async def build_chat_backend(session: AsyncSession, profile: BackendProfile) -> ChatBackend:
    """Instantiate the profile's chat backend, resolving its secret ref.

    Every HTTP backend honours the profile's ``config.base_url`` when set
    (R-02 fix: Ollama and OpenRouter previously ignored it, so a profile
    pointing at a non-default endpoint silently probed/generated against
    the adapter default instead)."""
    secret = await resolve_secret(session, profile.user_id, profile.chat_secret_ref)
    base_url = _config_base_url(profile)
    if profile.chat_backend == "ollama":
        kwargs = {"model": profile.chat_model or "llama3.1"}
        if base_url:
            kwargs["base_url"] = base_url
        return OllamaChatBackend(**kwargs)
    if profile.chat_backend == "openrouter":
        kwargs = {
            "model": profile.chat_model or "openai/gpt-4o-mini",
            "api_key": secret or "",
        }
        if base_url:
            kwargs["base_url"] = base_url
        return OpenRouterChatBackend(**kwargs)
    if profile.chat_backend == "aesir":
        return AesirChatBackend(
            model=profile.chat_model or "local-model",
            base_url=base_url or AESIR_DEFAULT_BASE_URL,
            api_key=secret,
        )
    if profile.chat_backend == "openai":
        kwargs = {"model": profile.chat_model or "gpt-4o-mini", "api_key": secret}
        if base_url:
            kwargs["base_url"] = base_url
        return OpenAICompatibleChatBackend(**kwargs)
    return FakeChatBackend()


async def build_embedding_backend(
    session: AsyncSession, profile: BackendProfile
) -> EmbeddingBackend:
    base_url = _config_base_url(profile)
    if profile.embedding_backend == "ollama":
        kwargs = {"model": profile.embedding_model or "nomic-embed-text"}
        if base_url:
            kwargs["base_url"] = base_url
        return OllamaEmbeddingBackend(**kwargs)
    if profile.embedding_backend == "aesir":
        secret = await resolve_secret(session, profile.user_id, profile.embedding_secret_ref)
        kwargs = {"model": profile.embedding_model or "local-embed", "api_key": secret}
        if base_url:
            kwargs["base_url"] = base_url
        return AesirEmbeddingBackend(**kwargs)
    if profile.embedding_backend == "openai":
        secret = await resolve_secret(session, profile.user_id, profile.embedding_secret_ref)
        kwargs = {"model": profile.embedding_model or "text-embedding-3-small", "api_key": secret}
        if base_url:
            kwargs["base_url"] = base_url
        return OpenAICompatibleEmbeddingBackend(**kwargs)
    if profile.embedding_backend == "fake":
        return FakeEmbeddingBackend()
    return UnavailableEmbeddingBackend()


async def resolve_profile(session: AsyncSession, profile: BackendProfile) -> ResolvedProfile:
    return ResolvedProfile(
        profile=profile,
        chat=await build_chat_backend(session, profile),
        embedding=await build_embedding_backend(session, profile),
    )
