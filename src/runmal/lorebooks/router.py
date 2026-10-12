"""Lorebook + lore entry REST API (S201). All routes require the local bearer credential."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session
from runmal.lorebooks import service
from runmal.lorebooks.service import entry_to_dict, lorebook_to_dict

router = APIRouter(tags=["lorebooks"])


class LorebookCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    scan_depth: int = Field(default=4, ge=1)
    token_budget: int | None = Field(default=None, ge=1)


class LorebookUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    scan_depth: int | None = Field(default=None, ge=1)
    token_budget: int | None = Field(default=None, ge=1)


class EntryCreate(BaseModel):
    name: str = ""
    content: str = ""
    keys: list[str] = Field(default_factory=list)
    secondary_keys: list[str] = Field(default_factory=list)
    priority: int = 100
    position: str = "before_char"
    enabled: bool = True
    constant: bool = False
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
    priority: int | None = None
    position: str | None = None
    enabled: bool | None = None
    constant: bool | None = None
    case_sensitive: bool | None = None
    whole_word: bool | None = None
    sticky_prompts: int | None = Field(default=None, ge=0)
    cooldown_prompts: int | None = Field(default=None, ge=0)
    delay_prompts: int | None = Field(default=None, ge=0)


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
            priority=body.priority,
            position=body.position,
            enabled=body.enabled,
            constant=body.constant,
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
