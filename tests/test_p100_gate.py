"""P-100 Part VI gate battery: the Extensions Row ships.

Roadmap line: *P-100 Part VI gate: the row ships with
P-084-P-090 + P-095 live; a third-party-shaped test plugin
(written blind against the docs) installs and runs.*

Gate discipline (P-030 / P-048 / P-064 / P-080 pattern): the
gate builds no new behaviour; it judges the banked Part VI
slices (P-081..P-099) end to end through their own public
contracts, from measured evidence only.

- Area A (the row ships live): the roadmap-named citizens
  P-084, P-085, P-086, P-087, P-088, P-089, P-090, P-095 --
  and the full shipped corpus of sixteen citizens -- pass
  the P-097 conformance kit AS SHIPPED, and all sixteen
  compose in one registry through the P-081 API (events
  dispatch, both prompt-hook stages, UI contributions)
  without interfering: no failures, seed content intact.
- Area B (blind third-party plugin): a fresh-authored
  plugin (ZqxGate100 world) written ONLY against the
  documented plugin surface (docs/PLUGIN_API_V1_2026-11-07.md,
  docs/PLUGIN_MANAGER_2026-11-07.md,
  docs/PLUGIN_SETTINGS_UI_2026-11-07.md,
  docs/PLUGIN_DATA_CUSTODY_2026-11-07.md,
  docs/PLUGIN_CONFORMANCE_KIT_2026-11-07.md) passes the
  conformance kit on data alone, packages as a P-083 local
  pack, installs + enables through the manager road, renders
  its settings schema through the P-098 UI, exports and
  deletes its data through the P-094 custody road, fires its
  declared events in a real HTTP chat flow (handlers bound
  through the documented citizen registration road -- packs
  carry no code in v1), and its crash is contained by the
  P-099 manners: self-disable at the limit, a plain report
  with no secret in it, the chat and a sibling unaffected.
  Uninstall leaves no residue, in the registry, the ledger,
  the settings store, or the shipped source tree.
- Area C (honest accounting): the carried Part VI items are
  pinned as measured facts, never loosened: the P-094 fixed
  citizen list omits runmal.game-bridge (P-096) and
  runmal.plugin-settings-ui (P-098) [that omission - gate
  finding F1 - was discharged by P-113 at the next custody
  touch, and its pin below now holds the covered state];
  P-098 stored values do
  not change a running citizen's behaviour; P-099 failure
  state is process-local; the P-081 boot registry is empty
  by deliberate design. Hygiene: migration head stays 0041
  and the roadmap's Part VI spans P-081..P-100 continuously.

Clean-room note: the blind plugin and its world are
fresh-authored for this gate (P-005 discipline); no
SillyTavern or Voxta source was inspected, and no real user
files are read. Plain pytest functions, no test classes.
One TestClient per test, sequential calls only.
"""

from __future__ import annotations

import asyncio
import copy
import re
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.plugins import conformance as cf
from runmal.plugins import custody as cu
from runmal.plugins import service as plugin_service
from runmal.plugins import settings_ui as su
from runmal.plugins.failure import failure_report
from runmal.plugins.manager import PluginManager
from runmal.plugins.manifest import manifest_from_data
from runmal.plugins.packs import build_pack
from runmal.plugins.registry import (
    PluginHandlers,
    PluginRegistry,
    PluginState,
)

REPO = Path(__file__).parent.parent
Z = "ZqxGate100"
SECRET = f"{Z}Secret"
BLIND_ID = "acme.word-counter"
SIBLING_ID = "acme.quiet-watcher"

#: The blind plugin's manifest, authored only against the
#: documented surface named in the module docstring. It
#: declares no prompt hooks (packs carry data only in v1).
BLIND = {
    "id": BLIND_ID,
    "name": "Word Counter",
    "version": "1.0.0",
    "api_version": 1,
    "description": "Counts words in chat messages.",
    "author": "Acme Third Party",
    "capabilities": ["chat.events", "ui.slots"],
    "permissions": ["chat.read", "ui.contribute"],
    "events": ["chat.created", "message.created"],
    "prompt_hooks": [],
    "ui_slots": [
        {"id": "word-count-panel", "slot": "chat.sidebar",
         "label": "Word Counter", "order": 200,
         "payload": {"kind": "panel", "route": "word-counter"}},
    ],
    "settings": {
        "schema": {
            "greeting": {"type": "string"},
            "max_words": {"type": "integer",
                          "minimum": 1, "maximum": 10000}},
        "defaults": {"greeting": "Words:", "max_words": 500}},
    "enabled_by_default": False,
}
BLIND_PERMISSIONS = ["chat.read", "ui.contribute"]

#: The sixteen shipped Part VI citizens, in roadmap order.
CITIZEN_IDS = [
    "runmal.summarise", "runmal.vector-storage",
    "runmal.translate", "runmal.image-generation",
    "runmal.web-search", "runmal.quick-replies",
    "runmal.regex-scripts", "runmal.tts", "runmal.stt",
    "runmal.expressions", "runmal.variables",
    "runmal.plugin-custody", "runmal.gallery",
    "runmal.game-bridge", "runmal.plugin-conformance",
    "runmal.plugin-settings-ui",
]

#: The roadmap-named row of the gate line itself.
ROW_IDS = [
    "runmal.summarise", "runmal.vector-storage",
    "runmal.translate", "runmal.image-generation",
    "runmal.web-search", "runmal.quick-replies",
    "runmal.regex-scripts", "runmal.gallery",
]


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    plugin_service.set_default_registry(None)
    yield
    plugin_service.set_default_registry(None)


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    factory = create_session_factory(engine)
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    yield client


def _composed_registry() -> PluginRegistry:
    import importlib
    registry = PluginRegistry()
    for path, _pid in cf.citizen_modules():
        importlib.import_module(path).register_plugin(
            registry, enable=True)
    return registry


# -- Area A: the row ships live --------------------------------


def test_a_row_citizens_pass_conformance_as_shipped():
    modules = dict(cf.citizen_modules())
    by_id = {pid: path for path, pid in cf.citizen_modules()}
    assert sorted(by_id) == sorted(CITIZEN_IDS)
    for plugin_id in ROW_IDS:
        report = cf.check_citizen(by_id[plugin_id])
        assert report["plugin_id"] == plugin_id
        assert report["passed"], (
            f"{plugin_id} failed its own kit: {report['failures']}")
        assert report["listable"] is True
    assert modules  # the corpus road itself is live


def test_a_full_corpus_passes_and_is_deterministic():
    corpus = cf.conformance_corpus()
    assert corpus["all_passed"] is True
    assert corpus["failed"] == []
    assert sorted(corpus["passed"]) == sorted(CITIZEN_IDS)
    assert corpus["listable"] == corpus["passed"]
    again = cf.conformance_corpus()
    assert again["content_sha256"] == corpus["content_sha256"]
    assert cf.listable_ids(corpus["citizens"]) == corpus["passed"]


def test_a_citizens_compose_in_one_registry():
    registry = _composed_registry()
    assert sorted(registry.keys()) == sorted(CITIZEN_IDS)
    assert len(registry.enabled_records()) == 16
    summary = registry.ui_slots_summary()
    assert sum(row["total"] for row in summary.values()) == 16
    assert sum(row["active"] for row in summary.values()) == 16
    report = asyncio.run(registry.dispatch_event(
        "chat.created", chat_id="gate-chat"))
    assert report.failed == []
    assert report.delivered == [
        "runmal.summarise", "runmal.vector-storage",
        "runmal.translate", "runmal.image-generation",
        "runmal.web-search", "runmal.quick-replies",
        "runmal.regex-scripts", "runmal.expressions",
        "runmal.variables", "runmal.gallery"]
    for record in registry.records():
        assert record.state is PluginState.ENABLED
        assert record.consecutive_failures == 0
        assert record.failure_log == []


def test_a_composed_prompt_hooks_run_without_interfering():
    from runmal.plugins.hooks import (
        apply_message_hooks,
        apply_slot_hooks,
    )
    from runmal.prompt.composer import ComposedMessage
    from runmal.prompt.slots import Slot
    registry = _composed_registry()
    slot_plan = registry.prompt_hook_plan("slots")
    assert [row["plugin_id"] for row in slot_plan] == [
        "runmal.image-generation", "runmal.web-search",
        "runmal.vector-storage", "runmal.summarise"]
    message_plan = registry.prompt_hook_plan("messages")
    assert [row["plugin_id"] for row in message_plan] == [
        "runmal.regex-scripts", "runmal.translate"]
    seed_slot = Slot(id="world", kind="world_info",
                     role="system", content=f"{Z} world seed.")
    slots, echoes = asyncio.run(apply_slot_hooks(
        registry, {"chat_id": "gate-chat"}, [seed_slot]))
    assert [row["plugin_id"] for row in echoes] == [
        row["plugin_id"] for row in slot_plan]
    assert all(row["outcome"] == "abstained" for row in echoes)
    assert [slot.content for slot in slots] == [f"{Z} world seed."]
    seed_msg = ComposedMessage(slot_id="m1", role="user",
                               content=f"hello {Z}")
    messages, msg_echoes = asyncio.run(apply_message_hooks(
        registry, {"chat_id": "gate-chat"}, [seed_msg]))
    assert [row["plugin_id"] for row in msg_echoes] == [
        row["plugin_id"] for row in message_plan]
    assert all(row["outcome"] == "abstained" for row in msg_echoes)
    assert [msg.content for msg in messages] == [f"hello {Z}"]
    for record in registry.records():
        assert record.consecutive_failures == 0


# -- Area B: the blind third-party plugin ----------------------


def test_b_blind_manifest_passes_conformance_on_data_alone():
    submission = copy.deepcopy(BLIND)
    report = cf.check_manifest_data(submission)
    assert report["plugin_id"] == BLIND_ID
    assert report["passed"], report["failures"]
    assert report["listable"] is True
    assert submission == BLIND  # checking never mutates it


def test_b_pack_installs_enables_and_contributes(tmp_path):
    registry = PluginRegistry()
    manager = PluginManager(registry, tmp_path / "store")
    pack = build_pack(copy.deepcopy(BLIND))
    assert pack["format"] == "runmal-plugin-pack"
    preview = manager.preview(pack)
    assert preview["installable"] is True
    assert preview["action"] == "install"
    outcome = manager.install(
        pack, granted_permissions=BLIND_PERMISSIONS, enable=True)
    assert outcome.outcome == "installed"
    record = registry.get(BLIND_ID)
    assert record.state is PluginState.ENABLED
    assert registry.has_enabled_subscriber("chat.created")
    assert registry.has_enabled_subscriber("message.created")
    rows = [row for row in registry.ui_contributions(
        "chat.sidebar", active_only=True)
        if row["plugin_id"] == BLIND_ID]
    assert len(rows) == 1
    assert rows[0]["active"] is True
    assert rows[0]["payload"] == {"kind": "panel",
                                  "route": "word-counter"}
    ledger_row = manager.row_for(BLIND_ID)
    assert ledger_row is not None
    assert ledger_row["source"]["kind"] == "local_pack"
    assert ledger_row["enabled"] is True


def test_b_settings_schema_renders_and_stores():
    manifest = manifest_from_data(copy.deepcopy(BLIND))
    form = su.build_settings_form(manifest)
    assert form["has_settings"] is True
    assert [field["name"] for field in form["fields"]] == [
        "greeting", "max_words"]
    widgets = {field["name"]: field["widget"]
               for field in form["fields"]}
    assert widgets == {"greeting": "text", "max_words": "number"}
    html = su.render_settings_form_html(form)
    assert "greeting" in html and "max_words" in html
    user_id = str(uuid.uuid4())
    saved = su.save_plugin_settings(
        user_id, manifest, {"max_words": 42})
    assert saved["values"] == {"greeting": "Words:",
                                "max_words": 42}
    assert su.get_plugin_settings(user_id, manifest) == {
        "greeting": "Words:", "max_words": 42}
    with pytest.raises(su.SettingsValidationError):
        su.save_plugin_settings(user_id, manifest, {"max_words": 0})
    with pytest.raises(su.SettingsValidationError):
        su.save_plugin_settings(
            user_id, manifest, {"max_words": "many"})
    # Refused patches stored nothing.
    assert su.get_plugin_settings(user_id, manifest) == {
        "greeting": "Words:", "max_words": 42}


def test_b_data_exports_and_deletes_via_custody(tmp_path):
    registry = PluginRegistry()
    manager = PluginManager(registry, tmp_path / "store")
    manager.install(build_pack(copy.deepcopy(BLIND)),
                    granted_permissions=BLIND_PERMISSIONS,
                    enable=True)
    manifest = manifest_from_data(copy.deepcopy(BLIND))
    user_id = str(uuid.uuid4())
    su.save_plugin_settings(user_id, manifest, {"max_words": 42})
    settings_doc = su.export_plugin_settings(user_id, manifest)
    assert settings_doc["sections"][0]["status"] == "exported"
    assert settings_doc["sections"][0]["stored"] == {
        "greeting": "Words:", "max_words": 42}
    assert su.verify_export_checksum(settings_doc) is True
    export = asyncio.run(cu.export_plugin_data(
        BLIND_ID, registry=registry, manager=manager))
    assert export["plugin_id"] == BLIND_ID
    assert export["manifest"]["id"] == BLIND_ID
    assert [(s["name"], s["status"]) for s in export["sections"]] == [
        ("host_ledger", "exported"), ("registration", "exported")]
    assert cu.verify_custody_checksum(export) is True
    deletion = asyncio.run(cu.delete_plugin_data(
        BLIND_ID, registry=registry, manager=manager))
    assert [(s["name"], s["status"]) for s in deletion["sections"]] == [
        ("host_ledger", "deleted"),
        ("registration", "not_applicable")]
    assert registry.find(BLIND_ID) is None
    assert manager.row_for(BLIND_ID) is None
    su.delete_plugin_settings(user_id, BLIND_ID)
    assert su.load_stored_values(user_id, BLIND_ID) is None
    with pytest.raises(cu.UnknownPluginError):
        asyncio.run(cu.export_plugin_data(
            BLIND_ID, registry=registry, manager=manager))


def test_b_uninstall_is_clean_and_leaves_no_residue(tmp_path):
    registry = PluginRegistry()
    manager = PluginManager(registry, tmp_path / "store")
    manager.install(build_pack(copy.deepcopy(BLIND)),
                    granted_permissions=BLIND_PERMISSIONS,
                    enable=True)
    outcome = manager.uninstall(BLIND_ID)
    assert outcome.outcome == "uninstalled"
    assert registry.keys() == []
    assert manager.installed_rows() == []
    assert registry.ui_contributions() == []
    # No test-plugin residue in shipped code: the blind plugin
    # lives only in this battery (fixtures/temp discipline).
    src = REPO / "src" / "runmal"
    for path in src.rglob("*.py"):
        assert BLIND_ID not in path.read_text(encoding="utf-8"), path


def _register_blind_pair(registry, seen, sibling_seen, crash):
    def on_event(event):
        if crash["on"]:
            raise RuntimeError(f"blind plugin blew up {SECRET}")
        seen.append(event)
    data = copy.deepcopy(BLIND)
    data["capabilities"] = ["chat.events"]
    data["ui_slots"] = []
    registry.register(manifest_from_data(data),
                      PluginHandlers(on_event=on_event))
    registry.enable(BLIND_ID)
    sibling = copy.deepcopy(BLIND)
    sibling["id"] = SIBLING_ID
    sibling["name"] = "Quiet Watcher"
    sibling["permissions"] = []
    sibling["capabilities"] = ["chat.events"]
    sibling["ui_slots"] = []
    sibling["settings"] = {"schema": {}, "defaults": {}}
    registry.register(
        manifest_from_data(sibling),
        PluginHandlers(on_event=lambda e: sibling_seen.append(e)))
    registry.enable(SIBLING_ID)


def test_b_events_fire_in_a_real_chat_flow(app_client):
    registry = plugin_service.get_default_registry()
    assert registry is not None  # create_app installed it
    assert registry.keys() == []  # the P-081 empty boot registry
    seen, sibling_seen = [], []
    _register_blind_pair(registry, seen, sibling_seen, {"on": False})
    created = app_client.post("/api/v1/chats",
                              json={"title": f"{Z} Hall"})
    assert created.status_code == 201, created.text
    chat_id = created.json()["id"]
    posted = app_client.post(
        f"/api/v1/chats/{chat_id}/messages",
        json={"role": "user", "content": f"hello {Z} world"})
    assert posted.status_code == 201, posted.text
    assert [event.name for event in seen] == [
        "chat.created", "message.created"]
    message_event = seen[1]
    assert message_event.data["content"] == f"hello {Z} world"
    assert message_event.data["content_chars"] == len(f"hello {Z} world")
    # The sibling fires too, but without chat.read its payload
    # carries no message text (the P-081 redaction rule).
    assert [event.name for event in sibling_seen] == [
        "chat.created", "message.created"]
    assert "content" not in sibling_seen[1].data
    assert sibling_seen[1].data["content_chars"] == len(f"hello {Z} world")


def test_b_crash_is_contained_by_the_p099_manners(app_client):
    registry = plugin_service.get_default_registry()
    seen, sibling_seen = [], []
    crash = {"on": False}
    _register_blind_pair(registry, seen, sibling_seen, crash)
    created = app_client.post("/api/v1/chats",
                              json={"title": f"{Z} Storm Hall"})
    assert created.status_code == 201, created.text
    chat_id = created.json()["id"]
    crash["on"] = True
    for index in range(3):
        posted = app_client.post(
            f"/api/v1/chats/{chat_id}/messages",
            json={"role": "user", "content": f"boom {index}"})
        assert posted.status_code == 201, posted.text
    record = registry.get(BLIND_ID)
    assert record.state is PluginState.ERRORED
    assert record.consecutive_failures == 3
    report = failure_report(registry, BLIND_ID, secret_values=(SECRET,))
    assert report.self_disabled is True
    assert report.total_recorded == 3
    assert "disabled itself" in report.plain
    assert SECRET not in report.plain
    assert SECRET not in str(report.to_dict())
    # The chat never dies with it, and the sibling is unaffected.
    after = app_client.post(
        f"/api/v1/chats/{chat_id}/messages",
        json={"role": "user", "content": "after the crash"})
    assert after.status_code == 201, after.text
    assert sibling_seen[-1].name == "message.created"
    assert registry.get(SIBLING_ID).state is PluginState.ENABLED
    assert registry.get(SIBLING_ID).consecutive_failures == 0
    assert app_client.get(f"/api/v1/chats/{chat_id}").status_code == 200
    # An errored plugin is never invoked again.
    assert len(record.failure_log) == 3


# -- Area C: honest accounting, pinned --------------------------


def test_c_custody_fixed_list_covers_two_citizens(tmp_path):
    # Until P-113 this test pinned gate finding F1: the
    # fixed list omitted both citizens and bare-id custody
    # refused them. P-113 discharged F1 at the next custody
    # touch; the pin now holds the covered state at equal
    # strength (the gate record doc is unchanged history).
    assert "runmal.game-bridge" in cu.CITIZEN_PLUGIN_IDS
    assert "runmal.plugin-settings-ui" in cu.CITIZEN_PLUGIN_IDS
    assert cu.custody_coverage()["citizens"] == list(
        cu.CITIZEN_PLUGIN_IDS)
    assert len(cu.CITIZEN_PLUGIN_IDS) == 14
    # Bare-id custody now serves both: each export stamps
    # its real manifest, carries its own data section and
    # verifies its checksum - the coverage is real, not
    # cosmetic, exactly as the omission was.
    for plugin_id, section_name in (
            ("runmal.game-bridge", "game_bridge_store"),
            ("runmal.plugin-settings-ui",
             "plugin_settings_store")):
        doc = asyncio.run(cu.export_plugin_data(
            plugin_id, user_id=str(uuid.uuid4()),
            base_dir=tmp_path))
        assert doc["plugin_id"] == plugin_id
        assert doc["manifest"]["id"] == plugin_id
        assert section_name in [
            s["name"] for s in doc["sections"]]
        assert cu.verify_custody_checksum(doc) is True
    # And both remain custody-reachable once registered,
    # exactly as the gate measured.
    registry = _composed_registry()
    for plugin_id in ("runmal.game-bridge",
                      "runmal.plugin-settings-ui"):
        doc = asyncio.run(cu.export_plugin_data(
            plugin_id, registry=registry))
        assert doc["plugin_id"] == plugin_id
        assert doc["manifest"]["id"] == plugin_id
        assert cu.verify_custody_checksum(doc) is True


def test_c_stored_settings_do_not_drive_a_running_citizen():
    from runmal.plugins import translate as translate_mod
    registry = PluginRegistry()
    _record, plugin = translate_mod.register_plugin(
        registry, enable=True)
    assert plugin.config.default_target_out == "en"
    assert plugin.config.max_chars == 4000
    manifest = translate_mod.build_manifest()
    user_id = str(uuid.uuid4())
    su.save_plugin_settings(user_id, manifest, {
        "target_out": "is", "max_chars": 10})
    assert su.get_plugin_settings(user_id, manifest) == {
        "target_in": "en", "target_out": "is", "max_chars": 10}
    # The running citizen never re-reads the store: its config
    # is still the manifest-derived one from registration.
    assert plugin.config.default_target_out == "en"
    assert plugin.config.max_chars == 4000


def test_c_failure_state_is_process_local():
    registry = PluginRegistry()
    calls = {"n": 0}
    def boom(event):
        calls["n"] += 1
        raise RuntimeError("local crash")
    data = copy.deepcopy(BLIND)
    data["capabilities"] = ["chat.events"]
    data["permissions"] = ["chat.read"]
    data["ui_slots"] = []
    data["settings"] = {"schema": {}, "defaults": {}}
    registry.register(manifest_from_data(data),
                      PluginHandlers(on_event=boom))
    registry.enable(BLIND_ID)
    for _ in range(3):
        asyncio.run(registry.dispatch_event("message.created"))
    assert registry.get(BLIND_ID).state is PluginState.ERRORED
    # A fresh process-local registry knows nothing of it: the
    # same manifest registers clean, with no strikes carried.
    fresh = PluginRegistry()
    fresh.register(manifest_from_data(copy.deepcopy(data)),
                   PluginHandlers(on_event=boom))
    record = fresh.get(BLIND_ID)
    assert record.state is PluginState.REGISTERED
    assert record.consecutive_failures == 0
    assert record.failure_log == []
    assert failure_report(fresh, BLIND_ID).total_recorded == 0


def test_c_boot_registry_is_empty_by_design(tmp_path):
    registry = plugin_service.build_registry()
    assert registry.keys() == []
    info = plugin_service.plugin_api_info(registry)
    assert info["registered"] == 0
    assert info["enabled"] == 0
    assert plugin_service.rehydration_problems() == []


def test_c_hygiene_migration_head_and_roadmap_span(tmp_path):
    assert MIGRATIONS[-1][0] == "0041"
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
    roadmap = (REPO / "docs"
               / "RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md"
               ).read_text(encoding="utf-8")
    section = roadmap[roadmap.index("## Part VI"):]
    section = section[:section.index("\n---")]
    ids = [int(m) for m in re.findall(r"\*\*P-(\d+)\*\*", section)]
    assert sorted(ids) == list(range(81, 101))
    assert len(ids) == 20
