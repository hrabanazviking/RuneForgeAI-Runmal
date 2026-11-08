"""P-136 — Binding plan preview (Part IX, DERIVED scope).

Pins: the preview envelope names the record it was
computed from (id, name, CURRENT revision, source
format); the plan inside it is P-132's own
plan_materialisation over the stored definition,
verbatim (kind -> chat-role map, cast-resolved speaker
names with no fabricated ids, blank / unseedable
entries skipped with the P-093 reasons); the counts are
read from the plan itself; the four standing honesty
notes ride in fixed order (definition-side only,
bind-time refusals not judged, missing-keys-only skips
unknowable before bind, current-revision law); a
replace moves the preview to the new revision and the
new body's plan; the owner-scoped HTTP road (200
owned, 404 unknown and foreign alike); the preview
writes nothing — the definitions document is
byte-untouched and no binding is created or changed by
previewing; the P-131 / P-132 roads answer exactly as
before beside it; and the migration head pinned at
0041. No network: fixtures only.
"""

from __future__ import annotations

import copy

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.scenarios.binding import plan_materialisation
from runmal.scenarios.bindpreview import preview_bind_plan
from runmal.scenarios.store import ScenarioStore, definitions_path

NOW = "2026-11-08T13:00:00+00:00"
LATER = "2026-11-08T13:30:00+00:00"
OWNER = "owner-q36"
FOREIGN = "foreign-q36"

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
        {"name": "Keeper", "character_name": "",
         "enabled_on_start": True, "can_speak": True},
    ],
    "bootstrap_messages": [
        {"kind": "instructions", "text": "Keep the lamps lit.", "role": ""},
        {"kind": "note", "text": "The tide is going out.", "role": "Narrator"},
        {"kind": "char", "text": "You came back.", "role": "Keeper"},
        {"kind": "user", "text": "I never left.", "role": ""},
        {"kind": "story", "text": "Gulls settle on the mast.", "role": ""},
        {"kind": "note", "text": "   ", "role": "Narrator"},
    ],
    "initial_flags": {"met_maera": True, "bad_flag": "yes"},
    "initial_variables": {
        "trust": 2, "mood": "calm", "nested": {"x": 1}, "bad key!": 3,
    },
}


def body() -> dict:
    return copy.deepcopy(BODY)


def _record(tmp_path, owner=OWNER, payload=None, now=NOW):
    store = ScenarioStore(tmp_path / "scenarios.json")
    return store, store.create(owner, payload or body(), now=now)


# --------------------------------------------------------- service


def test_envelope_names_the_record_and_carries_p132s_plan(tmp_path):
    _store, rec = _record(tmp_path)
    env = preview_bind_plan(rec)
    assert env["definition_id"] == rec.id
    assert env["definition_name"] == "Harbour Lights at Dusk"
    assert env["definition_revision"] == 1
    assert env["source_format"] == rec.source_format
    assert env["plan"] == plan_materialisation(rec.definition)
    plan = env["plan"]
    assert env["counts"] == {
        "messages": len(plan["messages"]),
        "flags": len(plan["flags"]),
        "variables": len(plan["variables"]),
        "skipped": len(plan["skipped"]),
    }
    assert env["counts"] == {
        "messages": 5, "flags": 1, "variables": 2, "skipped": 4,
    }


def test_plan_content_roles_speakers_and_skips(tmp_path):
    _store, rec = _record(tmp_path)
    plan = preview_bind_plan(rec)["plan"]
    assert [(m["kind"], m["chat_role"]) for m in plan["messages"]] == [
        ("instructions", "system"), ("note", "assistant"),
        ("char", "assistant"), ("user", "user"), ("story", "assistant"),
    ]
    assert [m["speaker_name"] for m in plan["messages"]] == [
        None, "Maera", "Keeper", "Ash", "The Harbour Voice",
    ]
    assert [m["bootstrap_index"] for m in plan["messages"]] == [0, 1, 2, 3, 4]
    assert plan["flags"] == {"met_maera": True}
    assert plan["variables"] == {"trust": 2, "mood": "calm"}
    skipped = {
        (s["where"], s["key_or_index"]): s["reason"] for s in plan["skipped"]
    }
    assert "blank" in skipped[("bootstrap", 5)]
    assert "not a bool" in skipped[("initial_flags", "bad_flag")]
    assert "not a typed scalar" in skipped[("initial_variables", "nested")]
    assert "key refused" in skipped[("initial_variables", "bad key!")]


def test_notes_are_the_four_standing_bounds_in_order(tmp_path):
    _store, rec = _record(tmp_path)
    notes = preview_bind_plan(rec)["notes"]
    assert len(notes) == 4
    assert "definition-side plan" in notes[0]
    assert "nothing has been written" in notes[0]
    assert "not judged here" in notes[1]
    assert "missing-keys-only" in notes[2]
    assert "seedable keys, not landed keys" in notes[2]
    assert "current" in notes[3] and "revision" in notes[3]


def test_bare_definition_plans_nothing_but_stays_honest(tmp_path):
    _store, rec = _record(tmp_path, payload={"name": "Bare"})
    env = preview_bind_plan(rec)
    assert env["plan"] == {
        "messages": [], "flags": {}, "variables": {}, "skipped": [],
    }
    assert env["counts"] == {
        "messages": 0, "flags": 0, "variables": 0, "skipped": 0,
    }
    assert len(env["notes"]) == 4


def test_preview_follows_the_current_revision_after_replace(tmp_path):
    store, rec = _record(tmp_path)
    new_body = body()
    new_body["bootstrap_messages"] = [
        {"kind": "note", "text": "A different opening.", "role": ""},
    ]
    new_body["initial_flags"] = {}
    new_body["initial_variables"] = {}
    replaced = store.replace(rec.id, OWNER, new_body, now=LATER)
    assert replaced is not None and replaced.revision == 2
    env = preview_bind_plan(replaced)
    assert env["definition_revision"] == 2
    assert [m["text"] for m in env["plan"]["messages"]] == [
        "A different opening.",
    ]
    assert env["counts"] == {
        "messages": 1, "flags": 0, "variables": 0, "skipped": 0,
    }
    # The superseded record's preview would have planned the old body.
    assert preview_bind_plan(rec)["definition_revision"] == 1


def test_service_preview_writes_nothing(tmp_path):
    store, rec = _record(tmp_path)
    before = (tmp_path / "scenarios.json").read_bytes()
    preview_bind_plan(rec)
    preview_bind_plan(store.get(rec.id, OWNER))
    assert (tmp_path / "scenarios.json").read_bytes() == before
    assert not (tmp_path / "scenario_bindings.json").exists()
    assert store.get(rec.id, OWNER).revision == 1


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
    return client, db_path


def test_http_preview_envelope(tmp_path, monkeypatch):
    client, _db = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/scenarios", json=body()).json()
    res = client.get(f"/api/v1/scenarios/{created['id']}/bind-plan")
    assert res.status_code == 200
    env = res.json()
    assert env["definition_id"] == created["id"]
    assert env["definition_name"] == created["name"]
    assert env["definition_revision"] == created["revision"] == 1
    assert env["counts"] == {
        "messages": 5, "flags": 1, "variables": 2, "skipped": 4,
    }
    assert env["plan"]["flags"] == {"met_maera": True}
    assert len(env["notes"]) == 4


def test_http_unknown_and_foreign_answer_404_alike(tmp_path, monkeypatch):
    client, _db = make_client(tmp_path, monkeypatch)
    mine = client.post("/api/v1/scenarios", json=body()).json()
    store = ScenarioStore(definitions_path())
    store.create(FOREIGN, body(), now=NOW)
    foreign_id = store.list_for_owner(FOREIGN)[0].id
    for target in (foreign_id, "no-such-id"):
        res = client.get(f"/api/v1/scenarios/{target}/bind-plan")
        assert res.status_code == 404
        assert res.json()["detail"] == "scenario definition not found"
    assert client.get(
        f"/api/v1/scenarios/{mine['id']}/bind-plan").status_code == 200


def test_http_preview_writes_nothing_and_binds_nothing(
    tmp_path, monkeypatch
):
    client, _db = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/scenarios", json=body()).json()
    defs_file = tmp_path / "scenarios.json"
    before = defs_file.read_bytes()
    res = client.get(f"/api/v1/scenarios/{created['id']}/bind-plan")
    assert res.status_code == 200
    assert defs_file.read_bytes() == before
    assert not (tmp_path / "scenario_bindings.json").exists()
    # No binding came into being by previewing: the P-132
    # single-read road still answers 404 for any chat.
    assert client.get(
        "/api/v1/scenarios/bindings/any-chat").status_code == 404
    again = client.get(f"/api/v1/scenarios/{created['id']}").json()
    assert again["revision"] == 1


def test_http_existing_roads_untouched_beside_preview(
    tmp_path, monkeypatch
):
    client, _db = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/scenarios", json=body()).json()
    assert client.get("/api/v1/scenarios").json()["total"] == 1
    assert client.get(
        f"/api/v1/scenarios/{created['id']}").status_code == 200
    res = client.post("/api/v1/scenarios/import", json=body())
    assert res.status_code == 200
    assert res.json()["scenario"]["name"] == "Harbour Lights at Dusk"
    res = client.get(f"/api/v1/scenarios/{created['id']}/export")
    assert res.status_code == 200 and res.json()["format"] == "native"
    res = client.get(
        f"/api/v1/scenarios/{created['id']}/organisation")
    assert res.status_code == 200


def test_migration_head_stays_0041(tmp_path, monkeypatch):
    assert MIGRATIONS[-1][0] == "0041"
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
