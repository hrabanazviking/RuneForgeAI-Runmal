"""P-139 - Definition delete-impact preview (Part IX, DERIVED).

Pins: the envelope (the P-136 identity four; P-135's own
binding summaries verbatim, definition_exists still true;
P-134's own organisation view verbatim, plus the one fact
no view can state - whether a persisted organisation row
exists at all); impact counts read from those answers;
the five standing honesty notes, in order; the contrast
after a real deletion (the promised staleness, named by
the standing P-135 surface); writes-nothing at service
and HTTP level (no document created or changed, the
definition still readable and still deletable, seeded
chat content untouched); and the HTTP road (200 envelope,
404 unknown and foreign alike, 404 after a real delete
while the whole-set bindings list names the stale
binding, the P-131 / P-135 / P-136 / P-137 roads
untouched beside it); and the migration head pinned at
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
from runmal.scenarios.binding import (
    ScenarioBinding,
    ScenarioBindingStore,
    list_bindings,
    list_bindings_for_definition,
)
from runmal.scenarios.deletepreview import preview_delete_impact
from runmal.scenarios.organisation import (
    ScenarioOrganisationStore,
    organisation_view,
)
from runmal.scenarios.store import ScenarioStore, definitions_path

NOW = "2026-11-08T16:00:00+00:00"
OWNER = "owner-p139"
FOREIGN = "foreign-p139"

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


def test_service_bare_definition_is_the_honest_zero(tmp_path):
    definitions, bindings, organisation = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    out = preview_delete_impact(
        record, bindings, organisation, {record.id})
    assert out["definition_id"] == record.id
    assert out["definition_name"] == "Harbour Lights at Dusk"
    assert out["definition_revision"] == 1
    assert out["source_format"] == record.source_format
    assert out["bindings"] == []
    assert out["organisation"] == {
        "definition_id": record.id,
        "name": "Harbour Lights at Dusk",
        "tags": [],
        "is_favourite": False,
    }
    assert out["organisation_row_exists"] is False
    assert out["impact"] == {
        "bindings_orphaned": 0,
        "organisation_row_orphaned": False,
        "chats_affected": 0,
    }


def test_service_notes_are_the_five_in_order(tmp_path):
    definitions, bindings, organisation = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    notes = preview_delete_impact(
        record, bindings, organisation, {record.id})["notes"]
    assert len(notes) == 5
    assert "preview is a read of the world as it stands" in notes[0]
    assert "does not cascade into the binding store" in notes[1]
    assert "definition_exists false" in notes[1]
    assert "does not cascade into the organisation store" in notes[2]
    assert "chat's own truth" in notes[3]
    assert "deletion is permanent" in notes[4]
    assert "stored-export road" in notes[4]


def test_service_bound_and_organised(tmp_path):
    definitions, bindings, organisation = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    other = definitions.create(OWNER, body("Mountain Gate"), now=NOW)
    bindings.add(_rec("b1", OWNER, "c1", record.id))
    bindings.add(_rec("b2", OWNER, "c2", record.id))
    bindings.add(_rec("b3", OWNER, "c3", other.id, name="Gate"))
    bindings.add(_rec("b4", FOREIGN, "c4", record.id))
    organisation.set_tags(record.id, OWNER, ["Harbour", "dusk"], now=NOW)
    organisation.set_favourite(record.id, OWNER, True, now=NOW)
    live = {record.id, other.id}
    out = preview_delete_impact(record, bindings, organisation, live)
    expected = list_bindings_for_definition(
        bindings, OWNER, record.id, live)
    assert out["bindings"] == expected
    assert [row["id"] for row in out["bindings"]] == ["b1", "b2"]
    assert all(row["definition_exists"] is True for row in out["bindings"])
    assert "seeded_messages" not in out["bindings"][0]
    row = organisation.get(record.id, OWNER)
    assert out["organisation"] == organisation_view(record, row)
    assert out["organisation"]["tags"] == ["Harbour", "dusk"]
    assert out["organisation"]["is_favourite"] is True
    assert out["organisation_row_exists"] is True
    assert out["impact"] == {
        "bindings_orphaned": 2,
        "organisation_row_orphaned": True,
        "chats_affected": 2,
    }


def test_service_contrast_after_real_delete(tmp_path):
    definitions, bindings, organisation = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    bindings.add(_rec("b1", OWNER, "c1", record.id))
    out = preview_delete_impact(
        record, bindings, organisation, {record.id})
    assert out["bindings"][0]["definition_exists"] is True
    removed = definitions.remove(record.id, OWNER)
    assert removed is not None
    stale = list_bindings(bindings, OWNER, set())
    assert stale[0]["definition_exists"] is False
    assert stale[0]["definition_id"] == record.id


def test_service_writes_nothing_and_creates_no_documents(tmp_path):
    definitions, bindings, organisation = _stores(tmp_path)
    record = definitions.create(OWNER, body(), now=NOW)
    before = (tmp_path / "scenarios.json").read_bytes()
    out = preview_delete_impact(
        record, bindings, organisation, {record.id})
    assert out["impact"]["bindings_orphaned"] == 0
    assert (tmp_path / "scenarios.json").read_bytes() == before
    assert not (tmp_path / "scenario_bindings.json").exists()
    assert not (tmp_path / "scenario_organisation.json").exists()
    assert definitions.get(record.id, OWNER) is not None
    assert definitions.remove(record.id, OWNER) is not None


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


def _bound(client, name=None):
    definition = client.post("/api/v1/scenarios", json=body(name)).json()
    chat = client.post("/api/v1/chats", json={"title": "Harbour"}).json()
    res = client.post(
        f"/api/v1/scenarios/{definition['id']}/bind",
        json={"chat_id": chat["id"]})
    assert res.status_code == 201
    return definition, chat


def test_http_envelope_for_bound_tagged_definition(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition, chat = _bound(client)
    res = client.put(
        f"/api/v1/scenarios/{definition['id']}/tags",
        json={"tags": ["harbour"]})
    assert res.status_code == 200
    res = client.get(f"/api/v1/scenarios/{definition['id']}/delete-impact")
    assert res.status_code == 200
    out = res.json()
    assert out["definition_id"] == definition["id"]
    assert out["definition_revision"] == 1
    assert out["impact"] == {
        "bindings_orphaned": 1,
        "organisation_row_orphaned": True,
        "chats_affected": 1,
    }
    assert out["bindings"][0]["chat_id"] == chat["id"]
    assert out["bindings"][0]["definition_exists"] is True
    assert out["organisation"]["tags"] == ["harbour"]
    assert out["organisation_row_exists"] is True
    assert len(out["notes"]) == 5


def test_http_bare_definition_honest_zero(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition = client.post("/api/v1/scenarios", json=body()).json()
    res = client.get(f"/api/v1/scenarios/{definition['id']}/delete-impact")
    assert res.status_code == 200
    out = res.json()
    assert out["bindings"] == []
    assert out["organisation_row_exists"] is False
    assert out["impact"]["bindings_orphaned"] == 0


def test_http_unknown_and_foreign_answer_404_alike(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    store = ScenarioStore(definitions_path())
    foreign = store.create(FOREIGN, body(), now=NOW)
    for target in (foreign.id, "no-such-id"):
        res = client.get(f"/api/v1/scenarios/{target}/delete-impact")
        assert res.status_code == 404
        assert res.json()["detail"] == "scenario definition not found"
    assert store.list_for_owner(FOREIGN) == [foreign]


def test_http_preview_consumes_nothing_then_delete_lands(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition, chat = _bound(client)
    url = f"/api/v1/scenarios/{definition['id']}/delete-impact"
    assert client.get(url).status_code == 200
    # the definition is still there, the binding still live,
    # and the chat keeps its seeded opening (2 messages)
    assert client.get(
        f"/api/v1/scenarios/{definition['id']}").status_code == 200
    listing = client.get("/api/v1/scenarios/bindings").json()
    assert listing["total"] == 1
    assert listing["bindings"][0]["definition_exists"] is True
    history = client.get(f"/api/v1/chats/{chat['id']}/messages")
    assert history.status_code == 200
    assert len(history.json()) == 2
    # the real delete still lands, and afterwards the
    # preview road 404s while the binding reads stale
    assert client.delete(
        f"/api/v1/scenarios/{definition['id']}").status_code == 200
    assert client.get(url).status_code == 404
    listing = client.get("/api/v1/scenarios/bindings").json()
    assert listing["total"] == 1
    assert listing["bindings"][0]["definition_exists"] is False


def test_http_neighbour_roads_untouched_beside_it(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition, _chat = _bound(client)
    base = f"/api/v1/scenarios/{definition['id']}"
    assert client.get(f"{base}/bind-plan").status_code == 200
    assert client.get(f"{base}/bindings").status_code == 200
    assert client.get(f"{base}/organisation").status_code == 200
    assert client.get(f"{base}/export").status_code == 200
    dup = client.post(f"{base}/duplicate")
    assert dup.status_code == 201
    assert client.get(f"{base}/delete-impact").status_code == 200
    assert client.get(
        f"/api/v1/scenarios/{dup.json()['id']}/delete-impact"
    ).status_code == 200


# ----------------------------------------------------- migration


def test_migration_head_stays_0041(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
    assert MIGRATIONS[-1][0] == "0041"
