"""Vision HTTP surface (P-117): describe-on-request for an
owned chat, the chat's description list, and the last
description (the VX-50 read surface, as data) — on the
``/api/v1/vision`` road, bearer-gated like every API and
wired in app.py.

Owner scoping: a chat that is unknown — or owned by someone
else — answers 404 on every road; existence never leaks.
The truth layer lives in runmal.vision.service; this module
is only the HTTP shape. The only provider this slice ships
is the metadata provider (sniffed truth, road "metadata");
no road here invents a semantic caption.

P-119: describe now selects its provider through
runmal.vision.selection — the request may name a provider
by road or provider_id, or require a semantic provider
(refused plainly today: none exists in-tree) — and
GET /vision/providers exposes the provider catalogue plus
the backends' declared vision truth as data.
P-120 adds the attachment roads on the same prefix:
user-supplied images attached to a chat (optionally to one
message of it), stored by runmal.vision.attachments, listed /
read / deleted owner-scoped, and describable through the
describe road as source_kind "attachment". An attachment
record claims sniffed truth only; attaching invents no
description.
P-122 adds the history/search/custody surface on the
same prefix: GET /vision/history (owner-scoped literal
search over the description store), single-record read
and delete under /vision/descriptions/{id}, and source
custody - deleting an attachment also purges the
descriptions derived from it.
P-124 adds watcher custody & control completion on the
same prefix: deleting an attachment also forgets its
watcher ingested records (the scan dedupe memory), and
the watch roads gain the single-watch read and the
enabled toggle (PATCH) that make a registration's
enabled flag reachable for the first time.
"""

from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.assets import service as asset_service
from runmal.chats import service as chat_service
from runmal.db.deps import get_owner_id, get_session
from runmal.vision import attachments as att_service
from runmal.vision import selection as vision_selection
from runmal.vision import service as vision_service
from runmal.vision import watcher as watcher_service

router = APIRouter(tags=["vision"])


def _store() -> vision_service.VisionStore:
    base = Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return vision_service.VisionStore(
        base / vision_service.DESCRIPTIONS_FILENAME)


def _attachment_store() -> att_service.AttachmentStore:
    base = Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return att_service.AttachmentStore(base)


async def _chat_or_404(session: AsyncSession, owner_id: str, chat_id: str):
    chat = await chat_service.get_chat(session, owner_id, chat_id)
    if chat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="chat not found")
    return chat


class DescribeRequest(BaseModel):
    chat_id: str
    attachment_id: str | None = None
    asset_id: str | None = None
    image_b64: str | None = None
    question: str = ""
    provider: str | None = None
    require_semantic: bool = False


@router.post("/vision/describe")
async def describe(
    body: DescribeRequest,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    chat = await _chat_or_404(session, owner_id, body.chat_id)
    if body.attachment_id:
        record_att = _attachment_store().get(body.attachment_id)
        if (record_att is None or record_att.owner_id != owner_id
                or record_att.chat_id != chat.id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="attachment not found")
        found_bytes = _attachment_store().read_bytes(record_att)
        if found_bytes is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="attachment bytes not found")
        image_bytes = found_bytes
        source_kind = vision_service.SOURCE_ATTACHMENT
        source_ref = body.attachment_id
    elif body.asset_id:
        if not chat.character_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="asset not found")
        asset = await asset_service.get_asset(
            session, owner_id, chat.character_id, body.asset_id)
        if asset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="asset not found")
        found = asset_service.read_asset_content(chat.character_id, asset)
        if found is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="asset bytes not found")
        image_bytes = found[0]
        source_kind = vision_service.SOURCE_ASSET
        source_ref = body.asset_id
    elif body.image_b64 is not None:
        try:
            image_bytes = base64.b64decode(body.image_b64, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="image_b64 is not valid base64") from None
        source_kind = vision_service.SOURCE_INLINE
        source_ref = ""
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="attachment_id, asset_id or image_b64 is required")
    try:
        provider = vision_selection.select_provider(
            body.provider, semantic_required=body.require_semantic)
        record = vision_service.describe_image(
            _store(),
            chat_id=chat.id,
            owner_id=owner_id,
            image_bytes=image_bytes,
            provider=provider,
            source_kind=source_kind,
            source_ref=source_ref,
            question=body.question or "",
        )
    except vision_service.VisionProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc)) from None
    except vision_service.VisionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc)) from None
    return record.to_dict()


@router.get("/vision/providers")
async def list_providers(
    owner_id: str = Depends(get_owner_id),
):
    return vision_selection.providers_payload()


@router.get("/vision/descriptions")
async def list_descriptions(
    chat_id: str,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    chat = await _chat_or_404(session, owner_id, chat_id)
    rows = _store().list_for_chat(chat.id)
    return {"chat_id": chat.id, "descriptions": [r.to_dict() for r in rows]}


@router.get("/vision/last")
async def last_description(
    chat_id: str,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    chat = await _chat_or_404(session, owner_id, chat_id)
    record = _store().last_for_chat(chat.id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no vision description for this chat")
    return record.to_dict()



# ------------------------------------------------- history (P-122)
# Owner-scoped history + literal search over the description
# store, single-record read/delete, and source custody. Search
# is literal substring matching over stored text (see
# VisionStore.search) - never semantic, never ranked.


def _description_or_404(description_id: str, owner_id: str):
    record = _store().get(description_id)
    if record is None or record.owner_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="vision description not found")
    return record


@router.get("/vision/history")
async def history(
    q: str = "",
    chat_id: str | None = None,
    source_kind: str | None = None,
    provider_road: str | None = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    chat = None
    if chat_id is not None:
        chat = await _chat_or_404(session, owner_id, chat_id)
    if provider_road is not None:
        known = {row.road for row in vision_selection.provider_catalogue()}
        if provider_road not in known:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=("unknown provider_road "
                        f"{provider_road!r}; known roads: "
                        f"{', '.join(sorted(known))}"))
    try:
        rows, total = _store().search(
            owner_id,
            q,
            chat_id=chat.id if chat is not None else None,
            source_kind=source_kind,
            provider_road=provider_road,
            limit=limit,
            offset=offset,
        )
    except vision_service.VisionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc)) from None
    return {
        "descriptions": [row.to_dict() for row in rows],
        "total": total,
        "returned": len(rows),
        "limit": max(1, min(200, int(limit))),
        "offset": max(0, int(offset)),
        "q": q,
        "chat_id": chat_id,
        "source_kind": source_kind,
        "provider_road": provider_road,
    }


@router.get("/vision/descriptions/{description_id}")
async def get_description(
    description_id: str,
    owner_id: str = Depends(get_owner_id),
):
    return _description_or_404(description_id, owner_id).to_dict()


@router.delete("/vision/descriptions/{description_id}")
async def delete_description(
    description_id: str,
    owner_id: str = Depends(get_owner_id),
):
    record = _description_or_404(description_id, owner_id)
    removed = _store().remove(record.id)
    return {"deleted": removed is not None, "id": record.id}

# ------------------------------------------------------- attachments
# P-120: user-supplied images attached to a chat / message.
# Owner scoping matches the describe roads: an attachment that
# is unknown — or owned by someone else, or bound to another
# chat — answers 404; existence never leaks.


class AttachRequest(BaseModel):
    chat_id: str
    message_id: str | None = None
    filename: str = ""
    image_b64: str


def _attachment_or_404(attachment_id: str, owner_id: str):
    record = _attachment_store().get(attachment_id)
    if record is None or record.owner_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="attachment not found")
    return record


@router.post("/vision/attachments", status_code=status.HTTP_201_CREATED)
async def attach(
    body: AttachRequest,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    chat = await _chat_or_404(session, owner_id, body.chat_id)
    if body.message_id:
        history = await chat_service.get_history(session, owner_id, chat.id)
        if not history or all(m.id != body.message_id for m in history):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="message not found")
    try:
        image_bytes = base64.b64decode(body.image_b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="image_b64 is not valid base64") from None
    try:
        record = att_service.attach_image(
            _attachment_store(),
            chat_id=chat.id,
            owner_id=owner_id,
            data=image_bytes,
            message_id=body.message_id,
            filename=body.filename or "",
        )
    except att_service.AttachmentError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc)) from None
    return record.to_dict()


@router.get("/vision/attachments")
async def list_attachments(
    chat_id: str,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    chat = await _chat_or_404(session, owner_id, chat_id)
    rows = _attachment_store().list_for_chat(chat.id)
    return {"chat_id": chat.id,
            "attachments": [r.to_dict() for r in rows]}


@router.get("/vision/attachments/{attachment_id}")
async def get_attachment(
    attachment_id: str,
    owner_id: str = Depends(get_owner_id),
):
    return _attachment_or_404(attachment_id, owner_id).to_dict()


@router.get("/vision/attachments/{attachment_id}/content")
async def get_attachment_content(
    attachment_id: str,
    owner_id: str = Depends(get_owner_id),
):
    record = _attachment_or_404(attachment_id, owner_id)
    data = _attachment_store().read_bytes(record)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="attachment bytes not found")
    return Response(content=data, media_type=record.media_type)


@router.delete("/vision/attachments/{attachment_id}")
async def delete_attachment(
    attachment_id: str,
    owner_id: str = Depends(get_owner_id),
):
    record = _attachment_or_404(attachment_id, owner_id)
    removed = _attachment_store().remove(record.id)
    purged = 0
    forgotten = 0
    if removed is not None:
        # P-122 source custody: descriptions derived from this
        # attachment die with it, so derived text never
        # outlives the bytes the owner deleted.
        purged = _store().purge_source(
            vision_service.SOURCE_ATTACHMENT, record.id)
        # P-124 watcher custody: the scan dedupe records
        # naming this attachment die with it, so its source
        # file can be ingested anew by a later scan instead
        # of skipping as already-ingested forever.
        forgotten = _watch_store().forget_attachment(record.id)
    return {"deleted": removed is not None, "id": record.id,
            "descriptions_purged": purged,
            "watch_records_forgotten": forgotten}


def _watch_store() -> watcher_service.WatchStore:
    base = Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return watcher_service.WatchStore(base)


def _scan_attacher():
    """The scan's attacher: None = resolve P-120 lazily (P-121).

    Tests monkeypatch this to inject a fake attacher; in
    production the watcher resolves runmal.vision.attachments
    at scan time and refuses plainly when it is absent.
    """
    return None


async def _watch_or_404(store, owner_id: str, watch_id: str):
    watch = store.get_watch(watch_id)
    if watch is None or watch.owner_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="watch folder not found")
    return watch


class WatchFolderRequest(BaseModel):
    chat_id: str
    path: str
    recursive: bool = False


@router.post("/vision/watch-folders", status_code=201)
async def create_watch_folder(
    body: WatchFolderRequest,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    chat = await _chat_or_404(session, owner_id, body.chat_id)
    try:
        watch = watcher_service.register_watch(
            _watch_store(), owner_id=owner_id, chat_id=chat.id,
            path=body.path, recursive=body.recursive)
    except watcher_service.WatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc)) from None
    return watch.to_dict()


@router.get("/vision/watch-folders")
async def list_watch_folders(
    chat_id: str,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    chat = await _chat_or_404(session, owner_id, chat_id)
    rows = _watch_store().list_for_chat(chat.id)
    rows = [r for r in rows if r.owner_id == owner_id]
    return {"chat_id": chat.id,
            "watch_folders": [r.to_dict() for r in rows]}


@router.get("/vision/watch-folders/{watch_id}")
async def get_watch_folder(
    watch_id: str,
    owner_id: str = Depends(get_owner_id),
):
    store = _watch_store()
    watch = await _watch_or_404(store, owner_id, watch_id)
    return watch.to_dict()


class WatchEnabledRequest(BaseModel):
    enabled: bool


@router.patch("/vision/watch-folders/{watch_id}")
async def set_watch_folder_enabled(
    watch_id: str,
    body: WatchEnabledRequest,
    owner_id: str = Depends(get_owner_id),
):
    store = _watch_store()
    watch = await _watch_or_404(store, owner_id, watch_id)
    updated = store.set_enabled(watch.id, body.enabled)
    return updated.to_dict()


@router.delete("/vision/watch-folders/{watch_id}")
async def delete_watch_folder(
    watch_id: str,
    owner_id: str = Depends(get_owner_id),
):
    store = _watch_store()
    watch = await _watch_or_404(store, owner_id, watch_id)
    store.remove_watch(watch.id)
    return {"deleted": watch.id}


@router.post("/vision/watch-folders/{watch_id}/scan")
async def scan_watch_folder(
    watch_id: str,
    owner_id: str = Depends(get_owner_id),
):
    store = _watch_store()
    watch = await _watch_or_404(store, owner_id, watch_id)
    try:
        report = watcher_service.scan_watch(
            store, watch, attacher=_scan_attacher())
    except watcher_service.WatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc)) from None
    return report.to_dict()


@router.get("/vision/watch-folders/{watch_id}/ingested")
async def list_watch_ingested(
    watch_id: str,
    owner_id: str = Depends(get_owner_id),
):
    store = _watch_store()
    watch = await _watch_or_404(store, owner_id, watch_id)
    rows = store.list_ingested(watch.id)
    return {"watch_id": watch.id,
            "ingested": [r.to_dict() for r in rows]}
