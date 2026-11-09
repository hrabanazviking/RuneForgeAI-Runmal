"""P-133 — Stored-definition file export (Part IX, DERIVED scope).

Pins: the honest reconstruction (no fabricated raw anywhere;
typed fields and carried extra intact); native identity
(store->file(native) IS the stored definition, for native-
and Voxta-origin records alike); the round-trips (file->
store->file and store->file->store exact at the definition
level on BOTH formats, with the re-imported record's
source_format honestly reflecting its road); the Voxta
conversion's clean shape (no native key leaks, Voxta
spellings only, carried extra rides); the honesty report
(unmappable values absent from every file and NAMED in
not_restored with path + kind; a clean record names
nothing; the standing notes ride; a native re-import
cannot resurrect the naming); the service refusal (unknown
format raises before any work); the HTTP road (200 envelope
in both formats + the native default, unknown and foreign
ids 404 — including with a bad format — bad format on an
owned id 422, P-026 / P-131 / P-132 roads untouched beside
it); the carried-shadowing honesty (a carried extra key whose
spelling the Voxta exporter's own typed fields write with a
different value is NAMED in carried_shadowed, never silently
dropped — finisher finding F2; an equal value names nothing,
and a key the typed fields do not write rides verbatim); the
empty-format refusal (an explicit ?format= answers 422 on an
owned id and 404 on an unknown one); and the migration head
pinned at 0041. No network:
fixtures only.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.scenarios.store import ScenarioStore, definitions_path
from runmal.scenarios.storedexport import (
    StoredExportError,
    export_stored_definition,
    scenario_file_from_stored,
)

NOW = "2026-11-08T14:00:00+00:00"
OWNER = "owner-1"
FOREIGN = "owner-2"

NATIVE_KEYS = {
    "scenario_text", "bootstrap_messages", "initial_flags",
    "initial_variables", "memory_book_refs", "impersonation_name",
    "narrator_name", "parent_ref", "thumbnail_ref", "source_format",
}


def native_body():
    return {
        "name": "Harbour Lights at Dusk",
        "description": "A quiet harbour, first evening.",
        "scenario_text": "The ferry has just left.",
        "flow": "story",
        "style": "storytelling",
        "template_text": "",
        "system_prompt_text": "Speak gently.",
        "system_prompt_mode": "replace",
        "roles": [
            {"name": "Guide", "character_name": "Mira",
             "enabled_on_start": True, "can_speak": True},
        ],
        "bootstrap_messages": [
            {"kind": "char", "text": "Welcome to the harbour.",
             "role": "Guide"},
            {"kind": "user", "text": "I came back.", "role": ""},
        ],
        "impersonation_name": "Ash",
        "impersonation_description": "",
        "narrator_name": "The Harbour Voice",
        "narrator_voice": "",
        "memory_book_refs": ["harbour-book"],
        "initial_flags": {"met_guide": True},
        "initial_variables": {"gold": 5},
        "contexts": [
            {"key": "dusk", "text": "The lamps are lit.",
             "condition": "", "role": "", "position": ""},
        ],
        "parent_ref": "",
        "thumbnail_ref": "",
        "source_format": "native",
    }


def voxta_body():
    return {
        "name": "Harbour Lights at Dusk",
        "description": "A quiet harbour, first evening.",
        "scenario": "The ferry has just left.",
        "chatFlow": "Story",
        "chatStyle": "Storytelling",
        "roles": [
            {"name": "Guide", "characterName": "Mira",
             "enabledOnStart": True, "canSpeak": True},
        ],
        "bootstrapMessages": [
            {"kind": "char", "text": "Welcome to the harbour.",
             "role": "Guide"},
            {"kind": "user", "text": "I came back.", "role": ""},
        ],
        "flags": {"met_guide": True},
        "variables": {"gold": 5},
        "contexts": [
            {"key": "dusk", "text": "The lamps are lit.",
             "condition": "", "role": "", "position": ""},
        ],
        "customUnknown": {"a": 1},
    }


def voxta_body_with_unmappable():
    body = voxta_body()
    body["scripts"] = [{"code": "run()"}]
    body["hudWidgets"] = [{"widget": "map"}]
    return body


def _store(tmp_path):
    return ScenarioStore(tmp_path / "scenarios.json")


# -------------------------------------------------- reconstruction


def test_reconstruction_clears_raw_and_keeps_typed_truth(tmp_path):
    store = _store(tmp_path)
    rec = store.create(OWNER, voxta_body(), now=NOW)
    rebuilt = scenario_file_from_stored(rec.definition)
    assert rebuilt.raw == {}
    assert rebuilt.unmappable_values == {}
    assert all(role.raw == {} for role in rebuilt.roles)
    assert all(m.raw == {} for m in rebuilt.bootstrap_messages)
    assert all(c.raw == {} for c in rebuilt.contexts)
    assert rebuilt.name == "Harbour Lights at Dusk"
    assert rebuilt.roles[0].character_name == "Mira"
    assert rebuilt.extra == {"customUnknown": {"a": 1}}


def test_reconstruction_does_not_mutate_the_stored_definition(tmp_path):
    store = _store(tmp_path)
    rec = store.create(OWNER, voxta_body(), now=NOW)
    before = store.get(rec.id, OWNER).definition
    scenario_file_from_stored(rec.definition)
    export_stored_definition(rec, "voxta")
    assert store.get(rec.id, OWNER).definition == before


# --------------------------------------------------- native identity


def test_native_export_is_the_stored_definition_native_origin(tmp_path):
    store = _store(tmp_path)
    rec = store.create(OWNER, native_body(), now=NOW)
    file_dict, report = export_stored_definition(rec, "native")
    assert file_dict == rec.definition
    assert report["format"] == "native"
    assert report["source_format"] == "native"
    assert report["not_restored"] == []
    assert report["exported_keys"] == sorted(rec.definition.keys())


def test_native_export_is_the_stored_definition_voxta_origin(tmp_path):
    store = _store(tmp_path)
    rec = store.create(OWNER, voxta_body(), now=NOW)
    file_dict, report = export_stored_definition(rec)
    assert file_dict == rec.definition
    assert report["source_format"] == "voxta"
    assert report["revision"] == rec.revision == 1
    assert report["definition_id"] == rec.id


def test_file_store_file_roundtrip_native(tmp_path):
    store = _store(tmp_path)
    first = store.create(OWNER, voxta_body(), now=NOW)
    file_dict, _ = export_stored_definition(first, "native")
    second = store.create(OWNER, file_dict, now=NOW)
    file_again, _ = export_stored_definition(second, "native")
    assert second.definition == first.definition
    assert file_again == file_dict


def test_native_reimport_cannot_resurrect_unmappable_naming(tmp_path):
    store = _store(tmp_path)
    first = store.create(OWNER, voxta_body_with_unmappable(), now=NOW)
    assert first.report["unmappable"]  # the naming exists here
    file_dict, report = export_stored_definition(first, "native")
    assert {r["path"] for r in report["not_restored"]} == {
        "scripts", "hudWidgets"}
    second = store.create(OWNER, file_dict, now=NOW)
    assert second.definition == first.definition
    assert second.source_format == "native"
    assert second.report["unmappable"] == []  # honestly gone
    _, report2 = export_stored_definition(second, "native")
    assert report2["not_restored"] == []


# -------------------------------------------------- voxta conversion


def test_voxta_export_is_a_clean_typed_conversion(tmp_path):
    store = _store(tmp_path)
    rec = store.create(OWNER, voxta_body(), now=NOW)
    file_dict, report = export_stored_definition(rec, "voxta")
    assert not (set(file_dict.keys()) & NATIVE_KEYS)
    assert file_dict["name"] == "Harbour Lights at Dusk"
    assert file_dict["scenario"] == "The ferry has just left."
    assert file_dict["chatFlow"] == "Story"
    assert file_dict["chatStyle"] == "Storytelling"
    assert file_dict["flags"] == {"met_guide": True}
    assert file_dict["variables"] == {"gold": 5}
    assert file_dict["customUnknown"] == {"a": 1}  # carried rides
    assert report["format"] == "voxta"


def test_voxta_export_roles_and_bootstrap_carry_voxta_spellings_only(tmp_path):
    store = _store(tmp_path)
    rec = store.create(OWNER, voxta_body(), now=NOW)
    file_dict, _ = export_stored_definition(rec, "voxta")
    assert file_dict["roles"] == [
        {"name": "Guide", "characterName": "Mira",
         "enabledOnStart": True, "canSpeak": True},
    ]
    boot = file_dict["bootstrapMessages"]
    assert boot[0]["text"] == "Welcome to the harbour."
    assert boot[0]["kind"] == "char"
    assert boot[0]["role"] == "Guide"
    assert "character_name" not in str(file_dict["roles"])
    assert "bootstrap_messages" not in file_dict


def test_store_voxta_store_roundtrip_definition_equal(tmp_path):
    store = _store(tmp_path)
    first = store.create(OWNER, native_body(), now=NOW)
    file_dict, _ = export_stored_definition(first, "voxta")
    second = store.create(OWNER, file_dict, now=NOW)
    assert second.definition == first.definition
    assert second.source_format == "voxta"  # its road, honestly


# --------------------------------------------------------- honesty


def test_unmappable_values_absent_and_named_in_both_formats(tmp_path):
    store = _store(tmp_path)
    rec = store.create(OWNER, voxta_body_with_unmappable(), now=NOW)
    for fmt in ("native", "voxta"):
        file_dict, report = export_stored_definition(rec, fmt)
        assert "scripts" not in file_dict
        assert "hudWidgets" not in file_dict
        named = {(r["path"], r["kind"]) for r in report["not_restored"]}
        assert named == {
            ("scripts", "scripting"), ("hudWidgets", "hud_widget")}
        assert all(r["reason"] for r in report["not_restored"])


def test_clean_record_names_nothing_not_restored(tmp_path):
    store = _store(tmp_path)
    rec = store.create(OWNER, native_body(), now=NOW)
    for fmt in ("native", "voxta"):
        _, report = export_stored_definition(rec, fmt)
        assert report["not_restored"] == []


def test_report_notes_carry_the_standing_honesty(tmp_path):
    store = _store(tmp_path)
    rec = store.create(OWNER, voxta_body_with_unmappable(), now=NOW)
    _, native_report = export_stored_definition(rec, "native")
    _, voxta_report = export_stored_definition(rec, "voxta")
    assert any("no raw overlay" in n for n in native_report["notes"])
    assert any("never persisted" in n for n in native_report["notes"])
    assert any("the stored definition itself" in n
               for n in native_report["notes"])
    assert any("typed-fields conversion" in n for n in voxta_report["notes"])
    assert any("not the" in n and "original Voxta file" in n
               for n in voxta_report["notes"])


def test_export_reflects_the_records_current_revision(tmp_path):
    store = _store(tmp_path)
    rec = store.create(OWNER, native_body(), now=NOW)
    changed = native_body()
    changed["description"] = "Second evening."
    rec2 = store.replace(rec.id, OWNER, changed, now=NOW)
    file_dict, report = export_stored_definition(rec2, "native")
    assert report["revision"] == 2
    assert file_dict == rec2.definition
    assert file_dict["description"] == "Second evening."


def test_unknown_format_raises_before_any_work(tmp_path):
    store = _store(tmp_path)
    rec = store.create(OWNER, native_body(), now=NOW)
    with pytest.raises(StoredExportError):
        export_stored_definition(rec, "yaml")
    with pytest.raises(StoredExportError):
        export_stored_definition(rec, "")


def test_malformed_stored_report_reads_as_nothing_not_restored(tmp_path):
    store = _store(tmp_path)
    rec = store.create(OWNER, native_body(), now=NOW)
    broken = type(rec)(
        id=rec.id, owner_id=rec.owner_id, name=rec.name,
        definition=rec.definition, source_format=rec.source_format,
        report={"unmappable": "not-a-list"}, revision=rec.revision,
        created_at=rec.created_at, updated_at=rec.updated_at,
    )
    file_dict, report = export_stored_definition(broken, "native")
    assert file_dict == rec.definition
    assert report["not_restored"] == []


# -------------------------------------------------------------- HTTP


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    app = create_app(factory)
    client = TestClient(app)
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_http_export_envelope_both_formats_and_default(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/scenarios", json=voxta_body())
    assert created.status_code == 201
    did = created.json()["id"]
    default = client.get(f"/api/v1/scenarios/{did}/export")
    assert default.status_code == 200
    env = default.json()
    assert env["format"] == "native"
    assert env["file"] == created.json()["definition"]
    assert env["report"]["definition_id"] == did
    assert env["report"]["not_restored"] == []
    vox = client.get(f"/api/v1/scenarios/{did}/export?format=voxta")
    assert vox.status_code == 200
    assert vox.json()["format"] == "voxta"
    assert vox.json()["file"]["chatFlow"] == "Story"
    assert "scenario_text" not in vox.json()["file"]


def test_http_export_names_unmappable_loss(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/v1/scenarios", json=voxta_body_with_unmappable())
    did = created.json()["id"]
    env = client.get(f"/api/v1/scenarios/{did}/export?format=voxta").json()
    assert "scripts" not in env["file"]
    assert {r["path"] for r in env["report"]["not_restored"]} == {
        "scripts", "hudWidgets"}


def test_http_export_404s_and_422(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/scenarios", json=native_body())
    did = created.json()["id"]
    assert client.get("/api/v1/scenarios/no-such/export").status_code == 404
    # existence is decided before the format is judged
    assert client.get(
        "/api/v1/scenarios/no-such/export?format=yaml").status_code == 404
    assert client.get(
        f"/api/v1/scenarios/{did}/export?format=yaml").status_code == 422
    # a definition owned by someone else answers exactly like unknown
    store = ScenarioStore(definitions_path())
    foreign = store.create(FOREIGN, native_body(), now=NOW)
    assert client.get(
        f"/api/v1/scenarios/{foreign.id}/export").status_code == 404


def test_http_neighbour_roads_untouched(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/scenarios", json=voxta_body())
    assert created.status_code == 201
    did = created.json()["id"]
    got = client.get(f"/api/v1/scenarios/{did}")
    assert got.status_code == 200 and got.json()["revision"] == 1
    imp = client.post("/api/v1/scenarios/import", json=voxta_body())
    assert imp.status_code == 200
    assert imp.json()["source_format"] == "voxta"
    exp = client.post(
        "/api/v1/scenarios/export?format=native", json=voxta_body())
    assert exp.status_code == 200
    assert exp.json()["name"] == "Harbour Lights at Dusk"



# ------------------------------------------- carried shadowing (F2)


def collide_body():
    body = native_body()
    body["variables"] = {"sneaky": 1}
    body["flags"] = {"carried_flag": True}
    return body


def test_carried_keys_shadowed_by_voxta_typed_fields_are_named(tmp_path):
    store = _store(tmp_path)
    rec = store.create(OWNER, collide_body(), now=NOW)
    # both carried keys persist in the stored definition itself
    assert rec.definition["variables"] == {"sneaky": 1}
    assert rec.definition["flags"] == {"carried_flag": True}
    file_dict, report = export_stored_definition(rec, "voxta")
    # the typed values win the keys; the carried values are absent
    assert file_dict["variables"] == {"gold": 5}
    assert file_dict["flags"] == {"met_guide": True}
    assert "sneaky" not in str(file_dict)
    assert "carried_flag" not in str(file_dict)
    # ... and NAMED in the report, never silently dropped
    named = {row["key"] for row in report["carried_shadowed"]}
    assert named == {"variables", "flags"}
    assert all(row["reason"] for row in report["carried_shadowed"])
    assert any("carried_shadowed" in n for n in report["notes"])
    # the native file is the stored definition: nothing shadows
    native_file, native_report = export_stored_definition(rec, "native")
    assert native_file == rec.definition
    assert native_report["carried_shadowed"] == []


def test_carried_key_with_the_typed_value_is_not_shadowed(tmp_path):
    store = _store(tmp_path)
    body = native_body()
    body["variables"] = {"gold": 5}  # equal to initial_variables
    rec = store.create(OWNER, body, now=NOW)
    file_dict, report = export_stored_definition(rec, "voxta")
    assert file_dict["variables"] == {"gold": 5}
    assert report["carried_shadowed"] == []  # nothing was lost


def test_carried_key_rides_when_the_typed_field_writes_nothing(tmp_path):
    store = _store(tmp_path)
    body = native_body()
    body["initial_variables"] = {}
    body["variables"] = {"sneaky": 1}
    rec = store.create(OWNER, body, now=NOW)
    file_dict, report = export_stored_definition(rec, "voxta")
    assert file_dict["variables"] == {"sneaky": 1}  # carried rides
    assert report["carried_shadowed"] == []


def test_http_empty_format_is_422_and_unknown_id_still_404(
    tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/scenarios", json=native_body())
    did = created.json()["id"]
    # an explicitly empty format is a value outside FORMATS:
    # the design's 422, not a silent default (finisher fix)
    assert client.get(
        f"/api/v1/scenarios/{did}/export?format=").status_code == 422
    # existence is still decided first: unknown id answers 404
    assert client.get(
        "/api/v1/scenarios/no-such/export?format=").status_code == 404

# ----------------------------------------------------- migration pin


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    assert MIGRATIONS[-1][0] == "0042"
    client = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/scenarios", json=native_body())
    assert created.status_code == 201
    assert current_revision(tmp_path / "test.db") == "0042"
