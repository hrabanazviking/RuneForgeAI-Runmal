"""The owner's DEFAULT chat backend profile (W-12).

One profile may be named the house default. Generation resolution
(the generation router, the bridge, continue/impersonate) is:

1. a profile named by the request itself,
2. the profile pinned to the chat,
3. THIS default, when one is set,
4. the offline fake default (labelled by every surface; a
   fake-kind profile chosen AS the default is a deliberate Demo
   and reaches step 3 honestly, never step 4 by fall-through).

Storage is the ``default_chat_profile`` table (m0043): one row per
owner holding a plain profile id, mirroring the S311 embedding
activation's shape and axis law — setting or clearing the default
touches no chat row and no profile row. A dangling id (the profile
was deleted after being named) reads as "no default", never as an
error, so a deleted default can never wedge generation.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.backends import profiles as backend_profiles
from runmal.db.models import BackendProfile, DefaultChatProfile, _utcnow

__all__ = [
    "clear_default_profile",
    "get_default_profile",
    "get_default_profile_id",
    "resolve_effective_profile",
    "set_default_profile",
]


async def get_default_profile_id(session: AsyncSession, user_id: str) -> str:
    """The named default's id, or "" when none is named."""
    row = await session.get(DefaultChatProfile, user_id)
    return str(row.profile_id or "") if row is not None else ""


async def get_default_profile(
    session: AsyncSession, user_id: str
) -> BackendProfile | None:
    """The named default profile, or None (unset or dangling)."""
    profile_id = await get_default_profile_id(session, user_id)
    if not profile_id:
        return None
    return await backend_profiles.get_profile(session, user_id, profile_id)


async def set_default_profile(
    session: AsyncSession, user_id: str, profile_id: str
) -> BackendProfile:
    """Name `profile_id` the owner's default chat profile.

    Raises KeyError for a missing or foreign profile — a default
    that names nothing is never written."""
    profile = await backend_profiles.get_profile(session, user_id, profile_id)
    if profile is None:
        raise KeyError(f"profile not found: {profile_id}")
    row = await session.get(DefaultChatProfile, user_id)
    if row is None:
        row = DefaultChatProfile(user_id=user_id)
        session.add(row)
    row.profile_id = profile_id
    row.updated_at = _utcnow()
    await session.commit()
    return profile


async def clear_default_profile(session: AsyncSession, user_id: str) -> None:
    """Unname the default. Chats and profiles are untouched."""
    row = await session.get(DefaultChatProfile, user_id)
    if row is not None:
        row.profile_id = ""
        row.updated_at = _utcnow()
        await session.commit()


async def resolve_effective_profile(
    session: AsyncSession, user_id: str, chat
) -> BackendProfile | None:
    """The profile a chat's generation resolves through, before
    the fake fall-through: the chat's pin when it resolves, else
    the house default when one is set, else None."""
    pin = getattr(chat, "backend_profile_id", None) if chat is not None else None
    if pin:
        profile = await backend_profiles.get_profile(session, user_id, str(pin))
        if profile is not None:
            return profile
    return await get_default_profile(session, user_id)
