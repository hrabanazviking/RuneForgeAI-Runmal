"""P-083 Plugin manager battery (TESTER).

Pins the plugin-manager contract from hidden_files/P083_DESIGN.md:
the local pack envelope (strict shape, checksum over the NORMALISED
manifest, provenance carried verbatim), permission cards (declared
surfaces rendered plainly, reserved permissions flagged, update
diffs), the manager (file ledger in the data dir, exact-grant rule,
data-only rule, duplicate/conflict discipline, versioned update with
restore discipline, uninstall, lifecycle sync, boot rehydration),
the router surface in the house POST-verb idiom (DELETE and
POST /plugins stay absent), and the neighbours (no migration: head
stays 0041, "0042" is not in MIGRATIONS).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.plugins import service as plugin_service
from runmal.plugins.cards import permission_card
from runmal.plugins.manager import (
    DataOnlyPackError,
    GrantMismatchError,
    NotManagedPluginError,
    PluginConflictError,
    PluginManager,
    PluginManagerError,
)
from runmal.plugins.manifest import manifest_from_data, manifest_to_data
from runmal.plugins.packs import (
    PackError,
    build_pack,
    manifest_checksum,
    pack_data_only_problem,
    parse_pack,
)
from runmal.plugins.registry import (
    PluginCompatibilityError,
    PluginHandlers,
    PluginRegistry,
    PluginState,
)

ALPHA = {
    "id": "pack.alpha",
    "name": "Pack Alpha",
    "version": "1.0.0",
    "api_version": 1,
    "description": "Alpha pack plugin.",
    "author": "Tester",
    "capabilities": ["chat.events", "ui.slots"],
    "permissions": ["chat.read", "ui.contribute"],
    "events": ["chat.created", "message.created"],
    "ui_slots": [
        {"id": "alpha-panel", "slot": "chat.sidebar",
         "label": "Alpha", "order": 100,
         "payload": {"kind": "panel", "route": "alpha"}}
    ],
    "enabled_by_default": False,
}
ALPHA_GRANT = ["chat.read", "ui.contribute"]

BETA = {
    "id": "pack.beta",
    "name": "Pack Beta",
    "version": "1.0.0",
    "api_version": 1,
}

HOOKY = {
    "id": "pack.hooky",
    "name": "Pack Hooky",
    "version": "1.0.0",
    "api_version": 1,
    "capabilities": ["prompt.hooks"],
    "permissions": ["prompt.inject"],
    "prompt_hooks": [{"id": "h1", "stage": "slots", "priority": 10}],
}


def alpha(**over):
    data = dict(ALPHA)
    data.update(over)
    return data


def alpha_pack(**over):
    return build_pack(alpha(**over))


@pytest.fixture(autouse=True)
def _reset_default_registry():
    plugin_service.set_default_registry(None)
    yield
    plugin_service.set_default_registry(None)


@pytest.fixture()
def manager(tmp_path):
    registry = PluginRegistry()
    return PluginManager(registry, tmp_path / "store")


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    factory = create_session_factory(engine)
    client = TestClient(create_app(factory))
    client.runmal_factory = factory
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    yield client


# ---------------- packs (pure) ----------------

def test_build_pack_envelope_and_provenance():
    pack = alpha_pack()
    assert pack["format"] == "runmal-plugin-pack"
    assert pack["pack_version"] == 1
    assert pack["kind"] == "plugin"
    assert pack["schema"] == "runmal-p083-plugin-pack-v1"
    assert pack["plugin"] == manifest_to_data(manifest_from_data(ALPHA))
    assert pack["content_sha256"] == manifest_checksum(
        manifest_from_data(ALPHA))
    provenance = pack["provenance"]
    assert provenance["provenance_version"] == 1
    assert provenance["source_kind"] == "plugin_pack_export"
    assert provenance["app_version"]
    assert "note" not in provenance
    noted = build_pack(ALPHA, note="from a friend")
    assert noted["provenance"]["note"] == "from a friend"


def test_parse_pack_roundtrip_and_provenance_verbatim():
    pack = alpha_pack()
    pack["provenance"]["custom_unknown"] = {"x": [1, 2]}
    parsed = parse_pack(pack)
    assert parsed.manifest == manifest_from_data(ALPHA)
    assert parsed.plugin_id == "pack.alpha"
    assert parsed.content_sha256 == pack["content_sha256"]
    assert parsed.provenance["custom_unknown"] == {"x": [1, 2]}


def test_parse_pack_checksum_is_over_normalised_manifest():
    pack = alpha_pack()
    reordered = dict(pack)
    reordered["plugin"] = dict(reversed(list(pack["plugin"].items())))
    parsed = parse_pack(reordered)
    assert parsed.content_sha256 == pack["content_sha256"]


def test_parse_pack_tampered_manifest_rejected():
    pack = alpha_pack()
    pack["plugin"] = dict(pack["plugin"], name="Tampered")
    with pytest.raises(PackError):
        parse_pack(pack)


def test_parse_pack_envelope_strictness():
    pack = alpha_pack()
    with pytest.raises(PackError):
        parse_pack(dict(pack, bogus=1))
    with pytest.raises(PackError):
        parse_pack(dict(pack, format="other"))
    with pytest.raises(PackError):
        parse_pack(dict(pack, pack_version=2))
    with pytest.raises(PackError):
        parse_pack(dict(pack, kind="lorebook"))
    with pytest.raises(PackError):
        parse_pack(dict(pack, schema="runmal-p999"))
    with pytest.raises(PackError):
        parse_pack("not a pack")
    missing_plugin = dict(pack)
    del missing_plugin["plugin"]
    with pytest.raises(PackError):
        parse_pack(missing_plugin)
    missing_sum = dict(pack)
    del missing_sum["content_sha256"]
    with pytest.raises(PackError):
        parse_pack(missing_sum)
    with pytest.raises(PackError):
        parse_pack(dict(pack, provenance=["nope"]))


def test_parse_pack_invalid_manifest_becomes_pack_error():
    pack = alpha_pack()
    pack["plugin"] = dict(pack["plugin"], id="Bad ID!")
    pack["content_sha256"] = "0" * 64
    with pytest.raises(PackError):
        parse_pack(pack)


def test_parse_pack_oversize_plugin_rejected():
    pack = alpha_pack()
    pack["plugin"] = dict(pack["plugin"], ui_slots=[{
        "id": "big", "slot": "home.panel", "label": "Big",
        "payload": {"blob": "x" * 300000}}])
    with pytest.raises(PackError):
        parse_pack(pack)


def test_pack_data_only_problem():
    hook_manifest = manifest_from_data(HOOKY)
    problem = pack_data_only_problem(hook_manifest)
    assert problem is not None and "data only" in problem
    assert pack_data_only_problem(manifest_from_data(ALPHA)) is None

# ---------------- permission cards (pure) ----------------

def test_permission_card_renders_declared_surfaces():
    card = permission_card(manifest_from_data(ALPHA))
    assert card["plugin_id"] == "pack.alpha"
    assert card["name"] == "Pack Alpha"
    assert card["version"] == "1.0.0"
    assert card["api_version"] == 1
    assert [c["name"] for c in card["capabilities"]] == [
        "chat.events", "ui.slots"]
    rows = {r["name"]: r for r in card["permissions"]}
    assert set(rows) == {"chat.read", "ui.contribute"}
    assert rows["chat.read"]["reserved"] is False
    assert rows["chat.read"]["granted"] is None
    assert rows["chat.read"]["effect"]
    assert card["events"] == ["chat.created", "message.created"]
    assert card["ui_slots"] == [
        {"id": "alpha-panel", "slot": "chat.sidebar", "label": "Alpha"}]
    assert card["prompt_hooks"] == []
    assert card["settings_declared"] is False
    assert card["requires_grant"] is True
    assert card["changes"] is None


def test_permission_card_grant_marks_rows():
    card = permission_card(manifest_from_data(ALPHA),
                           granted={"chat.read"})
    rows = {r["name"]: r for r in card["permissions"]}
    assert rows["chat.read"]["granted"] is True
    assert rows["ui.contribute"]["granted"] is False


def test_permission_card_reserved_permission_flagged():
    manifest = manifest_from_data({
        "id": "pack.writer", "name": "Writer", "version": "1.0.0",
        "api_version": 1, "permissions": ["chat.write"]})
    card = permission_card(manifest)
    row = card["permissions"][0]
    assert row["name"] == "chat.write" and row["reserved"] is True
    assert any("reserved" in note for note in card["notes"])


def test_permission_card_honesty_note_for_inert_permission():
    manifest = manifest_from_data({
        "id": "pack.quiet", "name": "Quiet", "version": "1.0.0",
        "api_version": 1, "permissions": ["chat.read"]})
    card = permission_card(manifest)
    assert any("chat.read" in note and "no event" in note
               for note in card["notes"])


def test_permission_card_hook_manifest_warns_data_only():
    card = permission_card(manifest_from_data(HOOKY))
    assert card["prompt_hooks"] == [
        {"id": "h1", "stage": "slots", "priority": 10}]
    assert any("data-only pack" in note for note in card["notes"])


def test_permission_card_changes_diff_for_update():
    previous = manifest_from_data(alpha(
        capabilities=["chat.events"], permissions=["chat.read"],
        events=["chat.created"], ui_slots=[]))
    card = permission_card(manifest_from_data(ALPHA), previous=previous)
    changes = card["changes"]
    assert changes["from_version"] == "1.0.0"
    assert changes["to_version"] == "1.0.0"
    assert changes["permissions_added"] == ["ui.contribute"]
    assert changes["permissions_removed"] == []
    assert changes["capabilities_added"] == ["ui.slots"]
    assert changes["events_added"] == ["message.created"]
    assert changes["events_removed"] == []


# ---------------- manager ----------------

def test_install_success_and_ledger_row(manager, tmp_path):
    outcome = manager.install(alpha_pack(), granted_permissions=ALPHA_GRANT)
    assert outcome.outcome == "installed"
    assert outcome.record.state is PluginState.REGISTERED
    assert outcome.card["plugin_id"] == "pack.alpha"
    row = manager.row_for("pack.alpha")
    assert row is not None and outcome.row == row
    assert row["content_sha256"] == alpha_pack()["content_sha256"]
    assert row["granted_permissions"] == sorted(ALPHA_GRANT)
    assert row["enabled"] is False
    assert row["source"]["kind"] == "local_pack"
    assert row["manifest"] == manifest_to_data(manifest_from_data(ALPHA))
    ledger_file = tmp_path / "store" / "installed.json"
    ledger = json.loads(ledger_file.read_text(encoding="utf-8"))
    assert ledger["format"] == "runmal-plugin-ledger"
    assert ledger["ledger_version"] == 1
    assert set(ledger["plugins"]) == {"pack.alpha"}
    assert manager.is_managed("pack.alpha") is True
    assert [r["plugin_id"] for r in manager.installed_rows()] == [
        "pack.alpha"]


def test_install_enable_true_enables_and_records(manager):
    outcome = manager.install(alpha_pack(), granted_permissions=ALPHA_GRANT,
                              enable=True)
    assert outcome.record.state is PluginState.ENABLED
    assert manager.row_for("pack.alpha")["enabled"] is True


def test_install_no_permission_plugin_needs_empty_grant(manager):
    outcome = manager.install(build_pack(BETA), granted_permissions=[])
    assert outcome.outcome == "installed"
    assert outcome.card["requires_grant"] is False


def test_install_grant_mismatch_refuses_and_writes_nothing(manager):
    with pytest.raises(GrantMismatchError):
        manager.install(alpha_pack(), granted_permissions=["chat.read"])
    with pytest.raises(GrantMismatchError):
        manager.install(alpha_pack(),
                        granted_permissions=ALPHA_GRANT + ["chat.write"])
    with pytest.raises(GrantMismatchError):
        manager.install(alpha_pack(), granted_permissions=None)
    assert manager.registry.find("pack.alpha") is None
    assert manager.installed_rows() == []


def test_install_data_only_pack_refused(manager):
    with pytest.raises(DataOnlyPackError):
        manager.install(build_pack(HOOKY),
                        granted_permissions=["prompt.inject"])
    assert manager.registry.find("pack.hooky") is None
    assert manager.installed_rows() == []


def test_install_incompatible_api_version_refused(manager):
    pack = alpha_pack(api_version=99)
    with pytest.raises(PluginCompatibilityError):
        manager.install(pack, granted_permissions=ALPHA_GRANT)
    assert manager.installed_rows() == []


def test_install_surface_violation_refused(manager):
    pack = alpha_pack(capabilities=["chat.events"], permissions=["chat.read"])
    with pytest.raises(PluginManagerError):
        manager.install(pack, granted_permissions=["chat.read"])
    assert manager.installed_rows() == []


def test_install_duplicate_exact_is_noop_report(manager):
    first = manager.install(alpha_pack(), granted_permissions=ALPHA_GRANT)
    again = manager.install(alpha_pack(), granted_permissions=[])
    assert again.outcome == "duplicate_exact"
    assert again.record is first.record
    assert len(manager.installed_rows()) == 1


def test_install_over_in_tree_citizen_conflicts(manager):
    manager.registry.register(manifest_from_data(BETA), PluginHandlers())
    with pytest.raises(PluginConflictError):
        manager.install(build_pack(BETA), granted_permissions=[])


def test_install_other_version_over_managed_conflicts(manager):
    manager.install(alpha_pack(), granted_permissions=ALPHA_GRANT)
    with pytest.raises(PluginConflictError):
        manager.install(alpha_pack(version="2.0.0"),
                        granted_permissions=ALPHA_GRANT)


def test_install_ledger_failure_rolls_back_registration(manager, monkeypatch):
    def boom(ledger):
        raise OSError("disk full")
    monkeypatch.setattr(manager, "_save_ledger", boom)
    with pytest.raises(OSError):
        manager.install(alpha_pack(), granted_permissions=ALPHA_GRANT,
                        enable=True)
    assert manager.registry.find("pack.alpha") is None


def test_preview_actions(manager):
    fresh = manager.preview(alpha_pack())
    assert fresh["action"] == "install" and fresh["installable"] is True
    assert fresh["problems"] == []
    assert fresh["permission_card"]["plugin_id"] == "pack.alpha"
    assert manager.installed_rows() == []
    tampered = alpha_pack()
    tampered["plugin"] = dict(tampered["plugin"], name="Nope")
    invalid = manager.preview(tampered)
    assert invalid["action"] == "invalid"
    assert invalid["installable"] is False
    assert invalid["permission_card"] is None and invalid["problems"]
    hook = manager.preview(build_pack(HOOKY))
    assert hook["installable"] is False and hook["problems"]
    manager.install(alpha_pack(), granted_permissions=ALPHA_GRANT)
    dup = manager.preview(alpha_pack())
    assert dup["action"] == "duplicate"
    newer = manager.preview(alpha_pack(version="2.0.0"))
    assert newer["action"] == "update" and newer["installable"] is True
    older = manager.preview(alpha_pack(version="0.9.0"))
    assert older["action"] == "conflict"
    assert older["installable"] is False


def test_preview_in_tree_conflict(manager):
    manager.registry.register(manifest_from_data(BETA), PluginHandlers())
    verdict = manager.preview(build_pack(BETA))
    assert verdict["action"] == "conflict"
    assert verdict["installable"] is False and verdict["problems"]

def _install_alpha(manager, enable=False):
    return manager.install(alpha_pack(), granted_permissions=ALPHA_GRANT,
                           enable=enable)


def test_update_success_swaps_and_preserves_install_time(manager):
    _install_alpha(manager, enable=True)
    before = manager.row_for("pack.alpha")
    v2 = alpha_pack(version="2.0.0", description="Alpha, second edition.",
                    events=["chat.created", "message.created", "chat.deleted"])
    outcome = manager.update("pack.alpha", v2,
                             granted_permissions=ALPHA_GRANT)
    assert outcome.outcome == "updated"
    assert outcome.record.manifest.version == "2.0.0"
    assert outcome.record.state is PluginState.ENABLED
    assert outcome.card["changes"]["from_version"] == "1.0.0"
    assert outcome.card["changes"]["to_version"] == "2.0.0"
    assert outcome.card["changes"]["events_added"] == ["chat.deleted"]
    row = manager.row_for("pack.alpha")
    assert row["installed_at"] == before["installed_at"]
    assert row["updated_at"] >= before["updated_at"]
    assert row["content_sha256"] == v2["content_sha256"]
    assert row["enabled"] is True


def test_update_same_version_same_content_is_duplicate(manager):
    _install_alpha(manager)
    outcome = manager.update("pack.alpha", alpha_pack(),
                             granted_permissions=[])
    assert outcome.outcome == "duplicate_exact"


def test_update_same_version_different_content_conflicts(manager):
    _install_alpha(manager)
    with pytest.raises(PluginConflictError):
        manager.update("pack.alpha", alpha_pack(description="Sneaky."),
                       granted_permissions=ALPHA_GRANT)
    record = manager.registry.get("pack.alpha")
    assert record.manifest.description == "Alpha pack plugin."


def test_update_older_version_conflicts(manager):
    manager.install(alpha_pack(version="2.0.0"),
                    granted_permissions=ALPHA_GRANT)
    with pytest.raises(PluginConflictError):
        manager.update("pack.alpha", alpha_pack(version="1.5.0"),
                       granted_permissions=ALPHA_GRANT)


def test_update_grant_mismatch_keeps_old_version(manager):
    _install_alpha(manager)
    with pytest.raises(GrantMismatchError):
        manager.update("pack.alpha", alpha_pack(version="2.0.0"),
                       granted_permissions=["chat.read"])
    assert manager.registry.get("pack.alpha").manifest.version == "1.0.0"
    assert manager.row_for("pack.alpha")["manifest"]["version"] == "1.0.0"


def test_update_pack_for_other_id_refused(manager):
    _install_alpha(manager)
    with pytest.raises(PluginManagerError):
        manager.update("pack.alpha", build_pack(BETA),
                       granted_permissions=[])


def test_update_unknown_and_in_tree(manager):
    with pytest.raises(KeyError):
        manager.update("pack.ghost", alpha_pack(id="pack.ghost"),
                       granted_permissions=ALPHA_GRANT)
    manager.registry.register(manifest_from_data(BETA), PluginHandlers())
    with pytest.raises(NotManagedPluginError):
        manager.update("pack.beta", build_pack(BETA), granted_permissions=[])


def test_uninstall_removes_registry_and_ledger(manager):
    _install_alpha(manager, enable=True)
    outcome = manager.uninstall("pack.alpha")
    assert outcome.outcome == "uninstalled"
    assert outcome.record is None and outcome.row is None
    assert manager.registry.find("pack.alpha") is None
    assert manager.row_for("pack.alpha") is None
    assert manager.installed_rows() == []


def test_uninstall_unknown_and_in_tree(manager):
    with pytest.raises(KeyError):
        manager.uninstall("pack.ghost")
    manager.registry.register(manifest_from_data(BETA), PluginHandlers())
    with pytest.raises(NotManagedPluginError):
        manager.uninstall("pack.beta")
    assert manager.registry.find("pack.beta") is not None


def test_sync_state_follows_registry_lifecycle(manager):
    _install_alpha(manager)
    manager.registry.enable("pack.alpha")
    manager.sync_state("pack.alpha")
    assert manager.row_for("pack.alpha")["enabled"] is True
    manager.registry.disable("pack.alpha")
    manager.sync_state("pack.alpha")
    assert manager.row_for("pack.alpha")["enabled"] is False
    manager.sync_state("pack.ghost")


def test_corrupt_ledger_raises_loudly(manager, tmp_path):
    store = tmp_path / "store"
    store.mkdir(parents=True)
    (store / "installed.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(PluginManagerError):
        manager.installed_rows()
    (store / "installed.json").write_text(
        json.dumps({"format": "other", "ledger_version": 1,
                    "plugins": {}}), encoding="utf-8")
    with pytest.raises(PluginManagerError):
        manager.is_managed("pack.alpha")


def test_rehydrate_restores_installs_and_enabled_flags(tmp_path):
    store = tmp_path / "store"
    first = PluginManager(PluginRegistry(), store)
    first.install(alpha_pack(), granted_permissions=ALPHA_GRANT, enable=True)
    first.install(build_pack(BETA), granted_permissions=[])
    registry = PluginRegistry()
    second = PluginManager(registry, store)
    installed, problems = second.rehydrate()
    assert installed == ["pack.alpha", "pack.beta"]
    assert problems == []
    assert registry.get("pack.alpha").state is PluginState.ENABLED
    assert registry.get("pack.beta").state is PluginState.REGISTERED


def test_rehydrate_skips_bad_row_and_reports_it(tmp_path):
    store = tmp_path / "store"
    first = PluginManager(PluginRegistry(), store)
    first.install(alpha_pack(), granted_permissions=ALPHA_GRANT)
    first.install(build_pack(BETA), granted_permissions=[])
    ledger_file = store / "installed.json"
    ledger = json.loads(ledger_file.read_text(encoding="utf-8"))
    ledger["plugins"]["pack.beta"]["content_sha256"] = "0" * 64
    ledger_file.write_text(json.dumps(ledger), encoding="utf-8")
    registry = PluginRegistry()
    second = PluginManager(registry, store)
    installed, problems = second.rehydrate()
    assert installed == ["pack.alpha"]
    assert [p["plugin_id"] for p in problems] == ["pack.beta"]
    assert registry.find("pack.beta") is None


def test_service_build_registry_rehydrates_from_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    registry = plugin_service.build_registry()
    assert registry.keys() == []
    assert plugin_service.rehydration_problems() == []
    manager = PluginManager(registry, plugin_service.default_plugin_store_dir())
    manager.install(alpha_pack(), granted_permissions=ALPHA_GRANT, enable=True)
    rebuilt = plugin_service.build_registry()
    record = rebuilt.get("pack.alpha")
    assert record.state is PluginState.ENABLED
    assert plugin_service.rehydration_problems() == []

# ---------------- router ----------------

BASE = "/api/v1/plugins"


def test_router_manager_view_not_swallowed_by_detail(app_client):
    view = app_client.get(f"{BASE}/manager")
    assert view.status_code == 200, view.text
    assert view.json() == {"installed": [], "rehydration_problems": []}


def test_router_preview_writes_nothing(app_client):
    verdict = app_client.post(f"{BASE}/install/preview",
                              json={"pack": alpha_pack()})
    assert verdict.status_code == 200, verdict.text
    body = verdict.json()
    assert body["action"] == "install" and body["installable"] is True
    assert body["permission_card"]["plugin_id"] == "pack.alpha"
    assert app_client.get(BASE).json() == []
    missing = app_client.post(f"{BASE}/install/preview", json={})
    assert missing.status_code == 422


def test_router_install_flow_and_duplicate_status(app_client):
    missing = app_client.post(f"{BASE}/install", json={})
    assert missing.status_code == 422
    created = app_client.post(f"{BASE}/install", json={
        "pack": alpha_pack(), "granted_permissions": ALPHA_GRANT})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["outcome"] == "installed"
    assert body["plugin"]["id"] == "pack.alpha"
    assert body["plugin"]["state"] == "registered"
    assert body["manager"]["plugin_id"] == "pack.alpha"
    assert body["permission_card"]["plugin_id"] == "pack.alpha"
    again = app_client.post(f"{BASE}/install", json={
        "pack": alpha_pack(), "granted_permissions": ALPHA_GRANT})
    assert again.status_code == 200, again.text
    assert again.json()["outcome"] == "duplicate_exact"
    view = app_client.get(f"{BASE}/manager")
    assert [r["plugin_id"] for r in view.json()["installed"]] == [
        "pack.alpha"]


def test_router_install_error_mapping(app_client):
    mismatch = app_client.post(f"{BASE}/install", json={
        "pack": alpha_pack(), "granted_permissions": ["chat.read"]})
    assert mismatch.status_code == 422
    hook = app_client.post(f"{BASE}/install", json={
        "pack": build_pack(HOOKY), "granted_permissions": ["prompt.inject"]})
    assert hook.status_code == 422
    tampered = alpha_pack()
    tampered["plugin"] = dict(tampered["plugin"], name="Nope")
    bad = app_client.post(f"{BASE}/install", json={
        "pack": tampered, "granted_permissions": ALPHA_GRANT})
    assert bad.status_code == 422
    registry = plugin_service.get_default_registry()
    registry.register(manifest_from_data(BETA), PluginHandlers())
    conflict = app_client.post(f"{BASE}/install", json={
        "pack": build_pack(BETA), "granted_permissions": []})
    assert conflict.status_code == 409


def test_router_permission_card_endpoint(app_client):
    app_client.post(f"{BASE}/install", json={
        "pack": alpha_pack(), "granted_permissions": ALPHA_GRANT})
    card = app_client.get(f"{BASE}/pack.alpha/permission-card")
    assert card.status_code == 200, card.text
    rows = {r["name"]: r for r in card.json()["permissions"]}
    assert rows["chat.read"]["granted"] is True
    assert rows["ui.contribute"]["granted"] is True
    registry = plugin_service.get_default_registry()
    registry.register(manifest_from_data(BETA), PluginHandlers())
    in_tree = app_client.get(f"{BASE}/pack.beta/permission-card")
    assert in_tree.status_code == 200
    assert in_tree.json()["permissions"] == []
    assert app_client.get(
        f"{BASE}/pack.ghost/permission-card").status_code == 404


def test_router_update_and_uninstall_flow(app_client):
    app_client.post(f"{BASE}/install", json={
        "pack": alpha_pack(), "granted_permissions": ALPHA_GRANT})
    v2 = alpha_pack(version="2.0.0", description="Alpha, second edition.")
    updated = app_client.post(f"{BASE}/pack.alpha/update", json={
        "pack": v2, "granted_permissions": ALPHA_GRANT})
    assert updated.status_code == 200, updated.text
    assert updated.json()["outcome"] == "updated"
    assert updated.json()["permission_card"]["changes"]["from_version"] == "1.0.0"
    unknown = app_client.post(f"{BASE}/pack.ghost/update", json={
        "pack": alpha_pack(id="pack.ghost"),
        "granted_permissions": ALPHA_GRANT})
    assert unknown.status_code == 404
    registry = plugin_service.get_default_registry()
    registry.register(manifest_from_data(BETA), PluginHandlers())
    not_managed = app_client.post(f"{BASE}/pack.beta/update", json={
        "pack": build_pack(BETA), "granted_permissions": []})
    assert not_managed.status_code == 422
    removed = app_client.post(f"{BASE}/pack.alpha/uninstall")
    assert removed.status_code == 200, removed.text
    assert removed.json()["outcome"] == "uninstalled"
    assert removed.json()["plugin_id"] == "pack.alpha"
    assert app_client.get(f"{BASE}/pack.alpha").status_code == 404
    assert app_client.post(f"{BASE}/pack.alpha/uninstall").status_code == 404
    in_tree = app_client.post(f"{BASE}/pack.beta/uninstall")
    assert in_tree.status_code == 422


def test_router_lifecycle_verbs_sync_ledger(app_client):
    app_client.post(f"{BASE}/install", json={
        "pack": alpha_pack(), "granted_permissions": ALPHA_GRANT})
    enabled = app_client.post(f"{BASE}/pack.alpha/enable")
    assert enabled.status_code == 200
    view = app_client.get(f"{BASE}/manager").json()
    assert view["installed"][0]["enabled"] is True
    disabled = app_client.post(f"{BASE}/pack.alpha/disable")
    assert disabled.status_code == 200
    view = app_client.get(f"{BASE}/manager").json()
    assert view["installed"][0]["enabled"] is False


def test_router_surface_pins_stay_absent(app_client):
    assert app_client.post(BASE, json={}).status_code == 405
    assert app_client.delete(f"{BASE}/pack.alpha").status_code == 405


def test_router_installs_survive_app_rebuild(app_client, tmp_path):
    app_client.post(f"{BASE}/install", json={
        "pack": alpha_pack(), "granted_permissions": ALPHA_GRANT,
        "enable": True})
    rebuilt = TestClient(create_app(app_client.runmal_factory))
    rebuilt.headers.update(dict(app_client.headers))
    rows = rebuilt.get(BASE).json()
    assert [r["id"] for r in rows] == ["pack.alpha"]
    assert rows[0]["state"] == "enabled"
    view = rebuilt.get(f"{BASE}/manager").json()
    assert [r["plugin_id"] for r in view["installed"]] == ["pack.alpha"]
    assert view["rehydration_problems"] == []


# ---------------- neighbours + exports ----------------

def test_no_migration_head_stays_0041(tmp_path):
    db_path = tmp_path / "mig.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
    assert "0042" not in MIGRATIONS


def test_public_exports():
    from runmal import plugins
    for name in ("build_pack", "parse_pack", "PackError", "ParsedPack",
                 "manifest_checksum", "permission_card", "PluginManager",
                 "ManagerOutcome", "PluginManagerError",
                 "GrantMismatchError", "PluginConflictError",
                 "NotManagedPluginError", "DataOnlyPackError"):
        assert name in plugins.__all__
        assert getattr(plugins, name) is not None
