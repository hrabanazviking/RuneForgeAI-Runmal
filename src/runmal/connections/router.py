"""Connection profile API (S211): CRUD, set-active, health probe."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.connections import service
from runmal.db.deps import get_owner_id, get_session

router = APIRouter(tags=["connections"])


class ProfileIn(BaseModel):
    name: str
    backend: str = "fake"
    base_url: str = ""
    model: str = ""


@router.post("/connections", status_code=status.HTTP_201_CREATED)
async def create_profile(
    body: ProfileIn,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        profile = await service.create_profile(
            session,
            user_id=user_id,
            name=body.name,
            backend=body.backend,
            base_url=body.base_url,
            model=body.model,
        )
    except ValueError as exc:
        msg = str(exc)
        code = (
            status.HTTP_409_CONFLICT
            if "already exists" in msg
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=code, detail=msg) from exc
    return service.profile_to_dict(profile)


@router.get("/connections")
async def list_profiles(
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    profiles = await service.list_profiles(session, user_id=user_id)
    return [service.profile_to_dict(p) for p in profiles]


@router.get("/connections/{profile_id}")
async def get_profile(
    profile_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    profile = await service.get_profile(session, user_id=user_id, profile_id=profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="connection profile not found")
    return service.profile_to_dict(profile)


@router.post("/connections/{profile_id}/activate")
async def activate_profile(
    profile_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    profile = await service.set_active(session, user_id=user_id, profile_id=profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="connection profile not found")
    return service.profile_to_dict(profile)


@router.get("/connections/{profile_id}/health")
async def profile_health(
    profile_id: str,
    request: Request,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    profile = await service.get_profile(session, user_id=user_id, profile_id=profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="connection profile not found")
    # Probe seam: tests (and future diagnostics) may install a fake prober
    # on the app state; production uses the default prober.
    prober = getattr(request.app.state, "prober", None)
    result = service.probe_profile(profile, prober=prober)
    return result.to_dict()


@router.delete("/connections/{profile_id}")
async def delete_profile(
    profile_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    if not await service.delete_profile(
        session, user_id=user_id, profile_id=profile_id
    ):
        raise HTTPException(status_code=404, detail="connection profile not found")
    return {"ok": True}
