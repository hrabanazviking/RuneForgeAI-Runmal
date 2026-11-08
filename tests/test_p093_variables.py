"""P-093 Variables & state plugin API battery.

Pins the contract from hidden_files/P093_DESIGN.md: the
citizen manifest as strict round-tripping data, the P-082
empty-grant stance, ONE shared durable per-chat store
(file idiom, corrupt store refuses, never reset), key
namespacing (a plugin's bare keys are its own; the shared
namespace is the documented collaboration surface; another
plugin's namespace refuses -- never a silent overwrite),
typing (JSON scalars only, flags are bool only, kinds
never blur), provenance on every entry (writer kind/id,
timestamps, version counter), addvar-shaped increment,
seed-only-missing Part IX seeding, the P-055 macro bridge
(shared namespace, strings only), per-chat scoping and
owner isolation, the HTTP surface, and the neighbours
(migration head stays 0041, no 0042).
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.plugins import service as plugin_service
from runmal.plugins import variables as vars_mod
from runmal.plugins.manifest import manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginRegistry, PluginState
from runmal.prompt.macros import MacroContext, expand_macros


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    plugin_service.set_default_registry(None)
    yield
    plugin_service.set_default_registry(None)


def ids():
    return str(uuid.uuid4()), str(uuid.uuid4())


# -- Citizen / manifest ------------------------------------------------------


def test_manifest_round_trips_and_registers():
    data = vars_mod.manifest_data()
    manifest = manifest_from_data(data)
    assert manifest_to_data(manifest) == data
    assert manifest.id == vars_mod.PLUGIN_ID == "runmal.variables"
    assert "chat.write" not in manifest.permissions
    registry = PluginRegistry()
    record, _plugin = vars_mod.register_plugin(registry)
    assert record.state == PluginState.REGISTERED


def test_sandbox_grants_are_empty():
    grants = vars_mod.sandbox_grants()
    assert grants.resources == frozenset()


def test_ui_contribution_is_the_sidebar_panel():
    registry = PluginRegistry()
    vars_mod.register_plugin(registry, enable=True)
    contributions = registry.ui_contributions("chat.sidebar")
    assert any(c["plugin_id"] == vars_mod.PLUGIN_ID
               for c in contributions)


def test_boot_registry_stays_empty(tmp_path):
    db_path = tmp_path / "boot.db"
    migrate_to_head(db_path)
    app = create_app(create_session_factory(create_db_engine(db_path)))
    registry = plugin_service.get_default_registry()
    assert registry is not None and registry.keys() == []
    assert app is not None


# -- Store: variables, flags, provenance --------------------------------------


def test_set_get_round_trip_with_provenance(tmp_path):
    user, chat = ids()
    entry = vars_mod.set_variable(user, chat, "mood", "calm",
                                  base_dir=tmp_path)
    assert entry["key"] == "shared:mood"
    assert entry["namespace"] == "shared" and entry["name"] == "mood"
    assert entry["kind"] == "variable" and entry["value"] == "calm"
    assert entry["writer_kind"] == "host"
    assert entry["writer_id"] == "runmal.host"
    assert entry["version"] == 1 and entry["created_at"]
    assert vars_mod.get_variable(user, chat, "mood",
                                 base_dir=tmp_path) == "calm"
    path = vars_mod.store_path(user, tmp_path)
    assert path.exists() and path.stat().st_mode & 0o777 == 0o600


def test_overwrite_bumps_version_and_records_last_writer(tmp_path):
    user, chat = ids()
    vars_mod.set_variable(user, chat, "mood", "calm", base_dir=tmp_path)
    entry = vars_mod.set_variable(
        user, chat, "shared:mood", "tense", writer_kind="plugin",
        writer_id="runmal.quick-replies", base_dir=tmp_path)
    assert entry["value"] == "tense" and entry["version"] == 2
    assert entry["writer_id"] == "runmal.quick-replies"
    assert entry["created_at"] <= entry["updated_at"]


def test_scalar_typing_and_refusals(tmp_path):
    user, chat = ids()
    for value in ("s", 3, 2.5, True, None):
        vars_mod.set_variable(user, chat, "k", value, base_dir=tmp_path)
        assert vars_mod.get_variable(user, chat, "k",
                                     base_dir=tmp_path) == value
    for bad in ([1], {"a": 1}, float("nan"), float("inf"), "x" * 4001):
        with pytest.raises(vars_mod.ChatVariableError):
            vars_mod.set_variable(user, chat, "k", bad, base_dir=tmp_path)


def test_missing_variable_raises_not_none(tmp_path):
    user, chat = ids()
    assert vars_mod.get_entry(user, chat, "nope", base_dir=tmp_path) is None
    with pytest.raises(vars_mod.ChatVariableNotFoundError):
        vars_mod.get_variable(user, chat, "nope", base_dir=tmp_path)


def test_flags_are_bool_only_and_kinds_never_blur(tmp_path):
    user, chat = ids()
    assert vars_mod.get_flag(user, chat, "met", base_dir=tmp_path) is False
    vars_mod.set_flag(user, chat, "met", True, base_dir=tmp_path)
    assert vars_mod.get_flag(user, chat, "met", base_dir=tmp_path) is True
    with pytest.raises(vars_mod.ChatVariableError):
        vars_mod.set_flag(user, chat, "met", "yes", base_dir=tmp_path)
    with pytest.raises(vars_mod.ChatVariableError):
        vars_mod.get_variable(user, chat, "met", base_dir=tmp_path)
    vars_mod.set_variable(user, chat, "score", 1, base_dir=tmp_path)
    with pytest.raises(vars_mod.ChatVariableError):
        vars_mod.get_flag(user, chat, "score", base_dir=tmp_path)
    with pytest.raises(vars_mod.ChatVariableError):
        vars_mod.set_flag(user, chat, "score", True, base_dir=tmp_path)


def test_increment_addvar_semantics(tmp_path):
    user, chat = ids()
    entry = vars_mod.increment_variable(user, chat, "score", 2,
                                        base_dir=tmp_path)
    assert entry["value"] == 2
    entry = vars_mod.increment_variable(user, chat, "score", 3,
                                        base_dir=tmp_path)
    assert entry["value"] == 5 and entry["version"] == 2
    vars_mod.set_variable(user, chat, "name", "asta", base_dir=tmp_path)
    with pytest.raises(vars_mod.ChatVariableError):
        vars_mod.increment_variable(user, chat, "name", 1, base_dir=tmp_path)
    with pytest.raises(vars_mod.ChatVariableError):
        vars_mod.increment_variable(user, chat, "score", True,
                                    base_dir=tmp_path)


# -- Namespacing ---------------------------------------------------------------


def test_plugin_bare_key_lands_in_own_namespace(tmp_path):
    user, chat = ids()
    entry = vars_mod.set_variable(
        user, chat, "count", 1, writer_kind="plugin",
        writer_id="runmal.quick-replies", base_dir=tmp_path)
    assert entry["key"] == "runmal.quick-replies:count"
    assert vars_mod.load_macro_variables(user, chat, base_dir=tmp_path) == {}


def test_plugin_cannot_write_or_delete_another_plugins_namespace(tmp_path):
    user, chat = ids()
    vars_mod.set_variable(user, chat, "secret", "s", writer_kind="plugin",
                          writer_id="plugin.alpha", base_dir=tmp_path)
    with pytest.raises(vars_mod.ChatVariableError):
        vars_mod.set_variable(user, chat, "plugin.alpha:secret", "x",
                              writer_kind="plugin",
                              writer_id="plugin.beta", base_dir=tmp_path)
    with pytest.raises(vars_mod.ChatVariableError):
        vars_mod.delete_variable(user, chat, "plugin.alpha:secret",
                                 writer_kind="plugin",
                                 writer_id="plugin.beta", base_dir=tmp_path)
    assert vars_mod.get_variable(
        user, chat, "secret", writer_kind="plugin",
        writer_id="plugin.alpha", base_dir=tmp_path) == "s"


def test_shared_namespace_is_the_collaboration_surface(tmp_path):
    user, chat = ids()
    vars_mod.set_variable(user, chat, "shared:omen", "storm",
                          writer_kind="plugin", writer_id="plugin.alpha",
                          base_dir=tmp_path)
    seen = vars_mod.get_variable(user, chat, "shared:omen",
                                 writer_kind="plugin",
                                 writer_id="plugin.beta", base_dir=tmp_path)
    assert seen == "storm"


def test_bad_keys_and_writers_refuse(tmp_path):
    user, chat = ids()
    for bad in ("", "a:b:c", "has space", "x" * 200, "ns:"):
        with pytest.raises(vars_mod.ChatVariableError):
            vars_mod.set_variable(user, chat, bad, 1, base_dir=tmp_path)
    with pytest.raises(vars_mod.ChatVariableError):
        vars_mod.set_variable(user, chat, "k", 1, writer_kind="ghost",
                              writer_id="x", base_dir=tmp_path)
    with pytest.raises(vars_mod.ChatVariableError):
        vars_mod.set_variable("not-a-uuid", chat, "k", 1, base_dir=tmp_path)


# -- Scoping, caps, durability ---------------------------------------------------


def test_per_chat_and_per_owner_isolation(tmp_path):
    user, chat = ids()
    other_chat = str(uuid.uuid4())
    other_user = str(uuid.uuid4())
    vars_mod.set_variable(user, chat, "mood", "calm", base_dir=tmp_path)
    assert vars_mod.list_entries(user, other_chat, base_dir=tmp_path) == []
    assert vars_mod.list_entries(other_user, chat, base_dir=tmp_path) == []


def test_entry_cap_refuses_new_keys_not_rewrites(tmp_path):
    user, chat = ids()
    for i in range(vars_mod.MAX_ENTRIES_PER_CHAT):
        vars_mod.set_variable(user, chat, f"k{i}", i, base_dir=tmp_path)
    vars_mod.set_variable(user, chat, "k0", 99, base_dir=tmp_path)
    with pytest.raises(vars_mod.ChatVariableError):
        vars_mod.set_variable(user, chat, "one.more", 1, base_dir=tmp_path)


def test_corrupt_store_raises_and_is_never_reset(tmp_path):
    user, chat = ids()
    vars_mod.set_variable(user, chat, "mood", "calm", base_dir=tmp_path)
    path = vars_mod.store_path(user, tmp_path)
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(vars_mod.ChatVariableError):
        vars_mod.get_variable(user, chat, "mood", base_dir=tmp_path)
    assert path.read_text(encoding="utf-8") == "{ not json"


def test_delete_snapshot_and_clear(tmp_path):
    user, chat = ids()
    vars_mod.set_variable(user, chat, "a", 1, base_dir=tmp_path)
    vars_mod.set_flag(user, chat, "b", True, base_dir=tmp_path)
    snap = vars_mod.snapshot_chat(user, chat, base_dir=tmp_path)
    assert [row["key"] for row in snap["entries"]] == ["shared:a", "shared:b"]
    snap["entries"][0]["value"] = "mutated"
    assert vars_mod.get_variable(user, chat, "a", base_dir=tmp_path) == 1
    assert vars_mod.delete_variable(user, chat, "a", base_dir=tmp_path)
    assert not vars_mod.delete_variable(user, chat, "a", base_dir=tmp_path)
    assert vars_mod.clear_chat(user, chat, base_dir=tmp_path) == 1
    assert vars_mod.list_entries(user, chat, base_dir=tmp_path) == []


# -- Part IX seeding + the P-055 macro bridge --------------------------------------


def test_seed_variables_never_overwrites_live_state(tmp_path):
    user, chat = ids()
    seeded = vars_mod.seed_variables(
        user, chat, {"mood": "calm", "met_asta": True, "gold": 10},
        writer_id="scenario.harbour", base_dir=tmp_path)
    assert seeded == ["shared:mood", "shared:met_asta", "shared:gold"]
    assert vars_mod.get_flag(user, chat, "met_asta", base_dir=tmp_path)
    entry = vars_mod.get_entry(user, chat, "mood", base_dir=tmp_path)
    assert entry["writer_kind"] == "scenario"
    assert entry["writer_id"] == "scenario.harbour"
    vars_mod.set_variable(user, chat, "mood", "tense", base_dir=tmp_path)
    again = vars_mod.seed_variables(user, chat, {"mood": "calm"},
                                    writer_id="scenario.harbour",
                                    base_dir=tmp_path)
    assert again == []
    assert vars_mod.get_variable(user, chat, "mood",
                                 base_dir=tmp_path) == "tense"


def test_macro_bridge_round_trip_through_p055(tmp_path):
    user, chat = ids()
    vars_mod.set_variable(user, chat, "place", "the harbour",
                          base_dir=tmp_path)
    loaded = vars_mod.load_macro_variables(user, chat, base_dir=tmp_path)
    assert loaded == {"place": "the harbour"}
    result = expand_macros(
        "{{setvar::mood::calm}}At {{getvar::place}}.",
        MacroContext(char_name="Asta", user_name="Volmarr",
                     variables=dict(loaded)))
    assert result.text == "At the harbour."
    vars_mod.apply_macro_variables(user, chat, result.report.variables,
                                   base_dir=tmp_path)
    entry = vars_mod.get_entry(user, chat, "mood", base_dir=tmp_path)
    assert entry["value"] == "calm" and entry["writer_kind"] == "macro"
    assert vars_mod.load_macro_variables(user, chat, base_dir=tmp_path) == {
        "mood": "calm", "place": "the harbour"}


def test_macro_bridge_renders_scalars_and_skips_none_and_flags(tmp_path):
    user, chat = ids()
    vars_mod.set_variable(user, chat, "gold", 10, base_dir=tmp_path)
    vars_mod.set_variable(user, chat, "ratio", 2.5, base_dir=tmp_path)
    vars_mod.set_variable(user, chat, "alive", True, base_dir=tmp_path)
    vars_mod.set_variable(user, chat, "blank", None, base_dir=tmp_path)
    vars_mod.set_flag(user, chat, "met", True, base_dir=tmp_path)
    assert vars_mod.load_macro_variables(user, chat, base_dir=tmp_path) == {
        "alive": "true", "gold": "10", "ratio": "2.5"}


# -- HTTP surface ---------------------------------------------------------------------


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_http_set_list_unset_clear(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat = client.post("/api/v1/chats", json={"title": "T"})
    assert chat.status_code in (200, 201)
    chat_id = chat.json()["id"]
    made = client.post("/api/v1/chat-variables/set", json={
        "chat_id": chat_id, "key": "mood", "value": "calm"})
    assert made.status_code == 200
    assert made.json()["key"] == "shared:mood"
    flagged = client.post("/api/v1/chat-variables/set", json={
        "chat_id": chat_id, "key": "met", "flag": True})
    assert flagged.status_code == 200 and flagged.json()["kind"] == "flag"
    listed = client.get("/api/v1/chat-variables",
                        params={"chat_id": chat_id})
    assert [row["key"] for row in listed.json()["entries"]] == [
        "shared:met", "shared:mood"]
    bad = client.post("/api/v1/chat-variables/set", json={
        "chat_id": chat_id, "key": "x", "value": [1, 2]})
    assert bad.status_code == 422
    gone = client.post("/api/v1/chat-variables/unset", json={
        "chat_id": chat_id, "key": "mood"})
    assert gone.status_code == 200
    missing = client.post("/api/v1/chat-variables/unset", json={
        "chat_id": chat_id, "key": "mood"})
    assert missing.status_code == 404
    unknown = client.get("/api/v1/chat-variables",
                         params={"chat_id": str(uuid.uuid4())})
    assert unknown.status_code == 404
    cleared = client.post("/api/v1/chat-variables/clear", json={
        "chat_id": chat_id})
    assert cleared.json()["removed"] == 1


# -- Neighbours --------------------------------------------------------------------------


def test_migration_head_stays_0041():
    assert MIGRATIONS[-1][0] == "0041"
    assert "0042" not in [row[0] for row in MIGRATIONS]
    assert all(not name.startswith("0042")
               for name in json.dumps([row[0] for row in MIGRATIONS]))


def test_current_revision_is_0041(tmp_path):
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
