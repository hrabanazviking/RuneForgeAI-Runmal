"""Plugin API REST surface (P-081, design section 8).

Read + lifecycle verbs only: there is deliberately NO
``POST /plugins`` (register/install) and NO ``DELETE`` --
registration is trusted in-process code in v1, and their absence
is pinned by the battery. Unknown plugin id -> 404;
:class:`InvalidPluginTransition` -> 422 (house ``_visible``
pattern); an ``on_enable`` failure answers 200 with the ERRORED
record -- the record IS the report, never a 500 (PLG-01).

The registry comes from the service layer's default holder
(lead adjudication B); when none is installed, one empty
registry is built lazily so the surface still answers honestly.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from runmal.plugins import service
from runmal.plugins.api import UI_SLOTS
from runmal.plugins.registry import InvalidPluginTransition

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


@router.get("/plugins")
async def list_plugins():
    registry = _registry()
    return [service.record_to_dict(registry.get(plugin_id))
            for plugin_id in registry.keys()]


@router.get("/plugins/{plugin_id}")
async def plugin_detail(plugin_id: str):
    registry = _registry()
    record = _record_or_404(registry, plugin_id)
    return service.record_detail_to_dict(record, registry)


@router.post("/plugins/{plugin_id}/enable")
async def plugin_enable(plugin_id: str):
    registry = _registry()
    _record_or_404(registry, plugin_id)
    try:
        record = registry.enable(plugin_id)
    except InvalidPluginTransition as exc:
        raise _visible(exc) from exc
    return service.record_detail_to_dict(record, registry)


@router.post("/plugins/{plugin_id}/disable")
async def plugin_disable(plugin_id: str):
    registry = _registry()
    _record_or_404(registry, plugin_id)
    try:
        record = registry.disable(plugin_id)
    except InvalidPluginTransition as exc:
        raise _visible(exc) from exc
    return service.record_detail_to_dict(record, registry)


@router.post("/plugins/{plugin_id}/acknowledge")
async def plugin_acknowledge(plugin_id: str):
    registry = _registry()
    _record_or_404(registry, plugin_id)
    try:
        record = registry.acknowledge(plugin_id)
    except InvalidPluginTransition as exc:
        raise _visible(exc) from exc
    return service.record_detail_to_dict(record, registry)
