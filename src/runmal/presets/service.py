"""Sampling presets: named canonical parameter bags (S207).

A preset is a user-owned, variable-shape bag of generation parameters plus
an optional prompt-template reference. Canonical fields are validated
(types and ranges); unknown fields are preserved verbatim so backends with
extra knobs keep working -- the bag is canonical in shape, not closed.

``template_ref`` names a prompt template. The stored-template registry is
a future slice's work; for now it is an opaque string reference carried
alongside the parameters.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.models import SamplingPreset

# Canonical fields: (accepted python types, range predicate or None).
_CANONICAL: dict[str, tuple[tuple[type, ...], object]] = {
    "temperature": ((int, float), lambda v: v >= 0),
    "top_p": ((int, float), lambda v: 0 < v <= 1),
    "top_k": ((int,), lambda v: v >= 0),
    "max_tokens": ((int,), lambda v: v >= 1),
    "frequency_penalty": ((int, float), None),
    "presence_penalty": ((int, float), None),
    "repetition_penalty": ((int, float), None),
    "stop": ((list,), lambda v: all(isinstance(s, str) for s in v)),
    "seed": ((int,), lambda v: v >= 0),
}


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_params(params: dict | None) -> dict:
    """Validate a parameter bag; return a JSON-safe normalized copy."""
    if params is None:
        return {}
    if not isinstance(params, dict):
        raise ValueError("params must be an object")
    out: dict = {}
    for key, value in params.items():
        if not isinstance(key, str) or not key:
            raise ValueError("param names must be non-empty strings")
        if key in _CANONICAL:
            types, check = _CANONICAL[key]
            if int in types and float not in types:
                ok = _is_int(value)
            else:
                ok = isinstance(value, types) and not isinstance(value, bool)
            if not ok:
                raise ValueError(f"param {key!r} has wrong type")
            if check is not None and not check(value):
                raise ValueError(f"param {key!r} out of range")
            out[key] = value
        else:
            # Unknown (backend-specific) fields ride along untouched, but
            # must survive a JSON round trip.
            try:
                json.dumps(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"param {key!r} is not JSON-serializable") from exc
            out[key] = value
    return out


def _now() -> datetime:
    return datetime.now(UTC)


def preset_to_dict(preset: SamplingPreset) -> dict:
    return {
        "id": preset.id,
        "name": preset.name,
        "params": json.loads(preset.params_json),
        "template_ref": preset.template_ref,
        "created_at": preset.created_at.isoformat(),
        "updated_at": preset.updated_at.isoformat() if preset.updated_at else None,
    }


async def _get_owned(
    session: AsyncSession, user_id: str, preset_id: str
) -> SamplingPreset | None:
    result = await session.execute(
        select(SamplingPreset).where(
            SamplingPreset.id == preset_id, SamplingPreset.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def create_preset(
    session: AsyncSession,
    user_id: str,
    name: str,
    params: dict | None = None,
    template_ref: str = "",
) -> SamplingPreset:
    if not name:
        raise ValueError("preset name must not be empty")
    preset = SamplingPreset(
        user_id=user_id,
        name=name,
        params_json=json.dumps(validate_params(params)),
        template_ref=template_ref or "",
    )
    session.add(preset)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ValueError(f"preset name already exists: {name!r}") from exc
    return preset


async def list_presets(session: AsyncSession, user_id: str) -> list[SamplingPreset]:
    result = await session.execute(
        select(SamplingPreset)
        .where(SamplingPreset.user_id == user_id)
        .order_by(SamplingPreset.name)
    )
    return list(result.scalars().all())


async def get_preset(
    session: AsyncSession, user_id: str, preset_id: str
) -> SamplingPreset | None:
    return await _get_owned(session, user_id, preset_id)


async def update_preset(
    session: AsyncSession,
    user_id: str,
    preset_id: str,
    name: str | None = None,
    params: dict | None = None,
    template_ref: str | None = None,
) -> SamplingPreset | None:
    preset = await _get_owned(session, user_id, preset_id)
    if preset is None:
        return None
    if name is not None:
        if not name:
            raise ValueError("preset name must not be empty")
        preset.name = name
    if params is not None:
        preset.params_json = json.dumps(validate_params(params))
    if template_ref is not None:
        preset.template_ref = template_ref
    preset.updated_at = _now()
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ValueError(f"preset name already exists: {name!r}") from exc
    return preset


async def delete_preset(session: AsyncSession, user_id: str, preset_id: str) -> bool:
    if await _get_owned(session, user_id, preset_id) is None:
        return False
    await session.execute(delete(SamplingPreset).where(SamplingPreset.id == preset_id))
    await session.commit()
    return True
