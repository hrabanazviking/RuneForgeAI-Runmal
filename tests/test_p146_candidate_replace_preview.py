"""P-146 - Candidate replace preview (Part IX, DERIVED).

Pins: the candidate judged through the store door's own
parser exactly as replace would store it (the would-be
native shape and import report are exactly what a real
replace with the same body then persists, at the
previewed next revision, and the replaced record's
bind-plan is the previewed candidate plan); the envelope
(the P-136 identity four plus next_revision; the current
side - P-131 summary verbatim, P-132 plan, P-136 counts;
the candidate side - shape, report, P-131-law counts,
plan and counts; the comparison read from those answers:
change flags, identical_body, count triples, seedable-key
added / removed; P-140's impact envelope whole and
verbatim); a refused candidate raising the door's own
typed refusals before any envelope; the six standing
honesty notes, in order; writes-nothing at service and
HTTP level (no document created or changed, the stored
record untouched, seeded chat content intact, a real
replace still landing afterwards); the HTTP road (200
envelope, 404 unknown and foreign alike EVEN with a
malformed candidate - existence before body, 422 refused
candidate on an owned definition, neighbour roads
untouched beside it); and the migration head pinned at
0041. No network: fixtures only.
"""

from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.scenarios.binding import ScenarioBinding, ScenarioBindingStore
from runmal.scenarios.bindpreview import preview_bind_plan
from runmal.scenarios.candidatepreview import preview_candidate_replace
from runmal.scenarios.filemodels import ScenarioParseError
from runmal.scenarios.organisation import ScenarioOrganisationStore
from runmal.scenarios.replacepreview import preview_replace_impact
from runmal.scenarios.store import (
    ScenarioStore,
    ScenarioStoreError,
    definitions_path,
)

NOW = "2026-11-08T19:00:00+00:00"
OWNER = "owner-p146"
FOREIGN = "foreign-p146"

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


def body(name=None) -> dict:
    out = copy.deepcopy(BODY)
    if name:
        out["name"] = name
    return out


def changed_body() -> dict:
    out = body("Harbour Lights at Dawn")
    out["scenario_text"] = "The ferry has returned."
    out["bootstrap_messages"] = [
        {"kind": "note", "text": "The tide is coming in.", "role": "Narrator"},
        {"kind": "user", "text": "I stayed.", "role": ""},
        {"kind": "note", "text": "Gulls over the harbour.", "role": "Narrator"},
    ]
    out["initial_flags"] = {"met_ferryman": True}
    out["initial_variables"] = {"trust": 3, "tide": "in"}
    return out


def _rec(bid, owner, chat, definition, name="Harbour", rev=1):
    return ScenarioBinding(
        id=bid, owner_id=owner, chat_id=chat, definition_id=definition,
        definition_name=name, definition_revision=rev, bound_at=NOW,
        cast=[{"name": "Narrator"}],
        seeded_messages=[{"message_id": "m1"}],
        seeded_keys=["shared:trust"],
        skipped=[],
    )


def _stores(tmp_path):
    definitions = ScenarioStore(tmp_path / "scenarios.json")
    bindings = ScenarioBindingStore(tmp_path / "scenario_bindings.json")
    organisation = ScenarioOrganisationStore(
        tmp_path / "scenario_organisation.json")
    return definitions, bindings, organisation


# ------------------------------------------------------- service


def test_service_identical_candidate_is_the_honest_mirror(tmp_path):
    definitions, bindings, organisation = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    out = preview_candidate_replace(
        record, bindings, organisation, {record.id}, body())
    assert out["definition_id"] == record.id
    assert out["definition_name"] == "Harbour Lights at Dusk"
    assert out["definition_revision"] == 1
    assert out["next_revision"] == 2
    assert out["source_format"] == record.source_format
    assert out["current"]["summary"] == record.summary()
    assert out["candidate"]["name"] == "Harbour Lights at Dusk"
    assert out["candidate"]["definition"] == record.definition
    assert out["candidate"]["report"] == record.report
    assert out["candidate"]["counts"] == {
        "role_count": 1, "bootstrap_count": 2, "has_unmappable": False,
    }
    assert out["candidate"]["plan"] == out["current"]["plan"]
    assert out["candidate"]["plan_counts"] == {
        "messages": 2, "flags": 1, "variables": 1, "skipped": 0,
    }
    assert out["current"]["counts"] == out["candidate"]["plan_counts"]
    comp = out["comparison"]
    assert comp["name_changed"] is False
    assert comp["source_format_changed"] is False
    assert comp["identical_body"] is True
    for key in ("roles", "bootstrap_messages", "plan_messages",
                "plan_flags", "plan_variables", "plan_skipped"):
        assert comp[key]["delta"] == 0, key
        assert comp[key]["current"] == comp[key]["candidate"], key
    assert comp["flag_keys_added"] == []
    assert comp["flag_keys_removed"] == []
    assert comp["variable_keys_added"] == []
    assert comp["variable_keys_removed"] == []


def test_service_notes_are_the_six_in_order(tmp_path):
    definitions, bindings, organisation = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    notes = preview_candidate_replace(
        record, bindings, organisation, {record.id}, body())["notes"]
    assert len(notes) == 6
    assert "pure read" in notes[0]
    assert "only replacer" in notes[0]
    assert "store door's own parser" in notes[1]
    assert "next revision" in notes[1]
    assert "definition-side only" in notes[2]
    assert "seedable keys, not landed keys" in notes[2]
    assert "P-140 envelope" in notes[3]
    assert "changes none of its facts" in notes[3]
    assert "unmappable raw values are not part" in notes[4]
    assert "parsed and planned as data" in notes[5]


def test_service_changed_candidate_comparison_is_exact(tmp_path):
    definitions, bindings, organisation = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    out = preview_candidate_replace(
        record, bindings, organisation, {record.id}, changed_body())
    assert out["candidate"]["name"] == "Harbour Lights at Dawn"
    assert (out["candidate"]["definition"]["scenario_text"]
            == "The ferry has returned.")
    assert out["candidate"]["counts"] == {
        "role_count": 1, "bootstrap_count": 3, "has_unmappable": False,
    }
    assert out["candidate"]["plan_counts"] == {
        "messages": 3, "flags": 1, "variables": 2, "skipped": 0,
    }
    comp = out["comparison"]
    assert comp["name_changed"] is True
    assert comp["source_format_changed"] is False
    assert comp["identical_body"] is False
    assert comp["roles"] == {"current": 1, "candidate": 1, "delta": 0}
    assert comp["bootstrap_messages"] == {
        "current": 2, "candidate": 3, "delta": 1}
    assert comp["plan_messages"] == {
        "current": 2, "candidate": 3, "delta": 1}
    assert comp["plan_flags"] == {"current": 1, "candidate": 1, "delta": 0}
    assert comp["plan_variables"] == {
        "current": 1, "candidate": 2, "delta": 1}
    assert comp["plan_skipped"] == {
        "current": 0, "candidate": 0, "delta": 0}
    assert comp["flag_keys_added"] == ["met_ferryman"]
    assert comp["flag_keys_removed"] == ["met_maera"]
    assert comp["variable_keys_added"] == ["tide"]
    assert comp["variable_keys_removed"] == []
    # the candidate plan is the changed body's own plan
    texts = [m["text"] for m in out["candidate"]["plan"]["messages"]]
    assert texts[0] == "The tide is coming in."
    assert out["candidate"]["plan"]["variables"] == {
        "trust": 3, "tide": "in"}


def test_service_unmappable_candidate_is_named_not_stored(tmp_path):
    definitions, bindings, organisation = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    # a Voxta-shaped candidate: P-026 reports the scripts
    # machinery unmappable (its own battery's law)
    candidate = {
        "name": "Harbour Lights at Dusk",
        "bootstrapMessages": [{"text": "The tide is going out."}],
        "scripts": [{"opaque": [1, 2, {"deep": True}]}],
    }
    out = preview_candidate_replace(
        record, bindings, organisation, {record.id}, candidate)
    report = out["candidate"]["report"]
    assert report["unmappable"][0]["path"] == "scripts"
    assert report["unmappable"][0]["kind"] == "scripting"
    assert out["candidate"]["counts"]["has_unmappable"] is True
    # the raw machinery is not part of the would-be shape
    assert "scripts" not in out["candidate"]["definition"]
    assert out["comparison"]["identical_body"] is False


def test_service_voxta_candidate_names_the_format_change(tmp_path):
    definitions, bindings, organisation = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    assert record.source_format == "native"
    candidate = {
        "name": "Harbour Lights at Dusk",
        "bootstrapMessages": [{"text": "The tide is going out."}],
    }
    out = preview_candidate_replace(
        record, bindings, organisation, {record.id}, candidate)
    assert out["candidate"]["source_format"] == "voxta"
    assert out["comparison"]["source_format_changed"] is True
    assert out["comparison"]["name_changed"] is False
    assert out["comparison"]["identical_body"] is False


def test_service_refused_candidates_raise_the_doors_own_refusals(tmp_path):
    definitions, bindings, organisation = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    before = (tmp_path / "scenarios.json").read_bytes()
    with pytest.raises(ScenarioParseError):
        preview_candidate_replace(
            record, bindings, organisation, {record.id},
            {"description": "no name"})
    with pytest.raises(ScenarioStoreError):
        preview_candidate_replace(
            record, bindings, organisation, {record.id},
            ["not", "a", "dict"])
    bad_roles = body()
    bad_roles["roles"] = "oops"
    with pytest.raises(ScenarioParseError):
        preview_candidate_replace(
            record, bindings, organisation, {record.id}, bad_roles)
    assert (tmp_path / "scenarios.json").read_bytes() == before
    assert definitions.get(record.id, OWNER).revision == 1


def test_service_impact_section_is_p140s_envelope_verbatim(tmp_path):
    definitions, bindings, organisation = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    bindings.add(_rec("b1", OWNER, "c1", record.id, rev=1))
    organisation.set_tags(record.id, OWNER, ["Harbour"], now=NOW)
    live = {record.id}
    out = preview_candidate_replace(
        record, bindings, organisation, live, changed_body())
    assert out["replace_impact"] == preview_replace_impact(
        record, bindings, organisation, live)
    assert out["replace_impact"]["impact"]["bindings_total"] == 1
    assert out["replace_impact"]["next_revision"] == 2


def test_service_writes_nothing_and_creates_no_documents(tmp_path):
    definitions, bindings, organisation = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    before = (tmp_path / "scenarios.json").read_bytes()
    out = preview_candidate_replace(
        record, bindings, organisation, {record.id}, changed_body())
    assert out["candidate"]["name"] == "Harbour Lights at Dawn"
    assert (tmp_path / "scenarios.json").read_bytes() == before
    assert not (tmp_path / "scenario_bindings.json").exists()
    assert not (tmp_path / "scenario_organisation.json").exists()
    stored = definitions.get(record.id, OWNER)
    assert stored.name == "Harbour Lights at Dusk"
    assert stored.revision == 1


def test_service_previewed_candidate_then_replaced_lands_exactly(tmp_path):
    definitions, bindings, organisation = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    candidate = changed_body()
    out = preview_candidate_replace(
        record, bindings, organisation, {record.id}, candidate)
    replaced = definitions.replace(record.id, OWNER, candidate, now=NOW)
    assert replaced is not None
    assert replaced.revision == out["next_revision"] == 2
    assert replaced.name == out["candidate"]["name"]
    assert replaced.definition == out["candidate"]["definition"]
    assert replaced.report == out["candidate"]["report"]
    assert replaced.source_format == out["candidate"]["source_format"]
    # and what it would plant is what the new body plans
    assert preview_bind_plan(replaced)["plan"] == out["candidate"]["plan"]


# --------------------------------------------------------- HTTP


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _create(client):
    res = client.post("/api/v1/scenarios", json=body())
    assert res.status_code == 201
    return res.json()


def _bind(client, definition_id):
    chat = client.post("/api/v1/chats", json={"title": "Harbour"}).json()
    res = client.post(
        f"/api/v1/scenarios/{definition_id}/bind",
        json={"chat_id": chat["id"]})
    assert res.status_code == 201
    return chat


def test_http_envelope_and_the_replace_that_follows_it(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    _bind(client, definition["id"])
    url = f"/api/v1/scenarios/{definition['id']}/replace-preview"
    res = client.post(url, json=changed_body())
    assert res.status_code == 200
    out = res.json()
    assert out["definition_id"] == definition["id"]
    assert out["definition_revision"] == 1
    assert out["next_revision"] == 2
    assert out["candidate"]["name"] == "Harbour Lights at Dawn"
    assert out["comparison"]["flag_keys_added"] == ["met_ferryman"]
    assert out["replace_impact"]["impact"]["bindings_total"] == 1
    assert len(out["notes"]) == 6
    # the real replace with the same body lands exactly
    # what the preview named
    res = client.put(
        f"/api/v1/scenarios/{definition['id']}", json=changed_body())
    assert res.status_code == 200
    landed = res.json()
    assert landed["revision"] == out["next_revision"]
    assert landed["name"] == out["candidate"]["name"]
    assert landed["definition"] == out["candidate"]["definition"]
    assert landed["report"] == out["candidate"]["report"]


def test_http_unknown_and_foreign_404_even_with_malformed_body(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    store = ScenarioStore(definitions_path())
    foreign = store.create(FOREIGN, body(), now=NOW)
    for target in (foreign.id, "no-such-id"):
        res = client.post(
            f"/api/v1/scenarios/{target}/replace-preview",
            json={"description": "no name"})
        assert res.status_code == 404
        assert res.json()["detail"] == "scenario definition not found"
    assert store.list_for_owner(FOREIGN) == [foreign]


def test_http_refused_candidate_422_and_record_untouched(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    url = f"/api/v1/scenarios/{definition['id']}/replace-preview"
    res = client.post(url, json={"description": "no name"})
    assert res.status_code == 422
    got = client.get(f"/api/v1/scenarios/{definition['id']}")
    assert got.status_code == 200
    assert got.json()["revision"] == 1
    assert got.json()["name"] == "Harbour Lights at Dusk"


def test_http_preview_consumes_nothing_then_replace_lands(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    chat = _bind(client, definition["id"])
    url = f"/api/v1/scenarios/{definition['id']}/replace-preview"
    assert client.post(url, json=changed_body()).status_code == 200
    got = client.get(f"/api/v1/scenarios/{definition['id']}")
    assert got.json()["revision"] == 1
    assert got.json()["name"] == "Harbour Lights at Dusk"
    listing = client.get("/api/v1/scenarios/bindings").json()
    assert listing["total"] == 1
    history = client.get(f"/api/v1/chats/{chat['id']}/messages")
    assert history.status_code == 200
    assert len(history.json()) == 2
    res = client.put(
        f"/api/v1/scenarios/{definition['id']}", json=changed_body())
    assert res.status_code == 200
    assert res.json()["revision"] == 2


def test_http_neighbour_roads_untouched_beside_it(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = _create(client)
    chat = _bind(client, definition["id"])
    base = f"/api/v1/scenarios/{definition['id']}"
    assert client.get(f"{base}/bind-plan").status_code == 200
    assert client.get(f"{base}/bind-plan/{chat['id']}").status_code == 200
    assert client.get(f"{base}/replace-impact").status_code == 200
    assert client.get(f"{base}/bindings").status_code == 200
    assert client.get(f"{base}/export").status_code == 200
    assert client.post(f"{base}/replace-preview",
                       json=body()).status_code == 200
    dup = client.post(f"{base}/duplicate")
    assert dup.status_code == 201
    assert client.post(
        f"/api/v1/scenarios/{dup.json()['id']}/replace-preview",
        json=body()).status_code == 200


# ----------------------------------------------------- migration


def test_migration_head_stays_0041(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
    assert MIGRATIONS[-1][0] == "0041"
