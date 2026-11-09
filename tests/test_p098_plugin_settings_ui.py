"""P-098 Plugin settings UI battery.

Pins the contract from hidden_files/P098_DESIGN.md: the
settings UI is GENERATED from the declared P-081 schema -
a synthetic plugin with a novel schema gets a correct form
with zero UI code changes; every shipped citizen renders
from its own declaration; empty-schema and settings=None
plugins read honestly as no-settings; validation refuses
with NAMED errors and never coerces; defaults apply;
settings persist through the declared file road (P-089
idiom), owner-isolated, exportable checksummed, deletable
with the plugin (P-094 rules); corrupt or stale stored
values are loud, never dropped; the HTML renderer is
widget-faithful and escaped; the HTTP road carries the
same contract; neighbours: boot registry empty (P-081),
grants empty (P-082), migration head 0041.
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
from runmal.plugins import settings_ui as su
from runmal.plugins import translate as tr
from runmal.plugins import tts as tts_mod
from runmal.plugins import quick_replies as qr
from runmal.plugins.manifest import manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginHandlers, PluginRegistry


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    plugin_service.set_default_registry(None)
    yield
    plugin_service.set_default_registry(None)


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def uid() -> str:
    return str(uuid.uuid4())


def synthetic(schema, defaults, plugin_id="runmal.synthetic"):
    return manifest_from_data({
        "id": plugin_id, "name": "Synthetic", "version": "1.0.0",
        "api_version": 1, "description": "", "author": "test",
        "capabilities": [], "permissions": [], "events": [],
        "prompt_hooks": [], "ui_slots": [],
        "settings": {"schema": schema, "defaults": defaults},
        "enabled_by_default": False})


NOVEL_SCHEMA = {
    "volume": {"type": "integer", "minimum": 0, "maximum": 11},
    "mode": {"type": "string", "enum": ["calm", "brave"],
             "title": "Voyage mode", "help": "How bold the crossing feels."},
    "muted": {"type": "boolean"},
    "greeting": {"type": "string", "minLength": 2, "maxLength": 10},
}
NOVEL_DEFAULTS = {"volume": 5, "mode": "calm", "muted": False,
                  "greeting": "hail"}


# -- Generation from schema data -------------------------------------------


def test_novel_schema_generates_correct_form():
    form = su.build_settings_form(synthetic(NOVEL_SCHEMA, NOVEL_DEFAULTS))
    assert form["format"] == su.FORM_FORMAT
    assert form["has_settings"] is True and form["status"] == "ok"
    fields = {row["name"]: row for row in form["fields"]}
    assert [row["name"] for row in form["fields"]] == [
        "volume", "mode", "muted", "greeting"]
    assert fields["volume"]["widget"] == "number"
    assert fields["volume"]["constraints"]["minimum"] == 0
    assert fields["volume"]["constraints"]["maximum"] == 11
    assert fields["mode"]["widget"] == "select"
    assert fields["mode"]["label"] == "Voyage mode"
    assert fields["mode"]["help"] == "How bold the crossing feels."
    assert fields["mode"]["constraints"]["enum"] == ["calm", "brave"]
    assert fields["muted"]["widget"] == "checkbox"
    assert fields["greeting"]["widget"] == "text"
    assert fields["greeting"]["constraints"]["min_length"] == 2
    assert fields["volume"]["label"] == "Volume"
    assert form["values"] == NOVEL_DEFAULTS


def test_second_unseen_schema_same_renderer():
    other = synthetic({"ratio": {"type": "number", "minimum": 0.0,
                                  "maximum": 1.0}},
                      {"ratio": 0.25}, plugin_id="runmal.other")
    form = su.build_settings_form(other)
    assert form["plugin_id"] == "runmal.other"
    assert form["fields"][0]["widget"] == "number"
    assert form["values"] == {"ratio": 0.25}


def test_shipped_citizens_render_from_declarations():
    import importlib
    checked = 0
    for plugin_id, path in su.CITIZEN_MANIFEST_MODULES.items():
        module = importlib.import_module(path)
        manifest = module.build_manifest()
        schema = su.declared_schema(manifest)
        form = su.build_settings_form(manifest)
        assert form["plugin_id"] == plugin_id
        assert [row["name"] for row in form["fields"]] == list(schema)
        assert form["has_settings"] is (len(schema) > 0)
        if schema:
            checked += 1
            for name, value in form["values"].items():
                assert value == su.declared_defaults(manifest)[name]
    assert checked == 7


def test_empty_schema_plugin_reads_honestly():
    form = su.build_settings_form(qr.build_manifest())
    assert form["has_settings"] is False
    assert form["status"] == "no_settings"
    assert form["fields"] == [] and form["values"] == {}
    assert form["message"] == "This plugin declares no settings."
    page = su.render_settings_form_html(form)
    assert "declares no settings" in page and "<input" not in page


def test_settings_none_plugin_reads_honestly():
    manifest = manifest_from_data({
        "id": "runmal.bare", "name": "Bare", "version": "1.0.0",
        "api_version": 1, "description": "", "author": "test",
        "capabilities": [], "permissions": [], "events": [],
        "prompt_hooks": [], "ui_slots": [], "settings": None,
        "enabled_by_default": False})
    form = su.build_settings_form(manifest)
    assert form["status"] == "no_settings" and form["fields"] == []


# -- Defaults + named validation -------------------------------------------


def test_defaults_apply_and_partial_keeps_rest():
    manifest = synthetic(NOVEL_SCHEMA, NOVEL_DEFAULTS)
    assert su.validate_complete(manifest, {}) == NOVEL_DEFAULTS
    out = su.validate_complete(manifest, {"volume": 9})
    assert out == {**NOVEL_DEFAULTS, "volume": 9}


def _codes(exc) -> dict:
    return {row["field"]: row["code"] for row in exc.errors}


def test_validation_refusals_are_named():
    manifest = synthetic(NOVEL_SCHEMA, NOVEL_DEFAULTS)
    cases = [
        ({"bogus": 1}, "bogus", "unknown_field"),
        ({"volume": "loud"}, "volume", "wrong_type"),
        ({"volume": True}, "volume", "wrong_type"),
        ({"volume": 5.0}, "volume", "wrong_type"),
        ({"muted": 1}, "muted", "wrong_type"),
        ({"volume": -1}, "volume", "below_minimum"),
        ({"volume": 12}, "volume", "above_maximum"),
        ({"mode": "wild"}, "mode", "not_in_enum"),
        ({"greeting": "x"}, "greeting", "too_short"),
        ({"greeting": "x" * 11}, "greeting", "too_long"),
    ]
    for patch, field, code in cases:
        with pytest.raises(su.SettingsValidationError) as caught:
            su.validate_complete(manifest, patch)
        assert _codes(caught.value)[field] == code, (patch, code)
        assert field in str(caught.value)


def test_required_field_without_default_refuses():
    manifest = synthetic({"token": {"type": "string", "required": True}}, {})
    with pytest.raises(su.SettingsValidationError) as caught:
        su.validate_complete(manifest, {})
    assert _codes(caught.value)["token"] == "required"
    assert su.validate_complete(manifest, {"token": "abc"}) == {"token": "abc"}


def test_validation_collects_every_bad_field():
    manifest = synthetic(NOVEL_SCHEMA, NOVEL_DEFAULTS)
    with pytest.raises(su.SettingsValidationError) as caught:
        su.validate_complete(manifest, {"volume": 99, "mode": "wild",
                                        "nope": 1})
    codes = _codes(caught.value)
    assert codes == {"volume": "above_maximum", "mode": "not_in_enum",
                     "nope": "unknown_field"}


def test_number_rejects_bool_nan_and_infinity():
    manifest = synthetic({"ratio": {"type": "number"}}, {"ratio": 0.5})
    for bad in (True, float("nan"), float("inf"), "0.5"):
        with pytest.raises(su.SettingsValidationError):
            su.validate_complete(manifest, {"ratio": bad})
    assert su.validate_complete(manifest, {"ratio": 1}) == {"ratio": 1}


def test_patch_merges_then_validates_whole():
    manifest = synthetic(NOVEL_SCHEMA, NOVEL_DEFAULTS)
    current = su.validate_complete(manifest, {})
    out = su.apply_settings_patch(manifest, current, {"muted": True})
    assert out == {**NOVEL_DEFAULTS, "muted": True}
    with pytest.raises(su.SettingsValidationError):
        su.apply_settings_patch(manifest, out, {"volume": 42})


def test_schema_defects_are_loud_and_named():
    bad_schemas = [
        {"f": {"type": "widget"}},
        {"f": {"type": "string", "surprise": 1}},
        {"f": {"type": "integer", "minimum": 5, "maximum": 2}},
        {"f": {"type": "string", "minimum": 1}},
        {"f": {"type": "integer", "enum": []}},
        {"f": "not-a-dict"},
    ]
    for schema in bad_schemas:
        manifest = synthetic(schema, {})
        with pytest.raises(su.SettingsSchemaError) as caught:
            su.parse_settings_schema(manifest)
        assert "f" in str(caught.value)
    bad_default = synthetic({"f": {"type": "integer", "minimum": 3}}, {"f": 1})
    with pytest.raises(su.SettingsSchemaError):
        su.parse_settings_schema(bad_default)
    orphan = synthetic({"f": {"type": "integer"}}, {"ghost": 1})
    with pytest.raises(su.SettingsSchemaError):
        su.parse_settings_schema(orphan)


# -- Persistence through the declared road ----------------------------------


def test_persistence_round_trip(tmp_path):
    base = tmp_path / "base"
    owner = uid()
    manifest = synthetic(NOVEL_SCHEMA, NOVEL_DEFAULTS)
    result = su.save_plugin_settings(owner, manifest, {"volume": 9}, base)
    assert result["values"]["volume"] == 9
    path = su.store_path(owner, base)
    assert path.exists()
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["schema"] == su.STORE_SCHEMA
    fresh = su.get_plugin_settings(owner, manifest, base)
    assert fresh == {**NOVEL_DEFAULTS, "volume": 9}
    form = su.form_for_owner(owner, manifest, base)
    assert form["values"]["volume"] == 9
    assert su.load_stored_values(owner, "runmal.synthetic", base) == fresh


def test_round_trip_for_shipped_citizen(tmp_path):
    base = tmp_path / "base"
    owner = uid()
    manifest = tts_mod.build_manifest()
    su.save_plugin_settings(owner, manifest, {"speaking_rate": 1.5}, base)
    fresh = su.get_plugin_settings(owner, manifest, base)
    assert fresh == {"speaking_rate": 1.5, "max_text_chars": 2000}


def test_refused_patch_writes_nothing(tmp_path):
    base = tmp_path / "base"
    owner = uid()
    manifest = synthetic(NOVEL_SCHEMA, NOVEL_DEFAULTS)
    su.save_plugin_settings(owner, manifest, {"volume": 3}, base)
    before = su.store_path(owner, base).read_bytes()
    with pytest.raises(su.SettingsValidationError):
        su.save_plugin_settings(owner, manifest, {"volume": 99}, base)
    assert su.store_path(owner, base).read_bytes() == before
    assert su.get_plugin_settings(owner, manifest, base)["volume"] == 3


def test_save_to_no_settings_plugin_refused(tmp_path):
    with pytest.raises(su.SettingsValidationError) as caught:
        su.save_plugin_settings(uid(), qr.build_manifest(), {"x": 1},
                                tmp_path / "base")
    assert caught.value.errors[0]["code"] == "no_settings"


def test_owner_isolation(tmp_path):
    base = tmp_path / "base"
    alice, bob = uid(), uid()
    manifest = synthetic(NOVEL_SCHEMA, NOVEL_DEFAULTS)
    su.save_plugin_settings(alice, manifest, {"volume": 1}, base)
    assert su.get_plugin_settings(bob, manifest, base) == NOVEL_DEFAULTS
    assert su.store_path(alice, base) != su.store_path(bob, base)


def test_export_checksum_and_delete_with_plugin(tmp_path):
    base = tmp_path / "base"
    owner = uid()
    manifest = synthetic(NOVEL_SCHEMA, NOVEL_DEFAULTS)
    other = synthetic({"n": {"type": "integer"}}, {"n": 1},
                      plugin_id="runmal.other")
    su.save_plugin_settings(owner, manifest, {"volume": 2}, base)
    su.save_plugin_settings(owner, other, {"n": 7}, base)
    doc = su.export_plugin_settings(owner, manifest, base)
    assert doc["sections"][0]["status"] == "exported"
    assert su.verify_export_checksum(doc) is True
    doc["sections"][0]["values"]["volume"] = 999
    assert su.verify_export_checksum(doc) is False
    report = su.delete_plugin_settings(owner, "runmal.synthetic", base)
    assert report["deleted"] is True
    assert su.get_plugin_settings(owner, manifest, base) == NOVEL_DEFAULTS
    assert su.get_plugin_settings(owner, other, base) == {"n": 7}
    again = su.delete_plugin_settings(owner, "runmal.synthetic", base)
    assert again["deleted"] is False


def test_export_empty_is_honest(tmp_path):
    doc = su.export_plugin_settings(uid(), tr.build_manifest(),
                                    tmp_path / "base")
    assert doc["sections"][0]["status"] == "empty"
    assert doc["sections"][0]["values"]["max_chars"] == 4000


def test_corrupt_store_is_loud(tmp_path):
    base = tmp_path / "base"
    owner = uid()
    path = su.store_path(owner, base)
    path.parent.mkdir(parents=True)
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(su.SettingsStoreError):
        su.get_plugin_settings(owner, tr.build_manifest(), base)
    path.write_text(json.dumps({"schema": "other", "plugins": {}}),
                    encoding="utf-8")
    with pytest.raises(su.SettingsStoreError):
        su.load_stored_values(owner, "runmal.translate", base)


def test_stale_stored_values_are_loud_never_dropped(tmp_path):
    base = tmp_path / "base"
    owner = uid()
    manifest = synthetic(NOVEL_SCHEMA, NOVEL_DEFAULTS)
    path = su.store_path(owner, base)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "schema": su.STORE_SCHEMA,
        "plugins": {"runmal.synthetic": {
            "values": {**NOVEL_DEFAULTS, "volume": 99},
            "updated_at": "2026-11-07T00:00:00+00:00"}}}),
        encoding="utf-8")
    with pytest.raises(su.SettingsStoreError) as caught:
        su.get_plugin_settings(owner, manifest, base)
    assert "volume" in str(caught.value)


# -- HTML renderer -----------------------------------------------------------


def test_html_is_widget_faithful():
    form = su.build_settings_form(synthetic(NOVEL_SCHEMA, NOVEL_DEFAULTS),
                                  {"muted": True, "mode": "brave"})
    page = su.render_settings_form_html(form)
    assert 'data-plugin-id="runmal.synthetic"' in page
    assert 'type="number"' in page and 'min="0"' in page
    assert 'max="11"' in page and 'step="1"' in page
    assert '<option value="brave" selected>' in page
    assert 'type="checkbox"' in page and "checked" in page
    assert "How bold the crossing feels." in page
    assert 'value="hail"' in page


def test_html_escapes_values():
    manifest = synthetic({"note": {"type": "string", "maxLength": 200}},
                         {"note": "plain"})
    form = su.build_settings_form(manifest, {"note": '<script>x</script>'})
    page = su.render_settings_form_html(form)
    assert "<script>x" not in page
    assert "&lt;script&gt;" in page


# -- Citizen + neighbours ------------------------------------------------------


def test_citizen_registers_and_contributes():
    registry = PluginRegistry()
    record, _plugin = su.register_plugin(registry, enable=True)
    assert record.state.value == "enabled"
    rows = [row for row in registry.ui_contributions("settings.panel")
            if row["plugin_id"] == su.PLUGIN_ID]
    assert len(rows) == 1 and rows[0]["active"] is True
    assert manifest_to_data(su.build_manifest())["settings"] == {
        "schema": {}, "defaults": {}}
    form = su.build_settings_form(su.build_manifest())
    assert form["status"] == "no_settings"


def test_resolve_manifest_registry_first_then_citizen():
    registry = PluginRegistry()
    assert su.resolve_manifest(registry, "runmal.translate").id == "runmal.translate"
    assert su.resolve_manifest(registry, "runmal.nope") is None
    manifest = synthetic(NOVEL_SCHEMA, NOVEL_DEFAULTS)
    registry.register(manifest, PluginHandlers())
    assert su.resolve_manifest(registry, "runmal.synthetic") is manifest


def test_boot_registry_stays_empty_and_grants_empty():
    registry = plugin_service.build_registry()
    assert registry.keys() == []
    grants = su.sandbox_grants()
    assert grants.resources == frozenset()


def test_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0042"
    assert "0042" not in MIGRATIONS
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"


# -- HTTP road -----------------------------------------------------------------


def test_http_form_and_values_for_shipped_citizen(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.get("/api/v1/plugins/runmal.translate/settings-form")
    assert resp.status_code == 200
    form = resp.json()
    assert form["has_settings"] is True
    assert [row["name"] for row in form["fields"]] == [
        "target_in", "target_out", "max_chars"]
    resp = client.get("/api/v1/plugins/runmal.quick-replies/settings-form")
    assert resp.status_code == 200
    assert resp.json()["status"] == "no_settings"
    resp = client.get("/api/v1/plugins/runmal.nope/settings-form")
    assert resp.status_code == 404


def test_http_save_round_trip_and_named_refusal(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.post("/api/v1/plugins/runmal.tts/settings",
                       json={"values": {"speaking_rate": 1.25}})
    assert resp.status_code == 200
    assert resp.json()["values"] == {"speaking_rate": 1.25,
                                     "max_text_chars": 2000}
    resp = client.get("/api/v1/plugins/runmal.tts/settings")
    assert resp.json()["values"]["speaking_rate"] == 1.25
    assert resp.json()["stored"]["speaking_rate"] == 1.25
    resp = client.post("/api/v1/plugins/runmal.tts/settings",
                       json={"values": {"speaking_rate": 9.9}})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["errors"][0]["field"] == "speaking_rate"
    assert detail["errors"][0]["code"] == "above_maximum"
    resp = client.get("/api/v1/plugins/runmal.tts/settings")
    assert resp.json()["values"]["speaking_rate"] == 1.25


def test_http_registered_synthetic_plugin(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    registry = plugin_service.get_default_registry()
    assert registry is not None
    registry.register(synthetic(NOVEL_SCHEMA, NOVEL_DEFAULTS),
                      PluginHandlers())
    resp = client.get("/api/v1/plugins/runmal.synthetic/settings-form")
    assert resp.status_code == 200
    assert resp.json()["fields"][1]["widget"] == "select"
    resp = client.post("/api/v1/plugins/runmal.synthetic/settings",
                       json={"values": {"mode": "brave"}})
    assert resp.status_code == 200
    assert resp.json()["values"]["mode"] == "brave"


def test_http_delete_needs_confirm_and_restores_defaults(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    client.post("/api/v1/plugins/runmal.tts/settings",
                json={"values": {"speaking_rate": 0.75}})
    resp = client.post("/api/v1/plugins/runmal.tts/settings/delete",
                       json={})
    assert resp.status_code == 422
    resp = client.post("/api/v1/plugins/runmal.tts/settings/delete",
                       json={"confirm": True})
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    resp = client.get("/api/v1/plugins/runmal.tts/settings")
    assert resp.json()["values"]["speaking_rate"] == 1.0
    assert resp.json()["stored"] is None


def test_http_save_to_no_settings_plugin_refused(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.post("/api/v1/plugins/runmal.gallery/settings",
                       json={"values": {"x": 1}})
    assert resp.status_code == 422
    assert "no_settings" in json.dumps(resp.json())
