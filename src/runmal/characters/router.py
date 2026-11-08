"""Character REST API (S106). All routes require the local bearer credential."""

from __future__ import annotations

import inspect
import json

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.cards import CardParseError
from runmal.characters import service, versioning
from runmal.chats import service as chats_service
from runmal.characters.service import UnsafeFilenameError, character_to_dict
from runmal.db.deps import get_owner_id, get_session
from runmal.lorebooks import service as lorebooks_service
from runmal.safety import SafetyError, read_upload_capped

router = APIRouter(tags=["characters"])


class CharacterCreate(BaseModel):
    card: dict
    name: str | None = None


class CharacterUpdate(BaseModel):
    card: dict | None = None
    name: str | None = None


class BindingPut(BaseModel):
    """Bind a lorebook to a character (P-039)."""

    lorebook_id: str
    precedence: str | None = None


class BindingPatch(BaseModel):
    """Change a binding's precedence (P-039)."""

    precedence: str


class MergedPreviewRequest(BaseModel):
    """Merged character-book + world lorebook preview (P-039)."""

    world_lorebook_id: str
    messages: list[str] = []
    scan_depth: int | None = None
    token_budget: int | None = None
    seed: int | None = None


class EditorUpdate(BaseModel):
    """Persona/scenario/greeting editor payload (S212)."""

    description: str | None = None
    personality: str | None = None
    scenario: str | None = None
    first_mes: str | None = None
    alternate_greetings: list[str] | None = None


@router.post("/characters", status_code=status.HTTP_201_CREATED)
async def create_character(
    body: CharacterCreate,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        character = await service.create_character(session, user_id, body.card, body.name)
    except CardParseError as exc:
        raise HTTPException(status_code=422, detail=f"invalid card: {exc.kind}") from exc
    if getattr(character, versioning.DUPLICATE_ATTR, False):
        return JSONResponse(
            status_code=200,
            content={**character_to_dict(character), "duplicate_exact": True},
        )
    return character_to_dict(character)


@router.get("/characters")
async def list_characters(
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    characters = await service.list_characters(session, user_id)
    return [character_to_dict(c) for c in characters]


@router.get("/characters/{character_id}")
async def get_character(
    character_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    character = await service.get_character(session, user_id, character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="character not found")
    return character_to_dict(character)


@router.get("/characters/{character_id}/versions")
async def list_character_versions(
    character_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    payload = await versioning.list_versions(session, user_id, character_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="character not found")
    return payload


@router.get("/characters/{character_id}/versions/{version_no}")
async def get_character_version(
    character_id: str,
    version_no: int,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    character = await service.get_character(session, user_id, character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="character not found")
    payload = await versioning.get_version(
        session, user_id, character_id, version_no
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="version not found")
    return payload


@router.patch("/characters/{character_id}")
async def update_character(
    character_id: str,
    body: CharacterUpdate,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        character = await service.update_character(
            session, user_id, character_id, name=body.name, card_data=body.card
        )
    except CardParseError as exc:
        raise HTTPException(status_code=422, detail=f"invalid card: {exc.kind}") from exc
    if character is None:
        raise HTTPException(status_code=404, detail="character not found")
    return character_to_dict(character)


@router.get("/characters/{character_id}/greetings")
async def get_character_greetings(
    character_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """The card's greeting deck (P-079): the greetings a new chat
    would seed from, in deck order with kinds and source indexes."""
    deck = await chats_service.get_character_greetings(session, user_id, character_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="character not found")
    return deck


@router.get("/characters/{character_id}/editor")
async def get_editor(
    character_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    view = await service.get_editor_fields(session, user_id, character_id)
    if view is None:
        raise HTTPException(status_code=404, detail="character not found")
    return view


@router.patch("/characters/{character_id}/editor")
async def update_editor(
    character_id: str,
    body: EditorUpdate,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        view = await service.update_editor_fields(
            session,
            user_id,
            character_id,
            description=body.description,
            personality=body.personality,
            scenario=body.scenario,
            first_mes=body.first_mes,
            alternate_greetings=body.alternate_greetings,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    if view is None:
        raise HTTPException(status_code=404, detail="character not found")
    return view


@router.post(
    "/characters/{character_id}/duplicate", status_code=status.HTTP_201_CREATED
)
async def duplicate_character(
    character_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    character = await service.duplicate_character(session, user_id, character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="character not found")
    return character_to_dict(character)


@router.post("/characters/{character_id}/restore")
async def restore_character(
    character_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        character = await service.restore_character(session, user_id, character_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    if character is None:
        raise HTTPException(status_code=404, detail="character not found")
    return character_to_dict(character)


@router.delete("/characters/{character_id}")
async def delete_character(
    character_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    if not await service.delete_character(session, user_id, character_id):
        raise HTTPException(status_code=404, detail="character not found")
    # Soft delete: recoverable via POST /characters/{id}/restore (S303).
    return {"deleted": True, "id": character_id, "undoable": True}


@router.post("/characters/{character_id}/avatar")
async def upload_avatar(
    character_id: str,
    file: UploadFile,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        data = await read_upload_capped(file, service.MAX_AVATAR_BYTES)
        stored = await service.set_avatar(session, user_id, character_id, file.filename or "", data)
    except SafetyError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="character not found") from None
    except UnsafeFilenameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"filename": stored}


@router.get("/characters/{character_id}/avatar")
async def get_avatar(
    character_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    character = await service.get_character(session, user_id, character_id)
    if character is None or not character.avatar_asset:
        raise HTTPException(status_code=404, detail="avatar not found")
    try:
        found = service.read_avatar(character_id, character.avatar_asset)
    except UnsafeFilenameError:
        raise HTTPException(status_code=404, detail="avatar not found") from None
    if found is None:
        raise HTTPException(status_code=404, detail="avatar not found")
    data, media_type = found
    return Response(content=data, media_type=media_type)

# -- Character lorebook binding (P-039) ---------------------------------
# A character may carry one bound lorebook: materialised from its
# card's embedded character_book at creation, or bound explicitly
# here. The binding mechanics live in runmal.lorebooks.binding,
# imported lazily per call so this router never forms an import
# cycle with it and stays importable while that module lands.


def _binding_module():
    from runmal.lorebooks import binding

    return binding


def _binding_kwargs(fn, **available):
    """Keep only the arguments ``fn`` actually declares, by name."""
    return {
        name: available[name]
        for name in inspect.signature(fn).parameters
        if name in available
    }


async def _fetch_binding(binding_module, session, user_id, character_id, character=None):
    fn = getattr(binding_module, "get_binding_row", None) or getattr(
        binding_module, "get_binding", None
    )
    if fn is None:
        return None
    available = {
        "session": session,
        "user_id": user_id,
        "owner_id": user_id,
        "character_id": character_id,
        "character": character,
    }
    return await fn(**_binding_kwargs(fn, **available))


def _binding_error(exc: ValueError) -> HTTPException:
    if "character not found" in str(exc).lower():
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
    )


async def _binding_payload(session, user_id, binding_module, binding_obj):
    lorebook = await lorebooks_service.get_lorebook(
        session, user_id, binding_obj.lorebook_id
    )
    entries = await lorebooks_service.list_entries(
        session, user_id, binding_obj.lorebook_id
    )
    entry_count = len(entries) if entries is not None else 0
    payload = binding_module.binding_to_dict(binding_obj, lorebook, entry_count)
    if not isinstance(payload, dict):
        payload = {"binding": payload}
    payload.setdefault("bound", True)
    payload.setdefault(
        "character_id", getattr(binding_obj, "character_id", None)
    )
    payload.setdefault("lorebook_id", binding_obj.lorebook_id)
    payload.setdefault("precedence", getattr(binding_obj, "precedence", None))
    payload.setdefault("entry_count", entry_count)
    if lorebook is not None:
        payload.setdefault(
            "lorebook",
            lorebooks_service.lorebook_to_dict(lorebook, entry_count),
        )
    return payload


@router.get("/characters/{character_id}/lorebook-binding")
async def get_lorebook_binding(
    character_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    character = await service.get_character(session, user_id, character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="character not found")
    binding_module = _binding_module()
    binding_obj = await _fetch_binding(
        binding_module, session, user_id, character_id, character
    )
    if binding_obj is None:
        # Honest empty state: the character exists, it is just unbound.
        return {"bound": False, "character_id": character_id}
    return await _binding_payload(session, user_id, binding_module, binding_obj)


@router.put("/characters/{character_id}/lorebook-binding")
async def put_lorebook_binding(
    character_id: str,
    body: BindingPut,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    character = await service.get_character(session, user_id, character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="character not found")
    binding_module = _binding_module()
    lorebook = await lorebooks_service.get_lorebook(
        session, user_id, body.lorebook_id
    )
    try:
        result = await binding_module.bind_book(
            **_binding_kwargs(
                binding_module.bind_book,
                session=session,
                user_id=user_id,
                owner_id=user_id,
                character_id=character_id,
                character=character,
                lorebook_id=body.lorebook_id,
                book_id=body.lorebook_id,
                lorebook=lorebook,
                book=lorebook,
                precedence=body.precedence,
            )
        )
    except ValueError as exc:
        raise _binding_error(exc) from exc
    binding_obj = (
        result
        if hasattr(result, "lorebook_id")
        else await _fetch_binding(
            binding_module, session, user_id, character_id, character
        )
    )
    if binding_obj is None:
        await session.commit()
        return {
            "bound": True,
            "character_id": character_id,
            "lorebook_id": body.lorebook_id,
            "precedence": body.precedence,
        }
    payload = await _binding_payload(session, user_id, binding_module, binding_obj)
    await session.commit()
    return payload


@router.patch("/characters/{character_id}/lorebook-binding")
async def patch_lorebook_binding(
    character_id: str,
    body: BindingPatch,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    character = await service.get_character(session, user_id, character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="character not found")
    binding_module = _binding_module()
    existing = await _fetch_binding(
        binding_module, session, user_id, character_id, character
    )
    if existing is None:
        raise HTTPException(status_code=404, detail="no bound lorebook")
    try:
        result = await binding_module.set_precedence(
            **_binding_kwargs(
                binding_module.set_precedence,
                session=session,
                user_id=user_id,
                owner_id=user_id,
                character_id=character_id,
                character=character,
                binding=existing,
                precedence=body.precedence,
            )
        )
    except ValueError as exc:
        raise _binding_error(exc) from exc
    binding_obj = (
        result
        if hasattr(result, "lorebook_id")
        else await _fetch_binding(
            binding_module, session, user_id, character_id, character
        )
        or existing
    )
    payload = await _binding_payload(session, user_id, binding_module, binding_obj)
    await session.commit()
    return payload


@router.delete("/characters/{character_id}/lorebook-binding")
async def delete_lorebook_binding(
    character_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    character = await service.get_character(session, user_id, character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="character not found")
    binding_module = _binding_module()
    existing = await _fetch_binding(
        binding_module, session, user_id, character_id, character
    )
    if existing is None:
        raise HTTPException(status_code=404, detail="no bound lorebook")
    try:
        result = await binding_module.unbind(
            **_binding_kwargs(
                binding_module.unbind,
                session=session,
                user_id=user_id,
                owner_id=user_id,
                character_id=character_id,
                character=character,
                binding=existing,
            )
        )
    except ValueError as exc:
        raise _binding_error(exc) from exc
    if result is False:
        raise HTTPException(status_code=404, detail="no bound lorebook")
    await session.commit()
    return {"unbound": True}


@router.get("/characters/{character_id}/character-book")
async def get_character_book(
    character_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    character = await service.get_character(session, user_id, character_id)
    if character is None:
        raise HTTPException(status_code=404, detail="character not found")
    binding_module = _binding_module()
    binding_obj = await _fetch_binding(
        binding_module, session, user_id, character_id, character
    )
    if binding_obj is not None:
        try:
            serialised = await binding_module.serialise_bound_book(
                session, binding_obj
            )
        except Exception:
            serialised = None
        if isinstance(serialised, dict):
            return serialised
    # Unbound: the book still travels inside the stored card JSON.
    try:
        stored = json.loads(character.card_json)
    except (TypeError, ValueError):
        stored = {}
    book = None
    if isinstance(stored, dict):
        data = stored.get("data")
        if isinstance(data, dict):
            book = data.get("character_book")
        else:
            book = stored.get("character_book")
    if not isinstance(book, dict) or not book:
        return {"entries": []}
    return book


@router.post("/characters/{character_id}/lorebook-preview")
async def post_lorebook_preview(
    character_id: str,
    body: MergedPreviewRequest,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    binding_module = _binding_module()
    try:
        result = await binding_module.merged_preview(
            session,
            user_id,
            character_id,
            body.world_lorebook_id,
            body.messages,
            body.scan_depth,
            body.token_budget,
            body.seed,
        )
    except ValueError as exc:
        raise _binding_error(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="character not found")
    return result

