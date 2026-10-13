"""Profile migration tooling: Ollama/OpenRouter -> Aesir (S704).

Cutover support for Campaign VII. Migration is a profile-level operation:
it creates a NEW Aesir profile from an existing one and (optionally)
repoints chats at it. Chat history and state are never touched — chats
keep their messages byte-for-byte; only their ``backend_profile_id``
reference moves when ``repoint_chats`` is requested.

Honesty rules (INV-005/023):

- **Model names are never silently translated.** A local (Ollama) model
  name is user-owned and carries over; a namespaced cloud (OpenRouter)
  ID has no Aesir equivalent, so the plan REQUIRES an explicit Aesir
  model choice instead of stripping the namespace and pretending.
- **Embeddings are an independent axis** (ADR-0001): they carry over
  unchanged unless the caller explicitly migrates them too, which also
  requires an explicit Aesir embedding model name.
- **Secret references are never carried across providers.** An
  OpenRouter key is not an Aesir credential; the target profile starts
  secret-free and the plan says so.
- **The source profile is never modified.** Migration is a copy; the
  old profile remains for rollback.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.backends.profiles import create_profile, get_profile
from runmal.db.models import BackendProfile, Chat

TARGET_CHAT_BACKEND = "aesir"


@dataclass(frozen=True)
class ProfileMigrationPlan:
    source_profile_id: str
    source_name: str
    source_chat_backend: str
    target_name: str
    chat_backend: str
    chat_model: str | None
    embedding_backend: str
    embedding_model: str | None
    stt_ref: str
    tts_ref: str
    base_url: str | None
    warnings: tuple[str, ...]
    requires_chat_model_choice: bool
    requires_embedding_model_choice: bool

    def to_dict(self) -> dict:
        return {
            "source_profile_id": self.source_profile_id,
            "source_name": self.source_name,
            "source_chat_backend": self.source_chat_backend,
            "target_name": self.target_name,
            "chat_backend": self.chat_backend,
            "chat_model": self.chat_model,
            "embedding_backend": self.embedding_backend,
            "embedding_model": self.embedding_model,
            "stt_ref": self.stt_ref,
            "tts_ref": self.tts_ref,
            "base_url": self.base_url,
            "warnings": list(self.warnings),
            "requires_chat_model_choice": self.requires_chat_model_choice,
            "requires_embedding_model_choice": self.requires_embedding_model_choice,
        }


@dataclass(frozen=True)
class ProfileMigrationResult:
    profile: BackendProfile
    plan: ProfileMigrationPlan
    repointed_chats: int


def _source_config(profile: BackendProfile) -> dict:
    try:
        config = json.loads(profile.config_json or "{}")
    except json.JSONDecodeError:
        return {}
    return config if isinstance(config, dict) else {}


def plan_profile_migration(
    profile: BackendProfile,
    *,
    target_name: str | None = None,
    aesir_chat_model: str | None = None,
    migrate_embeddings: bool = False,
    aesir_embedding_model: str | None = None,
    base_url: str | None = None,
) -> ProfileMigrationPlan:
    """Pure planning: what an Aesir migration of ``profile`` would do."""
    if profile.chat_backend == TARGET_CHAT_BACKEND:
        raise ValueError(f"profile {profile.name!r} already uses Aesir")
    warnings: list[str] = []

    # --- chat model ---
    requires_chat_model = False
    if aesir_chat_model:
        chat_model: str | None = aesir_chat_model
    elif profile.chat_backend == "ollama":
        chat_model = profile.chat_model or None
        warnings.append(
            "chat model name carried from Ollama; the model must exist on "
            "the Aesir server — migration does not copy model weights"
        )
    elif profile.chat_backend == "openrouter":
        chat_model = None
        requires_chat_model = True
        warnings.append(
            f"OpenRouter model {profile.chat_model!r} is namespaced and has "
            "no Aesir equivalent; an explicit Aesir chat model is required"
        )
    else:  # fake or anything else: a shell, say so
        chat_model = profile.chat_model or None
        warnings.append(
            f"source chat backend {profile.chat_backend!r} is not a real "
            "inference backend; the migrated profile keeps its model name "
            "as a placeholder"
        )

    # --- embeddings (independent axis, ADR-0001) ---
    requires_embedding_model = False
    if migrate_embeddings:
        embedding_backend = TARGET_CHAT_BACKEND
        if aesir_embedding_model:
            embedding_model: str | None = aesir_embedding_model
        else:
            embedding_model = None
            requires_embedding_model = True
            warnings.append(
                "embedding migration to Aesir requires an explicit Aesir "
                "embedding model; embedding spaces never translate silently"
            )
    else:
        embedding_backend = profile.embedding_backend
        embedding_model = profile.embedding_model or None
        if embedding_backend:
            warnings.append(
                f"embeddings stay on {embedding_backend!r} (independent "
                "modality axis); pass migrate_embeddings to move them too"
            )

    # --- secrets never cross providers ---
    if profile.chat_secret_ref or profile.embedding_secret_ref:
        warnings.append(
            "secret references are NOT carried across providers; the "
            "Aesir profile starts secret-free — add a new secret if the "
            "Aesir server requires one"
        )

    # --- base_url: different server, never inherited silently ---
    source_config = _source_config(profile)
    if base_url is None and source_config.get("base_url"):
        warnings.append(
            "source profile base_url not carried (different server); "
            "the Aesir adapter default applies unless base_url is given"
        )

    return ProfileMigrationPlan(
        source_profile_id=profile.id,
        source_name=profile.name,
        source_chat_backend=profile.chat_backend,
        target_name=target_name or f"{profile.name} (Aesir)",
        chat_backend=TARGET_CHAT_BACKEND,
        chat_model=chat_model,
        embedding_backend=embedding_backend,
        embedding_model=embedding_model,
        stt_ref=profile.stt_ref,
        tts_ref=profile.tts_ref,
        base_url=base_url,
        warnings=tuple(warnings),
        requires_chat_model_choice=requires_chat_model,
        requires_embedding_model_choice=requires_embedding_model,
    )


async def apply_profile_migration(
    session: AsyncSession,
    user_id: str,
    profile_id: str,
    *,
    repoint_chats: bool = False,
    **plan_kwargs,
) -> ProfileMigrationResult:
    """Create the Aesir target profile; optionally repoint chats to it.

    The source profile is left untouched (rollback path). Chat rows are
    only re-referenced; their messages/history are never modified.
    """
    source = await get_profile(session, user_id, profile_id)
    if source is None:
        raise ValueError(f"profile not found: {profile_id}")
    plan = plan_profile_migration(source, **plan_kwargs)
    if plan.requires_chat_model_choice:
        raise ValueError(
            "migration requires an explicit Aesir chat model "
            "(aesir_chat_model) for this source profile"
        )
    if plan.requires_embedding_model_choice:
        raise ValueError(
            "embedding migration requires an explicit Aesir embedding model (aesir_embedding_model)"
        )
    target = await create_profile(
        session,
        user_id,
        name=plan.target_name,
        chat_backend=plan.chat_backend,
        chat_model=plan.chat_model or "",
        embedding_backend=plan.embedding_backend,
        embedding_model=plan.embedding_model or "",
        stt_ref=plan.stt_ref,
        tts_ref=plan.tts_ref,
        config={"base_url": plan.base_url} if plan.base_url else {},
    )
    repointed = 0
    if repoint_chats:
        result = await session.execute(
            update(Chat)
            .where(
                Chat.user_id == user_id,
                Chat.backend_profile_id == source.id,
            )
            .values(backend_profile_id=target.id)
        )
        repointed = int(result.rowcount or 0)
        await session.commit()
    return ProfileMigrationResult(profile=target, plan=plan, repointed_chats=repointed)


async def list_migratable_profiles(session: AsyncSession, user_id: str) -> list[BackendProfile]:
    """Profiles a migration could start from (anything not yet Aesir)."""
    rows = await session.scalars(
        select(BackendProfile)
        .where(
            BackendProfile.user_id == user_id,
            BackendProfile.chat_backend != TARGET_CHAT_BACKEND,
        )
        .order_by(BackendProfile.name)
    )
    return list(rows)
