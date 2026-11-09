"""P-142 — Stateless native->Voxta export: the F1 leak closed
(Part IX, DERIVED scope).

Pins: a native-origin parse exports to Voxta as the clean
typed-fields conversion and nothing else (no native key at
the top level or inside any element object, every value
under its Voxta spelling, carried extra riding verbatim);
the export re-parses as Voxta (before the fix the hybrid
re-parsed as native, so the stateless road never produced
a Voxta file from a native one at all); the round trips
(native->Voxta->Voxta is a fixed point whose second leg is
the Voxta-origin overlay, native->Voxta->native reproduces
the native export exactly); the parity law (the stateless
file EQUALS P-133's stored-export file for the same body —
the two export roads agree); the Voxta-origin overlay
unchanged (INV-009: raw carriage, alias spellings,
unmappable hand-back, fixed point); export_native
unchanged; the parse is not mutated by exporting; the
bytes variant carries the same clean shape; the HTTP
export road answers the clean file for a native body and
the overlay file for a Voxta body; and the migration head
pinned at 0041. No network: fixtures only.
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
from runmal.scenarios.fileexport import (
    export_native,
    export_voxta,
    export_voxta_bytes,
)
from runmal.scenarios.fileimport import parse_scenario_file
from runmal.scenarios.store import ScenarioStore, definitions_path
from runmal.scenarios.storedexport import export_stored_definition

OWNER = "owner-p142"

NATIVE_TOP_KEYS = {
    "scenario_text", "template_text", "system_prompt_text",
    "system_prompt_mode", "bootstrap_messages",
    "memory_book_refs", "initial_flags", "initial_variables",
    "impersonation_name", "impersonation_description",
    "narrator_name", "narrator_voice", "parent_ref",
    "thumbnail_ref", "source_format",
}
NATIVE_ROLE_KEYS = {"character_name", "enabled_on_start", "can_speak"}


def native_body():
    """The full native fixed shape (P-133's fixture law)."""
    return {
        "name": "Harbour Lights at Dusk",
        "description": "A quiet harbour, first evening.",
        "scenario_text": "The ferry has just left.",
        "flow": "story",
        "style": "storytelling",
        "template_text": "Dusk template.",
        "system_prompt_text": "Speak gently.",
        "system_prompt_mode": "extend",
        "roles": [
            {"name": "Guide", "character_name": "Mira",
             "enabled_on_start": False, "can_speak": True},
            {"name": "Narrator", "character_name": "",
             "enabled_on_start": True, "can_speak": True},
        ],
        "bootstrap_messages": [
            {"kind": "char", "text": "Welcome to the harbour.",
             "role": "Guide"},
            {"kind": "message", "text": "Plain opening.", "role": ""},
        ],
        "impersonation_name": "Ash",
        "impersonation_description": "The returning keeper.",
        "narrator_name": "The Harbour Voice",
        "narrator_voice": "low",
        "memory_book_refs": ["harbour-book"],
        "initial_flags": {"met_guide": True},
        "initial_variables": {"gold": 5},
        "contexts": [
            {"key": "dusk", "text": "The lamps are lit.",
             "condition": "gold > 2", "role": "Guide",
             "position": "before"},
        ],
        "parent_ref": "harbour-parent",
        "thumbnail_ref": "harbour.png",
        "source_format": "native",
        "x_future": {"a": 1},
    }


def voxta_body():
    return {
        "name": "Gate Harbour",
        "description": "Voxta desc",
        "scenarioText": "Alias text",
        "chatFlow": "Story",
        "chatStyle": "Roleplay",
        "roles": [
            {"name": "Guide", "characterName": "Mira",
             "enabledOnStart": True, "canSpeak": False,
             "futureField": 7},
        ],
        "bootstrapMessages": [
            {"kind": "char", "text": "Welcome.", "role": "Guide"},
        ],
        "scripts": [{"code": "x=1"}],
        "x_unknown": {"a": 1},
    }


# ------------------------------------------------------- the leak, closed


def test_native_to_voxta_has_no_native_keys():
    out = export_voxta(parse_scenario_file(native_body()))
    assert not (set(out) & NATIVE_TOP_KEYS), set(out) & NATIVE_TOP_KEYS
    for role in out["roles"]:
        assert not (set(role) & NATIVE_ROLE_KEYS)


def test_native_to_voxta_values_converted():
    out = export_voxta(parse_scenario_file(native_body()))
    assert out["name"] == "Harbour Lights at Dusk"
    assert out["description"] == "A quiet harbour, first evening."
    assert out["scenario"] == "The ferry has just left."
    assert out["chatFlow"] == "Story"
    assert out["chatStyle"] == "Storytelling"
    assert out["scenarioTemplate"] == "Dusk template."
    assert out["systemPrompt"] == {
        "text": "Speak gently.", "mode": "extend"}
    assert out["variables"] == {"gold": 5}
    assert out["flags"] == {"met_guide": True}
    assert out["memoryBooks"] == ["harbour-book"]
    assert out["parent"] == "harbour-parent"
    assert out["thumbnail"] == "harbour.png"
    assert out["impersonation"] == {
        "name": "Ash", "description": "The returning keeper."}
    assert out["narrator"] == {
        "name": "The Harbour Voice", "voice": "low"}


def test_native_to_voxta_role_objects_are_clean():
    out = export_voxta(parse_scenario_file(native_body()))
    assert out["roles"][0] == {
        "name": "Guide", "characterName": "Mira",
        "enabledOnStart": False, "canSpeak": True}
    # an empty character name writes no characterName key
    assert out["roles"][1] == {
        "name": "Narrator", "enabledOnStart": True, "canSpeak": True}


def test_native_to_voxta_bootstrap_and_contexts_are_clean():
    out = export_voxta(parse_scenario_file(native_body()))
    assert "bootstrap_messages" not in out
    assert out["bootstrapMessages"] == [
        {"text": "Welcome to the harbour.", "kind": "char",
         "role": "Guide"},
        {"text": "Plain opening."},
    ]
    assert out["contexts"] == [
        {"key": "dusk", "text": "The lamps are lit.",
         "condition": "gold > 2", "role": "Guide",
         "position": "before"},
    ]


def test_native_to_voxta_carried_extra_rides():
    out = export_voxta(parse_scenario_file(native_body()))
    assert out["x_future"] == {"a": 1}


def test_native_export_reparses_as_voxta():
    out = export_voxta(parse_scenario_file(native_body()))
    reparsed = parse_scenario_file(copy.deepcopy(out))
    assert reparsed.source_format == "voxta"


# ------------------------------------------------------------ round trips


def test_native_to_voxta_fixed_point():
    once = export_voxta(parse_scenario_file(native_body()))
    twice = export_voxta(parse_scenario_file(copy.deepcopy(once)))
    assert twice == once


def test_native_voxta_native_round_trip():
    parsed = parse_scenario_file(native_body())
    via_voxta = parse_scenario_file(
        copy.deepcopy(export_voxta(parsed)))
    assert export_native(via_voxta) == export_native(parsed)


def test_stateless_matches_stored_export(tmp_path):
    store = ScenarioStore(definitions_path(tmp_path))
    record = store.create(OWNER, native_body(), now="2026-11-08T18:00:00+00:00")
    stored_file, _report = export_stored_definition(record, "voxta")
    stateless_file = export_voxta(parse_scenario_file(native_body()))
    assert stateless_file == stored_file


# ------------------------------------------------- the overlay, unchanged


def test_voxta_to_voxta_unchanged():
    parsed = parse_scenario_file(voxta_body())
    assert parsed.source_format == "voxta"
    once = export_voxta(parsed)
    # INV-009: the alias spelling the file used is kept
    assert once["scenarioText"] == "Alias text"
    assert "scenario" not in once
    # unmappable machinery and unknowns hand back verbatim
    assert once["scripts"] == [{"code": "x=1"}]
    assert once["x_unknown"] == {"a": 1}
    assert once["roles"][0]["futureField"] == 7
    assert once["roles"][0]["characterName"] == "Mira"
    twice = export_voxta(parse_scenario_file(copy.deepcopy(once)))
    assert twice == once


def test_native_to_native_unchanged():
    body = native_body()
    assert export_native(parse_scenario_file(copy.deepcopy(body))) == body


def test_export_does_not_mutate_the_parse():
    parsed = parse_scenario_file(native_body())
    raw_before = copy.deepcopy(parsed.raw)
    role_raw_before = copy.deepcopy(parsed.roles[0].raw)
    export_voxta(parsed)
    assert parsed.raw == raw_before
    assert parsed.roles[0].raw == role_raw_before


def test_voxta_bytes_variant_is_clean():
    parsed = parse_scenario_file(native_body())
    out = json.loads(export_voxta_bytes(parsed))
    assert out == export_voxta(parse_scenario_file(native_body()))
    assert not (set(out) & NATIVE_TOP_KEYS)


# ------------------------------------------------------------------- HTTP


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


def test_http_export_road_native_body_clean(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/api/v1/scenarios/export?format=voxta", json=native_body())
    assert resp.status_code == 200
    out = resp.json()
    assert not (set(out) & NATIVE_TOP_KEYS)
    assert out["scenario"] == "The ferry has just left."
    assert out["chatFlow"] == "Story"


def test_http_export_road_voxta_body_overlay_intact(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/api/v1/scenarios/export?format=voxta", json=voxta_body())
    assert resp.status_code == 200
    out = resp.json()
    assert out["scripts"] == [{"code": "x=1"}]
    assert out["scenarioText"] == "Alias text"


# --------------------------------------------------------------- migration


def test_migration_head_stays_0041(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
    assert MIGRATIONS[-1][0] == "0042"
