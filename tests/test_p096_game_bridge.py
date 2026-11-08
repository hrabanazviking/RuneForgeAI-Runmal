"""P-096 Dice & game-bridge plugin surface battery.

Pins the contract from hidden_files/P096_DESIGN.md: the
citizen manifest as strict round-tripping data, the
P-082 empty-grant stance, the dice notation grammar
(common forms parsed, everything else refused plainly),
the P-036 honesty discipline (a seeded roll reproduces
from its own record forever; an unseeded roll is
labelled and unverifiable, never dressed as
reproducible), keep-highest/lowest math, the durable
per-owner store (file idiom, corrupt store refuses,
never reset), persisted rolls minting their dice.rolled
bridge event in the same save, the bridge event surface
(closed kinds/targets, per-kind payload shapes,
dice.rolled never forgeable through the generic emit
road, after-seq poll, monotonic ack cursors, honest
prune counting), the metadata-only event handler, the
HTTP surface, and the neighbours (migration head stays
0041, no 0042).
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.plugins import game_bridge as gb
from runmal.plugins import service as plugin_service
from runmal.plugins.manifest import manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginRegistry, PluginState


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    plugin_service.set_default_registry(None)
    yield
    plugin_service.set_default_registry(None)


def ids():
    return str(uuid.uuid4()), str(uuid.uuid4())


# -- Citizen / manifest ------------------------------------------------------


def test_manifest_round_trips_and_registers():
    data = gb.manifest_data()
    manifest = manifest_from_data(data)
    assert manifest_to_data(manifest) == data
    assert manifest.id == gb.PLUGIN_ID == "runmal.game-bridge"
    assert "chat.write" not in manifest.permissions
    registry = PluginRegistry()
    record, _plugin = gb.register_plugin(registry)
    assert record.state == PluginState.REGISTERED


def test_sandbox_grants_are_empty():
    grants = gb.sandbox_grants()
    assert grants.resources == frozenset()


def test_ui_contribution_is_the_toolbar_panel():
    registry = PluginRegistry()
    gb.register_plugin(registry, enable=True)
    contributions = registry.ui_contributions("chat.toolbar")
    assert any(c["plugin_id"] == gb.PLUGIN_ID for c in contributions)


def test_boot_registry_stays_empty(tmp_path):
    db_path = tmp_path / "boot.db"
    migrate_to_head(db_path)
    app = create_app(create_session_factory(create_db_engine(db_path)))
    registry = plugin_service.get_default_registry()
    assert registry is not None and registry.keys() == []
    assert app is not None


# -- Notation ------------------------------------------------------------------


def test_parse_common_notations():
    cases = {
        "2d6": (2, 6, None, None, 0, "2d6"),
        "d20": (1, 20, None, None, 0, "1d20"),
        "2D6 + 3": (2, 6, None, None, 3, "2d6+3"),
        "1d8-2": (1, 8, None, None, -2, "1d8-2"),
        "4d6kh3": (4, 6, "kh", 3, 0, "4d6kh3"),
        "2d10kl1-1": (2, 10, "kl", 1, -1, "2d10kl1-1"),
        "3d6kh2+4": (3, 6, "kh", 2, 4, "3d6kh2+4"),
    }
    for text, expected in cases.items():
        spec = gb.parse_notation(text)
        got = (spec.count, spec.sides, spec.keep, spec.keep_count,
               spec.modifier, spec.canonical)
        assert got == expected, text


def test_parse_refuses_malformed_plainly():
    bad = ["", "   ", "abc", "2d", "d", "2d6+", "2d6!", "2d6!!",
           "2d6+1d4", "0d6", "21d6", "2d1", "2d1001", "4d6kh0",
           "4d6kh5", "2d6+10001", "2d6-10001", "2dd6", "2d6kh",
           "2d6p", "-2d6", None, 42, 2.5, True, ["2d6"]]
    for text in bad:
        with pytest.raises(gb.DiceBridgeError):
            gb.parse_notation(text)


# -- Dice: the pure road --------------------------------------------------------


def test_seeded_roll_reproduces_forever():
    first = gb.roll_notation("2d6+1", seed=42, context="duel")
    second = gb.roll_notation("2d6+1", seed=42, context="duel")
    assert first.faces == second.faces
    assert first.draws == second.draws
    assert first.total == second.total
    verdict = gb.verify_roll(first.to_dict())
    assert verdict["verifiable"] is True
    assert verdict["reproduced"] is True


def test_seeded_rolls_vary_by_context_and_key():
    base = gb.roll_notation("8d6", seed=7, context="a")
    other_ctx = gb.roll_notation("8d6", seed=7, context="b")
    other_key = gb.roll_notation("8d6", seed=7, context="a", roll_key="k2")
    assert base.draws != other_ctx.draws
    assert base.draws != other_key.draws


def test_unseeded_roll_is_labelled_and_unverifiable():
    roll = gb.roll_notation("3d6")
    assert roll.seeded is False and roll.seed is None
    verdict = gb.verify_roll(roll.to_dict())
    assert verdict["verifiable"] is False
    assert verdict["reproduced"] is False
    assert "unseeded" in verdict["reason"]


def test_faces_bounds_and_total_across_seeds():
    for seed in range(25):
        roll = gb.roll_notation("3d8-2", seed=seed, context="sweep")
        assert len(roll.faces) == 3
        assert all(1 <= face <= 8 for face in roll.faces)
        assert roll.total == sum(roll.faces) - 2
        assert all(0.0 <= draw < 1.0 for draw in roll.draws)


def test_keep_highest_and_lowest_math():
    roll = gb.roll_notation("4d6kh3", seed=99, context="stat")
    assert sorted(roll.kept, reverse=True) == sorted(roll.faces, reverse=True)[:3]
    assert len(roll.dropped) == 1
    assert roll.dropped[0] == min(roll.faces)
    assert roll.total == sum(roll.kept)
    low = gb.roll_notation("4d6kl2", seed=99, context="stat")
    assert sorted(low.kept) == sorted(low.faces)[:2]
    assert low.total == sum(low.kept)


def test_verify_detects_a_tampered_record():
    roll = gb.roll_notation("2d6", seed=5, context="honest")
    data = roll.to_dict()
    data["faces"] = [1, 1] if list(roll.faces) != [1, 1] else [2, 2]
    data["total"] = sum(data["faces"])
    verdict = gb.verify_roll(data)
    assert verdict["verifiable"] is True
    assert verdict["reproduced"] is False


def test_seed_must_be_a_real_int():
    for bad_seed in (True, "42", 1.5):
        with pytest.raises(gb.DiceBridgeError):
            gb.roll_notation("1d6", seed=bad_seed)


# -- Persisted rolls -------------------------------------------------------------


def test_roll_for_chat_persists_with_provenance_and_event(tmp_path):
    user, chat = ids()
    out = gb.roll_for_chat(user, chat, "2d6+1", seed=42, context="duel",
                           target="vrchat", base_dir=tmp_path)
    assert out["actor"] == "runmal.host"
    assert out["chat_id"] == chat and out["seeded"] is True
    assert out["roll_key"] == out["id"]
    event = out["bridge_event"]
    assert event["kind"] == "dice.rolled" and event["target"] == "vrchat"
    assert event["seq"] == 1
    assert event["payload"]["total"] == out["total"]
    assert event["payload"]["faces"] == out["faces"]
    path = gb.store_path(user, tmp_path)
    assert path.exists() and path.stat().st_mode & 0o777 == 0o600
    rows = gb.list_rolls(user, chat, base_dir=tmp_path)
    assert [row["id"] for row in rows] == [out["id"]]


def test_persisted_seeded_roll_verifies(tmp_path):
    user, chat = ids()
    out = gb.roll_for_chat(user, chat, "3d6kh2", seed=11, context="c",
                           base_dir=tmp_path)
    verdict = gb.verify_persisted_roll(user, chat, out["id"], base_dir=tmp_path)
    assert verdict["roll"]["id"] == out["id"]
    assert verdict["verification"]["reproduced"] is True


def test_persisted_unseeded_roll_reports_unverifiable(tmp_path):
    user, chat = ids()
    out = gb.roll_for_chat(user, chat, "1d20", base_dir=tmp_path)
    verdict = gb.verify_persisted_roll(user, chat, out["id"], base_dir=tmp_path)
    assert verdict["verification"]["verifiable"] is False


def test_two_rolls_one_seed_stay_distinct_and_each_verifies(tmp_path):
    user, chat = ids()
    one = gb.roll_for_chat(user, chat, "2d6", seed=3, context="same",
                           base_dir=tmp_path)
    two = gb.roll_for_chat(user, chat, "2d6", seed=3, context="same",
                           base_dir=tmp_path)
    assert one["id"] != two["id"]
    assert one["roll_key"] != two["roll_key"]
    for row in (one, two):
        verdict = gb.verify_persisted_roll(user, chat, row["id"],
                                           base_dir=tmp_path)
        assert verdict["verification"]["reproduced"] is True
    events = gb.list_bridge_events(user, chat, base_dir=tmp_path)
    assert [row["seq"] for row in events] == [1, 2]


def test_get_roll_missing_raises_not_found(tmp_path):
    user, chat = ids()
    with pytest.raises(gb.DiceBridgeNotFoundError):
        gb.get_roll(user, chat, str(uuid.uuid4()), base_dir=tmp_path)


def test_rolls_are_per_chat_and_owner_isolated(tmp_path):
    user, chat = ids()
    other_user, other_chat = ids()
    mine = gb.roll_for_chat(user, chat, "1d6", seed=1, base_dir=tmp_path)
    theirs = gb.roll_for_chat(user, other_chat, "1d6", seed=2,
                              base_dir=tmp_path)
    assert [r["id"] for r in gb.list_rolls(user, chat, base_dir=tmp_path)] == [mine["id"]]
    assert [r["id"] for r in gb.list_rolls(user, other_chat, base_dir=tmp_path)] == [theirs["id"]]
    assert gb.list_rolls(other_user, chat, base_dir=tmp_path) == []


def test_corrupt_store_raises_and_is_never_reset(tmp_path):
    user, chat = ids()
    gb.roll_for_chat(user, chat, "1d6", seed=1, base_dir=tmp_path)
    path = gb.store_path(user, tmp_path)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(gb.DiceBridgeError):
        gb.list_rolls(user, chat, base_dir=tmp_path)
    assert path.read_text(encoding="utf-8") == "{not json"


def test_roll_cap_refuses_rather_than_pruning(tmp_path, monkeypatch):
    monkeypatch.setattr(gb, "MAX_ROLLS_PER_CHAT", 2)
    user, chat = ids()
    gb.roll_for_chat(user, chat, "1d6", seed=1, base_dir=tmp_path)
    gb.roll_for_chat(user, chat, "1d6", seed=2, base_dir=tmp_path)
    with pytest.raises(gb.DiceBridgeError):
        gb.roll_for_chat(user, chat, "1d6", seed=3, base_dir=tmp_path)
    assert len(gb.list_rolls(user, chat, base_dir=tmp_path)) == 2


# -- Bridge events -----------------------------------------------------------------


def test_emit_chat_message_and_game_event(tmp_path):
    user, chat = ids()
    msg = gb.emit_bridge_event(
        user, chat, "chat.message",
        {"role": "assistant", "speaker": "Yrsa", "text": "The gate holds."},
        target="skyrim", base_dir=tmp_path)
    assert msg["seq"] == 1 and msg["kind"] == "chat.message"
    assert msg["source"] == "runmal.host"
    game = gb.emit_bridge_event(
        user, chat, "game.event",
        {"game_kind": "world_event", "text": "A dragon circles overhead."},
        base_dir=tmp_path)
    assert game["seq"] == 2 and game["target"] == "generic"
    rows = gb.list_bridge_events(user, chat, base_dir=tmp_path)
    assert [row["kind"] for row in rows] == ["chat.message", "game.event"]


def test_emit_refusals_are_plain(tmp_path):
    user, chat = ids()
    with pytest.raises(gb.DiceBridgeError):
        gb.emit_bridge_event(user, chat, "dice.rolled", {}, base_dir=tmp_path)
    with pytest.raises(gb.DiceBridgeError):
        gb.emit_bridge_event(user, chat, "chat.exploded", {}, base_dir=tmp_path)
    with pytest.raises(gb.DiceBridgeError):
        gb.emit_bridge_event(user, chat, "chat.message",
                             {"role": "dm", "text": "x"}, base_dir=tmp_path)
    with pytest.raises(gb.DiceBridgeError):
        gb.emit_bridge_event(user, chat, "chat.message",
                             {"role": "user", "text": ""}, base_dir=tmp_path)
    with pytest.raises(gb.DiceBridgeError):
        gb.emit_bridge_event(user, chat, "chat.message",
                             {"role": "user", "text": "x", "extra": 1},
                             base_dir=tmp_path)
    with pytest.raises(gb.DiceBridgeError):
        gb.emit_bridge_event(user, chat, "game.event",
                             {"game_kind": "quest_done", "text": "x"},
                             base_dir=tmp_path)
    with pytest.raises(gb.DiceBridgeError):
        gb.emit_bridge_event(user, chat, "chat.message",
                             {"role": "user", "text": "x"},
                             target="minecraft", base_dir=tmp_path)
    assert gb.list_bridge_events(user, chat, base_dir=tmp_path) == []


def test_poll_after_seq_and_filters(tmp_path):
    user, chat = ids()
    gb.roll_for_chat(user, chat, "1d6", seed=1, target="vrchat",
                     base_dir=tmp_path)
    gb.emit_bridge_event(user, chat, "chat.message",
                         {"role": "user", "text": "hello"},
                         target="vrchat", base_dir=tmp_path)
    gb.emit_bridge_event(user, chat, "chat.message",
                         {"role": "assistant", "text": "hi"},
                         target="skyrim", base_dir=tmp_path)
    assert len(gb.list_bridge_events(user, chat, base_dir=tmp_path)) == 3
    tail = gb.list_bridge_events(user, chat, after_seq=1, base_dir=tmp_path)
    assert [row["seq"] for row in tail] == [2, 3]
    only_rolls = gb.list_bridge_events(user, chat, kind="dice.rolled",
                                       base_dir=tmp_path)
    assert len(only_rolls) == 1
    only_vr = gb.list_bridge_events(user, chat, target="vrchat",
                                    base_dir=tmp_path)
    assert [row["seq"] for row in only_vr] == [1, 2]


def test_ack_cursor_is_monotonic(tmp_path):
    user, chat = ids()
    gb.emit_bridge_event(user, chat, "chat.message",
                         {"role": "user", "text": "one"}, base_dir=tmp_path)
    gb.emit_bridge_event(user, chat, "chat.message",
                         {"role": "user", "text": "two"}, base_dir=tmp_path)
    out = gb.ack_bridge_events(user, chat, "vrchat-follower", 2,
                               base_dir=tmp_path)
    assert out == {"consumer": "vrchat-follower", "cursor": 2, "next_seq": 3}
    assert gb.consumer_cursor(user, chat, "vrchat-follower",
                              base_dir=tmp_path) == 2
    assert gb.consumer_cursor(user, chat, "other", base_dir=tmp_path) == 0
    with pytest.raises(gb.DiceBridgeError):
        gb.ack_bridge_events(user, chat, "vrchat-follower", 1,
                             base_dir=tmp_path)


def test_event_pruning_counts_honestly(tmp_path, monkeypatch):
    monkeypatch.setattr(gb, "MAX_EVENTS_PER_CHAT", 3)
    user, chat = ids()
    for n in range(5):
        gb.emit_bridge_event(user, chat, "chat.message",
                             {"role": "user", "text": f"m{n}"},
                             base_dir=tmp_path)
    rows = gb.list_bridge_events(user, chat, base_dir=tmp_path)
    assert [row["seq"] for row in rows] == [3, 4, 5]
    info = gb.inspect_chat(user, chat, base_dir=tmp_path)
    assert info["events"] == 3 and info["pruned_events"] == 2
    assert info["next_seq"] == 6


def test_clear_chat_is_the_only_bulk_delete(tmp_path):
    user, chat = ids()
    gb.roll_for_chat(user, chat, "1d6", seed=1, base_dir=tmp_path)
    gb.emit_bridge_event(user, chat, "chat.message",
                         {"role": "user", "text": "x"}, base_dir=tmp_path)
    removed = gb.clear_chat(user, chat, base_dir=tmp_path)
    assert removed == {"rolls": 1, "events": 2}
    assert gb.list_rolls(user, chat, base_dir=tmp_path) == []
    assert gb.list_bridge_events(user, chat, base_dir=tmp_path) == []
    assert gb.clear_chat(user, chat, base_dir=tmp_path) == {
        "rolls": 0, "events": 0}


def test_surface_document_states_no_transport():
    doc = gb.surface_document()
    assert doc["plugin_id"] == "runmal.game-bridge"
    assert doc["dice_algorithm"] == "runmal-p096-dice-v1"
    assert doc["bridge_targets"] == ["generic", "skyrim", "vrchat"]
    assert "none" in doc["transport"]


# -- Event handler: metadata only, never durable ------------------------------------


def test_handler_observes_metadata_only_and_deletes_nothing(tmp_path):
    user, chat = ids()
    gb.roll_for_chat(user, chat, "1d6", seed=1, base_dir=tmp_path)
    registry = PluginRegistry()
    _record, plugin = gb.register_plugin(registry, enable=True)
    asyncio.run(registry.dispatch_event(
        "message.created", chat_id=chat, message_id=str(uuid.uuid4()),
        data={"chat_id": chat, "role": "assistant",
              "content": "secret text that must not be kept"}))
    observed = plugin.observed_events()
    assert len(observed) == 1
    assert observed[0]["name"] == "message.created"
    assert observed[0]["content_chars"] == len(
        "secret text that must not be kept")
    assert "content" not in observed[0]
    assert "secret" not in json.dumps(observed)
    asyncio.run(registry.dispatch_event(
        "chat.deleted", chat_id=chat, data={"chat_id": chat}))
    assert len(gb.list_rolls(user, chat, base_dir=tmp_path)) == 1
    assert len(gb.list_bridge_events(user, chat, base_dir=tmp_path)) == 1


# -- HTTP surface ---------------------------------------------------------------------


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_http_roll_events_inspect_clear(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat = client.post("/api/v1/chats", json={"title": "T"})
    assert chat.status_code in (200, 201)
    chat_id = chat.json()["id"]
    rolled = client.post("/api/v1/game-bridge/roll", json={
        "chat_id": chat_id, "notation": "2d6+1", "seed": 42,
        "context": "duel", "target": "vrchat"})
    assert rolled.status_code == 200
    body = rolled.json()
    assert body["seeded"] is True and body["canonical"] == "2d6+1"
    assert body["bridge_event"]["kind"] == "dice.rolled"
    detail = client.get(f"/api/v1/game-bridge/rolls/{body['id']}",
                        params={"chat_id": chat_id})
    assert detail.status_code == 200
    assert detail.json()["verification"]["reproduced"] is True
    listed = client.get("/api/v1/game-bridge/rolls",
                        params={"chat_id": chat_id})
    assert [row["id"] for row in listed.json()["rolls"]] == [body["id"]]
    forged = client.post("/api/v1/game-bridge/events", json={
        "chat_id": chat_id, "kind": "dice.rolled", "payload": {}})
    assert forged.status_code == 422
    emitted = client.post("/api/v1/game-bridge/events", json={
        "chat_id": chat_id, "kind": "chat.message", "target": "skyrim",
        "payload": {"role": "assistant", "text": "The gate holds."}})
    assert emitted.status_code == 200 and emitted.json()["seq"] == 2
    events = client.get("/api/v1/game-bridge/events",
                        params={"chat_id": chat_id, "after_seq": 1})
    assert [row["seq"] for row in events.json()["events"]] == [2]
    acked = client.post("/api/v1/game-bridge/events/ack", json={
        "chat_id": chat_id, "consumer": "skyrim-mod", "up_to_seq": 2})
    assert acked.status_code == 200 and acked.json()["cursor"] == 2
    info = client.get("/api/v1/game-bridge/inspect",
                      params={"chat_id": chat_id})
    assert info.json()["rolls"] == 1 and info.json()["events"] == 2
    assert info.json()["cursors"] == {"skyrim-mod": 2}
    cleared = client.post("/api/v1/game-bridge/clear",
                          json={"chat_id": chat_id})
    assert cleared.json()["removed"] == {"rolls": 1, "events": 2}


def test_http_refusals_and_unknowns(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat = client.post("/api/v1/chats", json={"title": "T"})
    chat_id = chat.json()["id"]
    bad = client.post("/api/v1/game-bridge/roll", json={
        "chat_id": chat_id, "notation": "2d6+1d4"})
    assert bad.status_code == 422
    unknown_chat = client.post("/api/v1/game-bridge/roll", json={
        "chat_id": str(uuid.uuid4()), "notation": "1d6"})
    assert unknown_chat.status_code == 404
    missing = client.get(
        f"/api/v1/game-bridge/rolls/{uuid.uuid4()}",
        params={"chat_id": chat_id})
    assert missing.status_code == 404
    unknown_list = client.get("/api/v1/game-bridge/events",
                              params={"chat_id": str(uuid.uuid4())})
    assert unknown_list.status_code == 404


# -- Neighbours --------------------------------------------------------------------------


def test_migration_head_stays_0041():
    assert MIGRATIONS[-1][0] == "0041"
    assert "0042" not in [row[0] for row in MIGRATIONS]


def test_current_revision_is_0041(tmp_path):
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
