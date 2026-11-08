"""P-081 Plugin API v1 battery (TESTER).

Pins the plugin contract from hidden_files/P081_DESIGN.md section 9:
the manifest as strict round-tripping data, the registry lifecycle
(discovered -> registered -> enabled/disabled/errored, failure
limit, acknowledge), fire-and-observe chat events with per-receiver
chat.read redaction and the S107 vocabulary pin, ordered prompt
hooks at the inspect choke point (forced provenance, namespacing,
isolation, budget honesty), UI slot contributions, the read-only
router surface, and the neighbours (no migration past 0041,
generation.before/after/failed carrying metadata only).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.backends.errors import BackendUnavailable
from runmal.backends.events import UsageUpdate
from runmal.backends.fake import FakeChatBackend
from runmal.backends.messages import ChatMessage
from runmal.chats import service as chats_svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.generation.service import generate_events
from runmal.plugins import service as plugin_service
from runmal.plugins.api import PLUGIN_EVENTS
from runmal.plugins.events import PLUGIN_EVENT_S107_VALUES
from runmal.plugins.manifest import (
    ManifestError,
    manifest_from_data,
    manifest_to_data,
)
from runmal.plugins.registry import (
    InvalidPluginTransition,
    PluginCompatibilityError,
    PluginHandlers,
    PluginRegistrationError,
    PluginRegistry,
    PluginState,
)
from runmal.plugins.service import plugin_api_info
from runmal.prompt.composer import ComposedMessage
from runmal.prompt.inspect import inspect_prompt
from runmal.prompt.slots import Slot

SECRET = "ZqxPluginSecret81"

# The section 1 canonical example, verbatim.
CANONICAL = {
    "id": "runmal.summarise",
    "name": "Memory Summarise",
    "version": "1.0.0",
    "api_version": 1,
    "description": "Rolling chat summary into memory.",
    "author": "Rúnmál",
    "capabilities": ["chat.events", "prompt.hooks"],
    "permissions": ["chat.read", "prompt.inject"],
    "events": ["chat.created", "message.created"],
    "prompt_hooks": [
        {"id": "summary-slot", "stage": "slots", "priority": 100}
    ],
    "ui_slots": [
        {"id": "summary-panel", "slot": "chat.sidebar",
         "label": "Summary", "order": 100,
         "payload": {"kind": "panel", "route": "summary"}}
    ],
    "settings": {"schema": {}, "defaults": {}},
    "enabled_by_default": False,
}


def manifest_data(**over):
    data = {
        "id": "test.plugin",
        "name": "Test Plugin",
        "version": "1.0.0",
        "api_version": 1,
    }
    data.update(over)
    return data


def make_manifest(**over):
    return manifest_from_data(manifest_data(**over))


def event_manifest(plugin_id, events, **over):
    base = {"id": plugin_id, "capabilities": ["chat.events"],
            "events": list(events)}
    base.update(over)
    return make_manifest(**base)


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def make_user(factory, name="volmarr"):
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


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


# ---------------- manifest (pure) ----------------

def test_manifest_roundtrip_exact():
    manifest = manifest_from_data(CANONICAL)
    assert manifest_to_data(manifest) == CANONICAL
    # And the serialised form parses back to the same manifest.
    assert manifest_from_data(manifest_to_data(manifest)) == manifest


def test_manifest_rejects_unknown_key_and_bad_id_and_bad_version():
    with pytest.raises(ManifestError):
        manifest_from_data(manifest_data(bogus_key=1))
    with pytest.raises(ManifestError):
        manifest_from_data(manifest_data(id="Bad ID!"))
    with pytest.raises(ManifestError):
        manifest_from_data(manifest_data(version="1.0"))
    with pytest.raises(ManifestError):
        manifest_from_data(manifest_data(version="1.0.0-beta"))
    with pytest.raises(ManifestError):
        manifest_from_data(manifest_data(name=""))
    with pytest.raises(ManifestError):
        manifest_from_data({"name": "No Id", "version": "1.0.0",
                            "api_version": 1})


def test_manifest_rejects_unknown_capability_permission_event_slot():
    with pytest.raises(ManifestError):
        manifest_from_data(manifest_data(capabilities=["fly.swim"]))
    with pytest.raises(ManifestError):
        manifest_from_data(manifest_data(permissions=["chat.hack"]))
    with pytest.raises(ManifestError):
        manifest_from_data(manifest_data(events=["chat.exploded"]))
    with pytest.raises(ManifestError):
        manifest_from_data(manifest_data(ui_slots=[{
            "id": "panel", "slot": "chat.bogus", "label": "Panel"}]))
    with pytest.raises(ManifestError):
        manifest_from_data(manifest_data(prompt_hooks=[{
            "id": "hook", "stage": "sideways"}]))


def test_manifest_rejects_surface_without_capability_or_permission():
    # Parse time does NOT enforce this (the canonical example itself
    # declares a ui_slots entry without ui.slots): register() does,
    # raising PluginRegistrationError (design section 1 + PLG-03).
    registry = PluginRegistry()
    # Prompt hook (slots stage) without prompt.inject.
    no_inject = make_manifest(
        id="bad.inject", capabilities=["prompt.hooks"], permissions=[],
        prompt_hooks=[{"id": "hook", "stage": "slots"}])
    with pytest.raises(PluginRegistrationError):
        registry.register(no_inject, PluginHandlers(
            prompt_hooks={"hook": lambda ctx, slots: None}))
    # Prompt hook without the prompt.hooks capability at all.
    no_cap = make_manifest(
        id="bad.nocap", capabilities=[], permissions=["prompt.inject"],
        prompt_hooks=[{"id": "hook", "stage": "slots"}])
    with pytest.raises(PluginRegistrationError):
        registry.register(no_cap, PluginHandlers(
            prompt_hooks={"hook": lambda ctx, slots: None}))
    # Messages-stage hook without prompt.modify.
    no_modify = make_manifest(
        id="bad.modify", capabilities=["prompt.hooks"],
        permissions=["prompt.inject"],
        prompt_hooks=[{"id": "hook", "stage": "messages"}])
    with pytest.raises(PluginRegistrationError):
        registry.register(no_modify, PluginHandlers(
            prompt_hooks={"hook": lambda ctx, msgs: None}))
    # UI contribution without ui.contribute.
    no_ui = make_manifest(
        id="bad.ui", capabilities=["ui.slots"], permissions=[],
        ui_slots=[{"id": "panel", "slot": "chat.sidebar",
                   "label": "Panel"}])
    with pytest.raises(PluginRegistrationError):
        registry.register(no_ui, PluginHandlers())
    # generation.* event without generation.observe.
    no_gen = make_manifest(
        id="bad.gen", capabilities=["chat.events"],
        events=["generation.before"])
    with pytest.raises(PluginRegistrationError):
        registry.register(no_gen, PluginHandlers(on_event=lambda e: None))
    # Any event without the chat.events capability.
    no_events_cap = make_manifest(
        id="bad.events", capabilities=[], events=["chat.created"])
    with pytest.raises(PluginRegistrationError):
        registry.register(no_events_cap, PluginHandlers())
    assert registry.keys() == []  # no partial records


def test_manifest_rejects_duplicate_hook_and_contribution_ids():
    with pytest.raises(ManifestError):
        manifest_from_data(manifest_data(prompt_hooks=[
            {"id": "hook", "stage": "slots"},
            {"id": "hook", "stage": "messages"}]))
    with pytest.raises(ManifestError):
        manifest_from_data(manifest_data(ui_slots=[
            {"id": "panel", "slot": "chat.sidebar", "label": "One"},
            {"id": "panel", "slot": "home.panel", "label": "Two"}]))


def test_manifest_non_int_api_version_is_malformed_not_incompatible():
    with pytest.raises(ManifestError):
        manifest_from_data(manifest_data(api_version="1"))
    with pytest.raises(ManifestError):
        manifest_from_data(manifest_data(api_version=True))
    with pytest.raises(ManifestError):
        manifest_from_data(manifest_data(api_version=1.0))
    # Any real int parses; compatibility is the registry's verdict.
    assert make_manifest(api_version=7).api_version == 7


def test_manifest_settings_stored_verbatim_and_must_be_dicts():
    settings = {"schema": {"type": "object", "props": ["a", "b"]},
                "defaults": {"level": 3, "nested": {"x": [1, 2]}}}
    manifest = make_manifest(settings=settings)
    assert manifest.settings == settings
    assert manifest_to_data(manifest)["settings"] == settings
    assert make_manifest().settings is None
    for bad in ({"schema": []}, {"defaults": "x"}, {"bogus": {}},
                ["schema"], "settings"):
        with pytest.raises(ManifestError):
            make_manifest(settings=bad)


# ---------------- registry + lifecycle ----------------

def test_register_lands_registered_and_duplicate_id_rejects():
    registry = PluginRegistry()
    manifest = event_manifest("dup.plugin", ["chat.created"])
    record = registry.register(manifest, PluginHandlers(on_event=lambda e: None))
    assert record.state is PluginState.REGISTERED
    assert record.plugin_id == "dup.plugin"
    assert record.registration_index == 0
    assert registry.keys() == ["dup.plugin"]
    assert registry.get("dup.plugin") is record
    assert registry.find("dup.plugin") is record
    assert registry.find("missing.plugin") is None
    assert registry.enabled_records() == []
    with pytest.raises(PluginRegistrationError):
        registry.register(manifest, PluginHandlers(on_event=lambda e: None))
    assert registry.keys() == ["dup.plugin"]


def test_register_rejects_undeclared_handler_and_missing_handler():
    registry = PluginRegistry()
    declared = make_manifest(
        id="hooks.plugin", capabilities=["prompt.hooks"],
        permissions=["prompt.inject"],
        prompt_hooks=[{"id": "hook", "stage": "slots"}])
    with pytest.raises(PluginRegistrationError):  # declared, no handler
        registry.register(declared, PluginHandlers())
    with pytest.raises(PluginRegistrationError):  # undeclared handler key
        registry.register(declared, PluginHandlers(prompt_hooks={
            "hook": lambda ctx, slots: None,
            "ghost": lambda ctx, slots: None}))
    plain = event_manifest("events.plugin", ["chat.created"])
    with pytest.raises(PluginRegistrationError):  # event map key undeclared
        registry.register(plain, PluginHandlers(
            on_event={"chat.renamed": lambda e: None}))
    # The declared shapes register cleanly.
    registry.register(declared, PluginHandlers(
        prompt_hooks={"hook": lambda ctx, slots: None}))
    registry.register(plain, PluginHandlers(
        on_event={"chat.created": lambda e: None}))
    assert registry.keys() == ["events.plugin", "hooks.plugin"]


def test_compatibility_rejects_api_0_and_api_2_with_supported_list():
    for bad_version in (0, 2):
        registry = PluginRegistry()
        manifest = make_manifest(id="future.plugin", api_version=bad_version)
        registry.note_discovered(manifest)
        with pytest.raises(PluginCompatibilityError) as caught:
            registry.register(manifest, PluginHandlers())
        err = caught.value
        assert err.plugin_id == "future.plugin"
        assert err.plugin_api_version == bad_version
        assert err.supported == [1]
        assert registry.find("future.plugin") is None
        assert registry.keys() == []
        # The DISCOVERED note remains, so the refusal is inspectable.
        assert registry.is_discovered("future.plugin")
        assert registry.discovered() == ["future.plugin"]


def test_lifecycle_happy_path():
    calls = []
    registry = PluginRegistry()
    manifest = event_manifest("life.plugin", ["chat.created"])
    registry.note_discovered(manifest)
    assert registry.discovered() == ["life.plugin"]
    record = registry.register(manifest, PluginHandlers(
        on_event=lambda e: None,
        on_enable=lambda: calls.append("enable"),
        on_disable=lambda: calls.append("disable")))
    assert record.state is PluginState.REGISTERED
    assert registry.discovered() == []
    registry.enable("life.plugin")
    assert record.state is PluginState.ENABLED
    registry.disable("life.plugin")
    assert record.state is PluginState.DISABLED
    assert calls == ["enable", "disable"]  # once each, in order
    registry.enable("life.plugin")  # DISABLED -> ENABLED again
    assert record.state is PluginState.ENABLED
    assert calls == ["enable", "disable", "enable"]
    assert registry.enabled_records() == [record]


def test_invalid_transitions_raise():
    registry = PluginRegistry()
    manifest = event_manifest("strict.plugin", ["chat.created"])
    registry.note_discovered(manifest)
    with pytest.raises(InvalidPluginTransition):  # DISCOVERED-only note
        registry.enable("strict.plugin")
    with pytest.raises(KeyError):  # wholly unknown id
        registry.enable("missing.plugin")
    record = registry.register(manifest, PluginHandlers(on_event=lambda e: None))
    with pytest.raises(InvalidPluginTransition):  # acknowledge non-ERRORED
        registry.acknowledge("strict.plugin")
    with pytest.raises(InvalidPluginTransition):  # disable never-enabled
        registry.disable("strict.plugin")
    registry.enable("strict.plugin")
    with pytest.raises(InvalidPluginTransition):  # unregister ENABLED
        registry.unregister("strict.plugin")
    registry.disable("strict.plugin")
    registry.unregister("strict.plugin")  # DISABLED -> gone
    assert registry.keys() == []
    assert record.state is PluginState.DISABLED


def test_on_enable_failure_lands_errored_not_enabled():
    def boom():
        raise RuntimeError("enable exploded")
    registry = PluginRegistry()
    record = registry.register(
        event_manifest("fragile.plugin", ["chat.created"]),
        PluginHandlers(on_event=lambda e: None, on_enable=boom))
    returned = registry.enable("fragile.plugin")  # reports, never raises
    assert returned is record
    assert record.state is PluginState.ERRORED
    assert record.last_error is not None
    assert record.last_error.surface == "lifecycle"
    assert record.last_error.hook == "on_enable"
    assert record.last_error.error_type == "RuntimeError"
    assert registry.enabled_records() == []


def test_on_disable_failure_cannot_veto_disable():
    def boom():
        raise RuntimeError("disable exploded")
    registry = PluginRegistry()
    record = registry.register(
        event_manifest("sticky.plugin", ["chat.created"]),
        PluginHandlers(on_event=lambda e: None, on_disable=boom))
    registry.enable("sticky.plugin")
    assert record.state is PluginState.ENABLED
    registry.disable("sticky.plugin")
    assert record.state is PluginState.DISABLED  # the disable stands
    assert record.consecutive_failures == 1
    assert record.last_error is not None
    assert record.last_error.hook == "on_disable"
    assert record.last_error.error_type == "RuntimeError"


async def test_failure_limit_three_consecutive_errors_plugin_and_success_resets_counter():
    state = {"fail": True, "calls": 0}
    def handler(event):
        state["calls"] += 1
        if state["fail"]:
            raise RuntimeError("handler exploded")
    registry = PluginRegistry()
    record = registry.register(
        event_manifest("flaky.plugin", ["chat.created"]),
        PluginHandlers(on_event=handler))
    registry.enable("flaky.plugin")
    report = await registry.dispatch_event("chat.created", chat_id="c1")
    assert report.delivered == []
    assert report.failed == [{"plugin_id": "flaky.plugin",
                              "error_type": "RuntimeError"}]
    await registry.dispatch_event("chat.created", chat_id="c1")
    assert record.consecutive_failures == 2
    assert record.state is PluginState.ENABLED  # below the limit
    state["fail"] = False
    report = await registry.dispatch_event("chat.created", chat_id="c1")
    assert report.delivered == ["flaky.plugin"]
    assert record.consecutive_failures == 0  # success resets
    state["fail"] = True
    for _ in range(3):
        await registry.dispatch_event("chat.created", chat_id="c1")
    assert record.consecutive_failures == 3
    assert record.state is PluginState.ERRORED  # FAILURE_LIMIT = 3
    calls_before = state["calls"]
    report = await registry.dispatch_event("chat.created", chat_id="c1")
    assert state["calls"] == calls_before  # ERRORED receives nothing
    assert report.delivered == [] and report.failed == []


async def test_acknowledge_clears_counter_keeps_log():
    def handler(event):
        raise ValueError("always broken")
    registry = PluginRegistry()
    record = registry.register(
        event_manifest("broken.plugin", ["chat.created"]),
        PluginHandlers(on_event=handler))
    registry.enable("broken.plugin")
    for _ in range(3):
        await registry.dispatch_event("chat.created", chat_id="c1")
    assert record.state is PluginState.ERRORED
    report = await registry.dispatch_event("chat.created", chat_id="c1")
    assert report.delivered == [] and report.failed == []  # no dispatch
    assert len(record.failure_log) == 3
    registry.acknowledge("broken.plugin")
    assert record.state is PluginState.DISABLED
    assert record.consecutive_failures == 0  # counter cleared
    assert len(record.failure_log) == 3  # log retained
    assert record.last_error is not None  # last_error retained
    assert record.last_error.error_type == "ValueError"


# ---------------- events ----------------

async def test_dispatch_only_enabled_subscribers_in_registration_order():
    calls = []
    registry = PluginRegistry()
    def sync_handler(tag):
        return lambda event: calls.append(tag)
    async def async_handler(event):
        calls.append("c")
    registry.register(event_manifest("a.plugin", ["chat.created"]),
                      PluginHandlers(on_event=sync_handler("a")))
    registry.register(event_manifest("b.plugin", ["chat.created"]),
                      PluginHandlers(on_event=sync_handler("b")))
    registry.register(event_manifest("c.plugin", ["chat.created"]),
                      PluginHandlers(on_event=async_handler))
    registry.register(event_manifest("d.plugin", ["chat.created"]),
                      PluginHandlers(on_event=sync_handler("d")))
    registry.register(event_manifest("e.plugin", ["chat.renamed"]),
                      PluginHandlers(on_event=sync_handler("e")))
    registry.enable("a.plugin")
    # b stays REGISTERED: receives nothing.
    registry.enable("c.plugin")
    registry.enable("d.plugin")
    registry.disable("d.plugin")  # DISABLED: receives nothing.
    registry.enable("e.plugin")  # ENABLED but not subscribed to this event.
    report = await registry.dispatch_event("chat.created", chat_id="c1")
    assert calls == ["a", "c"]  # registration order, enabled only
    assert report.delivered == ["a.plugin", "c.plugin"]
    assert report.failed == []


async def test_failing_event_handler_isolated_chat_operation_succeeds(tmp_path):
    received = []
    def boom(event):
        raise RuntimeError("subscriber exploded")
    registry = PluginRegistry()
    failing = registry.register(
        event_manifest("fail.plugin", ["message.created"]),
        PluginHandlers(on_event=boom))
    registry.register(
        event_manifest("rec.plugin", ["message.created"]),
        PluginHandlers(on_event=lambda e: received.append(e.name)))
    registry.enable("fail.plugin")
    registry.enable("rec.plugin")
    plugin_service.set_default_registry(registry)
    try:
        factory = make_factory(tmp_path)
        user_id = await make_user(factory)
        async with factory() as session:
            chat = await chats_svc.create_chat(session, user_id, "Hall")
            chat_id = chat.id
        async with factory() as session:
            message = await chats_svc.append_message(
                session, user_id, chat_id, "user", "Hail and well met.")
        # PLG-01: the host operation succeeded, untouched.
        assert message.content == "Hail and well met."
        assert message.chat_id == chat_id
    finally:
        plugin_service.set_default_registry(None)
    # The healthy plugin still received the event; the failure was
    # recorded on the failing plugin, never raised through.
    assert received == ["message.created"]
    assert failing.consecutive_failures == 1
    assert failing.last_error.error_type == "RuntimeError"
    assert failing.last_error.surface == "event"


async def test_event_payload_redaction():
    seen = {}
    registry = PluginRegistry()
    registry.register(event_manifest(
        "reader.plugin", ["message.created"], permissions=["chat.read"]),
        PluginHandlers(on_event=lambda e: seen.__setitem__("reader", e)))
    registry.register(event_manifest("blind.plugin", ["message.created"]),
        PluginHandlers(on_event=lambda e: seen.__setitem__("blind", e)))
    registry.enable("reader.plugin")
    registry.enable("blind.plugin")
    await registry.dispatch_event(
        "message.created", chat_id="c1", message_id="m1",
        data={"chat_id": "c1", "message_id": "m1", "role": "user",
              "content": SECRET, "content_chars": len(SECRET)})
    reader = seen["reader"]
    assert reader.data["content"] == SECRET  # chat.read keeps the text
    assert reader.data["content_chars"] == len(SECRET)
    blind = seen["blind"]
    assert "content" not in blind.data  # dropped for everyone else
    assert blind.data["content_chars"] == len(SECRET)
    assert SECRET not in json.dumps(blind.to_dict())
    assert blind.name == "message.created"
    assert blind.api_version == 1


def test_event_names_pin_s107_vocabulary():
    # The plugin catalogue reuses the S107 chats vocabulary; the one
    # renamed event is message.created -> EVENT_MESSAGE_APPENDED.
    assert chats_svc.EVENT_CHAT_CREATED == "chat.created"
    assert chats_svc.EVENT_CHAT_RENAMED == "chat.renamed"
    assert chats_svc.EVENT_MESSAGE_EDITED == "message.edited"
    assert chats_svc.EVENT_MESSAGE_DELETED == "message.deleted"
    assert chats_svc.EVENT_MESSAGE_SWIPE_SELECTED == "message.swipe_selected"
    assert chats_svc.EVENT_MESSAGE_APPENDED == "message.appended"
    assert PLUGIN_EVENT_S107_VALUES["message.created"] == "message.appended"
    chats_values = {value for key, value in vars(chats_svc).items()
                    if key.startswith("EVENT_") and isinstance(value, str)}
    shared = {"chat.created", "chat.renamed", "message.edited",
              "message.deleted", "message.swipe_selected"}
    assert PLUGIN_EVENTS & chats_values == shared
    mapped = {value for value in PLUGIN_EVENT_S107_VALUES.values()
              if value is not None}
    assert mapped == shared | {"message.appended"}
    assert set(PLUGIN_EVENT_S107_VALUES) == set(PLUGIN_EVENTS)
    assert PLUGIN_EVENT_S107_VALUES["chat.deleted"] is None
    assert PLUGIN_EVENT_S107_VALUES["generation.before"] is None


def test_chat_lifecycle_events_end_to_end_via_api(app_client):
    seen = []
    registry = plugin_service.get_default_registry()
    assert registry is not None  # create_app installed it
    registry.register(event_manifest("watcher.plugin", [
        "chat.created", "chat.renamed", "message.created",
        "message.edited", "message.deleted", "chat.deleted"]),
        PluginHandlers(on_event=lambda e: seen.append(e.name)))
    registry.enable("watcher.plugin")
    created = app_client.post("/api/v1/chats", json={"title": "First"})
    assert created.status_code == 201, created.text
    chat_id = created.json()["id"]
    renamed = app_client.patch(f"/api/v1/chats/{chat_id}",
                               json={"title": "Second"})
    assert renamed.status_code == 200, renamed.text
    appended = app_client.post(f"/api/v1/chats/{chat_id}/messages",
                               json={"role": "user", "content": "hello"})
    assert appended.status_code == 201, appended.text
    message_id = appended.json()["id"]
    edited = app_client.patch(
        f"/api/v1/chats/{chat_id}/messages/{message_id}",
        json={"content": "hello, edited"})
    assert edited.status_code == 200, edited.text
    deleted_msg = app_client.delete(
        f"/api/v1/chats/{chat_id}/messages/{message_id}")
    assert deleted_msg.status_code == 200, deleted_msg.text
    deleted_chat = app_client.delete(f"/api/v1/chats/{chat_id}")
    assert deleted_chat.status_code == 200, deleted_chat.text
    assert seen == ["chat.created", "chat.renamed", "message.created",
                    "message.edited", "message.deleted", "chat.deleted"]


# ---------------- prompt hooks ----------------

def hook_registry(plugin_id, decls, handlers, *, enable=True):
    """Register one prompt-hook plugin; decls = [(id, stage, priority)]."""
    permissions = []
    if any(stage == "slots" for _, stage, _ in decls):
        permissions.append("prompt.inject")
    if any(stage == "messages" for _, stage, _ in decls):
        permissions.append("prompt.modify")
    manifest = make_manifest(
        id=plugin_id, capabilities=["prompt.hooks"],
        permissions=permissions,
        prompt_hooks=[{"id": hook_id, "stage": stage, "priority": prio}
                      for hook_id, stage, prio in decls])
    registry = PluginRegistry()
    record = registry.register(manifest, PluginHandlers(prompt_hooks=handlers))
    if enable:
        registry.enable(plugin_id)
    return registry, record


async def _inspect(factory, user_id, registry=None, **kw):
    async with factory() as session:
        return await inspect_prompt(
            session, user_id, messages=["m1", "m2"],
            plugin_registry=registry, **kw)


async def test_slot_hook_adds_namespaced_forced_provenance_and_abstain(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    def add_slot(ctx, slots):
        return [Slot(id="note", kind="plugin_note", role="system",
                     content="A plugin note.", provenance="host.forged")]
    registry, _ = hook_registry(
        "hook.plugin", [("adder", "slots", 100)], {"adder": add_slot})
    result = await _inspect(factory, user_id, registry)
    assert result["plugins"] == {
        "api_version": 1,
        "slots_stage": [{"plugin_id": "hook.plugin", "hook_id": "adder",
                         "outcome": "applied", "slots_added": 1}],
        "messages_stage": []}
    rows = {row["slot_id"]: row for row in result["slots"]}
    row = rows["hook.plugin:note"]  # id namespaced <plugin_id>:<local>
    assert row["provenance"] == "plugin:hook.plugin"  # forced, not forged
    assert row["status"] != "discarded"
    # Abstention: a hook returning None changes nothing at all.
    abstain_registry, _ = hook_registry(
        "quiet.plugin", [("adder", "slots", 100)],
        {"adder": lambda ctx, slots: None})
    abstained = await _inspect(factory, user_id, abstain_registry)
    assert abstained["plugins"]["slots_stage"] == [{
        "plugin_id": "quiet.plugin", "hook_id": "adder",
        "outcome": "abstained", "slots_added": 0}]
    baseline = await _inspect(factory, user_id, PluginRegistry())
    def strip(r):
        return {k: v for k, v in r.items() if k != "plugins"}
    assert strip(abstained) == strip(baseline)


async def test_slot_hook_cannot_force_required_or_foreign_namespace(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    cases = [
        ("req.plugin", Slot(id="note", kind="plugin_note", role="system",
                            content="forced", required=True)),
        ("foreign.plugin", Slot(id="other.plugin:note", kind="plugin_note",
                                role="system", content="forged")),
    ]
    for plugin_id, bad_slot in cases:
        registry, record = hook_registry(
            plugin_id, [("adder", "slots", 100)],
            {"adder": lambda ctx, slots, s=bad_slot: [s]})
        result = await _inspect(factory, user_id, registry)  # never raises
        assert result is not None
        assert result["plugins"]["slots_stage"] == [{
            "plugin_id": plugin_id, "hook_id": "adder",
            "outcome": "failed", "slots_added": 0}]
        # The whole contribution was discarded: no trace row for it.
        assert all("note" not in row["slot_id"] for row in result["slots"])
        assert record.consecutive_failures == 1
        assert record.last_error.surface == "prompt"


async def test_hook_ordering_priority_then_registration(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    calls = []
    def recorder(tag):
        def handler(ctx, items):
            calls.append(tag)
            return None
        return handler
    registry = PluginRegistry()
    def add(plugin_id, decls, handlers):
        permissions = []
        if any(s == "slots" for _, s, _ in decls):
            permissions.append("prompt.inject")
        if any(s == "messages" for _, s, _ in decls):
            permissions.append("prompt.modify")
        registry.register(make_manifest(
            id=plugin_id, capabilities=["prompt.hooks"],
            permissions=permissions,
            prompt_hooks=[{"id": h, "stage": s, "priority": p}
                          for h, s, p in decls]),
            PluginHandlers(prompt_hooks=handlers))
        registry.enable(plugin_id)
    add("ord.a", [("s", "slots", 200)], {"s": recorder("ord.a:slots")})
    add("ord.b", [("s", "slots", 50), ("m", "messages", 1)],
        {"s": recorder("ord.b:slots"), "m": recorder("ord.b:messages")})
    add("ord.c", [("s", "slots", 50)], {"s": recorder("ord.c:slots")})
    plan = registry.prompt_hook_plan("slots")
    assert [(row["plugin_id"], row["hook_id"]) for row in plan] == [
        ("ord.b", "s"), ("ord.c", "s"), ("ord.a", "s")]
    assert [row["priority"] for row in plan] == [50, 50, 200]
    assert registry.prompt_hook_plan("messages") == [{
        "plugin_id": "ord.b", "hook_id": "m", "priority": 1,
        "registration_index": 1}]
    await _inspect(factory, user_id, registry)
    # Priority ASC, then registration order; slots stage always
    # before messages, even though the messages hook has priority 1.
    assert calls == ["ord.b:slots", "ord.c:slots", "ord.a:slots",
                     "ord.b:messages"]


async def test_messages_hook_transforms_and_failing_hook_leaves_pre_hook_messages_intact(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    def add_message(ctx, messages):
        return list(messages) + [ComposedMessage(
            role="system", content="An extra plugin line.",
            slot_id="extra")]
    registry, _ = hook_registry(
        "msg.mod", [("mod", "messages", 100)], {"mod": add_message})
    result = await _inspect(factory, user_id, registry, include_preview=True)
    assert result["plugins"]["messages_stage"] == [{
        "plugin_id": "msg.mod", "hook_id": "mod", "outcome": "applied",
        "messages_added": 1, "messages_removed": 0}]
    preview = result["prompt_preview"]["messages"]
    extra = [m for m in preview if m["content"] == "An extra plugin line."]
    assert len(extra) == 1
    assert extra[0]["slot_id"] == "msg.mod:extra"  # namespaced
    # A failing hook leaves the pre-hook messages exactly intact.
    def boom(ctx, messages):
        raise RuntimeError("transform exploded")
    bad_registry, bad_record = hook_registry(
        "msg.bad", [("mod", "messages", 100)], {"mod": boom})
    failed = await _inspect(factory, user_id, bad_registry,
                            include_preview=True)
    assert failed["plugins"]["messages_stage"] == [{
        "plugin_id": "msg.bad", "hook_id": "mod", "outcome": "failed",
        "messages_added": 0, "messages_removed": 0}]
    baseline = await _inspect(factory, user_id, PluginRegistry(),
                              include_preview=True)
    assert (failed["prompt_preview"]["messages"]
            == baseline["prompt_preview"]["messages"])
    assert bad_record.consecutive_failures == 1
    # A foreign-namespace slot_id is a violation, never silently
    # re-prefixed into a nested forgery: the whole contribution
    # is discarded and the failure recorded (finisher fix 8).
    def forge(ctx, messages):
        return [ComposedMessage(
            role="system", content="Forged.", slot_id="other.plugin:stolen")]
    forge_registry, forge_record = hook_registry(
        "msg.forge", [("mod", "messages", 100)], {"mod": forge})
    forged = await _inspect(factory, user_id, forge_registry,
                            include_preview=True)
    assert forged["plugins"]["messages_stage"] == [{
        "plugin_id": "msg.forge", "hook_id": "mod", "outcome": "failed",
        "messages_added": 0, "messages_removed": 0}]
    assert (forged["prompt_preview"]["messages"]
            == baseline["prompt_preview"]["messages"])
    assert forge_record.consecutive_failures == 1
    assert forge_record.last_error.surface == "prompt"


async def test_no_plugins_pipeline_byte_identical(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    plugin_service.set_default_registry(None)
    async with factory() as session:
        no_registry = await inspect_prompt(
            session, user_id, messages=["m1", "m2"])
    empty = await _inspect(factory, user_id, PluginRegistry())
    assert no_registry == empty  # identical, plugins echo included
    assert empty["plugins"] == {"api_version": 1, "slots_stage": [],
                                 "messages_stage": []}
    # Hook slots still answer to the composer budget: a huge slot
    # under a tiny context limit is discarded in the trace while
    # inspect itself returns normally.
    registry, _ = hook_registry(
        "big.plugin", [("big", "slots", 100)],
        {"big": lambda ctx, slots: [Slot(
            id="big", kind="plugin_note", role="system",
            content="x" * 20000)]})
    result = await _inspect(factory, user_id, registry,
                            context_limit=256, reserve_response=64)
    assert result is not None
    rows = {row["slot_id"]: row for row in result["slots"]}
    assert rows["big.plugin:big"]["status"] == "discarded"
    assert rows["big.plugin:big"]["provenance"] == "plugin:big.plugin"


# ---------------- UI slots + router ----------------

def ui_manifest(plugin_id, decls):
    return make_manifest(
        id=plugin_id, capabilities=["ui.slots"],
        permissions=["ui.contribute"], ui_slots=decls)


def test_ui_contributions_ordering_active_flags_and_summary():
    registry = PluginRegistry()
    registry.register(ui_manifest("ui.one", [
        {"id": "side-b", "slot": "chat.sidebar", "label": "Side B",
         "order": 200, "payload": {"kind": "panel", "route": "b"}},
        {"id": "head-a", "slot": "chat.header", "label": "Head A",
         "order": 50, "payload": {"kind": "panel", "route": "a"}},
    ]), PluginHandlers())
    registry.register(ui_manifest("ui.two", [
        {"id": "side-a", "slot": "chat.sidebar", "label": "Side A",
         "order": 100, "payload": {"kind": "link", "href": "/x"}},
    ]), PluginHandlers())
    registry.enable("ui.one")
    registry.enable("ui.two")
    registry.disable("ui.two")  # DISABLED owner: contribution goes inert
    rows = registry.ui_contributions()
    # Sorted by (slot, order, registration_index, id).
    assert [(r["slot"], r["id"]) for r in rows] == [
        ("chat.header", "head-a"), ("chat.sidebar", "side-a"),
        ("chat.sidebar", "side-b")]
    by_id = {r["id"]: r for r in rows}
    assert by_id["side-b"]["active"] is True
    assert by_id["side-b"]["owner_state"] == "enabled"
    assert by_id["side-b"]["plugin_id"] == "ui.one"
    assert by_id["side-b"]["payload"] == {"kind": "panel", "route": "b"}
    assert by_id["side-a"]["active"] is False
    assert by_id["side-a"]["owner_state"] == "disabled"
    assert [r["id"] for r in registry.ui_contributions(active_only=True)] == [
        "head-a", "side-b"]
    assert [r["id"] for r in registry.ui_contributions("chat.sidebar")] == [
        "side-a", "side-b"]
    summary = registry.ui_slots_summary()
    assert set(summary) == {"chat.header", "chat.sidebar", "chat.toolbar",
                            "message.actions", "settings.panel", "home.panel"}
    assert summary["chat.sidebar"] == {"total": 2, "active": 1}
    assert summary["chat.header"] == {"total": 1, "active": 1}
    assert summary["home.panel"] == {"total": 0, "active": 0}
    # Payload canonical JSON over 4096 bytes rejects at registration.
    big = ui_manifest("ui.big", [
        {"id": "blob", "slot": "home.panel", "label": "Blob",
         "payload": {"blob": "x" * 5000}}])
    with pytest.raises(PluginRegistrationError):
        registry.register(big, PluginHandlers())
    assert registry.find("ui.big") is None


def test_router_surface(app_client):
    base = "/api/v1/plugins"
    info = app_client.get(f"{base}/api")
    assert info.status_code == 200, info.text
    body = info.json()
    assert body["plugin_api_version"] == 1
    assert body["supported_api_versions"] == [1]
    assert body["failure_limit"] == 3
    assert body["registered"] == 0 and body["enabled"] == 0
    assert body["events"] == sorted(PLUGIN_EVENTS)
    assert "chat.events" in body["capabilities"]
    assert "chat.read" in body["permissions"]
    assert "chat.sidebar" in body["ui_slots"]
    assert body["prompt_stages"] == ["messages", "slots"]
    assert isinstance(body["app_version"], str) and body["app_version"]
    assert app_client.get(base).json() == []
    assert app_client.get(f"{base}/missing.plugin").status_code == 404
    # Register a plugin in-process (the only registration road in v1).
    registry = plugin_service.get_default_registry()
    registry.register(event_manifest("web.plugin", ["chat.created"]),
                      PluginHandlers(on_event=lambda e: None))
    rows = app_client.get(base).json()
    assert [r["id"] for r in rows] == ["web.plugin"]
    assert rows[0]["state"] == "registered"
    assert rows[0]["events"] == ["chat.created"]
    detail = app_client.get(f"{base}/web.plugin")
    assert detail.status_code == 200
    assert detail.json()["manifest"]["id"] == "web.plugin"
    assert detail.json()["failure_log"] == []
    # Lifecycle over HTTP; invalid transitions are 422, never 500.
    assert app_client.post(
        f"{base}/web.plugin/acknowledge").status_code == 422
    enabled = app_client.post(f"{base}/web.plugin/enable")
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["state"] == "enabled"
    disabled = app_client.post(f"{base}/web.plugin/disable")
    assert disabled.status_code == 200
    assert disabled.json()["state"] == "disabled"
    assert app_client.post(
        f"{base}/web.plugin/disable").status_code == 422
    assert app_client.post(
        f"{base}/missing.plugin/enable").status_code == 404
    # UI slots endpoint: unknown slot name 422s; a real one answers.
    assert app_client.get(f"{base}/ui-slots",
                          params={"slot": "bogus"}).status_code == 422
    slots = app_client.get(f"{base}/ui-slots",
                           params={"slot": "chat.sidebar"})
    assert slots.status_code == 200
    assert slots.json()["slots"]["chat.sidebar"] == {"total": 0, "active": 0}
    assert slots.json()["contributions"] == []
    # No HTTP registration or removal exists in v1.
    assert app_client.post(base, json={}).status_code == 405
    assert app_client.delete(f"{base}/web.plugin").status_code == 405
    # Unauthenticated requests 401 like every /api/v1 route.
    app_client.headers.pop("Authorization")
    assert app_client.get(base).status_code == 401
    assert app_client.get(f"{base}/api").status_code == 401


# ---------------- neighbours ----------------

def test_no_migration_head_stays_0041_and_app_boots_empty_registry(
        tmp_path, app_client):
    db_path = tmp_path / "mig.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
    assert "0042" not in MIGRATIONS
    registry = plugin_service.get_default_registry()
    assert registry is not None
    assert registry.keys() == []
    info = plugin_api_info(registry)
    assert info["registered"] == 0 and info["enabled"] == 0


async def test_generation_events_fire_before_after_and_failed():
    received = []
    registry = PluginRegistry()
    registry.register(make_manifest(
        id="gen.watch", capabilities=["chat.events", "generation.observe"],
        events=["generation.before", "generation.after",
                "generation.failed"]),
        PluginHandlers(on_event=lambda e: received.append(e)))
    registry.enable("gen.watch")
    plugin_service.set_default_registry(registry)
    try:
        out = [d async for d in generate_events(
            "req-p081", messages=[ChatMessage("user", SECRET)],
            backend=FakeChatBackend(chunks=("hi",),
                                    usage=UsageUpdate(1, 2, 3)))]
        failed_out = [d async for d in generate_events(
            "req-p081-fail", messages=[ChatMessage("user", SECRET)],
            backend=FakeChatBackend(
                fail_with=BackendUnavailable("down")))]
    finally:
        plugin_service.set_default_registry(None)
    assert [d["type"] for d in out] == ["token", "usage", "done"]
    assert [d["type"] for d in failed_out] == ["error", "done"]
    names = [e.name for e in received]
    assert names == ["generation.before", "generation.after",
                     "generation.before", "generation.failed"]
    before, after, _, failed = received
    assert before.data["request_id"] == "req-p081"
    assert before.data["backend_key"] == "fake"
    assert before.data["model_id"] == "fake-1"
    assert before.data["message_count"] == 1
    assert after.data["finish_reason"] == "stop"
    assert after.data["usage"] == {"type": "usage", "prompt_tokens": 1,
                                    "completion_tokens": 2,
                                    "total_tokens": 3}
    assert failed.data["request_id"] == "req-p081-fail"
    assert failed.data["error_code"] == "backend_unavailable"
    assert failed.data["retryable"] is True
    # PLG-05: generation events carry metadata only, never content.
    for event in received:
        assert SECRET not in json.dumps(event.to_dict())
