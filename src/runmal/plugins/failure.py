"""Failure manners (P-099): plain reports, guarded calls,
and the sandbox bridge.

Roadmap line: a crashing plugin disables itself with a
plain report; the chat never dies with it. The foundations
are P-081 (registry record_failure: strikes, ERRORED at
FAILURE_LIMIT consecutive failures, no dispatch while not
ENABLED, enable/acknowledge lifecycle) and P-082 (Sandbox
.run isolation + quarantine at 3). This module makes the
manners complete without changing either foundation:

- PLAIN REPORTS: one inspectable report per plugin saying,
  in plain words, what crashed, on which road, with what
  exception class, when, how many strikes, whether the
  plugin has disabled itself, and what happens next.
- GUARDED CALLS: guard_plugin_call / _async wrap ANY
  host-invoked plugin callable in the recording road, so
  a direct citizen call is contained exactly like an
  event dispatch or a prompt hook: recorded, never raised
  through, siblings and host unaffected.
- SANDBOX BRIDGE: sandbox failures are mirrored into the
  registry record 1:1 (surface "sandbox", hook "run",
  the real exception class), so a sandbox-quarantined
  plugin self-disables in the registry too and is not
  dispatched on other roads.

Declared re-enable rule (R4): re-enabling is ONLY the
registry explicit enable verb. It clears the strike
counter and KEEPS the failure history (failure_log and
last_error). Nothing here retries or auto-re-enables:
no timer, no loop, no second chance inside a road.

Report hygiene (R6): reports carry ids, road, exception
CLASS, timestamps and counts - never payloads. Message
text appears only scrubbed (caller-named secret values
replaced with [redacted], length capped); the plain
report never embeds message text at all, so it cannot
leak a secret value or a payload by construction.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any

from runmal.plugins.api import FAILURE_LIMIT
from runmal.plugins.registry import (
    PluginFailure,
    PluginRecord,
    PluginRegistry,
    PluginState,
)

__all__ = [
    "FailureReport", "GuardOutcome", "all_failure_reports",
    "apply_sandbox_bridge", "build_failure_report",
    "failure_report", "guard_plugin_call",
    "guard_plugin_call_async", "plain_report", "scrub_text",
    "sandbox_failure_report",
]

REDACTED = "[redacted]"
MESSAGE_LIMIT = 200


def scrub_text(text: object, secret_values=(), *,
               limit: int = MESSAGE_LIMIT) -> str:
    """Message text safe for a report: caller-named secret
    values replaced, length capped. Secrets are handled by
    VALUE here only because the caller names what to hide;
    nothing is stored and no secret is ever echoed."""
    out = "" if text is None else str(text)
    for value in secret_values or ():
        if value:
            out = out.replace(str(value), REDACTED)
    return out[:limit]


def _failure_dict(failure: PluginFailure, secret_values) -> dict:
    return {
        "plugin_id": failure.plugin_id,
        "surface": failure.surface,
        "hook": failure.hook,
        "error_type": failure.error_type,
        "message": scrub_text(failure.message, secret_values),
        "at": failure.at.isoformat(),
    }


def plain_report(record: PluginRecord) -> str:
    """The plain report: deterministic, message-free text.

    Names the plugin, its state, its recorded failures
    (road + exception class + time), its strike count,
    whether it has disabled itself, and the one road back
    (a deliberate re-enable, which keeps this history).
    """
    pid = record.manifest.id
    state = record.state.value
    total = len(record.failure_log)
    if total == 0:
        return (f"Plugin '{pid}' is {state}; "
                "no failures have been recorded for it.")
    last = record.failure_log[-1]
    head = (f"Plugin '{pid}' has crashed {total} time(s); "
            f"the latest crash was on the {last.surface} road "
            f"({last.hook}), which raised {last.error_type} "
            f"at {last.at.isoformat()}. It has "
            f"{record.consecutive_failures} strike(s) in a row "
            f"(it disables itself at {FAILURE_LIMIT}).")
    if record.state is PluginState.ERRORED:
        tail = (" It has disabled itself and will not run "
                "again until you deliberately re-enable it; "
                "re-enabling clears its strikes but keeps "
                "this failure history.")
    elif record.state is PluginState.DISABLED:
        tail = (" It is disabled and will not run again "
                "until you deliberately re-enable it.")
    elif record.state is PluginState.ENABLED:
        tail = (" It is still enabled; if it keeps crashing "
                "it will disable itself.")
    else:
        tail = f" It is currently {state}."
    return head + tail


@dataclass(frozen=True)
class FailureReport:
    """One plugin's inspectable failure report (P-099)."""

    plugin_id: str
    state: str
    enabled: bool
    self_disabled: bool
    consecutive_failures: int
    failure_limit: int
    total_recorded: int
    last_failure: dict | None
    failures: list[dict] = field(default_factory=list)
    plain: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "state": self.state,
            "enabled": self.enabled,
            "self_disabled": self.self_disabled,
            "consecutive_failures": self.consecutive_failures,
            "failure_limit": self.failure_limit,
            "total_recorded": self.total_recorded,
            "last_failure": self.last_failure,
            "failures": [dict(row) for row in self.failures],
            "plain": self.plain,
            "reenable_rule": (
                "deliberate enable only; strikes clear, "
                "failure history is kept; nothing retries "
                "or re-enables automatically"),
        }


def build_failure_report(record: PluginRecord, *,
                         secret_values=()) -> FailureReport:
    failures = [_failure_dict(row, secret_values)
                for row in record.failure_log]
    return FailureReport(
        plugin_id=record.manifest.id,
        state=record.state.value,
        enabled=record.state is PluginState.ENABLED,
        self_disabled=record.state is PluginState.ERRORED,
        consecutive_failures=record.consecutive_failures,
        failure_limit=FAILURE_LIMIT,
        total_recorded=len(failures),
        last_failure=failures[-1] if failures else None,
        failures=failures,
        plain=plain_report(record),
    )


def failure_report(registry: PluginRegistry, plugin_id: str,
                   *, secret_values=()) -> FailureReport:
    """The report for one registered plugin (KeyError if
    the id is unknown - an inspect road must not invent a
    report for a plugin that does not exist)."""
    return build_failure_report(
        registry.get(plugin_id), secret_values=secret_values)


def all_failure_reports(registry: PluginRegistry, *,
                        secret_values=()) -> list[FailureReport]:
    """Reports for every registered plugin, in
    registration order (the PLG-04 order)."""
    return [build_failure_report(record, secret_values=secret_values)
            for record in registry.records()]


@dataclass(frozen=True)
class GuardOutcome:
    """The result of one guarded host invocation (R5:
    the outcome always names what happened)."""

    plugin_id: str
    invoked: bool
    ok: bool
    value: Any = None
    failure: PluginFailure | None = None
    skipped_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "invoked": self.invoked,
            "ok": self.ok,
            "skipped_reason": self.skipped_reason,
            "failure": (
                {"surface": self.failure.surface,
                 "hook": self.failure.hook,
                 "error_type": self.failure.error_type,
                 "at": self.failure.at.isoformat()}
                if self.failure is not None else None),
        }


def _gate(registry, plugin_id):
    record = registry.find(plugin_id)
    if record is None:
        return None, GuardOutcome(
            plugin_id=plugin_id, invoked=False, ok=False,
            skipped_reason="unknown_plugin")
    if record.state is not PluginState.ENABLED:
        return None, GuardOutcome(
            plugin_id=plugin_id, invoked=False, ok=False,
            skipped_reason="not_enabled")
    return record, None


def guard_plugin_call(registry: PluginRegistry, plugin_id: str,
                      surface: str, hook: str, fn, *args,
                      **kwargs) -> GuardOutcome:
    """Invoke ``fn`` for an ENABLED plugin, contained (R1).

    A raise is recorded through registry.record_failure
    (which may self-disable the plugin at the limit) and
    returned as data - it never propagates. A non-ENABLED
    or unknown plugin is not invoked at all (R3) and the
    skip is named, not recorded as a new failure.
    A sync guard refuses an awaitable result honestly:
    the coroutine is closed and recorded as a TypeError
    failure (the registry lifecycle precedent), never
    silently dropped.
    """
    record, skipped = _gate(registry, plugin_id)
    if skipped is not None:
        return skipped
    try:
        value = fn(*args, **kwargs)
        if inspect.isawaitable(value):
            if inspect.iscoroutine(value):
                value.close()
            raise TypeError(
                "async plugin callables need "
                "guard_plugin_call_async")
    except Exception as exc:
        failure = registry.record_failure(record, surface, hook, exc)
        return GuardOutcome(plugin_id=plugin_id, invoked=True,
                            ok=False, failure=failure)
    registry.record_success(record)
    return GuardOutcome(plugin_id=plugin_id, invoked=True,
                        ok=True, value=value)


async def guard_plugin_call_async(registry: PluginRegistry,
                                  plugin_id: str, surface: str,
                                  hook: str, fn, *args,
                                  **kwargs) -> GuardOutcome:
    """The async twin of :func:`guard_plugin_call`: sync
    and async callables are both accepted, same manners."""
    record, skipped = _gate(registry, plugin_id)
    if skipped is not None:
        return skipped
    try:
        value = fn(*args, **kwargs)
        if inspect.isawaitable(value):
            value = await value
    except Exception as exc:
        failure = registry.record_failure(record, surface, hook, exc)
        return GuardOutcome(plugin_id=plugin_id, invoked=True,
                            ok=False, failure=failure)
    registry.record_success(record)
    return GuardOutcome(plugin_id=plugin_id, invoked=True,
                        ok=True, value=value)


# -- sandbox bridge ------------------------------------------------
# Watermark per (sandbox object, plugin): how many of that
# sandbox's recorded failures have already been mirrored.
_BRIDGED: dict[tuple[int, str], int] = {}


def _bridged_exc(failure) -> Exception:
    """Rebuild an exception carrying the sandbox failure's
    real class NAME and message, so record_failure stores
    the true error_type (the sandbox RunFailure is data,
    not the original exception object)."""
    name = failure.error_type
    cls = Exception
    if isinstance(name, str) and name.isidentifier():
        cls = type(name, (Exception,), {})
    return cls(failure.message)


def apply_sandbox_bridge(registry: PluginRegistry, sandbox,
                         ) -> int:
    """Mirror unbridged sandbox failures into the registry
    record, 1:1, surface "sandbox" / hook "run". Returns
    how many were bridged this call; idempotent - a second
    call with no new sandbox failures bridges zero. When
    the mirrored strikes reach FAILURE_LIMIT the registry
    self-disables the plugin exactly as on any other road,
    so a quarantined sandbox and an ERRORED record agree.
    An unknown plugin bridges nothing and returns 0."""
    record = registry.find(sandbox.plugin_id)
    if record is None:
        return 0
    key = (id(sandbox), sandbox.plugin_id)
    done = _BRIDGED.get(key, 0)
    failures = sandbox.failures()
    bridged = 0
    for failure in failures[done:]:
        registry.record_failure(
            record, "sandbox", "run", _bridged_exc(failure))
        bridged += 1
    _BRIDGED[key] = done + bridged
    return bridged


def sandbox_failure_report(sandbox, *, secret_values=()) -> dict:
    """The sandbox silo in the same report shape: road
    "sandbox", quarantine named plainly, messages scrubbed,
    plain text message-free like every other report."""
    from runmal.sandbox.guard import FAILURE_LIMIT as SB_LIMIT
    failures = [{
        "plugin_id": row.plugin_id, "surface": "sandbox",
        "hook": "run", "error_type": row.error_type,
        "message": scrub_text(row.message, secret_values),
        "at": row.at.isoformat()} for row in sandbox.failures()]
    pid = sandbox.plugin_id
    if not failures:
        plain = (f"Plugin '{pid}' sandbox has recorded no "
                 "failures; it is not quarantined.")
    elif sandbox.quarantined:
        plain = (f"Plugin '{pid}' sandbox has quarantined "
                 f"itself after {sandbox.consecutive_failures} "
                 "consecutive failures; it refuses to run "
                 "until its failures are reset.")
    else:
        plain = (f"Plugin '{pid}' sandbox has recorded "
                 f"{len(failures)} failure(s), "
                 f"{sandbox.consecutive_failures} in a row; "
                 "it is not quarantined.")
    return {
        "plugin_id": pid, "surface": "sandbox",
        "quarantined": sandbox.quarantined,
        "consecutive_failures": sandbox.consecutive_failures,
        "failure_limit": SB_LIMIT,
        "total_recorded": len(failures),
        "last_failure": failures[-1] if failures else None,
        "failures": failures, "plain": plain,
    }
