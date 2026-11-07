"""P-054 acceptance: preset bundles — save/load/share + overrides.

Roadmap line: *Presets: save/load/share sampler+prompt bundles;
per-character and per-chat overrides.*

Honesty contract pinned here:
- every carried field survives save/load and share round trips
  value-identically (all 28 canonical sampler keys, an unknown
  sampler key, layout, both template selection kinds, the legacy
  template_ref, the P-021 prompts/prompt_order carriage, and
  unknown top-level fields carried as extensions);
- normalisation is a fixed point and storage is canonical;
- malformed known sections refuse cleanly and store nothing;
- share checksums verify over the normalised bundle: cosmetic
  re-serialisation passes, content tampering refuses;
- overrides layer bundle < character < chat with per-field
  sources, sampler null deletes a base key, an override typo
  refuses, different-bundle shadowing is reported not dropped;
- migration head is PROVISIONAL 0036 (P-065); ownership is scoped throughout.
"""

from __future__ import annotations

import asyncio
import copy
import json

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.presets import bundles
from runmal.presets.bundles import (
    BundleError,
    build_share,
    merge_bundle,
    parse_share,
    validate_bundle,
    validate_overrides,
)

FULL_SAMPLER = {
    "temperature": 0.8, "top_p": 0.9, "top_k": 40, "max_tokens": 512,
    "frequency_penalty": 0.1, "presence_penalty": -0.2,
    "repetition_penalty": 1.05, "stop": ["END", "STOP"], "seed": 42,
    "min_p": 0.05, "context_length": 8192, "typical_p": 0.95,
    "top_a": 0.1, "tfs_z": 0.9, "epsilon_cutoff": 0.0003,
    "eta_cutoff": 0.0006, "dry_multiplier": 0.8, "dry_base": 1.75,
    "dry_allowed_length": 2, "dry_penalty_last_n": 128,
    "dry_sequence_breakers": ["\n"], "xtc_probability": 0.5,
    "xtc_threshold": 0.1, "mirostat_mode": 2, "mirostat_tau": 5.0,
    "mirostat_eta": 0.1, "dynamic_temperature_range": 0.4,
    "dynamic_temperature_exponent": 1.0,
    "backend_custom_knob": {"nested": [1, 2, 3]},
}


def full_bundle(name="Hall Bundle"):
    return {
        "name": name,
        "sampler": copy.deepcopy(FULL_SAMPLER),
        "prompt_layout": {"blocks": [
            {"block": "history", "enabled": False},
            {"block": "system", "enabled": True},
        ]},
        "instruct_template": {"kind": "builtin", "name": "chatml"},
        "context_template": {"kind": "builtin", "name": "default"},
        "template_ref": "legacy-ref",
        "prompts": [{"identifier": "main", "content": "You are helpful."}],
        "prompt_order": [{"identifier": "main", "enabled": True}],
        "foreign_future_field": {"x": [True, None, 1.5]},
    }


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    factory = create_session_factory(engine)
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client, factory


def api_character(client, name="Sigrun"):
    payload = {
        "spec": "chara_card_v2", "spec_version": "2.0", "name": name,
        "description": "A test seer.", "personality": "Calm.",
        "scenario": "A test hall.", "first_mes": "Hail!",
        "mes_example": "", "creator_notes": "", "system_prompt": "",
        "post_history_instructions": "", "alternate_greetings": [],
        "tags": [], "creator": "test", "extensions": {},
    }
    resp = client.post("/api/v1/characters", json={"card": payload})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def api_chat(client, character_id, title="Hall"):
    resp = client.post("/api/v1/chats", json={"title": title, "character_id": character_id})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def api_bundle(client, bundle=None, name="Hall Bundle"):
    resp = client.post("/api/v1/presets/bundles", json={"bundle": bundle or full_bundle(name)})
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------- validation + fixed point ----------------

def test_full_bundle_round_trips_every_field():
    out = validate_bundle(full_bundle())
    assert out["sampler"] == FULL_SAMPLER
    assert out["template_ref"] == "legacy-ref"
    assert out["instruct_template"] == {"kind": "builtin", "name": "chatml"}
    assert out["context_template"] == {"kind": "builtin", "name": "default"}
    assert out["prompts"] == full_bundle()["prompts"]
    assert out["prompt_order"] == full_bundle()["prompt_order"]
    assert out["extensions"] == {"foreign_future_field": {"x": [True, None, 1.5]}}
    blocks = {b["block"]: b["enabled"] for b in out["prompt_layout"]["blocks"]}
    assert blocks["history"] is False and blocks["system"] is True
    assert len(blocks) == 10  # missing blocks filled, none lost (post_history block added by P-057)


def test_normalisation_is_a_fixed_point():
    once = validate_bundle(full_bundle())
    assert validate_bundle(once) == once
    assert validate_bundle(json.loads(json.dumps(once))) == once


def test_minimal_bundle_defaults_honestly():
    out = validate_bundle({"name": "Bare"})
    assert out["sampler"] == {} and out["prompt_layout"] is None
    assert out["instruct_template"] is None and out["extensions"] == {}


def test_custom_selections_carry_full_data():
    data = full_bundle()
    data["instruct_template"] = {"kind": "custom", "template": {
        "name": "mine", "wrappers": {"user": {"prefix": "U: ", "suffix": "\n"}},
        "stop_strings": ["U:"],
    }}
    data["context_template"] = {"kind": "story_string", "text": "{{system}}\n{{chatHistory}}"}
    out = validate_bundle(data)
    assert out["instruct_template"]["template"]["name"] == "mine"
    assert out["context_template"] == {"kind": "story_string", "text": "{{system}}\n{{chatHistory}}"}
    assert validate_bundle(out) == out


@pytest.mark.parametrize("bad", [
    {"name": ""}, {"name": 7}, {"sampler": {"temperature": -1}},
    {"name": "x", "sampler": {"temperature": True}},
    {"name": "x", "sampler": {"top_k": 1.5}},
    {"name": "x", "prompt_layout": {"blocks": [{"block": "nope"}]}},
    {"name": "x", "instruct_template": {"kind": "builtin", "name": "nope"}},
    {"name": "x", "instruct_template": {"kind": "custom", "template": {"name": "t", "bogus": 1}}},
    {"name": "x", "context_template": {"kind": "story_string", "text": "no placeholders"}},
    {"name": "x", "prompts": {}}, {"name": "x", "template_ref": 3},
    {"name": "x", "extensions": []}, "not-a-dict",
])
def test_malformed_bundles_refuse(bad):
    with pytest.raises(BundleError):
        validate_bundle(bad)


# ---------------- share envelope ----------------

def test_share_round_trip_and_fixed_point():
    bundle = validate_bundle(full_bundle())
    share = build_share(bundle, exported_at="2026-11-06T00:00:00+00:00")
    out, report = parse_share(share)
    assert out == bundle and report["checksum_verified"] is True
    assert report["extension_keys"] == ["foreign_future_field"]
    reserialised = json.loads(json.dumps(share, indent=3))
    out2, _ = parse_share(reserialised)
    assert out2 == bundle


def test_share_tampering_refuses():
    share = build_share(validate_bundle(full_bundle()))
    share["bundle"]["sampler"]["temperature"] = 1.9
    with pytest.raises(BundleError):
        parse_share(share)
    share2 = build_share(validate_bundle(full_bundle()))
    share2["format"] = "something-else"
    with pytest.raises(BundleError):
        parse_share(share2)


def test_bare_bundle_parse_reports_no_checksum():
    out, report = parse_share(full_bundle())
    assert report["via"] == "bare_bundle" and report["checksum_verified"] is False
    assert out["name"] == "Hall Bundle"


# ---------------- overrides: pure merge ----------------

def test_merge_precedence_and_sources():
    base = validate_bundle(full_bundle())
    char_delta = validate_overrides({"sampler": {"temperature": 0.3}, "template_ref": "char-ref"})
    chat_delta = validate_overrides({"sampler": {"temperature": 0.1, "seed": None}})
    effective, sources = merge_bundle(base, char_delta, chat_delta)
    assert effective["sampler"]["temperature"] == 0.1
    assert "seed" not in effective["sampler"]  # explicit null deletion
    assert effective["template_ref"] == "char-ref"
    assert sources["sampler"]["temperature"] == "delta2"
    assert sources["template_ref"] == "delta1"


def test_override_unknown_key_refuses():
    with pytest.raises(BundleError):
        validate_overrides({"sampelr": {}})
    with pytest.raises(BundleError):
        validate_overrides({"sampler": {"top_p": 9}})


# ---------------- API: CRUD + share ----------------

def test_migration_head_is_0036_provisional(tmp_path):
    db_path = tmp_path / "m.db"
    migrate_to_head(db_path)
    assert MIGRATIONS[-1][0] == "0039"  # head moved by P-065 (PROVISIONAL 0036)
    assert current_revision(db_path) == "0039"
    assert migrate_to_head(db_path) == []  # idempotent


def test_bundle_crud_via_api(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    created = api_bundle(client)
    assert created["bundle"]["sampler"] == FULL_SAMPLER
    assert created["bundle"]["extensions"]["foreign_future_field"] == {"x": [True, None, 1.5]}
    fetched = client.get(f"/api/v1/presets/bundles/{created['id']}")
    assert fetched.status_code == 200 and fetched.json()["bundle"] == created["bundle"]
    listed = client.get("/api/v1/presets/bundles").json()
    assert [b["name"] for b in listed] == ["Hall Bundle"]
    dup = client.post("/api/v1/presets/bundles", json={"bundle": full_bundle()})
    assert dup.status_code == 409
    bad = client.post("/api/v1/presets/bundles", json={"bundle": {"name": "x", "sampler": {"top_p": 2}}})
    assert bad.status_code == 422
    assert client.get("/api/v1/presets/bundles/missing").status_code == 404
    updated = client.patch(f"/api/v1/presets/bundles/{created['id']}", json={"bundle": full_bundle("Renamed")})
    assert updated.status_code == 200 and updated.json()["name"] == "Renamed"
    assert client.delete(f"/api/v1/presets/bundles/{created['id']}").status_code == 200
    assert client.get(f"/api/v1/presets/bundles/{created['id']}").status_code == 404


def test_share_and_import_via_api(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    created = api_bundle(client)
    share = client.get(f"/api/v1/presets/bundles/{created['id']}/share")
    assert share.status_code == 200
    envelope = share.json()
    assert envelope["format"] == "runmal-preset-bundle"
    assert client.delete(f"/api/v1/presets/bundles/{created['id']}").status_code == 200
    imported = client.post("/api/v1/presets/bundles/import", json=envelope)
    assert imported.status_code == 201, imported.text
    assert imported.json()["bundle"] == created["bundle"]
    assert imported.json()["import_report"]["checksum_verified"] is True
    tampered = copy.deepcopy(envelope)
    tampered["bundle"]["sampler"]["seed"] = 99
    refused = client.post("/api/v1/presets/bundles/import", json=tampered)
    assert refused.status_code == 422


def test_s207_presets_unaffected(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    resp = client.post("/api/v1/presets", json={"name": "plain", "params": {"temperature": 0.5}})
    assert resp.status_code == 201, resp.text
    api_bundle(client)
    assert client.get("/api/v1/presets").status_code == 200
    assert client.get("/api/v1/presets/bundles").status_code == 200


# ---------------- API: overrides + resolution ----------------

def _setup_override_world(client):
    char = api_character(client)
    chat = api_chat(client, char["id"])
    bundle = api_bundle(client)
    return char, chat, bundle


def test_override_and_resolve_via_api(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    char, chat, bundle = _setup_override_world(client)
    put = client.put(f"/api/v1/presets/overrides/character/{char['id']}", json={"bundle_id": bundle["id"], "overrides": {"sampler": {"temperature": 0.3}}})
    assert put.status_code == 200, put.text
    put2 = client.put(f"/api/v1/presets/overrides/chat/{chat['id']}", json={"bundle_id": bundle["id"], "overrides": {"sampler": {"temperature": 0.1, "max_tokens": None}}})
    assert put2.status_code == 200, put2.text
    view = client.get("/api/v1/presets/resolve", params={"chat_id": chat["id"]})
    assert view.status_code == 200
    effective = view.json()["effective"]
    assert effective["bundle_id"] == bundle["id"]
    assert effective["effective"]["sampler"]["temperature"] == 0.1
    assert "max_tokens" not in effective["effective"]["sampler"]
    assert effective["sources"]["sampler"]["temperature"] == "chat"
    assert effective["sources"]["sampler"]["top_p"] == "bundle"
    assert [a["scope_kind"] for a in effective["applied"]] == ["character", "chat"]
    assert effective["shadowed"] == []


def test_resolve_character_only_and_none(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    char, chat, bundle = _setup_override_world(client)
    empty = client.get("/api/v1/presets/resolve", params={"chat_id": chat["id"]}).json()
    assert empty["effective"] is None
    client.put(f"/api/v1/presets/overrides/character/{char['id']}", json={"bundle_id": bundle["id"], "overrides": {}})
    view = client.get("/api/v1/presets/resolve", params={"character_id": char["id"]}).json()["effective"]
    assert view["effective"]["sampler"] == FULL_SAMPLER
    assert client.delete(f"/api/v1/presets/overrides/character/{char['id']}").status_code == 200
    gone = client.get("/api/v1/presets/resolve", params={"character_id": char["id"]}).json()
    assert gone["effective"] is None


def test_override_refusals(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    char, chat, bundle = _setup_override_world(client)
    bad_scope = client.put(f"/api/v1/presets/overrides/planet/{char['id']}", json={"bundle_id": bundle["id"], "overrides": {}})
    assert bad_scope.status_code == 422
    bad_bundle = client.put(f"/api/v1/presets/overrides/chat/{chat['id']}", json={"bundle_id": "missing", "overrides": {}})
    assert bad_bundle.status_code == 404
    bad_owner = client.put("/api/v1/presets/overrides/chat/missing", json={"bundle_id": bundle["id"], "overrides": {}})
    assert bad_owner.status_code == 404
    typo = client.put(f"/api/v1/presets/overrides/chat/{chat['id']}", json={"bundle_id": bundle["id"], "overrides": {"sampelr": {}}})
    assert typo.status_code == 422


def test_different_bundle_shadowing_is_reported(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    char, chat, bundle = _setup_override_world(client)
    other = api_bundle(client, name="Other Bundle")
    client.put(f"/api/v1/presets/overrides/character/{char['id']}", json={"bundle_id": bundle["id"], "overrides": {}})
    client.put(f"/api/v1/presets/overrides/chat/{chat['id']}", json={"bundle_id": other["id"], "overrides": {"sampler": {"seed": 7}}})
    view = client.get("/api/v1/presets/resolve", params={"chat_id": chat["id"]}).json()["effective"]
    assert view["bundle_id"] == other["id"]
    assert view["effective"]["sampler"]["seed"] == 7
    assert len(view["shadowed"]) == 1 and view["shadowed"][0]["scope_kind"] == "character"


# ---------------- service-level ownership ----------------

def test_service_ownership_isolation(tmp_path, monkeypatch):
    client, factory = make_client(tmp_path, monkeypatch)
    created = api_bundle(client)

    async def probe():
        async with factory() as session:
            from runmal.db.owners import get_or_create_owner
            owner = await get_or_create_owner(session)
            mine = await bundles.list_bundles(session, owner.id)
            theirs = await bundles.list_bundles(session, "someone-else")
            return [b.id for b in mine], theirs, await bundles.get_bundle(session, "someone-else", created["id"])
    mine_ids, theirs, stolen = asyncio.run(probe())
    assert mine_ids == [created["id"]] and theirs == [] and stolen is None
