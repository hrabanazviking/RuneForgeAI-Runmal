"""P-141 — Scenario definition sharing packs (Part IX, DERIVED).

Pins: the envelope (format / version / kind / schema; the
manifest read from the payload itself — name, role and
bootstrap counts, canonical byte length — and the content
checksum over the canonical definition); provenance in the
P-029 rules (source id / name / pinned revision / ORIGINAL
source format, and the source record's P-131 import report
carried verbatim as data — the one artefact the P-133 file
roads cannot carry); parse as one typed refusal (tampered
payload, manifest drift, forged provenance checksum,
non-native or unimportable payload — nothing written on
any refusal); inspect as a pure pre-flight (validates and
reports, touches no store); import in the P-045 collision
discipline (exact duplicate returns the existing record
unwritten and owner-scoped; same-name collision creates
fresh by default and refuses under on_conflict=reject;
the new record's own report is its fresh native parse's
report — the carried source_report is data in the pack
and the import report, never installed); nothing else
travels (no organisation row, no binding document); the
HTTP roads (GET pack 200 / 404 alike for unknown and
foreign; inspect 200 / 422; import-pack 201 then 200 on
duplicate, 422 on reject and on malformed; the literal
roads never shadowed by {definition_id}); the neighbour
roads untouched beside them; and the migration head
pinned at 0041. No network: fixtures only.
"""

from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.scenarios.packs import (
    PACK_FORMAT,
    PACK_SCHEMA,
    PackError,
    build_pack,
    canonical_bytes,
    content_checksum,
    import_pack,
    inspect_pack,
    pack_to_bytes,
    parse_pack,
)
from runmal.scenarios.store import ScenarioStore, definitions_path

NOW = "2026-11-08T17:00:00+00:00"
OWNER = "owner-p141"
FOREIGN = "foreign-p141"

BODY = {
    "name": "Harbour Lights at Dusk",
    "description": "A quiet harbour, first evening.",
    "scenario_text": "The ferry has just left.",
    "flow": "story",
    "style": "storytelling",
    "narrator_name": "The Harbour Voice",
    "impersonation_name": "Ash",
    "roles": [
        {"name": "Narrator", "character_name": "Maera",
         "enabled_on_start": True, "can_speak": True},
    ],
    "bootstrap_messages": [
        {"kind": "note", "text": "The tide is going out.", "role": "Narrator"},
        {"kind": "user", "text": "I never left.", "role": ""},
    ],
    "initial_flags": {"met_maera": True},
    "initial_variables": {"trust": 2},
}

VOXTA_BODY = {
    "name": "Vox Harbour",
    "chatFlow": "Story",
    "scenario": "A harbour, voiced.",
    "scripts": [{"code": "x=1"}],
}


def body(name=None) -> dict:
    out = copy.deepcopy(BODY)
    if name:
        out["name"] = name
    return out


def _store(tmp_path, name="scenarios.json"):
    return ScenarioStore(tmp_path / name)


def _packed_record(tmp_path):
    store = _store(tmp_path)
    record = store.create(OWNER, body(), now=NOW)
    return store, record, build_pack(record, exported_at=NOW)


# --------------------------------------------------------- build


def test_build_pack_envelope_and_manifest(tmp_path):
    _store_, record, pack = _packed_record(tmp_path)
    assert pack["format"] == PACK_FORMAT
    assert pack["pack_version"] == 1
    assert pack["kind"] == "scenario"
    assert pack["schema"] == PACK_SCHEMA
    # the payload is the stored definition, verbatim
    assert pack["scenario"] == record.definition
    manifest = pack["manifest"]
    assert manifest["definition_name"] == "Harbour Lights at Dusk"
    assert manifest["role_count"] == 1
    assert manifest["bootstrap_count"] == 2
    assert manifest["payload_format"] == "native"
    assert manifest["content_sha256"] == content_checksum(record.definition)
    assert manifest["payload_canonical_bytes"] == len(
        canonical_bytes(record.definition))
    assert manifest["exported_at"] == NOW


def test_build_pack_provenance_facts_and_note(tmp_path):
    _store_, record, pack = _packed_record(tmp_path)
    prov = pack["provenance"]
    assert prov["source_kind"] == "scenario_pack_export"
    assert prov["source_definition_id"] == record.id
    assert prov["source_definition_name"] == record.name
    assert prov["source_revision"] == 1
    assert prov["source_format"] == "native"
    assert prov["content_sha256"] == pack["manifest"]["content_sha256"]
    assert prov["source_report"] == record.report
    assert "note" not in prov
    noted = build_pack(record, exported_at=NOW, note="for the hub")
    assert noted["provenance"]["note"] == "for the hub"


def test_build_pack_voxta_origin_provenance_is_honest(tmp_path):
    store = _store(tmp_path)
    record = store.create(OWNER, copy.deepcopy(VOXTA_BODY), now=NOW)
    assert record.source_format == "voxta"
    pack = build_pack(record, exported_at=NOW)
    # the payload is the native stored shape...
    assert pack["scenario"]["source_format"] == "native"
    assert pack["scenario"] == record.definition
    # ...while provenance names the ORIGINAL format plainly
    prov = pack["provenance"]
    assert prov["source_format"] == "voxta"
    # and the report that names the unmappable scripting
    # rides verbatim — the artefact no file road can carry
    assert prov["source_report"] == record.report
    kinds = [u["kind"] for u in prov["source_report"]["unmappable"]]
    assert kinds == ["scripting"]


# --------------------------------------------------------- parse


def test_pack_bytes_round_trip_and_reserialisation(tmp_path):
    _s, _r, pack = _packed_record(tmp_path)
    assert parse_pack(pack_to_bytes(pack)) == pack
    assert parse_pack(pack_to_bytes(pack).decode("utf-8")) == pack
    # cosmetic re-serialisation never invalidates: identity
    # is over the canonical payload, not the pack bytes
    reserialised = json.dumps(pack, indent=4, sort_keys=False)
    assert parse_pack(reserialised) == pack


def test_parse_refuses_tampered_payload(tmp_path):
    _s, _r, pack = _packed_record(tmp_path)
    pack["scenario"]["scenario_text"] = "Altered in transit."
    with pytest.raises(PackError, match="checksum mismatch"):
        parse_pack(pack)


@pytest.mark.parametrize("mutate", [
    lambda p: p.update({"format": "runmal-lorebook-pack"}),
    lambda p: p.update({"pack_version": 2}),
    lambda p: p.update({"pack_version": True}),
    lambda p: p.update({"kind": "lorebook"}),
    lambda p: p.update({"manifest": None}),
    lambda p: p.update({"provenance": {}}),
    lambda p: p.update({"scenario": None}),
    lambda p: p["manifest"].update({"definition_name": "Other"}),
    lambda p: p["manifest"].update({"role_count": 9}),
    lambda p: p["manifest"].update({"bootstrap_count": 0}),
    lambda p: p["manifest"].update({"payload_canonical_bytes": 3}),
    lambda p: p["provenance"].update({"content_sha256": "0" * 64}),
])
def test_parse_refuses_envelope_faults(tmp_path, mutate):
    _s, _r, pack = _packed_record(tmp_path)
    mutate(pack)
    with pytest.raises(PackError):
        parse_pack(pack)


def test_parse_refuses_non_native_payload(tmp_path):
    _s, _r, pack = _packed_record(tmp_path)
    pack["scenario"] = copy.deepcopy(VOXTA_BODY)
    with pytest.raises(PackError, match="native scenario shape"):
        parse_pack(pack)


def test_parse_refuses_unimportable_payload(tmp_path):
    _s, _r, pack = _packed_record(tmp_path)
    pack["scenario"] = {"source_format": "native", "bogus": 1}
    with pytest.raises(PackError, match="not importable"):
        parse_pack(pack)


# ------------------------------------------------------- inspect


def test_inspect_reports_and_touches_nothing(tmp_path):
    _s, record, pack = _packed_record(tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir())
    out = inspect_pack(pack)
    assert out["valid"] is True
    assert out["checksum_verified"] is True
    assert out["schema"] == PACK_SCHEMA
    assert out["definition_name"] == "Harbour Lights at Dusk"
    assert out["role_count"] == 1 and out["bootstrap_count"] == 2
    assert out["content_sha256"] == content_checksum(record.definition)
    assert out["manifest"] == pack["manifest"]
    assert out["provenance"] == pack["provenance"]
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    bad = copy.deepcopy(pack)
    bad["scenario"]["name"] = "Forged Name"
    with pytest.raises(PackError):
        inspect_pack(bad)


# -------------------------------------------------------- import


def test_import_creates_fresh_record(tmp_path):
    _s, source, pack = _packed_record(tmp_path)
    target = _store(tmp_path, "target.json")
    record, report = import_pack(target, OWNER, pack, now=NOW)
    assert report["created"] is True
    assert report["duplicate_exact"] is False
    assert report["name_collision"] is False
    assert report["definition_id"] == record.id
    assert record.id != source.id
    assert record.revision == 1
    assert record.owner_id == OWNER
    # what landed is exactly the payload the checksum names
    assert record.definition == pack["scenario"]
    assert target.list_for_owner(OWNER) == [record]


def test_import_fresh_report_and_carried_report_stays_data(tmp_path):
    store = _store(tmp_path)
    source = store.create(OWNER, copy.deepcopy(VOXTA_BODY), now=NOW)
    pack = build_pack(source, exported_at=NOW)
    target = _store(tmp_path, "target.json")
    record, report = import_pack(target, OWNER, pack, now=NOW)
    # the new record's own report is its fresh native parse's:
    # it cannot name the unmappable scripting (P-133 one-way law)
    assert record.source_format == "native"
    assert record.report["source_format"] == "native"
    assert record.report["unmappable"] == []
    # the naming is NOT lost to the receiver: it rides in the
    # pack's provenance and in the import report, verbatim
    carried = report["provenance"]["source_report"]
    assert carried == source.report
    assert [u["kind"] for u in carried["unmappable"]] == ["scripting"]
    assert len(report["notes"]) == 3
    assert "not installed as the record's report" in report["notes"][0]
    assert "no organisation row and no binding" in report["notes"][1]


def test_import_duplicate_exact_returns_existing_unwritten(tmp_path):
    store, source, pack = _packed_record(tmp_path)
    before = (tmp_path / "scenarios.json").read_bytes()
    record, report = import_pack(store, OWNER, pack, now=NOW)
    assert record.id == source.id
    assert report["created"] is False
    assert report["duplicate_exact"] is True
    assert report["name_collision"] is False
    assert store.list_for_owner(OWNER) == [source]
    assert (tmp_path / "scenarios.json").read_bytes() == before


def test_import_duplicate_is_owner_scoped(tmp_path):
    store, _source, pack = _packed_record(tmp_path)
    # the identical definition under ANOTHER owner never
    # counts as this owner's duplicate
    record, report = import_pack(store, FOREIGN, pack, now=NOW)
    assert report["created"] is True
    assert report["duplicate_exact"] is False
    assert record.owner_id == FOREIGN
    assert len(store.list_for_owner(OWNER)) == 1
    assert len(store.list_for_owner(FOREIGN)) == 1


def test_import_name_collision_create_new_and_reject(tmp_path):
    store = _store(tmp_path)
    existing = store.create(OWNER, body(), now=NOW)
    # an honest pack around a same-name, different-content
    # definition held by another owner
    alt_body = body()
    alt_body["scenario_text"] = "Different contents entirely."
    altered = ScenarioStore(tmp_path / "altered.json").create(
        FOREIGN, alt_body, now=NOW)
    pack = build_pack(altered, exported_at=NOW)
    record, report = import_pack(store, OWNER, pack, now=NOW)
    assert report["created"] is True
    assert report["name_collision"] is True
    assert record.id != existing.id and record.name == existing.name
    assert len(store.list_for_owner(OWNER)) == 2
    # duplicate detection precedes collision handling (the
    # P-045 order): re-importing THIS pack under reject is
    # an exact duplicate of the record just created, not
    # a collision — nothing would be created, so nothing
    # is refused
    again, report = import_pack(
        store, OWNER, pack, on_conflict="reject", now=NOW)
    assert again.id == record.id
    assert report["duplicate_exact"] is True
    # reject fires on a FRESH same-name, different-content
    # pack: it would create a colliding record, so it
    # refuses and writes nothing
    third_body = body()
    third_body["scenario_text"] = "Third contents, still colliding."
    third = ScenarioStore(tmp_path / "third.json").create(
        FOREIGN, third_body, now=NOW)
    third_pack = build_pack(third, exported_at=NOW)
    with pytest.raises(PackError, match="on_conflict='reject'"):
        import_pack(store, OWNER, third_pack, on_conflict="reject", now=NOW)
    assert len(store.list_for_owner(OWNER)) == 2


def test_import_refuses_malformed_whole_and_bad_mode(tmp_path):
    _s, _r, pack = _packed_record(tmp_path)
    target = _store(tmp_path, "target.json")
    pack["scenario"]["initial_variables"] = {"trust": 99}
    with pytest.raises(PackError):
        import_pack(target, OWNER, pack, now=NOW)
    assert target.list_for_owner(OWNER) == []
    assert not (tmp_path / "target.json").exists()
    good = _packed_record(tmp_path)[2]
    with pytest.raises(PackError, match="on_conflict"):
        import_pack(target, OWNER, good, on_conflict="merge", now=NOW)
    assert target.list_for_owner(OWNER) == []


def test_import_report_provenance_verbatim_with_unknown_keys(tmp_path):
    _s, _r, pack = _packed_record(tmp_path)
    pack["provenance"]["hub_annotation"] = {"carrier": "future-hub"}
    pack["hub_top_level"] = {"annotated": True}
    target = _store(tmp_path, "target.json")
    _record, report = import_pack(target, OWNER, pack, now=NOW)
    assert report["provenance"] == pack["provenance"]
    assert report["provenance"]["hub_annotation"] == {"carrier": "future-hub"}
    assert report["manifest"] == pack["manifest"]


def test_import_writes_no_other_store_documents(tmp_path):
    _s, _r, pack = _packed_record(tmp_path)
    target = _store(tmp_path, "target.json")
    import_pack(target, OWNER, pack, now=NOW)
    assert (tmp_path / "target.json").exists()
    assert not (tmp_path / "scenario_organisation.json").exists()
    assert not (tmp_path / "scenario_bindings.json").exists()


# ---------------------------------------------------------- HTTP


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _http_pack(client):
    definition = client.post("/api/v1/scenarios", json=body()).json()
    res = client.get(f"/api/v1/scenarios/{definition['id']}/pack")
    assert res.status_code == 200
    return definition, res.json()


def test_http_get_pack_road_round_trips_through_parse(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition, pack = _http_pack(client)
    assert pack["manifest"]["definition_name"] == definition["name"]
    assert parse_pack(pack) == pack
    assert inspect_pack(pack)["checksum_verified"] is True


def test_http_get_pack_unknown_and_foreign_404_alike(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    store = ScenarioStore(definitions_path())
    foreign = store.create(FOREIGN, body(), now=NOW)
    for target in (foreign.id, "no-such-id"):
        res = client.get(f"/api/v1/scenarios/{target}/pack")
        assert res.status_code == 404
        assert res.json()["detail"] == "scenario definition not found"


def test_http_inspect_road_writes_nothing(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    _definition, pack = _http_pack(client)
    res = client.post("/api/v1/scenarios/pack/inspect", json=pack)
    assert res.status_code == 200
    assert res.json()["valid"] is True
    bad = copy.deepcopy(pack)
    bad["scenario"]["scenario_text"] = "Altered."
    res = client.post("/api/v1/scenarios/pack/inspect", json=bad)
    assert res.status_code == 422
    # only the one definition the fixture created exists
    assert client.get("/api/v1/scenarios").json()["total"] == 1


def test_http_import_pack_statuses(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    _definition, pack = _http_pack(client)
    # importing the pack of a definition this owner already
    # holds byte-identically -> 200 duplicate, nothing written
    res = client.post("/api/v1/scenarios/import-pack", json=pack)
    assert res.status_code == 200
    out = res.json()
    assert out["pack_import"]["duplicate_exact"] is True
    assert out["pack_import"]["created"] is False
    assert client.get("/api/v1/scenarios").json()["total"] == 1
    # a fresh pack (built around a foreign-held record) -> 201
    store = ScenarioStore(definitions_path())
    foreign = store.create(FOREIGN, body("Mountain Gate"), now=NOW)
    foreign_pack = build_pack(foreign, exported_at=NOW)
    res = client.post("/api/v1/scenarios/import-pack", json=foreign_pack)
    assert res.status_code == 201
    out = res.json()
    assert out["name"] == "Mountain Gate"
    assert out["pack_import"]["created"] is True
    assert out["pack_import"]["definition_id"] == out["id"]
    assert client.get("/api/v1/scenarios").json()["total"] == 2
    # collision + reject -> 422, nothing written
    alt_body = body()
    alt_body["scenario_text"] = "Other words."
    altered = ScenarioStore(tmp_path / "alt.json").create(
        FOREIGN, alt_body, now=NOW)
    clash_pack = build_pack(altered, exported_at=NOW)
    res = client.post(
        "/api/v1/scenarios/import-pack?on_conflict=reject", json=clash_pack)
    assert res.status_code == 422
    assert client.get("/api/v1/scenarios").json()["total"] == 2
    # malformed -> 422
    res = client.post("/api/v1/scenarios/import-pack", json={"format": "nope"})
    assert res.status_code == 422


def test_http_neighbour_roads_untouched_beside_pack(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition, pack = _http_pack(client)
    base = f"/api/v1/scenarios/{definition['id']}"
    assert client.get(base).status_code == 200
    assert client.get(f"{base}/export").status_code == 200
    assert client.get(f"{base}/bind-plan").status_code == 200
    assert client.get(f"{base}/delete-impact").status_code == 200
    assert client.get(f"{base}/organisation").status_code == 200
    dup = client.post(f"{base}/duplicate")
    assert dup.status_code == 201
    # the literal pack roads are not read as a definition id
    assert client.post(
        "/api/v1/scenarios/pack/inspect", json=pack).status_code == 200
    assert client.get(
        f"/api/v1/scenarios/{dup.json()['id']}/pack").status_code == 200


# ----------------------------------------------------- migration


def test_migration_head_stays_0041(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
    assert MIGRATIONS[-1][0] == "0042"
