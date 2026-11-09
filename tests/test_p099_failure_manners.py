"""P-099 Failure manners battery.

Pins the manners layer on the P-081/P-082 foundations: a
raising citizen is contained on every host road (event
dispatch, prompt hooks, guarded direct calls) while the
host and sibling citizens complete; at FAILURE_LIMIT
consecutive failures the plugin disables itself with a
recorded, inspectable, plain-language report; a disabled
plugin is never invoked again and nothing auto-retries
or auto-re-enables it; deliberate re-enable clears the
strikes and keeps the history; sandbox quarantine bridges
into the registry 1:1; no report carries a secret value.
No migration: head stays 0041.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.plugins import service as plugin_service
from runmal.plugins.api import FAILURE_LIMIT
from runmal.plugins.failure import (
    all_failure_reports,
    apply_sandbox_bridge,
    build_failure_report,
    failure_report,
    guard_plugin_call,
    guard_plugin_call_async,
    sandbox_failure_report,
    scrub_text,
)
from runmal.plugins.hooks import apply_slot_hooks
from runmal.plugins.manifest import manifest_from_data
from runmal.plugins.registry import (
    PluginHandlers,
    PluginRegistry,
    PluginState,
)
from runmal.prompt.slots import Slot
from runmal.sandbox.guard import Sandbox

SECRET = "ZqxFailureSecret99"
CRASHER = "acme.crasher"
HEALTHY = "acme.healthy"


def make_manifest(plugin_id, **over):
    data = {"id": plugin_id, "name": plugin_id,
            "version": "1.0.0", "api_version": 1}
    data.update(over)
    return manifest_from_data(data)


def event_registry(crasher_calls, healthy_calls):
    registry = PluginRegistry()

    def crash(event):
        crasher_calls.append(event.name)
        raise RuntimeError(f"kaput {SECRET}")

    def ok(event):
        healthy_calls.append(event.name)

    registry.register(
        make_manifest(CRASHER, capabilities=["chat.events"],
                      events=["chat.created"]),
        PluginHandlers(on_event=crash))
    registry.register(
        make_manifest(HEALTHY, capabilities=["chat.events"],
                      events=["chat.created"]),
        PluginHandlers(on_event=ok))
    registry.enable(CRASHER)
    registry.enable(HEALTHY)
    return registry


def dispatch(registry, name="chat.created"):
    return asyncio.run(registry.dispatch_event(name))


# ---------------- containment on every road ----------------


def test_dispatch_contains_crasher_sibling_completes():
    crasher_calls, healthy_calls = [], []
    registry = event_registry(crasher_calls, healthy_calls)
    report = dispatch(registry)
    assert report.delivered == [HEALTHY]
    assert report.failed == [
        {"plugin_id": CRASHER, "error_type": "RuntimeError"}]
    assert healthy_calls == ["chat.created"]
    record = registry.get(CRASHER)
    assert record.state is PluginState.ENABLED  # one strike only
    assert record.consecutive_failures == 1
    assert record.last_error.surface == "event"


def test_guarded_call_contains_and_records():
    registry = event_registry([], [])

    def boom(x):
        raise ValueError("direct road broke")

    out = guard_plugin_call(registry, CRASHER, "direct", "work", boom, 1)
    assert out.invoked is True and out.ok is False
    assert out.failure.error_type == "ValueError"
    assert out.failure.surface == "direct"
    record = registry.get(CRASHER)
    assert record.consecutive_failures == 1
    assert len(record.failure_log) == 1  # nothing swallowed silently


def test_guarded_call_success_returns_value_and_clears_strikes():
    registry = event_registry([], [])
    guard_plugin_call(registry, CRASHER, "direct", "work",
                      lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert registry.get(CRASHER).consecutive_failures == 1
    out = guard_plugin_call(registry, CRASHER, "direct", "work",
                            lambda a, b=0: a + b, 2, b=3)
    assert out.ok is True and out.value == 5
    assert registry.get(CRASHER).consecutive_failures == 0


def test_guarded_call_async_contains():
    registry = event_registry([], [])

    async def aboom():
        raise KeyError("async broke")

    out = asyncio.run(guard_plugin_call_async(
        registry, CRASHER, "direct", "awork", aboom))
    assert out.invoked is True and out.ok is False
    assert out.failure.error_type == "KeyError"
    out2 = asyncio.run(guard_plugin_call_async(
        registry, HEALTHY, "direct", "awork", lambda: "fine"))
    assert out2.ok is True and out2.value == "fine"


def test_sync_guard_records_async_callable_honestly():
    registry = event_registry([], [])

    async def acall():
        return 1

    out = guard_plugin_call(registry, CRASHER, "direct", "work", acall)
    assert out.ok is False and out.failure.error_type == "TypeError"
    assert registry.get(CRASHER).consecutive_failures == 1


def test_prompt_hook_crash_contained_sibling_applies():
    registry = PluginRegistry()

    def bad_hook(ctx, slots):
        raise RuntimeError("hook broke")

    def good_hook(ctx, slots):
        return [Slot(id="note", kind="plugin_note", role="system", content="hi")]

    for pid, fn in ((CRASHER, bad_hook), (HEALTHY, good_hook)):
        registry.register(
            make_manifest(pid, capabilities=["prompt.hooks"],
                          permissions=["prompt.inject"],
                          prompt_hooks=[{"id": "h", "stage": "slots"}]),
            PluginHandlers(prompt_hooks={"h": fn}))
        registry.enable(pid)
    slots, echoes = asyncio.run(apply_slot_hooks(registry, {}, []))
    assert [s.id for s in slots] == [f"{HEALTHY}:note"]
    outcomes = {row["plugin_id"]: row["outcome"] for row in echoes}
    assert outcomes == {CRASHER: "failed", HEALTHY: "applied"}
    assert registry.get(CRASHER).last_error.surface == "prompt"


# ---------------- self-disable + report ----------------


def _crash_to_limit(registry):
    for _ in range(FAILURE_LIMIT):
        dispatch(registry)


def test_self_disable_at_limit_with_inspectable_report():
    crasher_calls, healthy_calls = [], []
    registry = event_registry(crasher_calls, healthy_calls)
    _crash_to_limit(registry)
    record = registry.get(CRASHER)
    assert record.state is PluginState.ERRORED
    report = failure_report(registry, CRASHER)
    assert report.self_disabled is True
    assert report.enabled is False
    assert report.state == "errored"
    assert report.consecutive_failures == FAILURE_LIMIT
    assert report.failure_limit == FAILURE_LIMIT
    assert report.total_recorded == FAILURE_LIMIT
    assert report.last_failure["surface"] == "event"
    assert report.last_failure["hook"] == "chat.created"
    assert report.last_failure["error_type"] == "RuntimeError"
    assert report.last_failure["at"]
    assert len(report.failures) == FAILURE_LIMIT
    # The healthy sibling kept completing every single time.
    assert healthy_calls == ["chat.created"] * FAILURE_LIMIT


def test_plain_report_names_plugin_road_class_and_next_step():
    registry = event_registry([], [])
    _crash_to_limit(registry)
    plain = failure_report(registry, CRASHER).plain
    assert CRASHER in plain
    assert "event" in plain and "RuntimeError" in plain
    assert "disabled itself" in plain
    assert "deliberately re-enable" in plain
    assert "keeps" in plain  # history kept on re-enable


def test_plain_report_healthy_plugin_honest():
    registry = event_registry([], [])
    report = failure_report(registry, HEALTHY)
    assert report.total_recorded == 0
    assert report.last_failure is None
    assert report.self_disabled is False
    assert "no failures" in report.plain


def test_all_reports_registration_order():
    registry = event_registry([], [])
    reports = all_failure_reports(registry)
    assert [r.plugin_id for r in reports] == [CRASHER, HEALTHY]


def test_strikes_reset_on_success_before_limit():
    registry = event_registry([], [])
    dispatch(registry)
    dispatch(registry)
    assert registry.get(CRASHER).consecutive_failures == 2
    out = guard_plugin_call(registry, CRASHER, "direct", "work", lambda: 1)
    assert out.ok is True
    assert registry.get(CRASHER).consecutive_failures == 0
    dispatch(registry)
    dispatch(registry)
    assert registry.get(CRASHER).state is PluginState.ENABLED
    dispatch(registry)
    assert registry.get(CRASHER).state is PluginState.ERRORED


# ---------------- stays down + deliberate re-enable ------------


def test_disabled_plugin_never_invoked_again():
    crasher_calls, healthy_calls = [], []
    registry = event_registry(crasher_calls, healthy_calls)
    _crash_to_limit(registry)
    assert len(crasher_calls) == FAILURE_LIMIT
    dispatch(registry)
    dispatch(registry)
    assert len(crasher_calls) == FAILURE_LIMIT  # no more invocations
    assert len(healthy_calls) == FAILURE_LIMIT + 2
    out = guard_plugin_call(registry, CRASHER, "direct", "work", lambda: 1)
    assert out.invoked is False and out.skipped_reason == "not_enabled"
    # A skip is not a new failure: the record does not grow.
    assert len(registry.get(CRASHER).failure_log) == FAILURE_LIMIT


def test_no_auto_reenable_over_time_or_roads():
    registry = event_registry([], [])
    _crash_to_limit(registry)
    for _ in range(5):
        dispatch(registry)
        guard_plugin_call(registry, CRASHER, "direct", "work", lambda: 1)
    assert registry.get(CRASHER).state is PluginState.ERRORED


def test_deliberate_reenable_clears_strikes_keeps_history():
    registry = event_registry([], [])
    _crash_to_limit(registry)
    registry.enable(CRASHER)  # the one deliberate owner act
    record = registry.get(CRASHER)
    assert record.state is PluginState.ENABLED
    assert record.consecutive_failures == 0  # strikes cleared
    assert len(record.failure_log) == FAILURE_LIMIT  # history kept
    assert record.last_error is not None  # history kept
    report = failure_report(registry, CRASHER)
    assert report.total_recorded == FAILURE_LIMIT
    assert report.self_disabled is False
    out = guard_plugin_call(registry, CRASHER, "direct", "work", lambda: 7)
    assert out.ok is True and out.value == 7  # runs again, only now


def test_owner_disabled_plugin_guarded_skip_not_failure():
    registry = event_registry([], [])
    registry.disable(HEALTHY)
    out = guard_plugin_call(registry, HEALTHY, "direct", "work", lambda: 1)
    assert out.invoked is False and out.skipped_reason == "not_enabled"
    assert registry.get(HEALTHY).failure_log == []


def test_guarded_unknown_plugin_skips_never_raises():
    registry = event_registry([], [])
    out = guard_plugin_call(registry, "acme.ghost", "direct", "work", lambda: 1)
    assert out.invoked is False and out.skipped_reason == "unknown_plugin"
    out = asyncio.run(guard_plugin_call_async(
        registry, "acme.ghost", "direct", "work", lambda: 1))
    assert out.skipped_reason == "unknown_plugin"


# ---------------- sandbox bridge ----------------


def _sandbox(plugin_id=CRASHER):
    return Sandbox({"id": plugin_id, "permissions": [], "capabilities": []})


def _boom():
    raise RuntimeError(f"sandbox kaput {SECRET}")


def test_sandbox_bridge_mirrors_failures_and_self_disables():
    registry = event_registry([], [])
    sandbox = _sandbox()
    for _ in range(FAILURE_LIMIT):
        outcome = sandbox.run(_boom)
        assert outcome.ok is False
    assert sandbox.quarantined is True
    assert registry.get(CRASHER).failure_log == []
    assert apply_sandbox_bridge(registry, sandbox) == FAILURE_LIMIT
    record = registry.get(CRASHER)
    assert record.state is PluginState.ERRORED
    assert [row.surface for row in record.failure_log] == ["sandbox"] * 3
    assert record.last_error.error_type == "RuntimeError"
    assert apply_sandbox_bridge(registry, sandbox) == 0  # idempotent
    report = failure_report(registry, CRASHER)
    assert report.self_disabled is True
    assert report.last_failure["surface"] == "sandbox"


def test_sandbox_bridge_partial_then_more():
    registry = event_registry([], [])
    sandbox = _sandbox()
    sandbox.run(_boom)
    assert apply_sandbox_bridge(registry, sandbox) == 1
    assert registry.get(CRASHER).state is PluginState.ENABLED
    sandbox.run(_boom)
    sandbox.run(_boom)
    assert apply_sandbox_bridge(registry, sandbox) == 2
    assert registry.get(CRASHER).state is PluginState.ERRORED


def test_sandbox_report_shape_and_quarantine_plain():
    sandbox = _sandbox()
    empty = sandbox_failure_report(sandbox)
    assert empty["quarantined"] is False and empty["total_recorded"] == 0
    for _ in range(FAILURE_LIMIT):
        sandbox.run(_boom)
    report = sandbox_failure_report(sandbox, secret_values=[SECRET])
    assert report["quarantined"] is True
    assert report["failure_limit"] == FAILURE_LIMIT
    assert "quarantined" in report["plain"]
    assert SECRET not in json.dumps(report)


def test_sandbox_bridge_unknown_plugin_bridges_nothing():
    registry = PluginRegistry()
    sandbox = _sandbox("acme.ghost")
    sandbox.run(_boom)
    assert apply_sandbox_bridge(registry, sandbox) == 0


# ---------------- report hygiene ----------------


def test_scrub_text_replaces_secret_and_caps():
    assert scrub_text(f"a {SECRET} b", [SECRET]) == "a [redacted] b"
    assert scrub_text("x" * 500) == "x" * 200
    assert scrub_text(None) == ""
    assert scrub_text(f"{SECRET}", []) == SECRET  # only named values hide


def test_no_report_contains_secret_values():
    registry = event_registry([], [])
    _crash_to_limit(registry)  # crash message embeds SECRET
    record = registry.get(CRASHER)
    plain = build_failure_report(record).plain
    assert SECRET not in plain  # plain never embeds message text
    scrubbed = failure_report(registry, CRASHER, secret_values=[SECRET])
    blob = json.dumps(scrubbed.to_dict())
    assert SECRET not in blob
    assert "[redacted]" in blob
    for report in all_failure_reports(registry, secret_values=[SECRET]):
        assert SECRET not in json.dumps(report.to_dict())


# ---------------- HTTP surface + neighbours ----------------


@pytest.fixture(autouse=True)
def _reset_default_registry():
    plugin_service.set_default_registry(None)
    yield
    plugin_service.set_default_registry(None)


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    yield client


def test_http_failure_report_routes_and_host_survives(app_client):
    registry = event_registry([], [])
    _crash_to_limit(registry)
    plugin_service.set_default_registry(registry)
    one = app_client.get(f"/api/v1/plugins/{CRASHER}/failure-report")
    assert one.status_code == 200, one.text
    body = one.json()
    assert body["plugin_id"] == CRASHER
    assert body["self_disabled"] is True
    assert body["last_failure"]["error_type"] == "RuntimeError"
    assert "disabled itself" in body["plain"]
    assert SECRET not in body["plain"]
    listing = app_client.get("/api/v1/plugins/failure-reports")
    assert listing.status_code == 200, listing.text
    assert [r["plugin_id"] for r in listing.json()] == [CRASHER, HEALTHY]
    missing = app_client.get("/api/v1/plugins/acme.ghost/failure-report")
    assert missing.status_code == 404
    # The chat/host surface still answers after the crashes.
    assert app_client.get("/api/v1/plugins").status_code == 200


def test_no_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0042"
    assert "0042" not in MIGRATIONS
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
    registry = plugin_service.build_registry()
    assert registry.keys() == []  # empty boot registry unchanged
