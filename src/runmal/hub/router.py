"""Hub registry HTTP surface (P-187): index a pack
artefact, read it back with its locator state judged
live, list the owner's index, and remove an entry - on
the /api/v1/hub road, bearer-gated like every API and
wired in app.py.

Owner scoping: an entry that is unknown - or owned by
someone else - answers 404 ("hub entry not found") on
the read and delete roads; existence never leaks. Every
locator state (ready / missing / not_a_file /
unreadable) is DATA at 200 on a read, never an error:
the client decides what to show from the named states.
The truth layer lives in runmal.hub.registry; this
module is only the HTTP shape. P-189 adds the census
road: GET /hub/census, the owner's whole estate composed
from the list and browse documents (see hub.census).
P-190 adds the search road: GET /hub/search, a literal
search over the owner's own entry data (see hub.search).
P-191 adds the content-search road: GET /hub/content-search,
a literal search over verified pack payload contents
(see hub.content_search).
P-192 adds the unified-search road: GET /hub/unified-search,
one query composed over the metadata and content searches
(see hub.unified_search). P-193 adds the content-census
road: GET /hub/content-census, the content-coverage census
over the owner estate (see hub.content_census).
P-194 adds the unified-search-census road:
GET /hub/unified-search-census, the aggregate of one
query's unified search - its returned matched-by, kind
and matched-field shape, occurrence totals, and the
skip-outcome shape of its coverage (see
hub.unified_search_census).
P-196 adds the content-shape-census road:
GET /hub/content-shape-census, the structural census
over the verified payloads of the owner estate (see
hub.content_shape_census).
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session
from runmal.hub import browse as hub_browse
from runmal.hub import census as hub_census
from runmal.hub import registry as hub_service
from runmal.hub import content_census as hub_content_census
from runmal.hub import content_search as hub_content_search
from runmal.hub import search as hub_search
from runmal.hub import unified_search as hub_unified_search
from runmal.hub import unified_search_census as hub_unified_search_census
from runmal.hub import content_shape_census as hub_content_shape_census

router = APIRouter(tags=["hub"])


def _store() -> hub_service.HubStore:
    base = Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return hub_service.HubStore(base)


class RegisterRequest(BaseModel):
    kind: str
    title: str
    locator: str
    content_sha256: str = ""
    note: str = ""


@router.post("/hub/entries", status_code=status.HTTP_201_CREATED)
async def register_hub_entry(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    try:
        entry = hub_service.register_entry(
            _store(), owner_id=owner_id, kind=body.kind,
            title=body.title, locator=body.locator,
            content_sha256=body.content_sha256, note=body.note)
    except hub_service.HubError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc)) from None
    return hub_service.entry_document(entry)


@router.get("/hub/census")
async def hub_census_document(
    owner_id: str = Depends(get_owner_id),
):
    entries = _store().list_for_owner(owner_id)
    return hub_census.census_document(entries)


@router.get("/hub/content-census")
async def hub_content_census_document(
    owner_id: str = Depends(get_owner_id),
):
    entries = _store().list_for_owner(owner_id)
    return hub_content_census.content_census_document(entries)


@router.get("/hub/content-shape-census")
async def hub_content_shape_census_document(
    owner_id: str = Depends(get_owner_id),
):
    entries = _store().list_for_owner(owner_id)
    return hub_content_shape_census.content_shape_census_document(entries)


@router.get("/hub/search")
async def hub_search_document(
    q: str = "",
    kind: str | None = None,
    owner_id: str = Depends(get_owner_id),
):
    entries = _store().list_for_owner(owner_id)
    try:
        return hub_search.search_document(entries, q, kind=kind)
    except hub_search.HubSearchError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc)) from None


@router.get("/hub/content-search")
async def hub_content_search_document(
    q: str = "",
    kind: str | None = None,
    owner_id: str = Depends(get_owner_id),
):
    entries = _store().list_for_owner(owner_id)
    try:
        return hub_content_search.content_search_document(
            entries, q, kind=kind)
    except hub_content_search.HubContentSearchError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc)) from None


@router.get("/hub/unified-search")
async def hub_unified_search_document(
    q: str = "",
    kind: str | None = None,
    owner_id: str = Depends(get_owner_id),
):
    entries = _store().list_for_owner(owner_id)
    try:
        return hub_unified_search.unified_search_document(
            entries, q, kind=kind)
    except hub_unified_search.HubUnifiedSearchError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc)) from None


@router.get("/hub/unified-search-census")
async def hub_unified_search_census_document(
    q: str = "",
    kind: str | None = None,
    owner_id: str = Depends(get_owner_id),
):
    entries = _store().list_for_owner(owner_id)
    try:
        return hub_unified_search_census.unified_search_census_document(
            entries, q, kind=kind)
    except hub_unified_search.HubUnifiedSearchError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc)) from None


@router.get("/hub/entries/{entry_id}")
async def read_hub_entry(
    entry_id: str,
    owner_id: str = Depends(get_owner_id),
):
    entry = _store().get_entry(entry_id)
    if entry is None or entry.owner_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="hub entry not found")
    return hub_service.entry_document(entry)


@router.get("/hub/entries/{entry_id}/browse")
async def browse_hub_entry(
    entry_id: str,
    owner_id: str = Depends(get_owner_id),
):
    entry = _store().get_entry(entry_id)
    if entry is None or entry.owner_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="hub entry not found")
    return hub_browse.browse_document(entry)


@router.get("/hub")
async def list_hub_entries(
    kind: str | None = None,
    owner_id: str = Depends(get_owner_id),
):
    if kind is not None and kind not in hub_service.HUB_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="unknown hub kind: " + kind)
    entries = _store().list_for_owner(owner_id)
    if kind is not None:
        entries = [row for row in entries if row.kind == kind]
    return hub_service.list_document(entries)


@router.delete("/hub/entries/{entry_id}")
async def remove_hub_entry(
    entry_id: str,
    owner_id: str = Depends(get_owner_id),
):
    store = _store()
    entry = store.get_entry(entry_id)
    if entry is None or entry.owner_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="hub entry not found")
    store.remove_entry(entry_id)
    return {"deleted": True, "id": entry_id}
