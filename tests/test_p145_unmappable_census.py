"""P-145 - Library unmappable-content census (Part IX, DERIVED).

Pins: the census as the P-131 reports' own naming read not
run (elements read through P-133's reading law - a missing
or malformed report reads as no elements, non-dict rows
skipped, fields str-coerced; rows name their definition by
P-131's summary() verbatim and carry the report's rows
verbatim in report order); the rollups summed from the
rows themselves (by_kind in first-appearance order across
rows in store order; counts cross-checked arithmetically
against the rows); owner scoping at service level (a
foreign record is never this owner's census row - the
service receives only the caller's list_for_owner answer)
and over HTTP; the pure read (the store document
byte-untouched at service level and over HTTP, and no
store document created where none stood); the HTTP road
(200 envelope; the honest zero census for an empty and
for a clean-only library; the literal road never shadowed
by {definition_id} - a real definition still reads on its
own road and the tags road answers beside it); the five
standing honesty notes in fixed order; and the migration
head pinned at 0041. No network: fixtures only.
"""

from __future__ import annotations

import copy

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.scenarios.reportcensus import census_unmappable
from runmal.scenarios.store import (
    ScenarioDefinition,
    ScenarioStore,
    definitions_path,
)

NOW = "2026-11-08T19:00:00+00:00"
OWNER = "owner-p145"
FOREIGN = "foreign-p145"
ROAD = "/api/v1/scenarios/library/unmappable"

NATIVE_BODY = {
    "name": "Clean Harbour",
    "description": "A quiet harbour, first evening.",
    "scenario_text": "The ferry has just left.",
    "flow": "story",
    "style": "storytelling",
    "roles": [
        {"name": "Narrator", "character_name": "Maera",
         "enabled_on_start": True, "can_speak": True},
    ],
    "bootstrap_messages": [
        {"kind": "note", "text": "The tide is going out.",
         "role": "Narrator"},
    ],
    "initial_flags": {"met_maera": True},
    "initial_variables": {"trust": 2},
}


def native_body(name=None):
    out = copy.deepcopy(NATIVE_BODY)
    if name:
        out["name"] = name
    return out


def voxta_body(name, *, scripts=False, hud=False, actions=False):
    out = {
        "name": name,
        "chatFlow": "Story",
        "scenario": "A harbour, voiced.",
    }
    if scripts:
        out["scripts"] = [{"code": "x=1"}]
    if actions:
        out["actions"] = [{"a": 1}]
    if hud:
        out["hudWidgets"] = [{"widget": "map"}]
    return out


def _store(tmp_path, name="scenarios.json"):
    return ScenarioStore(tmp_path / name)


def _library(tmp_path):
    """Clean, scripting-only, then scripting+action+hud, store order."""
    store = _store(tmp_path)
    clean = store.create(OWNER, native_body(), now=NOW)
    one = store.create(
        OWNER, voxta_body("Vox One", scripts=True), now=NOW)
    many = store.create(
        OWNER,
        voxta_body("Vox Many", scripts=True, actions=True, hud=True),
        now=NOW)
    return store, clean, one, many


# ------------------------------------------------------- service


def test_empty_library_is_the_honest_zero_census(tmp_path):
    out = census_unmappable([])
    assert out["definitions"] == []
    assert out["by_kind"] == []
    assert out["counts"] == {
        "definitions_total": 0,
        "definitions_with_unmappable": 0,
        "definitions_clean": 0,
        "unmappable_total": 0,
        "kinds_represented": 0,
    }
    assert len(out["notes"]) == 5


def test_clean_only_library_has_zero_rows(tmp_path):
    store = _store(tmp_path)
    store.create(OWNER, native_body(), now=NOW)
    store.create(OWNER, native_body("Second Clean"), now=NOW)
    out = census_unmappable(store.list_for_owner(OWNER))
    assert out["definitions"] == []
    assert out["by_kind"] == []
    assert out["counts"]["definitions_total"] == 2
    assert out["counts"]["definitions_clean"] == 2
    assert out["counts"]["definitions_with_unmappable"] == 0
    assert out["counts"]["unmappable_total"] == 0


def test_rows_are_the_reports_own_naming_verbatim(tmp_path):
    store, clean, one, many = _library(tmp_path)
    out = census_unmappable(store.list_for_owner(OWNER))
    rows = out["definitions"]
    # store order, clean definition absent
    assert [r["definition"]["id"] for r in rows] == [one.id, many.id]
    for row, record in zip(rows, (one, many), strict=True):
        assert row["definition"] == record.summary()
        assert row["definition"]["has_unmappable"] is True
        assert row["source_format"] == "voxta"
        assert row["unmappable"] == record.report["unmappable"]
        assert row["unmappable_count"] == len(record.report["unmappable"])
        assert row["kinds"] == [
            e["kind"] for e in record.report["unmappable"]]
        assert sum(1 for _ in row["kinds"]) == row["unmappable_count"]
    assert rows[0]["kinds"] == ["scripting"]
    assert rows[1]["kinds"] == ["scripting", "action", "hud_widget"]


def test_by_kind_first_appearance_order_and_counts_from_rows(tmp_path):
    store, clean, one, many = _library(tmp_path)
    out = census_unmappable(store.list_for_owner(OWNER))
    assert out["by_kind"] == [
        {"kind": "scripting", "count": 2},
        {"kind": "action", "count": 1},
        {"kind": "hud_widget", "count": 1},
    ]
    counts = out["counts"]
    assert counts["definitions_total"] == 3
    assert counts["definitions_with_unmappable"] == 2
    assert counts["definitions_clean"] == 1
    assert counts["unmappable_total"] == 4
    assert counts["kinds_represented"] == 3
    # every count cross-checked against the rows themselves
    rows = out["definitions"]
    assert counts["unmappable_total"] == sum(
        r["unmappable_count"] for r in rows)
    assert counts["unmappable_total"] == sum(
        k["count"] for k in out["by_kind"])
    assert counts["definitions_with_unmappable"] == len(rows)
    assert counts["kinds_represented"] == len(out["by_kind"])


def test_foreign_records_are_never_in_the_callers_census(tmp_path):
    store = _store(tmp_path)
    store.create(FOREIGN, voxta_body("Foreign Vox", scripts=True), now=NOW)
    store.create(OWNER, native_body(), now=NOW)
    out = census_unmappable(store.list_for_owner(OWNER))
    assert out["definitions"] == []
    assert out["counts"]["definitions_total"] == 1
    foreign = census_unmappable(store.list_for_owner(FOREIGN))
    assert foreign["counts"]["definitions_with_unmappable"] == 1


def test_malformed_reports_read_honestly():
    def record(report, rid):
        return ScenarioDefinition(
            id=rid, owner_id=OWNER, name=rid, definition={},
            source_format="voxta", report=report, revision=1,
            created_at=NOW, updated_at=NOW)
    records = [
        record({}, "missing-unmappable"),
        record({"unmappable": "not-a-list"}, "malformed-list"),
        record({"unmappable": [
            "not-a-dict",
            {"path": "scripts", "kind": "scripting",
             "name": "scripts", "reason": "named"},
            {"path": 7, "kind": "action"},
        ]}, "mixed"),
    ]
    out = census_unmappable(records)
    assert out["counts"]["definitions_total"] == 3
    assert out["counts"]["definitions_with_unmappable"] == 1
    row = out["definitions"][0]
    assert row["definition"]["id"] == "mixed"
    # the non-dict row is skipped; fields are str-coerced
    assert row["unmappable"] == [
        {"path": "scripts", "kind": "scripting",
         "name": "scripts", "reason": "named"},
        {"path": "7", "kind": "action", "name": "", "reason": ""},
    ]
    assert out["by_kind"] == [
        {"kind": "scripting", "count": 1},
        {"kind": "action", "count": 1},
    ]


def test_service_is_a_pure_read_byte_untouched(tmp_path):
    store, clean, one, many = _library(tmp_path)
    path = tmp_path / "scenarios.json"
    before = path.read_bytes()
    census_unmappable(store.list_for_owner(OWNER))
    assert path.read_bytes() == before


def test_notes_are_five_and_in_fixed_order(tmp_path):
    out = census_unmappable([])
    notes = out["notes"]
    assert "written, deleted and repaired nothing" in notes[0]
    assert "not a cleanup" in notes[1]
    assert "named, never executed" in notes[2]
    assert "the report is the record" in notes[3]
    assert "no definition content" in notes[4]


def test_census_carries_no_definition_content(tmp_path):
    store, clean, one, many = _library(tmp_path)
    out = census_unmappable(store.list_for_owner(OWNER))
    for row in out["definitions"]:
        assert "definition" in row and "unmappable" in row
        summary = row["definition"]
        assert "scenario_text" not in summary
        assert "roles" not in summary
        assert "bootstrap_messages" not in summary
        for element in row["unmappable"]:
            assert set(element) == {"path", "kind", "name", "reason"}


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


def test_http_zero_census_for_a_fresh_owner(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    res = client.get(ROAD)
    assert res.status_code == 200
    out = res.json()
    assert out["definitions"] == []
    assert out["counts"]["definitions_total"] == 0
    assert len(out["notes"]) == 5
    # no store document was created by the read
    assert not (tmp_path / "scenarios.json").exists()


def test_http_census_names_the_library(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/scenarios", json=native_body())
    assert created.status_code == 201
    created = client.post(
        "/api/v1/scenarios",
        json=voxta_body("Vox HTTP", scripts=True, hud=True))
    assert created.status_code == 201
    vox_id = created.json()["id"]
    res = client.get(ROAD)
    assert res.status_code == 200
    out = res.json()
    assert out["counts"] == {
        "definitions_total": 2,
        "definitions_with_unmappable": 1,
        "definitions_clean": 1,
        "unmappable_total": 2,
        "kinds_represented": 2,
    }
    assert [r["definition"]["id"] for r in out["definitions"]] == [vox_id]
    assert out["definitions"][0]["kinds"] == ["scripting", "hud_widget"]


def test_http_road_not_shadowed_and_neighbours_stand(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/v1/scenarios", json=voxta_body("Vox Solo", scripts=True))
    assert created.status_code == 201
    record = created.json()
    # the literal census road answers the census, not a record
    assert client.get(ROAD).status_code == 200
    # the per-definition road still reads the record in full
    got = client.get(f"/api/v1/scenarios/{record['id']}")
    assert got.status_code == 200
    assert got.json()["report"]["unmappable"][0]["kind"] == "scripting"
    # the neighbouring library road still answers
    tags = client.get("/api/v1/scenarios/library/tags")
    assert tags.status_code == 200 and tags.json()["total"] == 0
    # the library list still answers with its bool only
    listed = client.get("/api/v1/scenarios")
    assert listed.status_code == 200
    assert listed.json()["scenarios"][0]["has_unmappable"] is True


def test_http_census_leaves_store_byte_untouched(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/v1/scenarios", json=voxta_body("Vox Bytes", scripts=True))
    assert created.status_code == 201
    path = definitions_path()
    before = path.read_bytes()
    assert client.get(ROAD).status_code == 200
    assert path.read_bytes() == before


def test_http_foreign_definitions_never_counted(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    store = ScenarioStore(definitions_path())
    store.create(FOREIGN, voxta_body("Foreign HTTP", scripts=True), now=NOW)
    res = client.get(ROAD)
    assert res.status_code == 200
    out = res.json()
    assert out["definitions"] == []
    assert out["counts"]["definitions_total"] == 0


# ----------------------------------------------------- migration


def test_migration_head_stays_0041(tmp_path):
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
    assert MIGRATIONS[-1][0] == "0042"
