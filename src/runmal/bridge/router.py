"""Bridge credential administration + bridge identity routes (S601).

Two surfaces, deliberately separate:

- `admin_router` — mounted behind the LOCAL application credential.
  The owner creates/lists/revokes bridge credentials here. The token
  plaintext appears exactly once, in the creation response.
- `router` — the bridge-facing surface under /api/v1/bridge/...,
  authenticated by bridge tokens only (see runmal.bridge.auth).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.bridge import service
from runmal.bridge.auth import BridgeIdentity, get_bridge_identity
from runmal.bridge.service import credential_to_dict
from runmal.db.deps import get_owner_id, get_session

admin_router = APIRouter(tags=["bridge-admin"])
router = APIRouter(prefix="/bridge", tags=["bridge"])


class CredentialCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    scopes: list[str] = Field(min_length=1)


@admin_router.post("/bridge/credentials", status_code=status.HTTP_201_CREATED)
async def create_credential(
    body: CredentialCreate,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        credential, token = await service.create_credential(
            session, user_id, body.name, body.scopes
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    payload = credential_to_dict(credential)
    payload["token"] = token  # shown once; only its hash is stored
    return payload


@admin_router.get("/bridge/credentials")
async def list_credentials(
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    rows = await service.list_credentials(session, user_id)
    return [credential_to_dict(row) for row in rows]


@admin_router.post("/bridge/credentials/{credential_id}/revoke")
async def revoke_credential(
    credential_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    credential = await service.revoke_credential(session, user_id, credential_id)
    if credential is None:
        raise HTTPException(status_code=404, detail="bridge credential not found")
    return credential_to_dict(credential)


@router.get("/whoami")
async def whoami(identity: BridgeIdentity = Depends(get_bridge_identity)):
    """The bridge's own view of itself: id, name, granted scopes.

    Never returns the token or its hash (INV-023). This is also the
    cheapest liveness/scope probe a bridge can make after pairing.
    """
    return {
        "bridge_id": identity.credential_id,
        "name": identity.name,
        "scopes": list(identity.scopes),
    }
