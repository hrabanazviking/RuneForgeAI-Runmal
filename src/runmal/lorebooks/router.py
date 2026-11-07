"""Lorebook + lore entry REST API (S201). All routes require the local bearer credential."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session
from runmal.lorebooks import scopes as lore_scopes
from runmal.lorebooks import service, transfer
from runmal.lorebooks.preview import preview_activation
from runmal.lorebooks.scan import MAX_RECURSIVE_SCAN_DEPTH
from runmal.lorebooks.service import entry_to_dict, lorebook_to_dict
from runmal.lorebooks.windows import ScanSettings, check_scan_mode

router = APIRouter(tags=["lorebooks"])


class LorebookCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    scan_depth: int = Field(default=4, ge=1)
    token_budget: int | None = Field(default=None, ge=1)
    scan_mode: str = "depth"
    scan_external_context: bool = False


class LorebookUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    scan_depth: int | None = Field(default=None, ge=1)
    token_budget: int | None = Field(default=None, ge=1)
    scan_mode: str | None = None
    scan_external_context: bool | None = None


class EntryCreate(BaseModel):
    name: str = ""
    content: str = ""
    keys: list[str] = Field(default_factory=list)
    secondary_keys: list[str] = Field(default_factory=list)
    selective_logic: str = "and_any"
    inclusion_group: str = ""
    group_weight: int = Field(default=100, ge=0)
    probability: int = Field(default=100, ge=0, le=100)
    priority: int = 100
    position: str = "before_char"
    depth: int | None = Field(default=None, ge=0)
    role: str = "system"
    enabled: bool = True
    constant: bool = False
    vectorised: bool = False
    case_sensitive: bool = False
    whole_word: bool = True
    sticky_prompts: int = Field(default=0, ge=0)
    cooldown_prompts: int = Field(default=0, ge=0)
    delay_prompts: int = Field(default=0, ge=0)


class EntryUpdate(BaseModel):
    name: str | None = None
    content: str | None = None
    keys: list[str] | None = None
    secondary_keys: list[str] | None = None
    selective_logic: str | None = None
    inclusion_group: str | None = None
    group_weight: int | None = Field(default=None, ge=0)
    probability: int | None = Field(default=None, ge=0, le=100)
    priority: int | None = None
    position: str | None = None
    depth: int | None = Field(default=None, ge=0)
    role: str | None = None
    enabled: bool | None = None
    constant: bool | None = None
    vectorised: bool | None = None
    case_sensitive: bool | None = None
    whole_word: bool | None = None
    sticky_prompts: int | None = Field(default=None, ge=0)
    cooldown_prompts: int | None = Field(default=None, ge=0)
    delay_prompts: int | None = Field(default=None, ge=0)


class PreviewRequest(BaseModel):
    messages: list[str] = Field(default_factory=list)
    scan_depth: int | None = Field(default=None, ge=1)
    token_budget: int | None = Field(default=None, ge=1)
    seed: int | None = None
    vector_hit_ids: list[str] = Field(default_factory=list)
    vector_threshold: float | None = Field(default=None, ge=-1, le=1)
    vector_max_entries: int | None = Field(default=None, ge=1)
    roll_context: str = ""
    scan_mode: str | None = None
    scan_external_context: bool | None = None
    external_context: list[str] = Field(default_factory=list)
    # Editor depth (P-042): the P-031 recursive-scan opt-in was
    # honoured by preview_activation but carried by no API shape;
    # it is a first-class preview control now.
    recursive_scan: bool = False
    max_recursion_depth: int | None = Field(default=None, ge=0)


class InspectRequest(PreviewRequest):
    """P-043 activation-inspector request: the preview fields
    plus opt-in recursive scanning."""

    recursive_scan: bool = False


def _service_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


@router.post("/lorebooks", status_code=status.HTTP_201_CREATED)
async def create_lorebook(
    body: LorebookCreate,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        book = await service.create_lorebook(
            session,
            user_id,
            body.name,
            body.description,
            body.scan_depth,
            body.token_budget,
            scan_mode=body.scan_mode,
            scan_external_context=body.scan_external_context,
        )
    except ValueError as exc:
        raise _service_error(exc) from exc
    return lorebook_to_dict(book)


@router.get("/lorebooks")
async def list_lorebooks(
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    return [
        lorebook_to_dict(book, count)
        for book, count in await service.list_lorebooks(session, user_id)
    ]


@router.post("/lorebooks/import", status_code=status.HTTP_201_CREATED)
async def import_lorebook(
    body: dict,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Import a lorebook in native or world-info shape (S304)."""
    try:
        book = await transfer.import_book(session, user_id, body)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    entries = await service.list_entries(session, user_id, book.id)
    return lorebook_to_dict(book, len(entries or []))


@router.post("/lorebooks/import-pack", status_code=status.HTTP_201_CREATED)
async def import_lorebook_pack(
    body: dict,
    on_conflict: str = "create_new",
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Import a lorebook sharing pack (P-045).

    Never overwrites: an exact duplicate returns the existing
    book with a 200 and ``pack_import.duplicate_exact`` set;
    a same-name collision creates a fresh book by default or
    refuses with ``?on_conflict=reject``.
    """
    from fastapi.responses import JSONResponse

    from runmal.lorebooks import packs

    try:
        book, report = await packs.import_pack(
            session, user_id, body, on_conflict=on_conflict
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    entries = await service.list_entries(session, user_id, book.id)
    payload = lorebook_to_dict(book, len(entries or []))
    payload["pack_import"] = report
    return JSONResponse(
        content=payload,
        status_code=200 if report["duplicate_exact"] else 201,
    )


@router.post("/lorebooks/pack/inspect")
async def inspect_lorebook_pack(
    body: dict,
    user_id: str = Depends(get_owner_id),
):
    """Validate a pack and report on it WITHOUT importing (P-045).

    The hub's pre-flight: format, manifest, provenance and the
    verified content checksum, as data. Owner-scoped like every
    lorebook route (the credential dependency is the scope);
    nothing is written.
    """
    from runmal.lorebooks import packs

    try:
        return packs.inspect_pack(body)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get("/lorebooks/{book_id}/export")
async def export_lorebook(
    book_id: str,
    format: str = "native",
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    book = await service.get_lorebook(session, user_id, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="lorebook not found")
    entries = await service.list_entries(session, user_id, book_id)
    book_dict = lorebook_to_dict(book, len(entries or []))
    entry_dicts = [entry_to_dict(e) for e in entries or []]
    if format == "native":
        return transfer.export_book(book_dict, entry_dicts)
    if format == "worldinfo":
        # P-019: the ST world-info shape, from the natively-modelled
        # fields only (the DB holds no Part III extras to hand back).
        from runmal.lorebooks.interop import worldinfo_from_native

        return worldinfo_from_native(book_dict, entry_dicts)
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"unknown export format: {format!r} (valid: native, worldinfo)",
    )


@router.get("/lorebooks/{book_id}/pack")
async def export_lorebook_pack(
    book_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Export one lorebook as a sharing pack (P-045): the native
    payload sealed in the pack envelope with its manifest and
    provenance (schema runmal-p045-lorebook-pack-v1)."""
    from runmal.lorebooks import packs

    book = await service.get_lorebook(session, user_id, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="lorebook not found")
    entries = await service.list_entries(session, user_id, book_id)
    book_dict = lorebook_to_dict(book, len(entries or []))
    entry_dicts = [entry_to_dict(e) for e in entries or []]
    return packs.build_pack(book_dict, entry_dicts)


@router.post("/lorebooks/{book_id}/preview")
async def preview_lorebook(
    book_id: str,
    body: PreviewRequest,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Activation preview (roadmap S209): run the server scan/activation/
    budget pipeline over sample messages and report, per entry, whether it
    would be injected and why. Unset scan_depth/token_budget fall back to
    the book's stored values. Unset scan settings (P-037: scan_mode /
    scan_external_context) likewise fall back to the book's stored
    settings; external_context carries the caller's external texts."""
    book = await service.get_lorebook(session, user_id, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="lorebook not found")
    entries = await service.list_entries(session, user_id, book_id) or []
    book_settings = ScanSettings.from_book(book)
    scan_depth = body.scan_depth if body.scan_depth is not None else book_settings.scan_depth
    token_budget = body.token_budget if body.token_budget is not None else book.token_budget
    scan_mode = body.scan_mode if body.scan_mode is not None else book_settings.scan_mode
    scan_external = (
        body.scan_external_context
        if body.scan_external_context is not None
        else book_settings.scan_external_context
    )
    try:
        # Strict at the API boundary: a bad mode override is a 422,
        # never a silent fall back to a different window.
        check_scan_mode(scan_mode)
        # Vectorised lore (P-041): with no caller-supplied vector
        # hits, the embedding matcher runs live -- the owner's
        # active embedding profile's backend, or the deterministic
        # local backend when no profile is active -- over the same
        # resolved scan window the preview itself will use.
        vector_match = None
        if not body.vector_hit_ids:
            from runmal.lorebooks.vector_match import (
                match_vectorised,
                resolve_lore_embedding_backend,
            )
            from runmal.lorebooks.windows import ScanSettings as _ScanSettings

            backend = await resolve_lore_embedding_backend(session, user_id)
            outcome = await match_vectorised(
                entries,
                body.messages,
                backend=backend,
                threshold=body.vector_threshold,
                max_entries=body.vector_max_entries,
                settings=_ScanSettings.normalised(
                    scan_depth=scan_depth,
                    scan_mode=scan_mode,
                    scan_external_context=scan_external,
                ),
                external_context=body.external_context,
            )
            if outcome.candidates:
                vector_match = outcome
        result = preview_activation(
            entries, body.messages, scan_depth, token_budget, seed=body.seed,
            vector_hit_ids=set(body.vector_hit_ids) if body.vector_hit_ids else None,
            vector_match=vector_match,
            roll_context=body.roll_context,
            scan_mode=scan_mode,
            scan_external_context=scan_external,
            external_context=body.external_context,
            recursive_scan=body.recursive_scan,
            max_recursion_depth=(
                body.max_recursion_depth
                if body.max_recursion_depth is not None
                else MAX_RECURSIVE_SCAN_DEPTH
            ),
        )
    except ValueError as exc:
        raise _service_error(exc) from exc
    result["book_id"] = book.id
    return result


@router.get("/lorebooks/editor-schema")
async def lorebook_editor_schema(
    user_id: str = Depends(get_owner_id),
):
    """P-042 editor census: every engine-honoured lorebook field,
    the API model that carries it and the editor element that edits
    it. The editor battery pins this census against the models,
    the service dicts and the shipped page/JS."""
    from runmal.lorebooks.editor import editor_schema

    return editor_schema()
@router.post("/lorebooks/{book_id}/inspect")
async def inspect_lorebook(
    book_id: str,
    body: InspectRequest,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Activation inspector (P-043): like the preview, but every
    entry's outcome is explained as data -- matched keys and
    where they matched, the selective-logic gate, the recorded
    probability roll, group exclusion, recursion, vector vs
    keyword-fallback, placement and the budget verdict, plus the
    near misses (secondary-gate refusals above all). Part XIII's
    Inspector consumes this payload (``schema``
    runmal-p043-activation-inspection-v1)."""
    book = await service.get_lorebook(session, user_id, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="lorebook not found")
    entries = await service.list_entries(session, user_id, book_id) or []
    book_settings = ScanSettings.from_book(book)
    scan_depth = body.scan_depth if body.scan_depth is not None else book_settings.scan_depth
    token_budget = body.token_budget if body.token_budget is not None else book.token_budget
    scan_mode = body.scan_mode if body.scan_mode is not None else book_settings.scan_mode
    scan_external = (
        body.scan_external_context
        if body.scan_external_context is not None
        else book_settings.scan_external_context
    )
    try:
        check_scan_mode(scan_mode)
        vector_match = None
        if not body.vector_hit_ids:
            from runmal.lorebooks.vector_match import (
                match_vectorised,
                resolve_lore_embedding_backend,
            )
            from runmal.lorebooks.windows import ScanSettings as _ScanSettings

            backend = await resolve_lore_embedding_backend(session, user_id)
            outcome = await match_vectorised(
                entries,
                body.messages,
                backend=backend,
                threshold=body.vector_threshold,
                max_entries=body.vector_max_entries,
                settings=_ScanSettings.normalised(
                    scan_depth=scan_depth,
                    scan_mode=scan_mode,
                    scan_external_context=scan_external,
                ),
                external_context=body.external_context,
            )
            if outcome.candidates:
                vector_match = outcome
        from runmal.lorebooks.inspector import inspect_activation

        result = inspect_activation(
            entries, body.messages, scan_depth, token_budget, seed=body.seed,
            vector_hit_ids=set(body.vector_hit_ids) if body.vector_hit_ids else None,
            vector_match=vector_match,
            vector_threshold=body.vector_threshold,
            roll_context=body.roll_context,
            recursive_scan=body.recursive_scan,
            scan_mode=scan_mode,
            scan_external_context=scan_external,
            external_context=body.external_context,
            lorebook_id=book.id,
        )
    except ValueError as exc:
        raise _service_error(exc) from exc
    result["book_id"] = book.id
    return result


@router.get("/lorebooks/{book_id}")
async def get_lorebook(
    book_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    book = await service.get_lorebook(session, user_id, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="lorebook not found")
    entries = await service.list_entries(session, user_id, book_id) or []
    payload = lorebook_to_dict(book, len(entries))
    payload["entries"] = [entry_to_dict(e) for e in entries]
    return payload


@router.patch("/lorebooks/{book_id}")
async def update_lorebook(
    book_id: str,
    body: LorebookUpdate,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        book = await service.update_lorebook(
            session,
            user_id,
            book_id,
            name=body.name,
            description=body.description,
            scan_depth=body.scan_depth,
            token_budget=body.token_budget,
            scan_mode=body.scan_mode,
            scan_external_context=body.scan_external_context,
        )
    except ValueError as exc:
        raise _service_error(exc) from exc
    if book is None:
        raise HTTPException(status_code=404, detail="lorebook not found")
    return lorebook_to_dict(book)


@router.delete("/lorebooks/{book_id}")
async def delete_lorebook(
    book_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    if not await service.delete_lorebook(session, user_id, book_id):
        raise HTTPException(status_code=404, detail="lorebook not found")
    return {"deleted": True, "id": book_id}


@router.post("/lorebooks/{book_id}/entries", status_code=status.HTTP_201_CREATED)
async def create_entry(
    book_id: str,
    body: EntryCreate,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        entry = await service.create_entry(
            session,
            user_id,
            book_id,
            name=body.name,
            content=body.content,
            keys=body.keys,
            secondary_keys=body.secondary_keys,
            selective_logic=body.selective_logic,
            inclusion_group=body.inclusion_group,
            group_weight=body.group_weight,
            probability=body.probability,
            priority=body.priority,
            position=body.position,
            depth=body.depth,
            role=body.role,
            enabled=body.enabled,
            constant=body.constant,
            vectorised=body.vectorised,
            case_sensitive=body.case_sensitive,
            whole_word=body.whole_word,
            sticky_prompts=body.sticky_prompts,
            cooldown_prompts=body.cooldown_prompts,
            delay_prompts=body.delay_prompts,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="lorebook not found") from None
    except ValueError as exc:
        raise _service_error(exc) from exc
    return entry_to_dict(entry)


@router.get("/lorebooks/{book_id}/entries")
async def list_entries(
    book_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    entries = await service.list_entries(session, user_id, book_id)
    if entries is None:
        raise HTTPException(status_code=404, detail="lorebook not found")
    return [entry_to_dict(e) for e in entries]


@router.get("/lorebooks/{book_id}/entries/{entry_id}")
async def get_entry(
    book_id: str,
    entry_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    entry = await service.get_entry(session, user_id, book_id, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="entry not found")
    return entry_to_dict(entry)


@router.patch("/lorebooks/{book_id}/entries/{entry_id}")
async def update_entry(
    book_id: str,
    entry_id: str,
    body: EntryUpdate,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    fields = body.model_dump(exclude_unset=True)
    try:
        entry = await service.update_entry(session, user_id, book_id, entry_id, **fields)
    except ValueError as exc:
        raise _service_error(exc) from exc
    if entry is None:
        raise HTTPException(status_code=404, detail="entry not found")
    return entry_to_dict(entry)


@router.delete("/lorebooks/{book_id}/entries/{entry_id}")
async def delete_entry(
    book_id: str,
    entry_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    if not await service.delete_entry(session, user_id, book_id, entry_id):
        raise HTTPException(status_code=404, detail="entry not found")
    return {"deleted": True, "id": entry_id}


class ScopeAssign(BaseModel):
    scope_kind: str
    owner_id: str | None = None
    token_budget: int | None = Field(default=None, ge=0)
    position: int = 0


class LayeredPreviewRequest(BaseModel):
    messages: list[str] = Field(default_factory=list)
    seed: int | None = None
    persona_character_id: str | None = None


@router.put("/lorebooks/{book_id}/scope", status_code=status.HTTP_201_CREATED)
async def assign_lorebook_scope(
    book_id: str,
    body: ScopeAssign,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        scope = await lore_scopes.assign_scope(
            session,
            user_id,
            book_id,
            body.scope_kind,
            body.owner_id,
            body.token_budget,
            body.position,
        )
    except ValueError as exc:
        if "not found" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise _service_error(exc) from exc
    book = await service.get_lorebook(session, user_id, book_id)
    return lore_scopes.scope_to_dict(scope, book)


@router.delete("/lorebooks/{book_id}/scope")
async def unassign_lorebook_scope(
    book_id: str,
    scope_kind: str,
    owner_id: str | None = None,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        removed = await lore_scopes.unassign_scope(
            session, user_id, book_id, scope_kind, owner_id
        )
    except ValueError as exc:
        raise _service_error(exc) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="scope assignment not found")
    return {"deleted": True, "lorebook_id": book_id, "scope_kind": scope_kind}


@router.get("/lorebooks/{book_id}/scopes")
async def list_lorebook_scopes(
    book_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    rows = await lore_scopes.list_book_scopes(session, user_id, book_id)
    if rows is None:
        raise HTTPException(status_code=404, detail="lorebook not found")
    book = await service.get_lorebook(session, user_id, book_id)
    return {
        "lorebook_id": book_id,
        "scopes": [lore_scopes.scope_to_dict(row, book) for row in rows],
    }


@router.get("/lore-scopes")
async def list_layer_scopes(
    scope_kind: str,
    owner_id: str | None = None,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        rows = await lore_scopes.list_scopes(session, user_id, scope_kind, owner_id)
    except ValueError as exc:
        raise _service_error(exc) from exc
    out = []
    for row in rows:
        book = await service.get_lorebook(session, user_id, row.lorebook_id)
        out.append(lore_scopes.scope_to_dict(row, book))
    return {"scope_kind": scope_kind, "scopes": out}


@router.post("/chats/{chat_id}/lore-preview")
async def layered_lore_preview(
    chat_id: str,
    body: LayeredPreviewRequest,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    result = await lore_scopes.layered_preview(
        session,
        user_id,
        chat_id=chat_id,
        persona_character_id=body.persona_character_id,
        messages=body.messages,
        seed=body.seed,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return result
