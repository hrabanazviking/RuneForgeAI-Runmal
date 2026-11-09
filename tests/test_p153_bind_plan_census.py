"""P-153 - Library bind-plan census (Part IX, DERIVED).

Pins: the census as P-136's own judgement read across the
whole library, not re-planned (each row carries
preview_bind_plan's counts and the plan's skipped rows
verbatim, beside the record's P-131 summary verbatim);
every definition rows in store order, clean and empty
included - the subject is the definition; the four-state
plan law (clean / partial / skips_only / empty) read from
P-136's counts alone; the rollups summed from the rows
themselves (by_where in first-appearance order; counts
cross-checked arithmetically against the rows); no
content carried (no message text, no seedable key, no
flag or variable value - a skipped row names exactly
where / key_or_index / reason); owner scoping at service
level and over HTTP; the pure read (the store document
byte-untouched at service level and over HTTP, and no
store document created where none stood); a replace
moving the row to the new revision and its new plan;
the HTTP road (200 envelope; the honest zero census for
a fresh owner; the row agreeing with the P-136
per-definition road beside it; the literal road never
shadowed by {definition_id} - a real definition still
reads on its own roads and the neighbouring library
roads answer beside it); the five standing honesty
notes in fixed order; and the migration head pinned at
0041. No network: fixtures only.
"""

from __future__ import annotations

import copy
import json

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.scenarios.bindpreview import preview_bind_plan
from runmal.scenarios.plancensus import census_bind_plans
from runmal.scenarios.store import (
    ScenarioDefinition,
    ScenarioStore,
    definitions_path,
)

NOW = "2026-11-08T20:00:00+00:00"
LATER = "2026-11-08T20:30:00+00:00"
OWNER = "owner-p153"
FOREIGN = "foreign-p153"
ROAD = "/api/v1/scenarios/library/bind-plans"

CLEAN_BODY = {
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

PARTIAL_BODY = {
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
        {"name": "Keeper", "character_name": "",
         "enabled_on_start": True, "can_speak": True},
    ],
    "bootstrap_messages": [
        {"kind": "instructions", "text": "Keep the lamps lit.",
         "role": ""},
        {"kind": "note", "text": "The tide is going out.",
         "role": "Narrator"},
        {"kind": "char", "text": "You came back.", "role": "Keeper"},
        {"kind": "user", "text": "I never left.", "role": ""},
        {"kind": "story", "text": "Gulls settle on the mast.",
         "role": ""},
        {"kind": "note", "text": "   ", "role": "Narrator"},
    ],
    "initial_flags": {"met_maera": True, "bad_flag": "yes"},
    "initial_variables": {
        "trust": 2, "mood": "calm", "nested": {"x": 1},
        "bad key!": 3,
    },
}

SKIPS_ONLY_BODY = {
    "name": "Skips Only",
    "bootstrap_messages": [
        {"kind": "note", "text": "   ", "role": ""},
    ],
    "initial_flags": {"bad_flag": "yes"},
    "initial_variables": {},
}

EMPTY_BODY = {"name": "Bare"}


def _store(tmp_path):
    return ScenarioStore(tmp_path / "scenarios.json")


def _library(tmp_path):
    """Clean, partial, skips-only, then empty, store order."""
    store = _store(tmp_path)
    clean = store.create(OWNER, copy.deepcopy(CLEAN_BODY), now=NOW)
    partial = store.create(
        OWNER, copy.deepcopy(PARTIAL_BODY), now=NOW)
    skips = store.create(
        OWNER, copy.deepcopy(SKIPS_ONLY_BODY), now=NOW)
    empty = store.create(OWNER, copy.deepcopy(EMPTY_BODY), now=NOW)
    return store, clean, partial, skips, empty


def _record(definition, rid):
    return ScenarioDefinition(
        id=rid, owner_id=OWNER, name=rid, definition=definition,
        source_format="native", report={}, revision=1,
        created_at=NOW, updated_at=NOW)


# ------------------------------------------------------- service


def test_empty_library_is_the_honest_zero_census():
    out = census_bind_plans([])
    assert out["definitions"] == []
    assert out["by_where"] == []
    assert out["counts"] == {
        "definitions_total": 0,
        "definitions_clean": 0,
        "definitions_partial": 0,
        "definitions_skips_only": 0,
        "definitions_empty": 0,
        "planned_messages_total": 0,
        "planned_flags_total": 0,
        "planned_variables_total": 0,
        "planned_total": 0,
        "skipped_total": 0,
    }
    assert len(out["notes"]) == 5


def test_every_definition_rows_in_store_order(tmp_path):
    store, clean, partial, skips, empty = _library(tmp_path)
    records = store.list_for_owner(OWNER)
    out = census_bind_plans(records)
    rows = out["definitions"]
    # every definition rows - clean and empty included
    assert [r["definition"]["id"] for r in rows] == [
        clean.id, partial.id, skips.id, empty.id]
    for row, record in zip(rows, records, strict=True):
        assert row["definition"] == record.summary()
        assert row["source_format"] == record.source_format
        assert row["definition_revision"] == record.revision


def test_rows_are_p136s_own_counts_and_skips_verbatim(tmp_path):
    store, clean, partial, skips, empty = _library(tmp_path)
    records = store.list_for_owner(OWNER)
    out = census_bind_plans(records)
    for row, record in zip(out["definitions"], records, strict=True):
        envelope = preview_bind_plan(record)
        counts = envelope["counts"]
        assert row["planned_messages"] == counts["messages"]
        assert row["planned_flags"] == counts["flags"]
        assert row["planned_variables"] == counts["variables"]
        assert row["planned_total"] == (
            counts["messages"] + counts["flags"]
            + counts["variables"])
        assert row["skipped_total"] == counts["skipped"]
        assert row["skipped"] == envelope["plan"]["skipped"]
        assert row["definition_revision"] == (
            envelope["definition_revision"])


def test_plan_state_law_four_states_in_one_library(tmp_path):
    _store_obj, clean, partial, skips, empty = _library(tmp_path)
    store = _store_obj
    out = census_bind_plans(store.list_for_owner(OWNER))
    states = {
        r["definition"]["id"]: r["plan_state"]
        for r in out["definitions"]
    }
    assert states == {
        clean.id: "clean",
        partial.id: "partial",
        skips.id: "skips_only",
        empty.id: "empty",
    }
    by_id = {r["definition"]["id"]: r for r in out["definitions"]}
    assert by_id[clean.id]["planned_total"] == 3
    assert by_id[clean.id]["skipped_total"] == 0
    assert by_id[partial.id]["planned_messages"] == 5
    assert by_id[partial.id]["planned_flags"] == 1
    assert by_id[partial.id]["planned_variables"] == 2
    assert by_id[partial.id]["skipped_total"] == 4
    assert by_id[skips.id]["planned_total"] == 0
    assert by_id[skips.id]["skipped_total"] == 2
    assert by_id[empty.id]["planned_total"] == 0
    assert by_id[empty.id]["skipped_total"] == 0


def test_counts_reconcile_with_the_rows_themselves(tmp_path):
    store, clean, partial, skips, empty = _library(tmp_path)
    out = census_bind_plans(store.list_for_owner(OWNER))
    rows = out["definitions"]
    counts = out["counts"]
    assert counts["definitions_total"] == len(rows) == 4
    assert (
        counts["definitions_clean"] + counts["definitions_partial"]
        + counts["definitions_skips_only"]
        + counts["definitions_empty"]
    ) == counts["definitions_total"]
    assert counts["definitions_clean"] == 1
    assert counts["definitions_partial"] == 1
    assert counts["definitions_skips_only"] == 1
    assert counts["definitions_empty"] == 1
    for state in ("clean", "partial", "skips_only", "empty"):
        assert counts[f"definitions_{state}"] == sum(
            1 for r in rows if r["plan_state"] == state)
    assert counts["planned_messages_total"] == sum(
        r["planned_messages"] for r in rows) == 6
    assert counts["planned_flags_total"] == sum(
        r["planned_flags"] for r in rows) == 2
    assert counts["planned_variables_total"] == sum(
        r["planned_variables"] for r in rows) == 3
    assert counts["planned_total"] == sum(
        r["planned_total"] for r in rows) == 11
    assert counts["planned_total"] == (
        counts["planned_messages_total"]
        + counts["planned_flags_total"]
        + counts["planned_variables_total"])
    assert counts["skipped_total"] == sum(
        r["skipped_total"] for r in rows) == 6
    assert counts["skipped_total"] == sum(
        len(r["skipped"]) for r in rows)
    assert counts["skipped_total"] == sum(
        w["count"] for w in out["by_where"])


def test_by_where_first_appearance_order_across_rows(tmp_path):
    store, clean, partial, skips, empty = _library(tmp_path)
    out = census_bind_plans(store.list_for_owner(OWNER))
    # the clean row skips nothing; the partial row's skips
    # appear bootstrap, initial_flags, initial_variables;
    # the skips-only row adds no new where
    assert out["by_where"] == [
        {"where": "bootstrap", "count": 2},
        {"where": "initial_flags", "count": 2},
        {"where": "initial_variables", "count": 2},
    ]


def test_foreign_records_are_never_in_the_callers_census(tmp_path):
    store = _store(tmp_path)
    store.create(
        FOREIGN, copy.deepcopy(PARTIAL_BODY), now=NOW)
    store.create(OWNER, copy.deepcopy(CLEAN_BODY), now=NOW)
    out = census_bind_plans(store.list_for_owner(OWNER))
    assert out["counts"]["definitions_total"] == 1
    assert out["definitions"][0]["plan_state"] == "clean"
    foreign = census_bind_plans(store.list_for_owner(FOREIGN))
    assert foreign["counts"]["definitions_total"] == 1
    assert foreign["definitions"][0]["plan_state"] == "partial"


def test_service_is_a_pure_read_byte_untouched(tmp_path):
    store, clean, partial, skips, empty = _library(tmp_path)
    path = tmp_path / "scenarios.json"
    before = path.read_bytes()
    census_bind_plans(store.list_for_owner(OWNER))
    assert path.read_bytes() == before
    # no other store document was created by the read
    assert not (tmp_path / "scenario_bindings.json").exists()
    assert not (tmp_path / "scenario_organisation.json").exists()


def test_notes_are_five_and_in_fixed_order():
    notes = census_bind_plans([])["notes"]
    assert len(notes) == 5
    assert "written, bound, seeded and repaired nothing" in notes[0]
    assert "definition-side only" in notes[1]
    assert "no chat has been consulted" in notes[1]
    assert "seedable keys, not landed keys" in notes[2]
    assert "only account of what actually landed" in notes[2]
    assert "no message text" in notes[3]
    assert "per-definition bind-plan road" in notes[3]
    assert "current revision" in notes[4]
    assert "data, never code" in notes[4]


def test_census_carries_no_content(tmp_path):
    store, clean, partial, skips, empty = _library(tmp_path)
    out = census_bind_plans(store.list_for_owner(OWNER))
    blob = json.dumps(out)
    # no planned message text rides the census
    assert "The tide is going out." not in blob
    assert "You came back." not in blob
    assert "Keep the lamps lit." not in blob
    # no seedable key or value is named anywhere
    assert "met_maera" not in blob
    assert "trust" not in blob
    assert "calm" not in blob
    # the skipped entries ARE named - where, key, reason only
    assert "bad_flag" in blob
    assert "nested" in blob
    for row in out["definitions"]:
        assert "definition" in row and "skipped" in row
        summary = row["definition"]
        assert "bootstrap_messages" not in summary
        assert "initial_flags" not in summary
        assert "initial_variables" not in summary
        for skipped in row["skipped"]:
            assert set(skipped) == {"where", "key_or_index", "reason"}


def test_replace_moves_the_row_to_the_new_revision(tmp_path):
    store = _store(tmp_path)
    record = store.create(
        OWNER, copy.deepcopy(PARTIAL_BODY), now=NOW)
    replaced = store.replace(
        record.id, OWNER, {"name": "Bare After"}, now=LATER)
    assert replaced is not None and replaced.revision == 2
    out = census_bind_plans(store.list_for_owner(OWNER))
    row = out["definitions"][0]
    assert row["definition"]["id"] == record.id
    assert row["definition_revision"] == 2
    assert row["plan_state"] == "empty"
    assert row["planned_total"] == 0
    assert out["counts"]["definitions_empty"] == 1


def test_hand_built_records_with_degenerate_shapes():
    records = [
        _record({}, "no-fields"),
        _record(
            {"bootstrap_messages": "nope", "initial_flags": [1]},
            "wrong-shapes"),
        _record(
            {"bootstrap_messages": [
                "not-a-dict", {"text": 7},
                {"kind": "note", "text": "Real line."}]},
            "ragged-bootstrap"),
        _record(
            {"initial_variables": {"nested": {"x": 1}}},
            "unseedable-only"),
    ]
    out = census_bind_plans(records)
    states = {
        r["definition"]["id"]: r["plan_state"]
        for r in out["definitions"]
    }
    assert states == {
        "no-fields": "empty",
        "wrong-shapes": "empty",
        "ragged-bootstrap": "partial",
        "unseedable-only": "skips_only",
    }
    ragged = out["definitions"][2]
    assert ragged["planned_messages"] == 1
    assert ragged["skipped_total"] == 2
    assert [s["where"] for s in ragged["skipped"]] == [
        "bootstrap", "bootstrap"]


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
    created = client.post(
        "/api/v1/scenarios", json=copy.deepcopy(CLEAN_BODY))
    assert created.status_code == 201
    clean_id = created.json()["id"]
    created = client.post(
        "/api/v1/scenarios", json=copy.deepcopy(PARTIAL_BODY))
    assert created.status_code == 201
    partial_id = created.json()["id"]
    res = client.get(ROAD)
    assert res.status_code == 200
    out = res.json()
    assert [r["definition"]["id"] for r in out["definitions"]] == [
        clean_id, partial_id]
    assert out["counts"]["definitions_total"] == 2
    assert out["counts"]["definitions_clean"] == 1
    assert out["counts"]["definitions_partial"] == 1
    assert out["counts"]["planned_total"] == 11
    assert out["counts"]["skipped_total"] == 4


def test_http_row_agrees_with_the_p136_road(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/v1/scenarios", json=copy.deepcopy(PARTIAL_BODY))
    assert created.status_code == 201
    record_id = created.json()["id"]
    census = client.get(ROAD).json()
    row = census["definitions"][0]
    envelope = client.get(
        f"/api/v1/scenarios/{record_id}/bind-plan").json()
    assert row["planned_messages"] == envelope["counts"]["messages"]
    assert row["planned_flags"] == envelope["counts"]["flags"]
    assert row["planned_variables"] == (
        envelope["counts"]["variables"])
    assert row["skipped_total"] == envelope["counts"]["skipped"]
    assert row["skipped"] == envelope["plan"]["skipped"]
    assert row["definition_revision"] == (
        envelope["definition_revision"])


def test_http_road_not_shadowed_and_neighbours_stand(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/v1/scenarios", json=copy.deepcopy(PARTIAL_BODY))
    assert created.status_code == 201
    record = created.json()
    # the literal census road answers the census, not a record
    assert client.get(ROAD).status_code == 200
    assert client.get(ROAD).json()["counts"][
        "definitions_total"] == 1
    # the per-definition roads still answer beside it
    got = client.get(f"/api/v1/scenarios/{record['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == record["id"]
    plan = client.get(f"/api/v1/scenarios/{record['id']}/bind-plan")
    assert plan.status_code == 200
    # the neighbouring library roads still answer
    tags = client.get("/api/v1/scenarios/library/tags")
    assert tags.status_code == 200 and tags.json()["total"] == 0
    unmappable = client.get("/api/v1/scenarios/library/unmappable")
    assert unmappable.status_code == 200
    library = client.get("/api/v1/scenarios/library/census")
    assert library.status_code == 200
    assert library.json()["counts"]["definitions_total"] == 1
    # the library list still answers with its counts only
    listed = client.get("/api/v1/scenarios")
    assert listed.status_code == 200
    assert listed.json()["scenarios"][0]["bootstrap_count"] == 6


def test_http_census_leaves_store_byte_untouched(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/v1/scenarios", json=copy.deepcopy(CLEAN_BODY))
    assert created.status_code == 201
    path = definitions_path()
    before = path.read_bytes()
    assert client.get(ROAD).status_code == 200
    assert path.read_bytes() == before


def test_http_foreign_definitions_never_counted(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    store = ScenarioStore(definitions_path())
    store.create(
        FOREIGN, copy.deepcopy(PARTIAL_BODY), now=NOW)
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
