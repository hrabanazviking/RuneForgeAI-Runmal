"""Plugin REST surface (P-081 read/lifecycle + P-083 manager).

P-081 surface: read + lifecycle verbs only. Registration was
trusted in-process code, so there was deliberately NO
``POST /plugins`` and NO ``DELETE`` -- and there still is not:
both stay 405, as the P-081 battery pins.

P-083 adds the manager surface in the same POST-verb idiom:

- ``POST /plugins/install/preview`` -- the permission-card
  verdict for a pack, writing nothing;
- ``POST /plugins/install`` -- install a local pack whose
  declared permissions the caller grants exactly;
- ``POST /plugins/{plugin_id}/update`` -- the versioned swap,
  same grant rule, card shows the diff;
- ``POST /plugins/{plugin_id}/uninstall`` -- removal as a verb;
- ``GET /plugins/manager`` -- the durable ledger view;
- ``GET /plugins/{plugin_id}/permission-card`` -- the card for
  an installed or in-tree plugin.

Error mapping: malformed packs, grant mismatches, data-only
refusals, compatibility verdicts and not-managed refusals are
422 (house ``_visible`` pattern); an occupied-id conflict is
409; an unknown plugin id is 404; an ``on_enable`` failure
answers 200 with the ERRORED record (PLG-01: the record IS
the report, never a 500). Lifecycle verbs also sync the
manager ledger's enabled flag for pack-managed plugins, so
HTTP enable/disable survives a restart like a manager call.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session
from runmal.plugins import service
from runmal.plugins.api import UI_SLOTS
from runmal.plugins.cards import permission_card
from runmal.plugins.manager import (
    PluginConflictError,
    PluginManagerError,
)
from runmal.plugins.packs import PackError
from runmal.plugins.registry import (
    InvalidPluginTransition,
    PluginCompatibilityError,
)

router = APIRouter(tags=["plugins"])


def _visible(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=str(exc))


def _registry():
    return service.ensure_default_registry()


def _record_or_404(registry, plugin_id: str):
    try:
        return registry.get(plugin_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown plugin: {plugin_id}") from None


def _manager_http_error(exc: Exception, plugin_id: str | None = None) -> HTTPException:
    if isinstance(exc, PluginConflictError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, KeyError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown plugin: {plugin_id}")
    return _visible(exc)


def _sync(plugin_id: str) -> None:
    """Ledger sync after a lifecycle verb. The registry state
    is the live truth and the verb has already succeeded, so a
    ledger write failure never fails the verb; the next
    manager operation rewrites the row wholesale."""
    try:
        service.sync_managed_state(plugin_id)
    except Exception:
        pass


def _outcome_payload(outcome, registry) -> dict:
    return {
        "outcome": outcome.outcome,
        "plugin": (
            service.record_detail_to_dict(outcome.record, registry)
            if outcome.record is not None else None),
        "manager": outcome.row,
        "permission_card": outcome.card,
    }


@router.get("/plugins/api")
async def plugin_api():
    return service.plugin_api_info(_registry())


@router.get("/plugins/ui-slots")
async def plugin_ui_slots(slot: str | None = None):
    registry = _registry()
    if slot is not None and slot not in UI_SLOTS:
        raise _visible(ValueError(f"unknown ui slot: {slot!r}"))
    return {
        "slots": registry.ui_slots_summary(),
        "contributions": registry.ui_contributions(slot),
    }


@router.get("/plugins/manager")
async def plugin_manager_view():
    manager = service.plugin_manager()
    return {
        "installed": manager.installed_rows(),
        "rehydration_problems": service.rehydration_problems(),
    }


@router.get("/plugins")
async def list_plugins():
    registry = _registry()
    return [service.record_to_dict(registry.get(plugin_id))
            for plugin_id in registry.keys()]


@router.post("/plugins/install/preview")
async def plugin_install_preview(body: dict):
    if "pack" not in body:
        raise _visible(ValueError("request body must carry a 'pack'"))
    manager = service.plugin_manager()
    return manager.preview(body["pack"])


@router.post("/plugins/install", status_code=status.HTTP_201_CREATED)
async def plugin_install(body: dict, response: Response):
    if "pack" not in body:
        raise _visible(ValueError("request body must carry a 'pack'"))
    manager = service.plugin_manager()
    try:
        outcome = manager.install(
            body["pack"],
            granted_permissions=body.get("granted_permissions"),
            enable=bool(body.get("enable", False)))
    except (KeyError, PackError, PluginManagerError,
            PluginCompatibilityError) as exc:
        raise _manager_http_error(exc) from exc
    if outcome.outcome == "duplicate_exact":
        response.status_code = status.HTTP_200_OK
    return _outcome_payload(outcome, _registry())


@router.get("/plugins/{plugin_id}")
async def plugin_detail(plugin_id: str):
    registry = _registry()
    record = _record_or_404(registry, plugin_id)
    return service.record_detail_to_dict(record, registry)


@router.get("/plugins/{plugin_id}/permission-card")
async def plugin_permission_card(plugin_id: str):
    registry = _registry()
    record = _record_or_404(registry, plugin_id)
    manager = service.plugin_manager()
    row = manager.row_for(plugin_id)
    granted = (set(row.get("granted_permissions", []))
               if row is not None else None)
    return permission_card(record.manifest, granted=granted)


@router.post("/plugins/{plugin_id}/update")
async def plugin_update(plugin_id: str, body: dict):
    if "pack" not in body:
        raise _visible(ValueError("request body must carry a 'pack'"))
    manager = service.plugin_manager()
    try:
        outcome = manager.update(
            plugin_id, body["pack"],
            granted_permissions=body.get("granted_permissions"))
    except (KeyError, PackError, PluginManagerError,
            PluginCompatibilityError) as exc:
        raise _manager_http_error(exc, plugin_id) from exc
    return _outcome_payload(outcome, _registry())


@router.post("/plugins/{plugin_id}/uninstall")
async def plugin_uninstall(plugin_id: str):
    manager = service.plugin_manager()
    try:
        outcome = manager.uninstall(plugin_id)
    except (KeyError, PackError, PluginManagerError,
            PluginCompatibilityError) as exc:
        raise _manager_http_error(exc, plugin_id) from exc
    return {
        "outcome": outcome.outcome,
        "plugin_id": outcome.plugin_id,
        "permission_card": outcome.card,
    }


@router.post("/plugins/{plugin_id}/enable")
async def plugin_enable(plugin_id: str):
    registry = _registry()
    _record_or_404(registry, plugin_id)
    try:
        record = registry.enable(plugin_id)
    except InvalidPluginTransition as exc:
        raise _visible(exc) from exc
    _sync(plugin_id)
    return service.record_detail_to_dict(record, registry)


@router.post("/plugins/{plugin_id}/disable")
async def plugin_disable(plugin_id: str):
    registry = _registry()
    _record_or_404(registry, plugin_id)
    try:
        record = registry.disable(plugin_id)
    except InvalidPluginTransition as exc:
        raise _visible(exc) from exc
    _sync(plugin_id)
    return service.record_detail_to_dict(record, registry)


@router.post("/plugins/{plugin_id}/acknowledge")
async def plugin_acknowledge(plugin_id: str):
    registry = _registry()
    _record_or_404(registry, plugin_id)
    try:
        record = registry.acknowledge(plugin_id)
    except InvalidPluginTransition as exc:
        raise _visible(exc) from exc
    _sync(plugin_id)
    return service.record_detail_to_dict(record, registry)


# -- Quick Replies surface (P-089) ---------------------------------------
# Stored, owner-scoped quick-reply definitions + one-tap
# execution, in the house router idiom (session + owner deps,
# ValueError -> 422 via _visible, unknown ids -> 404, create
# -> 201). The store and the execution road live in
# runmal.plugins.quick_replies; imports are lazy so this
# router's import graph is unchanged at module load.



@router.get("/quick-replies")
async def quick_replies_list(
    chat_id: str | None = None,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import quick_replies as qr

    try:
        return qr.list_replies(user_id, chat_id=chat_id)
    except ValueError as exc:
        raise _visible(exc) from exc


@router.post("/quick-replies", status_code=status.HTTP_201_CREATED)
async def quick_replies_create(
    body: dict,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.chats import service as chats_svc
    from runmal.plugins import quick_replies as qr

    chat_id = body.get("chat_id") if isinstance(body, dict) else None
    if chat_id is not None:
        if await chats_svc.get_chat(session, user_id, chat_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"unknown chat: {chat_id}")
    try:
        return qr.create_reply(user_id, body)
    except ValueError as exc:
        raise _visible(exc) from exc


@router.get("/quick-replies/executions")
async def quick_replies_executions(
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import quick_replies as qr

    try:
        return qr.list_executions(user_id)
    except ValueError as exc:
        raise _visible(exc) from exc


@router.get("/quick-replies/{reply_id}")
async def quick_replies_detail(
    reply_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import quick_replies as qr

    try:
        reply = qr.get_reply(user_id, reply_id)
    except ValueError as exc:
        raise _visible(exc) from exc
    if reply is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown quick reply: {reply_id}")
    return reply


@router.put("/quick-replies/{reply_id}")
async def quick_replies_update(
    reply_id: str,
    body: dict,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.chats import service as chats_svc
    from runmal.plugins import quick_replies as qr

    chat_id = body.get("chat_id") if isinstance(body, dict) else None
    if chat_id is not None:
        if await chats_svc.get_chat(session, user_id, chat_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"unknown chat: {chat_id}")
    try:
        reply = qr.update_reply(user_id, reply_id, body)
    except ValueError as exc:
        raise _visible(exc) from exc
    if reply is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown quick reply: {reply_id}")
    return reply


@router.delete("/quick-replies/{reply_id}")
async def quick_replies_delete(
    reply_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import quick_replies as qr

    try:
        deleted = qr.delete_reply(user_id, reply_id)
    except ValueError as exc:
        raise _visible(exc) from exc
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown quick reply: {reply_id}")
    return {"deleted": True, "id": reply_id}


@router.post("/quick-replies/{reply_id}/execute")
async def quick_replies_execute(
    reply_id: str,
    body: dict,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import quick_replies as qr

    chat_id = body.get("chat_id") if isinstance(body, dict) else None
    if not chat_id:
        raise _visible(ValueError("request body must carry a 'chat_id'"))
    try:
        record = await qr.execute_reply(session, user_id, chat_id, reply_id)
    except ValueError as exc:
        raise _visible(exc) from exc
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="unknown quick reply or chat")
    return record
