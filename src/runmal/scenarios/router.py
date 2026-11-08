"""Scenario API: file interop (P-026) + stored definitions (P-131)
+ scenario-to-chat binding (P-132) + stored-definition file export (P-133)
+ scenario library organisation (P-134) + binding
  lifecycle read surface (P-135) + binding plan
  preview (P-136) + definition duplication (P-137) + chat-scoped bind preview (P-138).
+ definition delete-impact preview (P-139) + definition replace-impact preview (P-140).

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
P-133 (Part IX, DERIVED scope) adds the by-id export road:
a stored definition hands back a FILE through P-026's own
exporters, with an honest export report naming whatever
cannot round-trip (a Voxta file's unmappable raw values
never persisted — P-131). The service lives in
runmal.scenarios.storedexport; this module is only the
HTTP shape.
P-136 (Part IX, DERIVED scope) adds the bind-plan preview
road: P-132's pure plan_materialisation for one stored
definition, handed back read-only in an envelope naming
the definition's current revision — what binding WOULD
plant and honestly skip, visible before any chat is
committed. The service lives in
runmal.scenarios.bindpreview; this module is only the
HTTP shape.

P-138 (Part IX, DERIVED scope) adds the chat-scoped
bind-plan road: P-136's preview judged against one
named chat — bind's refusal facts (group room,
already bound, non-empty) reported as data in bind's
decision order, and the plan's seedable keys split by
P-093's own presence law into would-seed and
already-present. The service lives in
runmal.scenarios.chatpreview; this module is only the
HTTP shape.
P-139 (Part IX, DERIVED scope) adds the delete-impact
preview road: what deleting one stored definition
WOULD orphan - its bindings, which do not cascade and
would afterwards read stale on the P-135 surface, and
its organisation row, which would stay an orphan
filtered at every read - named before the irreversible
act in an envelope with standing honesty notes. The
service lives in runmal.scenarios.deletepreview; this
module is only the HTTP shape.

P-140 (Part IX, DERIVED scope) adds the replace-impact preview road: for one stored definition, the bindings a PUT replace would leave pinning a superseded revision - split by their pinned revision against the current one - the organisation row that stays live, and the next revision, all read before any replace is committed. The service lives in runmal.scenarios.replacepreview; this module is only the HTTP shape.

No road here plays a scenario back or executes anything a
definition carries (P-027: content is data, never code).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session
from runmal.scenarios.binding import (
    BindingConflictError,
    BindingNotFoundError,
    ScenarioBindingStore,
    bind_scenario,
    bindings_path,
    get_binding,
    list_bindings,
    list_bindings_for_definition,
    unbind,
)
from runmal.scenarios.fileexport import export_native, export_voxta
from runmal.scenarios.fileimport import parse_scenario_file
from runmal.scenarios.filemodels import ScenarioParseError
from runmal.scenarios.organisation import (
    ScenarioOrganisationError,
    ScenarioOrganisationStore,
    list_tags,
    organisation_path,
    organisation_view,
    query_definitions,
)
from runmal.scenarios.store import (
    ScenarioStore,
    ScenarioStoreError,
    definitions_path,
)
from runmal.scenarios.bindpreview import preview_bind_plan
from runmal.scenarios.chatpreview import preview_bind_for_chat
from runmal.scenarios.deletepreview import preview_delete_impact
from runmal.scenarios.replacepreview import preview_replace_impact
from runmal.scenarios.storedexport import (
    DEFAULT_FORMAT,
    FORMATS,
    export_stored_definition,
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


def _organisation() -> ScenarioOrganisationStore:
    return ScenarioOrganisationStore(organisation_path())


def _records_by_id(user_id: str) -> dict:
    return {
        row.definition_id: row for row in _organisation().list_for_owner(user_id)
    }


@router.get("/scenarios/library/tags", status_code=status.HTTP_200_OK)
async def list_scenario_library_tags(
    user_id: str = Depends(get_owner_id),
):
    """The caller's tag census over their definitions (P-134)."""
    rows = _store().list_for_owner(user_id)
    tags = list_tags(rows, _records_by_id(user_id))
    return {"tags": tags, "total": len(tags)}


@router.get("/scenarios/bindings", status_code=status.HTTP_200_OK)
async def list_scenario_bindings(
    user_id: str = Depends(get_owner_id),
):
    """Every binding the caller holds, summary shape (P-135).

    Declared before the {definition_id} roads so the
    literal "bindings" is never read as a definition id
    (the P-134 library/tags precedent). Summaries carry
    counts, never seeded content, and each names
    definition_exists: deleting a definition does not
    cascade into the binding store, so a stale binding is
    named here, never hidden. Pure read.
    """
    live = {row.id for row in _store().list_for_owner(user_id)}
    rows = list_bindings(_bindings(), user_id, live)
    return {"bindings": rows, "total": len(rows)}


@router.get("/scenarios", status_code=status.HTTP_200_OK)
async def list_scenario_definitions(
    q: str | None = None,
    tag: list[str] | None = Query(default=None),
    tag_mode: str = "any",
    favourites_only: bool = False,
    sort: str = "oldest",
    limit: int | None = None,
    offset: int = 0,
    user_id: str = Depends(get_owner_id),
):
    """The caller's definitions, enriched summary shape.

    With no query parameters this is exactly the P-131
    answer (creation order, every row). P-134 adds the
    library surface: q search, repeatable tag filters
    (tag_mode any / all), favourites_only, named sorts
    and limit / offset paging; total is the filtered
    count before paging. Invalid parameters answer 422.
    """
    rows = _store().list_for_owner(user_id)
    try:
        page, total = query_definitions(
            rows,
            _records_by_id(user_id),
            q=q,
            tags=tag,
            tag_mode=tag_mode,
            favourites_only=favourites_only,
            sort=sort,
            limit=limit,
            offset=offset,
        )
    except ScenarioOrganisationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return {"scenarios": page, "total": total}


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


@router.post(
    "/scenarios/{definition_id}/duplicate",
    status_code=status.HTTP_201_CREATED,
)
async def duplicate_scenario_definition(
    definition_id: str,
    user_id: str = Depends(get_owner_id),
):
    """Clone one owned definition faithfully (P-137).

    The clone is a new citizen under a fresh id: the
    source's definition and its P-131 import report
    preserved exactly, its source format preserved,
    its name carrying the house " (copy)" suffix (the
    characters S303 law). The answer is the clone's
    full record, the create road's shape. Unknown or
    foreign answers 404 — existence never leaks. No
    organisation row and no binding is carried.
    """
    record = _store().duplicate(definition_id, user_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="scenario definition not found",
        )
    return record.to_dict()



# --------------------------------- delete-impact preview (P-139)


@router.get(
    "/scenarios/{definition_id}/delete-impact",
    status_code=status.HTTP_200_OK,
)
async def preview_scenario_delete_impact(
    definition_id: str,
    user_id: str = Depends(get_owner_id),
):
    """What deleting this definition WOULD orphan (P-139).

    The envelope names the definition (id, name, its
    current revision, its source format), the bindings a
    deletion would leave stale (P-135's own summaries,
    each naming definition_exists while it is still
    true), the definition's organisation view (P-134)
    plus whether a persisted organisation row exists at
    all, impact counts read from those answers, and the
    standing honesty notes: no cascade into either
    store, seeded chat content kept, and deletion
    permanent - the stored-export road is the way to
    keep a file copy first. Unknown or foreign answers
    404 (existence never leaks). The road writes,
    deletes and cascades nothing.
    """
    record = _store().get(definition_id, user_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="scenario definition not found",
        )
    live = {row.id for row in _store().list_for_owner(user_id)}
    return preview_delete_impact(
        record, _bindings(), _organisation(), live)


# --------------------------------------- organisation (P-134)


def _owned_definition_or_404(definition_id: str, user_id: str):
    record = _store().get(definition_id, user_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="scenario definition not found",
        )
    return record


def _view(definition_id: str, user_id: str) -> dict:
    definition = _owned_definition_or_404(definition_id, user_id)
    return organisation_view(definition, _organisation().get(definition_id, user_id))


@router.get(
    "/scenarios/{definition_id}/organisation", status_code=status.HTTP_200_OK
)
async def get_scenario_organisation(
    definition_id: str,
    user_id: str = Depends(get_owner_id),
):
    """One owned definition's organisation view, or 404."""
    return _view(definition_id, user_id)


@router.put("/scenarios/{definition_id}/tags", status_code=status.HTTP_200_OK)
async def replace_scenario_tags(
    definition_id: str,
    body: dict,
    user_id: str = Depends(get_owner_id),
):
    """Replace one owned definition's tag set, or 404 / 422.

    Existence is decided before the body is judged, so a
    foreign id with invalid tags still answers 404.
    """
    _owned_definition_or_404(definition_id, user_id)
    try:
        _organisation().set_tags(definition_id, user_id, body.get("tags"))
    except ScenarioOrganisationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _view(definition_id, user_id)


@router.post("/scenarios/{definition_id}/tags", status_code=status.HTTP_200_OK)
async def add_scenario_tags(
    definition_id: str,
    body: dict,
    user_id: str = Depends(get_owner_id),
):
    """Add to one owned definition's tag set, or 404 / 422."""
    _owned_definition_or_404(definition_id, user_id)
    try:
        _organisation().add_tags(definition_id, user_id, body.get("tags"))
    except ScenarioOrganisationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _view(definition_id, user_id)


@router.delete(
    "/scenarios/{definition_id}/tags/{tag}", status_code=status.HTTP_200_OK
)
async def remove_scenario_tag(
    definition_id: str,
    tag: str,
    user_id: str = Depends(get_owner_id),
):
    """Remove one tag (absent is a no-op), or 404 / 422."""
    _owned_definition_or_404(definition_id, user_id)
    try:
        _organisation().remove_tag(definition_id, user_id, tag)
    except ScenarioOrganisationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _view(definition_id, user_id)


@router.put("/scenarios/{definition_id}/favourite", status_code=status.HTTP_200_OK)
async def set_scenario_favourite(
    definition_id: str,
    body: dict,
    user_id: str = Depends(get_owner_id),
):
    """Set one owned definition's favourite flag, or 404 / 422."""
    _owned_definition_or_404(definition_id, user_id)
    try:
        _organisation().set_favourite(
            definition_id, user_id, body.get("is_favourite")
        )
    except ScenarioOrganisationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _view(definition_id, user_id)


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


@router.get(
    "/scenarios/{definition_id}/bindings",
    status_code=status.HTTP_200_OK,
)
async def list_scenario_bindings_for_definition(
    definition_id: str,
    user_id: str = Depends(get_owner_id),
):
    """One owned definition's bindings, summary shape (P-135).

    Existence is decided before anything is read: an
    unknown or foreign definition answers 404, exactly
    like every other parameterised road. An owned
    definition with no bindings answers 200 with an
    empty list — the honest zero, not a refusal.
    """
    record = _store().get(definition_id, user_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="scenario definition not found",
        )
    live = {row.id for row in _store().list_for_owner(user_id)}
    rows = list_bindings_for_definition(
        _bindings(), user_id, definition_id, live)
    return {
        "definition_id": definition_id,
        "bindings": rows,
        "total": len(rows),
    }


# ------------------------------------- bind-plan preview (P-136)


@router.get(
    "/scenarios/{definition_id}/bind-plan",
    status_code=status.HTTP_200_OK,
)
async def preview_scenario_bind_plan(
    definition_id: str,
    user_id: str = Depends(get_owner_id),
):
    """What binding this definition WOULD do, as data (P-136).

    The envelope names the definition (id, name, its
    current revision, its source format), the plan
    P-132's bind computes from the definition alone
    (bootstrap lines mapped to chat roles with
    cast-resolved speakers, seedable flags / variables,
    and every skip with its reason), counts read from
    the plan itself, and the standing honesty notes: no
    chat has been consulted, bind-time refusals are not
    judged here, and keys a specific chat already holds
    are knowable only at bind time. Unknown or foreign
    answers 404 (existence never leaks). The road writes
    nothing and executes nothing.
    """
    record = _store().get(definition_id, user_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="scenario definition not found",
        )
    return preview_bind_plan(record)

# --------------------------- chat-scoped bind preview (P-138)


@router.get(
    "/scenarios/{definition_id}/bind-plan/{chat_id}",
    status_code=status.HTTP_200_OK,
)
async def preview_scenario_bind_plan_for_chat(
    definition_id: str,
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """What binding this definition WOULD do to THIS chat (P-138).

    P-136's envelope judged against one named chat:
    bind's refusal facts reported as data in bind's
    decision order (group room, already bound — naming
    the standing binding — and non-empty, with its
    message count), would_bind, and the plan's seedable
    keys split by the P-093 store's own presence law
    into would-seed and already-present. The definition
    is decided first: unknown or foreign answers 404
    ("scenario definition not found"); an unknown or
    foreign chat answers 404 ("chat not found") —
    existence never leaks on either side. The road
    writes nothing, refuses nothing and executes
    nothing; bind re-decides every fact when it runs.
    """
    record = _store().get(definition_id, user_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="scenario definition not found",
        )
    envelope = await preview_bind_for_chat(
        session, record, user_id, chat_id)
    if envelope is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="chat not found",
        )
    return envelope


# --------------------------- replace-impact preview (P-140)


@router.get(
    "/scenarios/{definition_id}/replace-impact",
    status_code=status.HTTP_200_OK,
)
async def preview_scenario_replace_impact(
    definition_id: str,
    user_id: str = Depends(get_owner_id),
):
    """What replacing this definition WOULD supersede (P-140).

    The envelope names the definition (id, name, its
    current revision, its source format), the next
    revision a successful replace would pin (current + 1,
    the P-131 replace law), the bindings read through
    P-135 summaries verbatim with the pinned split read
    from those summaries (pinned at the current revision,
    already pinned older, and pinned newer - impossible
    by construction, counted so a hand-damaged store is
    named, never hidden), the organisation view read
    through P-134 verbatim plus whether a persisted row
    exists at all, and five standing honesty notes: the
    preview replaces, writes and cascades nothing; a
    successful replace is permanent for the current body
    with no un-replace and no definition history; no
    binding is re-materialised and seeded content stays
    the chats own truth; the organisation row stays live
    against this id, unlike deletion, which orphans it;
    and no candidate body is judged here. Unknown or
    foreign answers 404 (existence never leaks). The PUT
    road remains the only replacer."""
    record = _store().get(definition_id, user_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="scenario definition not found",
        )
    live = {row.id for row in _store().list_for_owner(user_id)}
    return preview_replace_impact(
        record, _bindings(), _organisation(), live)

# ------------------------------------ stored export (P-133)


@router.get(
    "/scenarios/{definition_id}/export",
    status_code=status.HTTP_200_OK,
)
async def export_scenario_definition(
    definition_id: str,
    format: str | None = None,
    user_id: str = Depends(get_owner_id),
):
    """Hand one owned definition back as a file (P-133).

    The answer is an envelope: the requested format, the
    file itself (built by P-026's own exporters from the
    stored definition), and the honest export report —
    what the export restores and, by name, what it cannot
    (a Voxta file's unmappable raw values never persisted;
    P-131). The default format is native, the stored
    truth's own shape. Unknown or foreign answers 404 —
    decided BEFORE the format is judged, so no verdict
    leaks about someone else's data; an unknown format on
    an owned definition answers 422.
    """
    record = _store().get(definition_id, user_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="scenario definition not found",
        )
    fmt = DEFAULT_FORMAT if format is None else format
    if fmt not in FORMATS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown export format: {fmt!r} (valid: native, voxta)",
        )
    file_dict, report = export_stored_definition(record, fmt)
    return {"format": fmt, "file": file_dict, "report": report}
