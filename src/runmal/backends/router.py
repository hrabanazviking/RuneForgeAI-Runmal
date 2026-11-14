"""Backend-profile API (R-02): CRUD + write-only secrets + health + models.

This router is the HTTP door over ``runmal.backends.profiles`` (S306) —
the profile system generation actually resolves through (see the
generation router's ``_resolve_backend``). Before R-02 that system had
no HTTP routes at all, so no client could create the profile generation
uses or store an API key for it.

Routes (mounted under ``/api/v1`` in ``runmal.app``):

- ``POST   /backend-profiles`` — create (201). Optional ``chat_secret`` /
  ``embedding_secret`` plaintext fields are accepted here as a one-shot
  convenience and stored via the secret store; they are write-only.
- ``GET    /backend-profiles`` — list (owner-scoped, name order).
- ``GET    /backend-profiles/{profile_id}`` — detail.
- ``PATCH  /backend-profiles/{profile_id}`` — partial update (no secrets).
- ``DELETE /backend-profiles/{profile_id}`` — delete (+ its secrets).
- ``PUT    /backend-profiles/{profile_id}/chat-secret`` — set chat key.
- ``DELETE /backend-profiles/{profile_id}/chat-secret`` — clear chat key.
- ``PUT    /backend-profiles/{profile_id}/embedding-secret`` — set
  embedding key.
- ``DELETE /backend-profiles/{profile_id}/embedding-secret`` — clear it.
- ``GET    /backend-profiles/{profile_id}/health`` — probe the profile's
  chat backend; failures are data (``ok: false``), never a 500.
- ``GET    /backend-profiles/{profile_id}/models`` — the chat backend's
  normalized model list, for the model picker.

Secrets discipline (INV-023): secret VALUES are write-only. They are
accepted only in request bodies, stored only via the secret store, and
never appear in any response — profile shapes carry ``has_*_secret``
booleans and opaque references only, health/model payloads carry no
credentials, and backend error messages are the adapters' sanitized
taxonomy strings (``runmal.backends.errors``), never provider payloads.

Legacy note: the S211 ``connections`` profiles are a different, retired
system whose data never drove generation. They are NOT migrated here
and there is nothing to migrate — see ``runmal/connections/service.py``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.backends import profiles as backend_profiles
from runmal.backends.errors import BackendError
from runmal.db.deps import get_owner_id, get_session

router = APIRouter(tags=["backend-profiles"])


class BackendProfileIn(BaseModel):
    name: str
    chat_backend: str = "fake"
    chat_model: str = ""
    embedding_backend: str = ""
    embedding_model: str = ""
    stt_ref: str = ""
    tts_ref: str = ""
    config: dict[str, Any] | None = None
    # Write-only conveniences (INV-023): stored via the secret store at
    # creation, never echoed. Prefer the dedicated secret routes for
    # later changes.
    chat_secret: str | None = None
    embedding_secret: str | None = None


class BackendProfilePatch(BaseModel):
    name: str | None = None
    chat_backend: str | None = None
    chat_model: str | None = None
    embedding_backend: str | None = None
    embedding_model: str | None = None
    stt_ref: str | None = None
    tts_ref: str | None = None
    config: dict[str, Any] | None = None


class SecretIn(BaseModel):
    value: str


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="backend profile not found")


def _value_error(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if "already exists" in msg:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg
    )


@router.post("/backend-profiles", status_code=status.HTTP_201_CREATED)
async def create_backend_profile(
    body: BackendProfileIn,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        profile = await backend_profiles.create_profile(
            session,
            user_id,
            name=body.name,
            chat_backend=body.chat_backend,
            chat_model=body.chat_model,
            embedding_backend=body.embedding_backend,
            embedding_model=body.embedding_model,
            stt_ref=body.stt_ref,
            tts_ref=body.tts_ref,
            config=body.config,
        )
        # Write-only inline secrets: set after creation so the profile
        # row never carries a value, only the resulting reference.
        if body.chat_secret:
            profile = await backend_profiles.set_profile_secret(
                session, user_id, profile.id, "chat", body.chat_secret
            )
        if body.embedding_secret:
            profile = await backend_profiles.set_profile_secret(
                session, user_id, profile.id, "embedding", body.embedding_secret
            )
    except ValueError as exc:
        raise _value_error(exc) from exc
    return backend_profiles.profile_to_dict(profile)


@router.get("/backend-profiles")
async def list_backend_profiles(
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    profiles = await backend_profiles.list_profiles(session, user_id)
    return [backend_profiles.profile_to_dict(p) for p in profiles]


@router.get("/backend-profiles/{profile_id}")
async def get_backend_profile(
    profile_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    profile = await backend_profiles.get_profile(session, user_id, profile_id)
    if profile is None:
        raise _not_found()
    return backend_profiles.profile_to_dict(profile)


@router.patch("/backend-profiles/{profile_id}")
async def update_backend_profile(
    profile_id: str,
    body: BackendProfilePatch,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        profile = await backend_profiles.update_profile(
            session,
            user_id,
            profile_id,
            name=body.name,
            chat_backend=body.chat_backend,
            chat_model=body.chat_model,
            embedding_backend=body.embedding_backend,
            embedding_model=body.embedding_model,
            stt_ref=body.stt_ref,
            tts_ref=body.tts_ref,
            config=body.config,
        )
    except ValueError as exc:
        raise _value_error(exc) from exc
    if profile is None:
        raise _not_found()
    return backend_profiles.profile_to_dict(profile)


@router.delete("/backend-profiles/{profile_id}")
async def delete_backend_profile(
    profile_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    if not await backend_profiles.delete_profile(session, user_id, profile_id):
        raise _not_found()
    return {"ok": True}


async def _set_secret(
    profile_id: str, kind: str, body: SecretIn, user_id: str, session: AsyncSession
):
    try:
        profile = await backend_profiles.set_profile_secret(
            session, user_id, profile_id, kind, body.value
        )
    except ValueError as exc:
        raise _value_error(exc) from exc
    if profile is None:
        raise _not_found()
    # The response is the profile shape: references + booleans only.
    return backend_profiles.profile_to_dict(profile)


async def _clear_secret(
    profile_id: str, kind: str, user_id: str, session: AsyncSession
):
    profile = await backend_profiles.clear_profile_secret(
        session, user_id, profile_id, kind
    )
    if profile is None:
        raise _not_found()
    return backend_profiles.profile_to_dict(profile)


@router.put("/backend-profiles/{profile_id}/chat-secret")
async def set_chat_secret(
    profile_id: str,
    body: SecretIn,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Set/replace the chat API key (write-only, INV-023)."""
    return await _set_secret(profile_id, "chat", body, user_id, session)


@router.delete("/backend-profiles/{profile_id}/chat-secret")
async def delete_chat_secret(
    profile_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    return await _clear_secret(profile_id, "chat", user_id, session)


@router.put("/backend-profiles/{profile_id}/embedding-secret")
async def set_embedding_secret(
    profile_id: str,
    body: SecretIn,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Set/replace the embedding API key (write-only, INV-023)."""
    return await _set_secret(profile_id, "embedding", body, user_id, session)


@router.delete("/backend-profiles/{profile_id}/embedding-secret")
async def delete_embedding_secret(
    profile_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    return await _clear_secret(profile_id, "embedding", user_id, session)


@router.get("/backend-profiles/{profile_id}/health")
async def backend_profile_health(
    profile_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Probe the profile's chat backend. Health is data: an unreachable
    backend answers ``ok: false`` with a plain detail, never a 500, and
    never any credential material."""
    profile = await backend_profiles.get_profile(session, user_id, profile_id)
    if profile is None:
        raise _not_found()
    try:
        # Construction is inside the guard too: a malformed profile
        # config (e.g. an unparseable base_url) is a health fact about
        # that profile, never a 500 for the probe route.
        backend = await backend_profiles.build_chat_backend(session, profile)
        health = await backend.health_check()
        payload = health.to_dict()
    except Exception as exc:  # a broken adapter must not 500 the probe
        payload = {
            "ok": False,
            "detail": f"health probe failed: {exc.__class__.__name__}",
            "latency_ms": None,
        }
    return {
        "profile_id": profile.id,
        "backend": profile.chat_backend,
        "model": profile.chat_model,
        **payload,
    }


@router.get("/backend-profiles/{profile_id}/models")
async def backend_profile_models(
    profile_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """The chat backend's normalized model list (model-picker source).
    A backend that cannot list answers 502 with its sanitized taxonomy
    message — provider payloads and credentials never cross (INV-001/023)."""
    profile = await backend_profiles.get_profile(session, user_id, profile_id)
    if profile is None:
        raise _not_found()
    try:
        backend = await backend_profiles.build_chat_backend(session, profile)
        models = await backend.list_models()
    except BackendError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=exc.message
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"model list failed: {exc.__class__.__name__}",
        ) from exc
    return {
        "profile_id": profile.id,
        "backend": profile.chat_backend,
        "models": [m.to_dict() for m in models],
    }
