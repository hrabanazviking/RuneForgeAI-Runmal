"""Plugin registry: lifecycle, failure rule, dispatch, UI queries (P-081).

Design sections 2 (lifecycle + failure rule), 3 (event dispatch),
5 (UI contributions) and 6 (registration-time compatibility). The
registry is process-local, in-memory state -- the tree's own
precedents are ``backends/registry.py`` (a plain dict behind sorted
``keys()``) and generation's module-level token dict. Nothing here
persists across a restart in v1 (design section 7).

Manners (PLG-01): no plugin failure -- event handler, lifecycle
callback, prompt hook (recorded via :meth:`PluginRegistry.
record_failure` from hooks.py) -- ever raises through a host path.
Failures append a :class:`PluginFailure`, increment a consecutive
counter, and at :data:`~runmal.plugins.api.FAILURE_LIMIT`
consecutive failures flip an ENABLED plugin to ERRORED, after
which it receives no dispatch of any kind until the owner
acknowledges or re-enables it.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from runmal.plugins.api import (
    FAILURE_LIMIT,
    SUPPORTED_API_VERSIONS,
)
from runmal.plugins.events import PluginEvent, make_event, payload_for_receiver
from runmal.plugins.manifest import (
    ManifestError,
    PluginManifest,
    validate_surface_requirements,
)

#: Canonical-JSON byte cap for one UI contribution payload
#: (design section 5): a contribution is a declaration, not a
#: data store.
UI_PAYLOAD_MAX_BYTES = 4096

#: How many failures a record retains for the detail view.
FAILURE_LOG_SIZE = 20


class PluginRegistrationError(ValueError):
    """Registration refused: duplicate id, unmet surface
    requirements, undeclared / missing handler bindings, oversized
    UI payload. No partial record is left behind."""


class PluginCompatibilityError(ValueError):
    """Registration refused: the manifest's ``api_version`` is not
    in :data:`SUPPORTED_API_VERSIONS` (design section 6, REJECT
    semantics). Carries the verdict as data."""

    def __init__(self, plugin_id: str, plugin_api_version: int,
                 supported: list[int]):
        self.plugin_id = plugin_id
        self.plugin_api_version = plugin_api_version
        self.supported = list(supported)
        super().__init__(
            f"plugin {plugin_id!r} targets api_version "
            f"{plugin_api_version}, supported: {self.supported}"
        )


class InvalidPluginTransition(ValueError):
    """A lifecycle verb was attempted from a state the design
    section 2 table does not list for it. Surfaced 422 by the
    router."""


class PluginState(StrEnum):
    DISCOVERED = "discovered"
    REGISTERED = "registered"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERRORED = "errored"


@dataclass(frozen=True)
class PluginFailure:
    """One recorded handler failure (design section 2).

    Metadata only (PLG-05): ids, surface, hook, the exception TYPE
    and a truncated ``str(exc)`` -- never payloads or content.
    """

    plugin_id: str
    surface: str  # "event" | "prompt" | "ui" | "lifecycle"
    hook: str
    error_type: str
    message: str
    at: datetime = field(
        default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict:
        return {
            "plugin_id": self.plugin_id,
            "surface": self.surface,
            "hook": self.hook,
            "error_type": self.error_type,
            "message": self.message,
            "at": self.at.isoformat(),
        }


@dataclass(frozen=True)
class PluginHandlers:
    """Code bound to a manifest at registration (design section 1).

    Never part of the manifest, never serialised. ``on_event`` is
    one callable for all declared events or a per-event mapping
    (the mapping wins per name); sync and async callables are both
    accepted everywhere. ``prompt_hooks`` is keyed by declared
    hook id.
    """

    on_event: Callable | Mapping[str, Callable] | None = None
    prompt_hooks: Mapping[str, Callable] = field(default_factory=dict)
    on_enable: Callable | None = None
    on_disable: Callable | None = None


@dataclass
class PluginRecord:
    """One registered plugin: manifest + bound handlers + state.

    Mutable by the registry alone (state flips, failure counters);
    outward views go through ``service.record_to_dict``.
    ``failure_log`` is a ring holding the last
    :data:`FAILURE_LOG_SIZE` failures.
    """

    manifest: PluginManifest
    handlers: PluginHandlers
    state: PluginState
    registration_index: int
    consecutive_failures: int = 0
    last_error: PluginFailure | None = None
    failure_log: list[PluginFailure] = field(default_factory=list)

    @property
    def plugin_id(self) -> str:
        return self.manifest.id


@dataclass(frozen=True)
class UIContribution:
    """One UI slot contribution: the manifest entry, as data
    (design section 5). ``active`` is computed at query time from
    the owning plugin's state."""

    id: str
    plugin_id: str
    slot: str
    label: str
    order: int
    payload: dict
    registration_index: int

    def to_dict(self, *, active: bool, owner_state: str) -> dict:
        return {
            "id": self.id,
            "plugin_id": self.plugin_id,
            "slot": self.slot,
            "label": self.label,
            "order": self.order,
            "payload": dict(self.payload),
            "active": active,
            "owner_state": owner_state,
            "registration_index": self.registration_index,
        }


@dataclass
class DispatchReport:
    """The outcome of one dispatch (design section 3): returned
    for tests / logging; host call sites ignore it (PLG-01)."""

    delivered: list[str] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"delivered": list(self.delivered),
                "failed": [dict(row) for row in self.failed]}


def _canonical_payload_size(payload: dict) -> int:
    return len(json.dumps(payload, sort_keys=True,
                          separators=(",", ":"),
                          ensure_ascii=False).encode("utf-8"))


class PluginRegistry:
    """All registered plugins, their lifecycle and dispatch."""

    def __init__(self) -> None:
        self._records: dict[str, PluginRecord] = {}
        self._discovered: dict[str, PluginManifest] = {}
        self._next_index = 0

    # -- discovery -------------------------------------------------

    def note_discovered(self, manifest: PluginManifest) -> PluginManifest:
        """Record a parsed manifest as DISCOVERED (design section
        2): known, but receiving and contributing nothing until
        trusted code registers it."""
        self._discovered[manifest.id] = manifest
        return manifest

    def discovered(self) -> list[str]:
        return sorted(self._discovered)

    def is_discovered(self, plugin_id: str) -> bool:
        return plugin_id in self._discovered

    # -- registration ----------------------------------------------

    def register(self, manifest: PluginManifest,
                 handlers: PluginHandlers | None = None) -> PluginRecord:
        """Validate + bind + land REGISTERED (design sections 1/6).

        Compatibility first (REJECT, no record), then duplicate
        live id, surface cross-checks, UI payload cap and handler
        cross-checks. Any failure raises before any state changes:
        no partial record, ever.
        """
        if manifest.api_version not in SUPPORTED_API_VERSIONS:
            raise PluginCompatibilityError(
                manifest.id, manifest.api_version,
                sorted(SUPPORTED_API_VERSIONS))
        if manifest.id in self._records:
            raise PluginRegistrationError(
                f"plugin id already registered: {manifest.id!r}")
        try:
            validate_surface_requirements(manifest)
        except ManifestError as exc:
            raise PluginRegistrationError(str(exc)) from exc
        for decl in manifest.ui_slots:
            if _canonical_payload_size(decl.payload) > UI_PAYLOAD_MAX_BYTES:
                raise PluginRegistrationError(
                    f"ui contribution {decl.id!r} payload exceeds "
                    f"{UI_PAYLOAD_MAX_BYTES} canonical JSON bytes")
        handlers = handlers if handlers is not None else PluginHandlers()
        self._check_handlers(manifest, handlers)
        record = PluginRecord(
            manifest=manifest, handlers=handlers,
            state=PluginState.REGISTERED,
            registration_index=self._next_index)
        self._next_index += 1
        self._records[manifest.id] = record
        self._discovered.pop(manifest.id, None)
        return record

    @staticmethod
    def _check_handlers(manifest: PluginManifest,
                        handlers: PluginHandlers) -> None:
        declared_hooks = {hook.id for hook in manifest.prompt_hooks}
        bound = dict(handlers.prompt_hooks or {})
        for hook_id in sorted(set(bound) - declared_hooks):
            raise PluginRegistrationError(
                f"handler bound for undeclared prompt hook: {hook_id!r}")
        for hook_id in sorted(declared_hooks - set(bound)):
            raise PluginRegistrationError(
                f"declared prompt hook has no handler: {hook_id!r}")
        for hook_id, fn in bound.items():
            if not callable(fn):
                raise PluginRegistrationError(
                    f"prompt hook handler is not callable: {hook_id!r}")
        on_event = handlers.on_event
        if isinstance(on_event, Mapping):
            for name in on_event:
                if name not in manifest.events:
                    raise PluginRegistrationError(
                        f"event handler bound for undeclared event: "
                        f"{name!r}")
                if not callable(on_event[name]):
                    raise PluginRegistrationError(
                        f"event handler is not callable: {name!r}")
        elif on_event is not None and not callable(on_event):
            raise PluginRegistrationError("on_event is not callable")
        for name in ("on_enable", "on_disable"):
            fn = getattr(handlers, name)
            if fn is not None and not callable(fn):
                raise PluginRegistrationError(f"{name} is not callable")

    # -- queries (BackendRegistry idiom) ----------------------------

    def get(self, plugin_id: str) -> PluginRecord:
        return self._records[plugin_id]

    def find(self, plugin_id: str) -> PluginRecord | None:
        return self._records.get(plugin_id)

    def __contains__(self, plugin_id: str) -> bool:
        return plugin_id in self._records

    def keys(self) -> list[str]:
        return sorted(self._records)

    def records(self) -> list[PluginRecord]:
        """All records in registration order (PLG-04's order)."""
        return sorted(self._records.values(),
                      key=lambda r: r.registration_index)

    def enabled_records(self) -> list[PluginRecord]:
        return [r for r in self.records()
                if r.state is PluginState.ENABLED]

    # -- failure machinery (design section 2) -----------------------

    def record_failure(self, record: PluginRecord, surface: str,
                       hook: str, exc: BaseException) -> PluginFailure:
        failure = PluginFailure(
            plugin_id=record.manifest.id, surface=surface, hook=hook,
            error_type=type(exc).__name__, message=str(exc)[:500])
        record.failure_log.append(failure)
        del record.failure_log[:-FAILURE_LOG_SIZE]
        record.last_error = failure
        record.consecutive_failures += 1
        if (record.state is PluginState.ENABLED
                and record.consecutive_failures >= FAILURE_LIMIT):
            record.state = PluginState.ERRORED
        return failure

    def record_success(self, record: PluginRecord) -> None:
        record.consecutive_failures = 0

    # -- lifecycle (design section 2 transition table) --------------

    def _record_for_transition(self, plugin_id: str,
                               verb: str) -> PluginRecord:
        record = self._records.get(plugin_id)
        if record is None:
            if plugin_id in self._discovered:
                raise InvalidPluginTransition(
                    f"cannot {verb} plugin {plugin_id!r}: "
                    f"state is 'discovered'")
            raise KeyError(plugin_id)
        return record

    @staticmethod
    def _call_sync(fn: Callable, *args):
        """Call a lifecycle callback from a sync lifecycle verb.

        Sync callbacks are the v1 expectation (trusted in-tree).
        An awaitable result is driven to completion when no event
        loop is running; inside a running loop it cannot be
        awaited from here, so it is closed and reported as a
        TypeError failure through the normal failure path --
        never silently dropped.
        """
        result = fn(*args)
        if inspect.isawaitable(result):
            import asyncio
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(_await_value(result))
            else:
                if inspect.iscoroutine(result):
                    result.close()
                raise TypeError(
                    "async lifecycle callbacks are not supported "
                    "by the sync lifecycle verbs in v1")
        return result

    def enable(self, plugin_id: str) -> PluginRecord:
        """REGISTERED / DISABLED / ERRORED -> ENABLED.

        ERRORED resets the failure counter first (the acknowledge
        reset, then enable). ``on_enable`` runs AFTER the flip; if
        it raises, the record lands ERRORED and the record itself
        is returned -- the failure is reported in the record,
        never raised through (PLG-01).
        """
        record = self._record_for_transition(plugin_id, "enable")
        if record.state not in (PluginState.REGISTERED,
                                PluginState.DISABLED,
                                PluginState.ERRORED):
            raise InvalidPluginTransition(
                f"cannot enable plugin {plugin_id!r}: "
                f"state is {record.state.value!r}")
        if record.state is PluginState.ERRORED:
            record.consecutive_failures = 0
        record.state = PluginState.ENABLED
        if record.handlers.on_enable is not None:
            try:
                self._call_sync(record.handlers.on_enable)
            except Exception as exc:
                self.record_failure(record, "lifecycle", "on_enable", exc)
                record.state = PluginState.ERRORED
            else:
                self.record_success(record)
        return record

    def disable(self, plugin_id: str) -> PluginRecord:
        """ENABLED -> DISABLED. ``on_disable`` runs AFTER the
        flip; its failure is recorded but can never veto the
        disable -- the plugin stays DISABLED."""
        record = self._record_for_transition(plugin_id, "disable")
        if record.state is not PluginState.ENABLED:
            raise InvalidPluginTransition(
                f"cannot disable plugin {plugin_id!r}: "
                f"state is {record.state.value!r}")
        record.state = PluginState.DISABLED
        if record.handlers.on_disable is not None:
            try:
                self._call_sync(record.handlers.on_disable)
            except Exception as exc:
                self.record_failure(record, "lifecycle", "on_disable", exc)
            else:
                self.record_success(record)
        return record

    def acknowledge(self, plugin_id: str) -> PluginRecord:
        """ERRORED -> DISABLED. Clears the consecutive counter;
        ``failure_log`` and ``last_error`` are retained."""
        record = self._record_for_transition(plugin_id, "acknowledge")
        if record.state is not PluginState.ERRORED:
            raise InvalidPluginTransition(
                f"cannot acknowledge plugin {plugin_id!r}: "
                f"state is {record.state.value!r}")
        record.state = PluginState.DISABLED
        record.consecutive_failures = 0
        return record

    def unregister(self, plugin_id: str) -> PluginRecord:
        """REGISTERED / DISABLED / ERRORED -> gone. An ENABLED
        plugin must be disabled first."""
        record = self._record_for_transition(plugin_id, "unregister")
        if record.state is PluginState.ENABLED:
            raise InvalidPluginTransition(
                f"cannot unregister plugin {plugin_id!r}: "
                f"state is 'enabled' (disable it first)")
        del self._records[plugin_id]
        return record

    # -- event dispatch (design section 3) --------------------------

    def _event_handler(self, record: PluginRecord,
                       name: str) -> Callable | None:
        on_event = record.handlers.on_event
        if on_event is None:
            return None
        if isinstance(on_event, Mapping):
            return on_event.get(name)
        return on_event

    def has_enabled_subscriber(self, name: str) -> bool:
        return any(name in r.manifest.events
                   for r in self.enabled_records())

    async def dispatch_event(self, name: str, *, chat_id=None,
                             message_id=None, data=None) -> DispatchReport:
        """Fire-and-observe delivery to ENABLED subscribers, in
        registration order. Per-receiver payloads are redacted by
        :func:`payload_for_receiver` (content only for chat.read
        receivers). Each handler is isolated: a failure is
        recorded, the rest still run, dispatch never raises."""
        base = make_event(name, chat_id=chat_id,
                          message_id=message_id, data=data or {})
        report = DispatchReport()
        for record in self.records():
            if record.state is not PluginState.ENABLED:
                continue
            if name not in record.manifest.events:
                continue
            handler = self._event_handler(record, name)
            if handler is None:
                continue
            event = PluginEvent(
                name=base.name, api_version=base.api_version,
                occurred_at=base.occurred_at, chat_id=base.chat_id,
                message_id=base.message_id,
                data=payload_for_receiver(
                    base.data, permissions=record.manifest.permissions))
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                self.record_failure(record, "event", name, exc)
                report.failed.append(
                    {"plugin_id": record.manifest.id,
                     "error_type": type(exc).__name__})
            else:
                self.record_success(record)
                report.delivered.append(record.manifest.id)
        return report

    # -- prompt hook plan (design section 4) -------------------------

    def prompt_hook_plan(self, stage: str) -> list[dict]:
        """The ordered plan for one stage: ENABLED plugins only,
        sorted (priority ASC, registration_index ASC) -- PLG-04."""
        rows: list[dict] = []
        for record in self.enabled_records():
            for hook in record.manifest.prompt_hooks:
                if hook.stage == stage:
                    rows.append({
                        "plugin_id": record.manifest.id,
                        "hook_id": hook.id,
                        "priority": hook.priority,
                        "registration_index": record.registration_index,
                    })
        rows.sort(key=lambda r: (r["priority"], r["registration_index"]))
        return rows

    def handler_for_hook(self, record: PluginRecord,
                         hook_id: str) -> Callable | None:
        return dict(record.handlers.prompt_hooks or {}).get(hook_id)

    # -- UI contributions (design section 5) -------------------------

    def _contributions(self, record: PluginRecord) -> list[UIContribution]:
        return [
            UIContribution(
                id=decl.id, plugin_id=record.manifest.id,
                slot=decl.slot, label=decl.label, order=decl.order,
                payload=dict(decl.payload),
                registration_index=record.registration_index)
            for decl in record.manifest.ui_slots
        ]

    def ui_contributions(self, slot: str | None = None, *,
                         active_only: bool = False) -> list[dict]:
        """All contributions (optionally for one slot), sorted
        (slot, order ASC, registration_index ASC, id). Inert
        owners' contributions stay queryable with active=False."""
        rows: list[dict] = []
        for record in self.records():
            active = record.state is PluginState.ENABLED
            if active_only and not active:
                continue
            for contribution in self._contributions(record):
                if slot is not None and contribution.slot != slot:
                    continue
                rows.append(contribution.to_dict(
                    active=active, owner_state=record.state.value))
        rows.sort(key=lambda r: (r["slot"], r["order"],
                                 r["registration_index"], r["id"]))
        return rows

    def ui_slots_summary(self) -> dict:
        """``{slot: {total, active}}`` for every name in UI_SLOTS,
        zeros included -- honest emptiness."""
        from runmal.plugins.api import UI_SLOTS
        summary = {name: {"total": 0, "active": 0}
                   for name in sorted(UI_SLOTS)}
        for row in self.ui_contributions():
            summary[row["slot"]]["total"] += 1
            if row["active"]:
                summary[row["slot"]]["active"] += 1
        return summary


async def _await_value(awaitable):
    return await awaitable
