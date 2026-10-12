"""Connection profiles + health probes (S211).

A profile names a backend (fake / ollama / openai-shaped), its base URL,
and its model. Exactly one profile per user is active. Secrets are never
stored on a profile.

Health probes report reachability, latency, and capabilities. The probe
callable is injectable (tests use a fake probe); the default probe answers
locally for the fake backend and HTTP-probes real base URLs otherwise.
"""

from __future__ import annotations

import time
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Callable

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.models import ConnectionProfile

VALID_BACKENDS = ("fake", "ollama", "openai")

#: Capabilities a healthy backend of each kind advertises.
BACKEND_CAPABILITIES: dict[str, list[str]] = {
    "fake": ["streaming", "offline"],
    "ollama": ["streaming", "local-models"],
    "openai": ["streaming"],
}


@dataclass
class ProbeOutcome:
    ok: bool
    capabilities: list[str] = field(default_factory=list)
    detail: str = ""


# A prober maps a profile to an outcome; latency is measured around it.
Prober = Callable[[ConnectionProfile], ProbeOutcome]


@dataclass
class HealthResult:
    profile_id: str
    ok: bool
    latency_ms: float
    capabilities: list[str]
    detail: str

    def to_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "ok": self.ok,
            "latency_ms": round(self.latency_ms, 2),
            "capabilities": self.capabilities,
            "detail": self.detail,
        }


def default_prober(profile: ConnectionProfile) -> ProbeOutcome:
    if profile.backend == "fake":
        return ProbeOutcome(True, list(BACKEND_CAPABILITIES["fake"]), "fake backend")
    if not profile.base_url:
        return ProbeOutcome(False, [], "no base_url configured")
    try:
        req = urllib.request.Request(profile.base_url, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:  # noqa: S310
            ok = 200 <= resp.status < 500
        caps = list(BACKEND_CAPABILITIES.get(profile.backend, [])) if ok else []
        return ProbeOutcome(ok, caps, f"HTTP probe of {profile.backend}")
    except Exception as exc:  # probe failures are data, not exceptions
        return ProbeOutcome(False, [], f"unreachable: {exc.__class__.__name__}")


def probe_profile(
    profile: ConnectionProfile, prober: Prober | None = None
) -> HealthResult:
    prober = prober or default_prober
    start = time.perf_counter()
    outcome = prober(profile)
    latency_ms = (time.perf_counter() - start) * 1000.0
    return HealthResult(
        profile_id=profile.id,
        ok=outcome.ok,
        latency_ms=latency_ms,
        capabilities=outcome.capabilities,
        detail=outcome.detail,
    )


def _now() -> datetime:
    return datetime.now(UTC)


def profile_to_dict(profile: ConnectionProfile) -> dict:
    return {
        "id": profile.id,
        "name": profile.name,
        "backend": profile.backend,
        "base_url": profile.base_url,
        "model": profile.model,
        "is_active": profile.is_active,
        "created_at": profile.created_at.isoformat(),
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


async def _get_owned(
    session: AsyncSession, user_id: str, profile_id: str
) -> ConnectionProfile | None:
    result = await session.execute(
        select(ConnectionProfile).where(
            ConnectionProfile.id == profile_id,
            ConnectionProfile.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def create_profile(
    session: AsyncSession,
    user_id: str,
    name: str,
    backend: str = "fake",
    base_url: str = "",
    model: str = "",
) -> ConnectionProfile:
    if not name:
        raise ValueError("profile name must not be empty")
    if backend not in VALID_BACKENDS:
        raise ValueError(f"unknown backend: {backend!r}")
    existing = await list_profiles(session, user_id)
    profile = ConnectionProfile(
        user_id=user_id,
        name=name,
        backend=backend,
        base_url=base_url,
        model=model,
        is_active=not existing,  # the first profile becomes active
    )
    session.add(profile)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ValueError(f"profile name already exists: {name!r}") from exc
    return profile


async def list_profiles(
    session: AsyncSession, user_id: str
) -> list[ConnectionProfile]:
    result = await session.execute(
        select(ConnectionProfile)
        .where(ConnectionProfile.user_id == user_id)
        .order_by(ConnectionProfile.name)
    )
    return list(result.scalars().all())


async def get_profile(
    session: AsyncSession, user_id: str, profile_id: str
) -> ConnectionProfile | None:
    return await _get_owned(session, user_id, profile_id)


async def set_active(
    session: AsyncSession, user_id: str, profile_id: str
) -> ConnectionProfile | None:
    """Make exactly this profile active for the user (single-active rule)."""
    profile = await _get_owned(session, user_id, profile_id)
    if profile is None:
        return None
    await session.execute(
        update(ConnectionProfile)
        .where(ConnectionProfile.user_id == user_id)
        .values(is_active=False)
    )
    profile.is_active = True
    profile.updated_at = _now()
    await session.commit()
    return profile


async def get_active(
    session: AsyncSession, user_id: str
) -> ConnectionProfile | None:
    result = await session.execute(
        select(ConnectionProfile).where(
            ConnectionProfile.user_id == user_id,
            ConnectionProfile.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def delete_profile(
    session: AsyncSession, user_id: str, profile_id: str
) -> bool:
    if await _get_owned(session, user_id, profile_id) is None:
        return False
    await session.execute(
        delete(ConnectionProfile).where(ConnectionProfile.id == profile_id)
    )
    await session.commit()
    return True
