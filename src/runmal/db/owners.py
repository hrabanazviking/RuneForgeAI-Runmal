"""Local owner resolution (S106): single-user loopback app."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.models import User


async def get_or_create_owner(session: AsyncSession) -> User:
    owner = (await session.execute(select(User).limit(1))).scalar_one_or_none()
    if owner is None:
        owner = User(name="owner")
        session.add(owner)
        await session.flush()
        await session.commit()
    return owner
