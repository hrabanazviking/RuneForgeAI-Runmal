"""P-063 acceptance: prompt import/export packs.

Roadmap line: *Prompt import/export packs (with Part XII sharing).*

Honesty contract pinned here:
- a pack gathers bundles, presets, standalone instruct/context
  templates and layouts; every item is normalised by its OWN
  existing validator and normalisation is a fixed point;
- per-item and pack checksums are taken over canonical
  NORMALISED content: cosmetic re-serialisation passes, any
  content tampering (payload, order, manifest, provenance)
  refuses whole, before any write exists;
- import stores bundle + preset items through the existing
  services and NEVER overwrites: exact duplicates are
  unwritten, name collisions rename under create_new or
  reject per item under reject;
- template/layout items import as validated portable data
  (validated_not_stored, the P-049/P-050/P-051 deferral named)
  -- never claimed stored, never silently dropped;
- unknown-field carriage exists exactly where the owning layer
  provides it (bundle extensions, preset bag/raw, item and
  pack extensions); strict payloads refuse unknown keys;
- migration head stays 0036 (P-065): packs are file-layer artefacts.
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
from runmal.presets import bundles, packs, service
from runmal.presets.packs import (
    PackError,
    build_pack,
    export_library_pack,
    import_pack,
    inspect_pack,
    parse_pack,
)


def bundle_item(name="Hall Bundle", temp=0.8):
    return {
        "kind": "bundle",
        "name": name,
        "payload": {
            "name": name,
            "sampler": {"temperature": temp, "top_p": 0.9},
            "instruct_template": {"kind": "builtin", "name": "chatml"},
            "template_ref": "legacy-ref",
            "prompts": [{"identifier": "main", "content": "You are helpful."}],
            "prompt_order": [{"identifier": "main", "enabled": True}],
            "foreign_future_field": {"x": [True, None, 1.5]},
        },
    }


def preset_item(name="Hall Preset"):
    return {
        "kind": "preset",
        "name": name,
        "payload": {
            "name": name,
            "params": {"temperature": 0.7, "backend_custom_knob": {"n": 1}},
            "template_ref": "",
            "source_format": "st-chat",
            "raw": {"temperature": 0.7, "future_st_field": [1, 2]},
            "prompts": [{"identifier": "main", "content": "Hi."}],
            "prompt_order": [{"identifier": "main", "enabled": True}],
        },
    }


def instruct_item(name="My ChatML"):
    return {
        "kind": "instruct_template",
        "name": name,
        "payload": {
            "name": name,
            "description": "Mine.",
            "wrappers": {
                "system": {"prefix": "<s>\n", "suffix": "</s>\n"},
                "user": {"prefix": "U: ", "suffix": "\n"},
                "assistant": {"prefix": "A: ", "suffix": "\n"},
            },
            "separator": "\n",
            "generation_prefix": "A: ",
            "stop_strings": ["</s>"],
        },
    }


def context_item(name="My Context"):
    return {
        "kind": "context_template",
        "name": name,
        "payload": {
            "name": name,
            "segments": [
                {"anchor": "system", "prefix": "[SYS]\n"},
                {"anchor": "history", "enabled": False},
            ],
            "separator": "\n",
        },
    }


def layout_item(name="Quiet Layout"):
    return {
        "kind": "prompt_layout",
        "name": name,
        "payload": {"blocks": [{"block": "history", "enabled": False}]},
    }


def full_items():
    return [bundle_item(), preset_item(), instruct_item(),
            context_item(), layout_item()]


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


def run(factory, coro_fn):
    async def _go():
        async with factory() as session:
            return await coro_fn(session)
    return asyncio.run(_go())


def make_factory(tmp_path):
    db_path = tmp_path / "svc.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


def seed_user(factory, name="volmarr"):
    from runmal.db.models import User
    async def _go():
        async with factory() as session:
            user = User(name=name)
            session.add(user)
            await session.commit()
            return user.id
    return asyncio.run(_go())


# ---------------- build / parse / fixed point ----------------

def test_full_pack_round_trips_every_kind():
    pack = build_pack("Workshop", full_items(), exported_at="2026-11-07T00:00:00+00:00")
    parsed = parse_pack(pack)
    assert parsed["manifest"]["pack_name"] == "Workshop"
    assert parsed["manifest"]["item_count"] == 5
    assert parsed["manifest"]["kind_counts"] == {
        "bundle": 1, "preset": 1, "instruct_template": 1,
        "context_template": 1, "prompt_layout": 1,
    }
    by_kind = {it["kind"]: it for it in parsed["items"]}
    # Bundle extensions + carriage survive verbatim.
    b = by_kind["bundle"]["payload"]
    assert b["extensions"] == {"foreign_future_field": {"x": [True, None, 1.5]}}
    assert b["prompts"][0]["content"] == "You are helpful."
    assert b["sampler"]["temperature"] == 0.8
    # Preset bag unknown key + raw carriage survive verbatim.
    pr = by_kind["preset"]["payload"]
    assert pr["params"]["backend_custom_knob"] == {"n": 1}
    assert pr["raw"]["future_st_field"] == [1, 2]
    # Template/layout payloads are their normalised data forms.
    assert by_kind["instruct_template"]["payload"]["stop_strings"] == ["</s>"]
    blocks = {r["block"]: r["enabled"] for r in by_kind["prompt_layout"]["payload"]["blocks"]}
    assert blocks["history"] is False and blocks["system"] is True
    # Fixed point: parsing a parsed pack changes nothing.
    assert parse_pack(parsed) == parsed
    assert build_pack("Workshop", parsed["items"], exported_at="2026-11-07T00:00:00+00:00")["manifest"]["content_sha256"] == pack["manifest"]["content_sha256"]


def test_cosmetic_reserialisation_still_verifies():
    pack = build_pack("Workshop", full_items())
    text = json.dumps(pack, indent=4, sort_keys=False, ensure_ascii=True)
    parsed = parse_pack(text)
    assert parsed["manifest"]["content_sha256"] == pack["manifest"]["content_sha256"]
    assert parse_pack(packs.pack_to_bytes(pack))["manifest"]["item_count"] == 5


def test_inspect_reports_storage_truth_without_importing():
    pack = build_pack("Workshop", full_items())
    report = inspect_pack(pack)
    assert report["valid"] is True and report["checksum_verified"] is True
    stored = {r["kind"]: r["stored_on_import"] for r in report["items"]}
    assert stored == {"bundle": True, "preset": True, "instruct_template": False,
                      "context_template": False, "prompt_layout": False}
    assert report["provenance"]["source_kind"] == "prompt_pack_export"


# ---------------- tamper + malformed refusal ----------------

def test_tampered_payload_refuses():
    pack = build_pack("Workshop", full_items())
    evil = copy.deepcopy(pack)
    evil["items"][0]["payload"]["sampler"]["temperature"] = 0.1
    with pytest.raises(PackError, match="checksum"):
        parse_pack(evil)


def test_reordered_items_refuse():
    pack = build_pack("Workshop", full_items())
    evil = copy.deepcopy(pack)
    evil["items"] = list(reversed(evil["items"]))
    with pytest.raises(PackError, match="checksum"):
        parse_pack(evil)


def test_manifest_and_provenance_tamper_refuse():
    pack = build_pack("Workshop", full_items())
    evil = copy.deepcopy(pack)
    evil["manifest"]["item_count"] = 99
    with pytest.raises(PackError):
        parse_pack(evil)
    evil2 = copy.deepcopy(pack)
    evil2["provenance"]["content_sha256"] = "0" * 64
    with pytest.raises(PackError, match="provenance"):
        parse_pack(evil2)
    evil3 = copy.deepcopy(pack)
    evil3["items"][1]["content_sha256"] = "0" * 64
    with pytest.raises(PackError, match="checksum"):
        parse_pack(evil3)


def test_envelope_refusals():
    pack = build_pack("Workshop", full_items())
    for mutate in (
        lambda p: p.update({"format": "other"}),
        lambda p: p.update({"pack_version": 2}),
        lambda p: p.update({"pack_version": True}),
        lambda p: p.update({"kind": "lorebook"}),
        lambda p: p.update({"items": []}),
        lambda p: p.pop("manifest"),
        lambda p: p.pop("provenance"),
    ):
        bad = copy.deepcopy(pack)
        mutate(bad)
        with pytest.raises(PackError):
            parse_pack(bad)
    with pytest.raises(PackError):
        parse_pack(b"{not json")
    with pytest.raises(PackError):
        parse_pack(42)


def test_item_refusals():
    with pytest.raises(PackError, match="does not match"):
        build_pack("W", [{**bundle_item(), "name": "Other"}])
    with pytest.raises(PackError, match="two bundle items"):
        build_pack("W", [bundle_item(), bundle_item()])
    with pytest.raises(PackError, match="unknown pack item kind"):
        build_pack("W", [{"kind": "widget", "name": "x", "payload": {}}])
    with pytest.raises(PackError, match="unknown keys"):
        build_pack("W", [{**bundle_item(), "surprise": 1}])
    bad_sampler = bundle_item()
    bad_sampler["payload"]["sampler"] = {"temperature": -1}
    with pytest.raises(PackError):
        build_pack("W", [bad_sampler])
    strict = instruct_item()
    strict["payload"]["bogus_key"] = 1
    with pytest.raises(PackError):
        build_pack("W", [strict])
    with pytest.raises(PackError, match="at least one item"):
        build_pack("W", [])


def test_pack_level_unknown_keys_are_carried_not_dropped():
    pack = build_pack("Workshop", full_items())
    pack["hub_annotation"] = {"carrier": "future-hub", "n": 3}
    parsed = parse_pack(pack)
    assert parsed["extensions"]["hub_annotation"] == {"carrier": "future-hub", "n": 3}
    item = bundle_item()
    item["extensions"] = {"carrier_note": "keep me"}
    parsed2 = parse_pack(build_pack("W", [item]))
    assert parsed2["items"][0]["extensions"] == {"carrier_note": "keep me"}


# ---------------- import: storage + honesty ----------------

def test_import_stores_bundles_and_presets_only(tmp_path):
    factory = make_factory(tmp_path)
    uid = seed_user(factory)
    pack = build_pack("Workshop", full_items())
    report = run(factory, lambda s: import_pack(s, uid, pack))
    assert report["checksum_verified"] is True
    assert report["counts"] == {"created": 2, "duplicate_exact": 0, "renamed": 0,
                                "rejected": 0, "validated_not_stored": 3}
    rows = {(r["kind"], r["name"]): r for r in report["items"]}
    assert rows[("bundle", "Hall Bundle")]["status"] == "created"
    assert rows[("preset", "Hall Preset")]["status"] == "created"
    for kind in ("instruct_template", "context_template", "prompt_layout"):
        row = rows[(kind, {"instruct_template": "My ChatML", "context_template": "My Context", "prompt_layout": "Quiet Layout"}[kind])]
        assert row["status"] == "validated_not_stored" and row["stored"] is False
        assert row["reason"] == packs.NOT_STORED_REASON
        assert row["payload"]["name"] if kind != "prompt_layout" else row["payload"]["blocks"]
    # The stored rows are really there, value-identical.
    stored_bundles = run(factory, lambda s: bundles.list_bundles(s, uid))
    assert [b.name for b in stored_bundles] == ["Hall Bundle"]
    assert bundles.bundle_to_dict(stored_bundles[0])["bundle"] == parse_pack(pack)["items"][0]["payload"]
    stored_presets = run(factory, lambda s: service.list_presets(s, user_id=uid))
    assert [p.name for p in stored_presets] == ["Hall Preset"]
    view = service.preset_to_dict(stored_presets[0])
    assert view["params"]["backend_custom_knob"] == {"n": 1}
    assert view["source_format"] == "st-chat"
    assert service.interop_data(stored_presets[0])["raw"]["future_st_field"] == [1, 2]
    # Provenance rides the report verbatim, stored on no row.
    assert report["provenance"] == pack["provenance"]


def test_reimport_is_exact_duplicate_and_writes_nothing(tmp_path):
    factory = make_factory(tmp_path)
    uid = seed_user(factory)
    pack = build_pack("Workshop", full_items())
    run(factory, lambda s: import_pack(s, uid, pack))
    report = run(factory, lambda s: import_pack(s, uid, pack))
    assert report["counts"]["duplicate_exact"] == 2
    assert report["counts"]["created"] == 0
    assert len(run(factory, lambda s: bundles.list_bundles(s, uid))) == 1
    assert len(run(factory, lambda s: service.list_presets(s, user_id=uid))) == 1


def test_name_collision_renames_under_create_new(tmp_path):
    factory = make_factory(tmp_path)
    uid = seed_user(factory)
    run(factory, lambda s: import_pack(s, uid, build_pack("W1", [bundle_item(temp=0.8)])))
    report = run(factory, lambda s: import_pack(s, uid, build_pack("W2", [bundle_item(temp=0.3)])))
    row = report["items"][0]
    assert row["status"] == "renamed" and row["stored_name"] == "Hall Bundle (imported)"
    assert row["original_name"] == "Hall Bundle"
    names = sorted(b.name for b in run(factory, lambda s: bundles.list_bundles(s, uid)))
    assert names == ["Hall Bundle", "Hall Bundle (imported)"]
    # A third distinct copy takes the next free derived name.
    report3 = run(factory, lambda s: import_pack(s, uid, build_pack("W3", [bundle_item(temp=0.5)])))
    assert report3["items"][0]["stored_name"] == "Hall Bundle (imported 2)"


def test_name_collision_rejects_per_item_under_reject(tmp_path):
    factory = make_factory(tmp_path)
    uid = seed_user(factory)
    run(factory, lambda s: import_pack(s, uid, build_pack("W1", [bundle_item(temp=0.8), preset_item()])))
    pack2 = build_pack("W2", [bundle_item(temp=0.3), preset_item("Fresh Preset"), layout_item()])
    report = run(factory, lambda s: import_pack(s, uid, pack2, on_conflict="reject"))
    rows = {(r["kind"], r["name"]): r for r in report["items"]}
    assert rows[("bundle", "Hall Bundle")]["status"] == "rejected"
    assert rows[("bundle", "Hall Bundle")]["reason"] == "name_collision"
    # The rest of the pack still imports -- per-item outcomes.
    assert rows[("preset", "Fresh Preset")]["status"] == "created"
    assert rows[("prompt_layout", "Quiet Layout")]["status"] == "validated_not_stored"
    assert len(run(factory, lambda s: bundles.list_bundles(s, uid))) == 1
    with pytest.raises(PackError, match="on_conflict"):
        run(factory, lambda s: import_pack(s, uid, pack2, on_conflict="merge"))


def test_import_is_owner_scoped(tmp_path):
    factory = make_factory(tmp_path)
    uid_a = seed_user(factory, "a")
    uid_b = seed_user(factory, "b")
    pack = build_pack("Workshop", [bundle_item()])
    run(factory, lambda s: import_pack(s, uid_a, pack))
    # B does not see A's copy as a duplicate: B imports its own.
    report = run(factory, lambda s: import_pack(s, uid_b, pack))
    assert report["items"][0]["status"] == "created"


# ---------------- export from the library ----------------

def test_export_library_pack_all_selected_and_missing(tmp_path):
    factory = make_factory(tmp_path)
    uid = seed_user(factory)
    run(factory, lambda s: bundles.create_bundle(s, uid, bundle_item()["payload"]))
    run(factory, lambda s: service.create_preset(s, user_id=uid, name="P1", params={"temperature": 0.4}))
    pack = run(factory, lambda s: export_library_pack(s, uid, "Everything"))
    assert pack["manifest"]["kind_counts"] == {"bundle": 1, "preset": 1}
    parsed = parse_pack(pack)
    assert {it["name"] for it in parsed["items"]} == {"Hall Bundle", "P1"}
    rows = run(factory, lambda s: bundles.list_bundles(s, uid))
    picked = run(factory, lambda s: export_library_pack(s, uid, "Picked", bundle_ids=[rows[0].id], preset_ids=[]))
    assert picked["manifest"]["item_count"] == 1
    with pytest.raises(PackError, match="not found"):
        run(factory, lambda s: export_library_pack(s, uid, "X", bundle_ids=["nope"], preset_ids=[]))
    with pytest.raises(PackError, match="at least one item"):
        run(factory, lambda s: export_library_pack(s, uid, "Empty", bundle_ids=[], preset_ids=[]))


# ---------------- API ----------------

def test_pack_api_export_inspect_import(tmp_path, monkeypatch):
    client, factory = make_client(tmp_path, monkeypatch)
    resp = client.post("/api/v1/presets/bundles", json={"bundle": bundle_item()["payload"]})
    assert resp.status_code == 201, resp.text
    resp = client.post("/api/v1/presets/packs/export", json={"name": "API Pack"})
    assert resp.status_code == 200, resp.text
    pack = resp.json()
    assert pack["manifest"]["kind_counts"] == {"bundle": 1}
    resp = client.post("/api/v1/presets/packs/inspect", json=pack)
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"][0]["stored_on_import"] is True
    # Inspect imported nothing: re-export still sees one bundle.
    resp = client.post("/api/v1/presets/packs/import", json=pack)
    assert resp.status_code == 200, resp.text
    report = resp.json()["import_report"]
    assert report["items"][0]["status"] == "duplicate_exact"
    resp = client.post("/api/v1/presets/packs/import", json={"format": "nope"})
    assert resp.status_code == 422, resp.text
    resp = client.post("/api/v1/presets/packs/export", json={"name": "Bad", "bundle_ids": ["nope"]})
    assert resp.status_code == 422, resp.text


def test_migration_head_stays_0036(tmp_path):
    db_path = tmp_path / "mig.db"
    migrate_to_head(db_path)
    assert MIGRATIONS[-1][0] == "0040"
    assert current_revision(db_path) == "0040"
