"""FastAPI dependencies for DB access (S106)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.owners import get_or_create_owner


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


async def get_owner_id(session: AsyncSession = Depends(get_session)) -> str:
    return (await get_or_create_owner(session)).id
