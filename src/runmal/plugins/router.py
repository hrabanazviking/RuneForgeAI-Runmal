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


# -- Expressions surface (P-092) ------------------------------------------
# Declared expression sets per character + current-expression
# selection per chat with provenance, in the house router idiom
# (session + owner deps, ValueError -> 422 via _visible, unknown
# ids -> 404, create -> 201). The store, binding and selection
# roads live in runmal.plugins.expressions; imports are lazy so
# this router's import graph is unchanged at module load.


@router.get("/expressions/sets")
async def expressions_sets_list(
    character_id: str | None = None,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import expressions as ex

    try:
        if character_id is not None:
            expr_set = ex.get_set(user_id, character_id)
            return [expr_set] if expr_set is not None else []
        return ex.list_sets(user_id)
    except ValueError as exc:
        raise _visible(exc) from exc


@router.post("/expressions/sets", status_code=status.HTTP_201_CREATED)
async def expressions_sets_create(
    body: dict,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.characters import service as characters_svc
    from runmal.plugins import expressions as ex

    character_id = body.get("character_id") if isinstance(body, dict) else None
    if character_id is not None:
        try:
            character = await characters_svc.get_character(
                session, user_id, character_id)
        except Exception:
            character = None
        if character is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"unknown character: {character_id}")
    try:
        return ex.create_set(user_id, body)
    except ValueError as exc:
        raise _visible(exc) from exc


@router.get("/expressions/sets/{character_id}")
async def expressions_set_detail(
    character_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import expressions as ex

    try:
        expr_set = ex.get_set(user_id, character_id)
    except ValueError as exc:
        raise _visible(exc) from exc
    if expr_set is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown expression set: {character_id}")
    return expr_set


@router.put("/expressions/sets/{character_id}")
async def expressions_set_update(
    character_id: str,
    body: dict,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import expressions as ex

    try:
        expr_set = ex.update_set(user_id, character_id, body)
    except ValueError as exc:
        raise _visible(exc) from exc
    if expr_set is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown expression set: {character_id}")
    return expr_set


@router.delete("/expressions/sets/{character_id}")
async def expressions_set_delete(
    character_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import expressions as ex

    try:
        deleted = ex.delete_set(user_id, character_id)
    except ValueError as exc:
        raise _visible(exc) from exc
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown expression set: {character_id}")
    return {"deleted": True, "character_id": character_id}


@router.get("/expressions/sets/{character_id}/bindings")
async def expressions_set_bindings(
    character_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import expressions as ex

    try:
        report = await ex.binding_report(session, user_id, character_id)
    except ValueError as exc:
        raise _visible(exc) from exc
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown character: {character_id}")
    return report


@router.post("/expressions/sets/{character_id}/derive")
async def expressions_set_derive(
    character_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import expressions as ex

    try:
        draft = await ex.derive_set_from_assets(session, user_id, character_id)
    except ValueError as exc:
        raise _visible(exc) from exc
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown character: {character_id}")
    return draft


@router.get("/expressions/current")
async def expressions_current(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import expressions as ex

    try:
        current = ex.current_expression(user_id, chat_id)
    except ValueError as exc:
        raise _visible(exc) from exc
    if current is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no current expression for chat: {chat_id}")
    return current


@router.get("/expressions/history")
async def expressions_history(
    chat_id: str | None = None,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import expressions as ex

    try:
        return ex.list_history(user_id, chat_id=chat_id)
    except ValueError as exc:
        raise _visible(exc) from exc


@router.get("/expressions/inspect")
async def expressions_inspect(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import expressions as ex

    try:
        state = await ex.inspect_state(session, user_id, chat_id)
    except ValueError as exc:
        raise _visible(exc) from exc
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown chat: {chat_id}")
    return state


@router.post("/expressions/select")
async def expressions_select(
    body: dict,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import expressions as ex

    chat_id = body.get("chat_id") if isinstance(body, dict) else None
    name = body.get("name") if isinstance(body, dict) else None
    if not chat_id or not name:
        raise _visible(ValueError("request body must carry 'chat_id' and 'name'"))
    try:
        selection = await ex.select_for_chat(
            session, user_id, chat_id, name,
            source=body.get("source"), reason=body.get("reason"),
            message_id=body.get("message_id"))
    except ValueError as exc:
        raise _visible(exc) from exc
    if selection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="unknown chat")
    return selection


@router.post("/expressions/clear")
async def expressions_clear(
    body: dict,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import expressions as ex

    chat_id = body.get("chat_id") if isinstance(body, dict) else None
    if not chat_id:
        raise _visible(ValueError("request body must carry a 'chat_id'"))
    try:
        cleared = ex.clear_selection(
            user_id, chat_id, reason=body.get("reason"))
    except ValueError as exc:
        raise _visible(exc) from exc
    if not cleared:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no current expression for chat: {chat_id}")
    return {"cleared": True, "chat_id": chat_id}


# -- Chat Variables surface (P-093) --------------------------------------
# The one shared per-chat variables/flags store, in the
# house router idiom (owner dep, chat ownership verified
# before acting, ValueError -> 422 via _visible, missing
# entries -> 404). The store lives in
# runmal.plugins.variables; imports are lazy so this
# router's import graph is unchanged at module load. HTTP
# writes carry host provenance: the caller is the owner
# acting through the host, recorded as exactly that.


async def _owned_chat(session, user_id: str, body):
    from runmal.chats import service as chats_svc

    chat_id = body.get("chat_id") if isinstance(body, dict) else None
    if not chat_id:
        raise _visible(ValueError("request must carry a 'chat_id'"))
    if await chats_svc.get_chat(session, user_id, chat_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown chat: {chat_id}")
    return chat_id


@router.get("/chat-variables")
async def chat_variables_list(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.chats import service as chats_svc
    from runmal.plugins import variables as vars_mod

    if await chats_svc.get_chat(session, user_id, chat_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown chat: {chat_id}")
    try:
        return vars_mod.snapshot_chat(user_id, chat_id)
    except ValueError as exc:
        raise _visible(exc) from exc


@router.post("/chat-variables/set")
async def chat_variables_set(
    body: dict,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import variables as vars_mod

    chat_id = await _owned_chat(session, user_id, body)
    key = body.get("key")
    try:
        if "flag" in body:
            return vars_mod.set_flag(user_id, chat_id, key, body.get("flag"))
        if "value" not in body:
            raise vars_mod.ChatVariableError(
                "request must carry a 'value' or a 'flag'")
        return vars_mod.set_variable(user_id, chat_id, key, body.get("value"))
    except ValueError as exc:
        raise _visible(exc) from exc


@router.post("/chat-variables/unset")
async def chat_variables_unset(
    body: dict,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import variables as vars_mod

    chat_id = await _owned_chat(session, user_id, body)
    try:
        deleted = vars_mod.delete_variable(user_id, chat_id, body.get("key"))
    except ValueError as exc:
        raise _visible(exc) from exc
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown chat variable: {body.get('key')}")
    return {"deleted": True, "key": body.get("key")}


@router.post("/chat-variables/clear")
async def chat_variables_clear(
    body: dict,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import variables as vars_mod

    chat_id = await _owned_chat(session, user_id, body)
    try:
        removed = vars_mod.clear_chat(user_id, chat_id)
    except ValueError as exc:
        raise _visible(exc) from exc
    return {"cleared": True, "chat_id": chat_id, "removed": removed}


# -- Plugin Data Custody surface (P-094) -----------------------------------
# Export + delete-with-the-plugin, in the house router idiom
# (owner dep, house error mapping). Instances are not in the
# registry (records hold handlers, not instances), so the HTTP
# road reaches the owner-scoped roads that need no live
# instance (durable file, database via the request session,
# host ledger via the default manager) and reports instance
# sections unavailable with the reason named - never a partial
# export dressed as complete. The in-process road
# (runmal.plugins.custody) reaches instance state.


@router.get("/plugins/{plugin_id}/custody/export")
async def plugin_custody_export(
    plugin_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import custody as cu

    try:
        return await cu.export_plugin_data(
            plugin_id, user_id=user_id, session=session,
            registry=_registry(), manager=service.plugin_manager())
    except cu.UnknownPluginError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc)) from exc
    except cu.CustodyError as exc:
        raise _visible(exc) from exc


@router.post("/plugins/{plugin_id}/custody/delete")
async def plugin_custody_delete(
    plugin_id: str,
    body: dict,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import custody as cu

    if not isinstance(body, dict) or body.get("confirm") is not True:
        raise _visible(ValueError(
            "custody deletion requires an explicit {confirm: true}"))
    try:
        report = await cu.delete_plugin_data(
            plugin_id, user_id=user_id, session=session,
            registry=_registry(), manager=service.plugin_manager())
    except cu.UnknownPluginError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc)) from exc
    except cu.CustodyError as exc:
        raise _visible(exc) from exc
    await session.commit()
    return report


# -- Dice & Game Bridge surface (P-096) -----------------------------------
# Seeded, inspectable dice rolls plus the declared
# game-bridge event record surface, in the house router
# idiom (owner dep, chat ownership verified before
# acting, ValueError -> 422 via _visible, missing rolls
# -> 404). The citizen lives in runmal.plugins.game_bridge;
# imports are lazy so this router's import graph is
# unchanged at module load. HTTP writes carry host
# provenance: the caller is the owner acting through the
# host, recorded as exactly that. No route here opens a
# connection to any game client - the records are the
# surface (see docs/DICE_GAME_BRIDGE_2026-11-07.md).


@router.post("/game-bridge/roll")
async def game_bridge_roll(
    body: dict,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import game_bridge as gb

    chat_id = await _owned_chat(session, user_id, body)
    try:
        return gb.roll_for_chat(
            user_id, chat_id, body.get("notation"),
            seed=body.get("seed"), context=body.get("context") or "",
            target=body.get("target"))
    except ValueError as exc:
        raise _visible(exc) from exc


@router.get("/game-bridge/rolls")
async def game_bridge_rolls(
    chat_id: str,
    limit: int = 100,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.chats import service as chats_svc
    from runmal.plugins import game_bridge as gb

    if await chats_svc.get_chat(session, user_id, chat_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown chat: {chat_id}")
    try:
        return {"chat_id": chat_id,
                "rolls": gb.list_rolls(user_id, chat_id, limit=limit)}
    except ValueError as exc:
        raise _visible(exc) from exc


@router.get("/game-bridge/rolls/{roll_id}")
async def game_bridge_roll_detail(
    roll_id: str,
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.chats import service as chats_svc
    from runmal.plugins import game_bridge as gb

    if await chats_svc.get_chat(session, user_id, chat_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown chat: {chat_id}")
    try:
        return gb.verify_persisted_roll(user_id, chat_id, roll_id)
    except gb.DiceBridgeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc)) from exc
    except ValueError as exc:
        raise _visible(exc) from exc


@router.post("/game-bridge/events")
async def game_bridge_events_emit(
    body: dict,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import game_bridge as gb

    chat_id = await _owned_chat(session, user_id, body)
    try:
        return gb.emit_bridge_event(
            user_id, chat_id, body.get("kind"), body.get("payload"),
            target=body.get("target"))
    except ValueError as exc:
        raise _visible(exc) from exc


@router.get("/game-bridge/events")
async def game_bridge_events_list(
    chat_id: str,
    after_seq: int = 0,
    limit: int = 100,
    kind: str | None = None,
    target: str | None = None,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.chats import service as chats_svc
    from runmal.plugins import game_bridge as gb

    if await chats_svc.get_chat(session, user_id, chat_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown chat: {chat_id}")
    try:
        return {"chat_id": chat_id,
                "events": gb.list_bridge_events(
                    user_id, chat_id, after_seq=after_seq, limit=limit,
                    kind=kind, target=target)}
    except ValueError as exc:
        raise _visible(exc) from exc


@router.post("/game-bridge/events/ack")
async def game_bridge_events_ack(
    body: dict,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import game_bridge as gb

    chat_id = await _owned_chat(session, user_id, body)
    try:
        return gb.ack_bridge_events(
            user_id, chat_id, body.get("consumer"), body.get("up_to_seq"))
    except ValueError as exc:
        raise _visible(exc) from exc


@router.get("/game-bridge/inspect")
async def game_bridge_inspect(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.chats import service as chats_svc
    from runmal.plugins import game_bridge as gb

    if await chats_svc.get_chat(session, user_id, chat_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown chat: {chat_id}")
    try:
        return gb.inspect_chat(user_id, chat_id)
    except ValueError as exc:
        raise _visible(exc) from exc


@router.post("/game-bridge/clear")
async def game_bridge_clear(
    body: dict,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    from runmal.plugins import game_bridge as gb

    chat_id = await _owned_chat(session, user_id, body)
    try:
        removed = gb.clear_chat(user_id, chat_id)
    except ValueError as exc:
        raise _visible(exc) from exc
    return {"cleared": True, "chat_id": chat_id, "removed": removed}


# -- Plugin Settings UI surface (P-098) ------------------------------------
# The generated settings form + the validated owner-value
# road, in the house router idiom (owner dep, ValueError
# -> 422 via _visible with the NAMED validation errors in
# the detail, unknown plugin -> 404). Manifest resolution:
# registry record first, else a shipped citizen manifest
# (the P-094 pattern). The citizen lives in
# runmal.plugins.settings_ui; imports are lazy so this
# router's import graph is unchanged at module load.


def _settings_manifest_or_404(plugin_id: str):
    from runmal.plugins import settings_ui as su

    manifest = su.resolve_manifest(_registry(), plugin_id)
    if manifest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown plugin: {plugin_id}")
    return manifest


def _settings_error(exc: Exception) -> HTTPException:
    from runmal.plugins import settings_ui as su

    if isinstance(exc, su.SettingsValidationError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "errors": exc.errors})
    return _visible(exc)


@router.get("/plugins/{plugin_id}/settings-form")
async def plugin_settings_form(
    plugin_id: str,
    user_id: str = Depends(get_owner_id),
):
    from runmal.plugins import settings_ui as su

    manifest = _settings_manifest_or_404(plugin_id)
    try:
        return su.form_for_owner(user_id, manifest)
    except ValueError as exc:
        raise _settings_error(exc) from exc


@router.get("/plugins/{plugin_id}/settings")
async def plugin_settings_values(
    plugin_id: str,
    user_id: str = Depends(get_owner_id),
):
    from runmal.plugins import settings_ui as su

    manifest = _settings_manifest_or_404(plugin_id)
    try:
        values = su.get_plugin_settings(user_id, manifest)
        stored = su.load_stored_values(user_id, plugin_id)
    except ValueError as exc:
        raise _settings_error(exc) from exc
    return {"plugin_id": plugin_id, "values": values, "stored": stored,
            "defaults": su.declared_defaults(manifest)}


@router.post("/plugins/{plugin_id}/settings")
async def plugin_settings_save(
    plugin_id: str,
    body: dict,
    user_id: str = Depends(get_owner_id),
):
    from runmal.plugins import settings_ui as su

    manifest = _settings_manifest_or_404(plugin_id)
    if not isinstance(body, dict) or not isinstance(body.get("values"), dict):
        raise _visible(ValueError(
            "request must carry a 'values' object"))
    try:
        return su.save_plugin_settings(user_id, manifest, body["values"])
    except ValueError as exc:
        raise _settings_error(exc) from exc


@router.post("/plugins/{plugin_id}/settings/delete")
async def plugin_settings_delete(
    plugin_id: str,
    body: dict,
    user_id: str = Depends(get_owner_id),
):
    from runmal.plugins import settings_ui as su

    _settings_manifest_or_404(plugin_id)
    if not isinstance(body, dict) or body.get("confirm") is not True:
        raise _visible(ValueError(
            "settings deletion requires an explicit {confirm: true}"))
    try:
        return su.delete_plugin_settings(user_id, plugin_id)
    except ValueError as exc:
        raise _settings_error(exc) from exc
