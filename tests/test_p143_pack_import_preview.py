"""P-143 — Library-scoped pack import preview (Part IX, DERIVED).

Pins: the preview as P-141's own judgement read not run
(validation through inspect_pack verbatim — its report
rides in the envelope whole; the mode validated first
with import's own refusal, exactly import's order; a
malformed or tampered pack refuses as PackError before
any library fact is read); the library scan in import's
own law (the owner's records only — a foreign identical
record is never this owner's duplicate; identity by
content checksum over the stored definition; collision
by name against the manifest); the envelope (the inspect
fields verbatim at the top level, on_conflict, the
library section with the duplicate named by P-131's
summary verbatim and every non-duplicate same-name
record summarised in store order, exactly one outcome in
import's own decision order — duplicate first, then
collision plus the reject refusal, then create — the
would_create / would_refuse bools read from it, import's
own refusal sentence verbatim, and the four standing
honesty notes in fixed order); the pure read (the store
document byte-untouched at service level and over HTTP,
and no store document created where none stood); the
HTTP road (200 fresh / duplicate / collision, with a
reject-mode would_refuse answered as DATA at 200 while
malformed packs and unknown modes answer 422; the
literal road never shadowed by {definition_id}; the
neighbour roads untouched beside it); and the migration
head pinned at 0041. No network: fixtures only.
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
from runmal.scenarios.packpreview import preview_pack_import
from runmal.scenarios.packs import PackError, build_pack, inspect_pack
from runmal.scenarios.store import ScenarioStore, definitions_path

NOW = "2026-11-08T18:00:00+00:00"
OWNER = "owner-p143"
FOREIGN = "foreign-p143"
NAME = "Harbour Lights at Dusk"
REFUSAL = (
    "a scenario definition named 'Harbour Lights at Dusk' "
    "already exists with different contents and "
    "on_conflict='reject'"
)

BODY = {
    "name": NAME,
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
        {"kind": "note", "text": "The tide is going out.",
         "role": "Narrator"},
        {"kind": "user", "text": "I never left.", "role": ""},
    ],
    "initial_flags": {"met_maera": True},
    "initial_variables": {"trust": 2},
}

INSPECT_KEYS = {
    "schema", "valid", "format", "pack_version", "kind",
    "definition_name", "role_count", "bootstrap_count",
    "content_sha256", "checksum_verified", "manifest",
    "provenance",
}


def body(name=None, text=None) -> dict:
    out = copy.deepcopy(BODY)
    if name:
        out["name"] = name
    if text:
        out["scenario_text"] = text
    return out


def _store(tmp_path, name="scenarios.json"):
    return ScenarioStore(tmp_path / name)


def _packed(tmp_path, owner=OWNER, data=None, store_name="source.json"):
    store = _store(tmp_path, store_name)
    record = store.create(owner, data if data is not None else body(), now=NOW)
    return build_pack(record, exported_at=NOW)


class _ExplodingStore:
    """A store that must never be read: pins refusal order."""

    def list_for_owner(self, owner_id):
        raise AssertionError("library read before pack validation")


# ------------------------------------------------------- service


def test_fresh_library_would_create_and_envelope_shape(tmp_path):
    pack = _packed(tmp_path)
    target = _store(tmp_path, "target.json")
    out = preview_pack_import(target, OWNER, pack)
    # the inspect report rides verbatim at the top level
    inspected = inspect_pack(pack)
    for key in INSPECT_KEYS:
        assert out[key] == inspected[key]
    assert set(out) == INSPECT_KEYS | {
        "on_conflict", "library", "outcome", "would_create",
        "would_refuse", "refusal_reason", "notes",
    }
    assert out["on_conflict"] == "create_new"
    assert out["outcome"] == "would_create"
    assert out["would_create"] is True
    assert out["would_refuse"] is False
    assert out["refusal_reason"] is None
    assert out["library"] == {
        "definitions_total": 0,
        "duplicate_exact": False,
        "duplicate_of": None,
        "name_collision": False,
        "name_collisions": [],
    }
    # a pure read creates no store document where none stood
    assert not (tmp_path / "target.json").exists()


def test_exact_duplicate_named_and_store_byte_untouched(tmp_path):
    store = _store(tmp_path)
    record = store.create(OWNER, body(), now=NOW)
    pack = build_pack(record, exported_at=NOW)
    before = (tmp_path / "scenarios.json").read_bytes()
    out = preview_pack_import(store, OWNER, pack)
    assert out["outcome"] == "duplicate_exact"
    assert out["would_create"] is False
    assert out["would_refuse"] is False
    assert out["refusal_reason"] is None
    library = out["library"]
    assert library["definitions_total"] == 1
    assert library["duplicate_exact"] is True
    # the duplicate is named by P-131's summary, verbatim
    assert library["duplicate_of"] == record.summary()
    # the duplicate itself is not also listed as a collision
    assert library["name_collision"] is False
    assert library["name_collisions"] == []
    assert (tmp_path / "scenarios.json").read_bytes() == before
    assert store.list_for_owner(OWNER) == [record]


def test_owner_scoping_foreign_identical_is_not_a_duplicate(tmp_path):
    store = _store(tmp_path)
    foreign = store.create(FOREIGN, body(), now=NOW)
    pack = build_pack(foreign, exported_at=NOW)
    out = preview_pack_import(store, OWNER, pack)
    assert out["outcome"] == "would_create"
    assert out["library"]["definitions_total"] == 0
    assert out["library"]["duplicate_exact"] is False
    assert out["library"]["duplicate_of"] is None
    # and the foreign owner, previewing the same pack, DOES
    # hold the duplicate — the scan is the caller's library
    own = preview_pack_import(store, FOREIGN, pack)
    assert own["outcome"] == "duplicate_exact"
    assert own["library"]["duplicate_of"]["id"] == foreign.id


def test_name_collision_under_both_modes(tmp_path):
    store = _store(tmp_path)
    existing = store.create(OWNER, body(), now=NOW)
    pack = _packed(tmp_path, owner=FOREIGN,
                   data=body(text="Different contents entirely."))
    before = (tmp_path / "scenarios.json").read_bytes()
    out = preview_pack_import(store, OWNER, pack)
    assert out["outcome"] == "would_create_with_name_collision"
    assert out["would_create"] is True
    assert out["would_refuse"] is False
    assert out["refusal_reason"] is None
    assert out["library"]["name_collision"] is True
    assert out["library"]["name_collisions"] == [existing.summary()]
    assert out["library"]["duplicate_exact"] is False
    refused = preview_pack_import(store, OWNER, pack, on_conflict="reject")
    assert refused["on_conflict"] == "reject"
    assert refused["outcome"] == "would_refuse"
    assert refused["would_create"] is False
    assert refused["would_refuse"] is True
    # import's own refusal sentence, verbatim
    assert refused["refusal_reason"] == REFUSAL
    assert refused["library"]["name_collisions"] == [existing.summary()]
    assert (tmp_path / "scenarios.json").read_bytes() == before


def test_duplicate_beats_collision_when_both_exist(tmp_path):
    store = _store(tmp_path)
    dupe = store.create(OWNER, body(), now=NOW)
    other = store.create(OWNER, body(text="Same name, other words."),
                         now=NOW)
    pack = build_pack(dupe, exported_at=NOW)
    # even under reject, an exact duplicate is import's first
    # verdict — nothing would be created, so nothing is refused
    out = preview_pack_import(store, OWNER, pack, on_conflict="reject")
    assert out["outcome"] == "duplicate_exact"
    assert out["library"]["duplicate_of"] == dupe.summary()
    # the other same-name record is still named as a collision
    assert out["library"]["name_collision"] is True
    assert out["library"]["name_collisions"] == [other.summary()]
    assert out["library"]["definitions_total"] == 2


def test_unknown_mode_refuses_with_imports_message_before_parsing(tmp_path):
    pack = _packed(tmp_path)
    target = _store(tmp_path, "target.json")
    with pytest.raises(PackError, match="unknown on_conflict mode"):
        preview_pack_import(target, OWNER, pack, on_conflict="merge")
    # the mode is judged before the pack is even parsed
    # (import's order): a malformed pack under a bad mode
    # still answers the mode refusal
    with pytest.raises(PackError, match="unknown on_conflict mode"):
        preview_pack_import(target, OWNER, {"format": "nope"},
                            on_conflict="merge")
    assert target.list_for_owner(OWNER) == []


def test_malformed_and_tampered_packs_refuse_before_any_read(tmp_path):
    pack = _packed(tmp_path)
    tampered = copy.deepcopy(pack)
    tampered["scenario"]["scenario_text"] = "Altered in transit."
    with pytest.raises(PackError, match="checksum mismatch"):
        preview_pack_import(_ExplodingStore(), OWNER, tampered)
    with pytest.raises(PackError):
        preview_pack_import(_ExplodingStore(), OWNER, {"format": "nope"})
    with pytest.raises(PackError):
        preview_pack_import(_ExplodingStore(), OWNER, {})


def test_notes_are_the_four_standing_notes_in_order(tmp_path):
    pack = _packed(tmp_path)
    out = preview_pack_import(_store(tmp_path, "t.json"), OWNER, pack)
    notes = out["notes"]
    assert len(notes) == 4
    assert "imported, written and created nothing" in notes[0]
    assert "only importer" in notes[0]
    assert "as it stands" in notes[1]
    assert "not transactional" in notes[1]
    assert "definition payload only" in notes[2]
    assert "no organisation row and no binding" in notes[3]


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


def _foreign_pack(tmp_path, data=None):
    store = ScenarioStore(definitions_path())
    record = store.create(FOREIGN, data if data is not None else body(),
                          now=NOW)
    return build_pack(record, exported_at=NOW)


def test_http_fresh_duplicate_and_collision_at_200(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition, pack = _http_pack(client)
    road = "/api/v1/scenarios/pack/import-preview"
    # the caller's own pack is an exact duplicate, named
    res = client.post(road, json=pack)
    assert res.status_code == 200
    out = res.json()
    assert out["outcome"] == "duplicate_exact"
    assert out["library"]["duplicate_of"]["id"] == definition["id"]
    assert out["would_create"] is False
    # a fresh pack (foreign-held, new name) would create
    fresh = _foreign_pack(tmp_path, body("Mountain Gate"))
    res = client.post(road, json=fresh)
    assert res.status_code == 200
    assert res.json()["outcome"] == "would_create"
    # a same-name, different-content pack collides...
    clash = _foreign_pack(tmp_path, body(text="Other words entirely."))
    res = client.post(road, json=clash)
    assert res.status_code == 200
    out = res.json()
    assert out["outcome"] == "would_create_with_name_collision"
    assert [row["id"] for row in out["library"]["name_collisions"]] == [
        definition["id"]]
    # ...and under reject the refusal is DATA at 200, never
    # the road's own answer
    res = client.post(f"{road}?on_conflict=reject", json=clash)
    assert res.status_code == 200
    out = res.json()
    assert out["outcome"] == "would_refuse"
    assert out["would_refuse"] is True
    assert out["refusal_reason"] == REFUSAL
    # nothing was ever imported by previewing
    assert client.get("/api/v1/scenarios").json()["total"] == 1


def test_http_malformed_and_bad_mode_are_422(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    _definition, pack = _http_pack(client)
    road = "/api/v1/scenarios/pack/import-preview"
    tampered = copy.deepcopy(pack)
    tampered["scenario"]["scenario_text"] = "Altered."
    assert client.post(road, json=tampered).status_code == 422
    assert client.post(road, json={"format": "nope"}).status_code == 422
    assert client.post(
        f"{road}?on_conflict=merge", json=pack).status_code == 422
    assert client.get("/api/v1/scenarios").json()["total"] == 1


def test_http_preview_leaves_store_byte_untouched(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    _definition, pack = _http_pack(client)
    # the clash pack is built BEFORE the snapshot: building
    # it stores its foreign source record in the document
    clash = _foreign_pack(tmp_path, body(text="Other words entirely."))
    path = definitions_path()
    before = path.read_bytes()
    road = "/api/v1/scenarios/pack/import-preview"
    assert client.post(road, json=pack).status_code == 200
    assert client.post(
        f"{road}?on_conflict=reject", json=clash).status_code == 200
    assert path.read_bytes() == before


def test_http_literal_road_unshadowed_and_neighbours_untouched(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    definition, pack = _http_pack(client)
    base = f"/api/v1/scenarios/{definition['id']}"
    # the literal preview road answers as itself — "pack"
    # is never read as a definition id
    res = client.post("/api/v1/scenarios/pack/import-preview", json=pack)
    assert res.status_code == 200
    assert res.json()["schema"] == pack["schema"]
    # the P-141 neighbours stand untouched beside it
    assert client.post(
        "/api/v1/scenarios/pack/inspect", json=pack).status_code == 200
    dup = client.post("/api/v1/scenarios/import-pack", json=pack)
    assert dup.status_code == 200
    assert dup.json()["pack_import"]["duplicate_exact"] is True
    assert client.get(base).status_code == 200
    assert client.get(f"{base}/pack").status_code == 200
    assert client.get(f"{base}/export").status_code == 200
    assert client.get(f"{base}/bind-plan").status_code == 200
    assert client.get(f"{base}/delete-impact").status_code == 200
    assert client.get(f"{base}/replace-impact").status_code == 200
    assert client.get(f"{base}/organisation").status_code == 200


# ----------------------------------------------------- migration


def test_migration_head_stays_0041(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
    assert MIGRATIONS[-1][0] == "0041"
