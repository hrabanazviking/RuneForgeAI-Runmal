"""Scenario API: file interop (P-026) + stored definitions (P-131)
+ scenario-to-chat binding (P-132).

P-026 roads (stateless): parse a scenario file and report
honestly, and re-export it. Those roads are unchanged.

P-131 (Part IX opener, DERIVED scope) adds the definition
roads on the same prefix: scenarios are now stored —
versioned, owner-scoped citizens in runmal.scenarios.store
— and can be created, listed, read, replaced and deleted.
Owner scoping: a definition that is unknown — or owned by
someone else — answers 404 on every parameterised road;
existence never leaks. The truth layer lives in
runmal.scenarios.store; this module is only the HTTP shape.
No road here plays a scenario back or executes anything a
definition carries (P-027: content is data, never code).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session
from runmal.scenarios.binding import (
    BindingConflictError,
    BindingNotFoundError,
    ScenarioBindingStore,
    bind_scenario,
    bindings_path,
    get_binding,
    unbind,
)
from runmal.scenarios.fileexport import export_native, export_voxta
from runmal.scenarios.fileimport import parse_scenario_file
from runmal.scenarios.filemodels import ScenarioParseError
from runmal.scenarios.store import (
    ScenarioStore,
    ScenarioStoreError,
    definitions_path,
)

router = APIRouter(tags=["scenarios"])


def _store() -> ScenarioStore:
    return ScenarioStore(definitions_path())


@router.post("/scenarios/import", status_code=status.HTTP_200_OK)
async def import_scenario(
    body: dict,
    user_id: str = Depends(get_owner_id),
):
    """Parse a scenario file (Voxta-shaped or native) and report honestly."""
    try:
        parsed = parse_scenario_file(body)
    except ScenarioParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return {
        "source_format": parsed.source_format,
        "scenario": export_native(parsed),
        "report": parsed.report.to_dict() if parsed.report else None,
    }


@router.post("/scenarios/export", status_code=status.HTTP_200_OK)
async def export_scenario(
    body: dict,
    format: str | None = None,
    user_id: str = Depends(get_owner_id),
):
    """Parse a scenario file, then re-export it in the requested format."""
    fmt = format or "voxta"
    if fmt not in ("voxta", "native"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown export format: {fmt!r} (valid: voxta, native)",
        )
    try:
        parsed = parse_scenario_file(body)
    except ScenarioParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return export_voxta(parsed) if fmt == "voxta" else export_native(parsed)


# ------------------------------------------- definitions (P-131)


@router.post("/scenarios", status_code=status.HTTP_201_CREATED)
async def create_scenario_definition(
    body: dict,
    user_id: str = Depends(get_owner_id),
):
    """Store a scenario file as an owned definition (P-131).

    The body is exactly what /scenarios/import accepts;
    what P-026 refuses, this road refuses (422) and
    nothing is stored.
    """
    try:
        record = _store().create(user_id, body)
    except (ScenarioParseError, ScenarioStoreError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return record.to_dict()


@router.get("/scenarios", status_code=status.HTTP_200_OK)
async def list_scenario_definitions(
    user_id: str = Depends(get_owner_id),
):
    """The caller's definitions, summary shape, creation order."""
    rows = _store().list_for_owner(user_id)
    return {
        "scenarios": [row.summary() for row in rows],
        "total": len(rows),
    }


@router.get("/scenarios/{definition_id}", status_code=status.HTTP_200_OK)
async def get_scenario_definition(
    definition_id: str,
    user_id: str = Depends(get_owner_id),
):
    """One owned definition in full, or 404."""
    record = _store().get(definition_id, user_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="scenario definition not found",
        )
    return record.to_dict()


@router.put("/scenarios/{definition_id}", status_code=status.HTTP_200_OK)
async def replace_scenario_definition(
    definition_id: str,
    body: dict,
    user_id: str = Depends(get_owner_id),
):
    """Replace one owned definition (revision + 1), or 404 / 422.

    The store decides existence before it looks at the
    body, so an unknown or foreign id answers 404 even
    with a malformed body — never a parse verdict about
    someone else's data.
    """
    try:
        record = _store().replace(definition_id, user_id, body)
    except (ScenarioParseError, ScenarioStoreError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="scenario definition not found",
        )
    return record.to_dict()


@router.delete("/scenarios/{definition_id}", status_code=status.HTTP_200_OK)
async def delete_scenario_definition(
    definition_id: str,
    user_id: str = Depends(get_owner_id),
):
    """Delete one owned definition, or 404."""
    record = _store().remove(definition_id, user_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="scenario definition not found",
        )
    return {"id": record.id, "deleted": True}


# --------------------------------------------- binding (P-132)


def _bindings() -> ScenarioBindingStore:
    return ScenarioBindingStore(bindings_path())


@router.post("/scenarios/{definition_id}/bind", status_code=status.HTTP_201_CREATED)
async def bind_scenario_definition(
    definition_id: str,
    body: dict,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Bind one owned definition to one owned empty chat (P-132).

    The definition's bootstrap lines become the chat's
    opening messages and its initial flags / variables seed
    through P-093, exactly as the binding record returned
    here accounts. Unknown or foreign definition OR chat
    answers 404 (existence never leaks); a group room, an
    already-bound chat or a chat with messages answers 409;
    a body without a string chat_id answers 422. Nothing is
    written on any refusal.
    """
    chat_id = body.get("chat_id") if isinstance(body, dict) else None
    if not isinstance(chat_id, str) or not chat_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="chat_id must be a non-empty string",
        )
    try:
        record = await bind_scenario(session, user_id, definition_id, chat_id)
    except BindingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except BindingConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return record.to_dict()


@router.get("/scenarios/bindings/{chat_id}", status_code=status.HTTP_200_OK)
async def get_scenario_binding(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
):
    """The chat's active binding record, or 404."""
    record = get_binding(_bindings(), user_id, chat_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="scenario binding not found",
        )
    return record.to_dict()


@router.delete("/scenarios/bindings/{chat_id}", status_code=status.HTTP_200_OK)
async def delete_scenario_binding(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
):
    """Remove the chat's binding record, or 404.

    Only the record goes: messages and variables the
    binding seeded are the chat's own truth and stay —
    the answer says so plainly.
    """
    record = unbind(_bindings(), user_id, chat_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="scenario binding not found",
        )
    return {
        "chat_id": record.chat_id,
        "binding_id": record.id,
        "unbound": True,
        "seeded_content_kept": True,
    }
