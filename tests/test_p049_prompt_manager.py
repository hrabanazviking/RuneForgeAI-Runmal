"""P-049 Prompt manager battery (BUILDER-3).

Pins the prompt-manager contract: default layout is an exact
identity on the baseline assembly, layout validation/fill-missing,
apply_layout drop/reorder/depth/managed-block semantics, the
resolve/echo service, and the inspector API surface (trace discards
with reason prompt_manager_disabled, ledger exclusion, 422s, and
the /debug/prompt-manager/default endpoint).
"""

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.prompt.composer import compose
from runmal.prompt.manager import (
    BLOCK_ORDER,
    apply_layout,
    block_for_kind,
    default_layout,
    layout_from_data,
    layout_to_data,
)
from runmal.prompt.service import layout_echo, resolve_layout
from runmal.prompt.slots import BASELINE_INDEX, BASELINE_ORDER, make_slot

FIXTURES = Path(__file__).parent / "fixtures" / "cards"
V2_CARD = json.loads((FIXTURES / "v2.json").read_text())
CTX = dict(context_limit=4096, reserve_response=512)


def layout_with(order=None, disabled=()):
    names = list(order) if order is not None else list(BLOCK_ORDER)
    return layout_from_data(
        [{"block": n, "enabled": n not in disabled} for n in names]
    )


def layout_payload(order=None, disabled=()):
    names = list(order) if order is not None else list(BLOCK_ORDER)
    return {
        "blocks": [{"block": n, "enabled": n not in disabled} for n in names]
    }


def all_kind_slots():
    slots = []
    for kind in BASELINE_ORDER:
        if kind == "history":
            slots.append(
                make_slot(kind, "user", "", id=f"s/{kind}", splittable=True, parts=("h1", "h2"))
            )
        else:
            slots.append(make_slot(kind, "system", f"content-{kind}", id=f"s/{kind}"))
    return slots


# ---------------- pure: default layout + identity ----------------

def test_default_layout_blocks_and_roundtrip():
    layout = default_layout()
    assert [b.block for b in layout.blocks] == list(BLOCK_ORDER)
    assert all(b.enabled for b in layout.blocks)
    data = layout_to_data(layout)
    assert layout_from_data(data) == layout
    assert layout_from_data(data["blocks"]) == layout
    assert layout_to_data(layout_from_data(data)) == data


def test_default_layout_identity_order():
    kept, dropped = apply_layout(all_kind_slots(), default_layout())
    assert dropped == []
    assert [s.kind for s in sorted(kept, key=lambda s: s.order)] == list(BASELINE_ORDER)


def test_default_layout_compose_identity():
    slots = all_kind_slots()
    kept, _ = apply_layout(slots, default_layout())
    plain = compose(list(slots), **CTX)
    managed = compose(kept, **CTX)
    assert [m.slot_id for m in managed.messages] == [m.slot_id for m in plain.messages]
    assert [m.content for m in managed.messages] == [m.content for m in plain.messages]


# ---------------- pure: validation ----------------

@pytest.mark.parametrize("bad", [
    [{"block": "nope"}],
    [{"block": "persona"}, {"block": "persona"}],
    ["persona"],
    [42],
    [{"block": "persona", "enabled": "true"}],
    [{"block": "persona", "enabled": 1}],
    [],
    "persona",
    42,
    {},
    {"foo": []},
    {"blocks": "persona"},
])
def test_layout_validation_rejects(bad):
    with pytest.raises(ValueError):
        layout_from_data(bad)


# ---------------- pure: fill-missing ----------------

def test_fill_missing_completes_layout():
    layout = layout_from_data([{"block": "lore_before", "enabled": False}])
    assert [b.block for b in layout.blocks] == list(BLOCK_ORDER)
    assert layout.is_enabled("lore_before") is False
    assert layout.position("lore_before") == list(BLOCK_ORDER).index("lore_before")
    assert all(layout.is_enabled(n) for n in BLOCK_ORDER if n != "lore_before")


def test_fill_missing_partial_reorder_keeps_relative_order():
    layout = layout_from_data([{"block": "history"}, {"block": "persona"}])
    assert len(layout.blocks) == len(BLOCK_ORDER)
    assert layout.position("history") < layout.position("persona")


# ---------------- pure: apply (drop / reorder) ----------------

def test_disabled_persona_drops_slot():
    persona = make_slot("persona", "system", "PERSONA", id="persona/x")
    system = make_slot("main_system", "system", "SYS", id="system/main", required=True)
    kept, dropped = apply_layout([system, persona], layout_with(disabled={"persona"}))
    assert [s.id for s in dropped] == ["persona/x"]
    assert [s.id for s in kept] == ["system/main"]


def test_disabled_system_drops_required_slot():
    system = make_slot("main_system", "system", "SYS", id="system/main", required=True)
    kept, dropped = apply_layout([system], layout_with(disabled={"system"}))
    assert kept == []
    assert [s.id for s in dropped] == ["system/main"]


def test_reorder_persona_after_history_changes_compose_order():
    order = [n for n in BLOCK_ORDER if n != "persona"]
    order.insert(order.index("history") + 1, "persona")
    slots = [
        make_slot("main_system", "system", "SYS", id="system/main", required=True),
        make_slot("persona", "system", "PERSONA", id="persona/x"),
        make_slot("history", "user", "", id="history", splittable=True, parts=("h1",)),
    ]
    kept, dropped = apply_layout(slots, layout_with(order=order))
    assert dropped == []
    ids = [m.slot_id for m in compose(kept, **CTX).messages]
    assert ids == ["system/main", "history", "persona/x"]


def test_lore_after_moved_before_lore_before_honoured():
    order = list(BLOCK_ORDER)
    order.remove("lore_after")
    order.insert(order.index("lore_before"), "lore_after")
    slots = [
        make_slot("lore_before", "system", "BEFORE", id="lore/b"),
        make_slot("lore_after", "system", "AFTER", id="lore/a"),
    ]
    kept, _ = apply_layout(slots, layout_with(order=order))
    ids = [m.slot_id for m in compose(kept, **CTX).messages]
    assert ids == ["lore/a", "lore/b"]


# ---------------- pure: depth (S206 splice contract) ----------------

def _depth_slot():
    return make_slot("lore_before", "system", "DEPTHNOTE", id="depth1", depth=1)


def _history_slot():
    return make_slot("history", "user", "", id="history", splittable=True, parts=("m1", "m2", "m3"))


def test_depth_splices_even_when_block_first():
    order = ["lore_before"] + [n for n in BLOCK_ORDER if n != "lore_before"]
    kept, dropped = apply_layout([_depth_slot(), _history_slot()], layout_with(order=order))
    assert dropped == []
    msgs = compose(kept, **CTX).messages
    assert [(m.slot_id, m.content) for m in msgs] == [
        ("history", "m1\nm2"), ("depth1", "DEPTHNOTE"), ("history", "m3")]


def test_depth_plain_when_history_disabled():
    system = make_slot("main_system", "system", "SYS", id="system/main", required=True)
    kept, dropped = apply_layout(
        [system, _depth_slot(), _history_slot()], layout_with(disabled={"history"}))
    assert [s.id for s in dropped] == ["history"]
    msgs = compose(kept, **CTX).messages
    assert [m.slot_id for m in msgs] == ["system/main", "depth1"]
    assert msgs[1].content == "DEPTHNOTE"


def test_depth_dropped_when_its_block_disabled():
    kept, dropped = apply_layout(
        [_depth_slot(), _history_slot()], layout_with(disabled={"lore_before"}))
    assert [s.id for s in dropped] == ["depth1"]
    assert [s.id for s in kept] == ["history"]


# ---------------- pure: managed post_history block / mapping / migration ----------------

def test_post_history_managed_block_order_value():
    post = make_slot("post_history", "system", "POST", id="post/1")
    layout = default_layout()
    kept, dropped = apply_layout([post], layout)
    assert dropped == []
    # Managed since P-057: order = block position * 100 + baseline index.
    # The default layout puts the post_history block last (position 9),
    # so 9 * 100 + 9 == 909 -- the same value the old unmanaged tail
    # produced, now with managed meaning.
    assert layout.position("post_history") == 9
    assert kept[0].order == 9 * 100 + 9 == 909


def test_post_history_composes_last_even_if_authors_note_first():
    order = ["authors_note"] + [n for n in BLOCK_ORDER if n != "authors_note"]
    slots = [
        make_slot("authors_note", "system", "NOTE", id="note/1"),
        make_slot("post_history", "system", "POST", id="post/1"),
        make_slot("main_system", "system", "SYS", id="system/main", required=True),
    ]
    kept, _ = apply_layout(slots, layout_with(order=order))
    ids = [m.slot_id for m in compose(kept, **CTX).messages]
    assert ids[0] == "note/1"
    # post_history follows its BLOCK position: it is still the last
    # block in this layout, so it still composes last -- as a managed
    # block now, not as an unmanaged tail.
    assert ids[-1] == "post/1"


def test_post_history_block_disabled_drops_slot():
    post = make_slot("post_history", "system", "POST", id="post/1")
    kept, dropped = apply_layout([post], layout_with(disabled={"post_history"}))
    assert kept == []
    assert [s.id for s in dropped] == ["post/1"]


def test_block_for_kind_mapping():
    assert block_for_kind("main_system") == "system"
    assert block_for_kind("persona") == "persona"
    assert block_for_kind("memory_nucleus") == "memory_nucleus"
    assert block_for_kind("memory_retrieved") == "memory_retrieved"
    assert block_for_kind("lore_before") == "lore_before"
    assert block_for_kind("lore_after") == "lore_after"
    assert block_for_kind("examples") == "examples"
    assert block_for_kind("history") == "history"
    assert block_for_kind("authors_note") == "authors_note"
    assert block_for_kind("post_history") == "post_history"
    assert block_for_kind("no-such-kind") is None


def test_migration_head_is_0035_provisional():
    assert MIGRATIONS[-1][0] == "0035"  # PROVISIONAL 0035 (P-057); P-056 provisional 0034 banks first


# ---------------- service ----------------

def test_resolve_layout_none_is_default():
    assert resolve_layout(None) == (None, "default")


def test_resolve_layout_explicit_list_and_dict():
    layout, source = resolve_layout([{"block": "persona", "enabled": False}])
    assert source == "explicit"
    assert layout is not None and layout.is_enabled("persona") is False
    layout2, source2 = resolve_layout({"blocks": [{"block": "persona", "enabled": False}]})
    assert source2 == "explicit" and layout2 == layout


def test_resolve_layout_invalid_raises():
    with pytest.raises(ValueError):
        resolve_layout([{"block": "nope"}])


def test_layout_echo_default_and_explicit():
    echo = layout_echo(None, "default")
    assert echo["source"] == "default"
    assert echo["blocks"] == layout_to_data(default_layout())["blocks"]
    layout, _ = resolve_layout([{"block": "persona", "enabled": False}])
    echo2 = layout_echo(layout, "explicit")
    assert echo2["source"] == "explicit"
    assert echo2["blocks"] == layout_to_data(layout)["blocks"]


# ---------------- inspector / API (s215 harness) ----------------

def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def seed_world(client, token_budget=None):
    card = copy.deepcopy(V2_CARD)
    card["name"] = "Bryn"
    card["description"] = "A smith of the harbor town."
    character = client.post("/api/v1/characters", json={"card": card}).json()["id"]
    book = client.post(
        "/api/v1/lorebooks", json={"name": "World", "token_budget": token_budget}
    ).json()
    entries = {}
    for name, content, keys in (
        ("Harbor", "The harbor freezes hard in deep winter months.", ["harbor"]),
        ("Distant", "Far away and never mentioned here at all.", ["zzz-absent"]),
        ("Anchor", "Always present anchor entry text.", []),
    ):
        created = client.post(
            f"/api/v1/lorebooks/{book['id']}/entries",
            json={"name": name, "content": content, "keys": keys, "constant": name == "Anchor"},
        )
        entries[name] = created.json()["id"]
    return character, book["id"], entries


def _inspect(client, **kw):
    resp = client.post("/api/v1/debug/prompt-inspect", json=kw)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_api_no_layout_default_source_system_included(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    character, _, _ = seed_world(client)
    result = _inspect(client, character_id=character, messages=["hello"])
    assert result["prompt_layout"]["source"] == "default"
    by_id = {s["slot_id"]: s for s in result["slots"]}
    assert by_id["system/main"]["status"] == "included"
    assert by_id[f"persona/{character}"]["status"] == "included"


def test_api_disable_persona_trace_and_ledger(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    character, _, _ = seed_world(client)
    base = _inspect(client, character_id=character, messages=["hello"])
    base_by = {s["slot_id"]: s for s in base["slots"]}
    persona_id = f"persona/{character}"
    persona_tokens = base_by[persona_id]["tokens"]
    assert persona_tokens > 0
    result = _inspect(client, character_id=character, messages=["hello"],
                      prompt_layout=layout_payload(disabled={"persona"}))
    by_id = {s["slot_id"]: s for s in result["slots"]}
    slot = by_id[persona_id]
    assert slot["status"] == "discarded"
    assert slot["reason"] == "prompt_manager_disabled"
    assert slot["kind"] == "persona" and slot["role"] == "system"
    assert slot["tokens"] == persona_tokens
    assert result["ledger"]["total_input_tokens"] == (
        base["ledger"]["total_input_tokens"] - persona_tokens
    )
    assert result["prompt_layout"]["source"] == "explicit"


def test_api_reorder_persona_after_history_trace_order(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    character, _, _ = seed_world(client)
    order = [n for n in BLOCK_ORDER if n != "persona"]
    order.insert(order.index("history") + 1, "persona")
    result = _inspect(client, character_id=character, messages=["hello"],
                      prompt_layout=layout_payload(order=order))
    included = [s["slot_id"] for s in result["slots"] if s["status"] == "included"]
    assert included.index(f"persona/{character}") > included.index("history")


def test_api_explicit_default_equals_no_layout_except_source(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    character, book_id, _ = seed_world(client)
    kw = dict(
        character_id=character, lorebook_ids=[book_id], messages=["Down at the harbor today."]
    )
    plain = _inspect(client, **kw)
    explicit = _inspect(client, prompt_layout=layout_payload(), **kw)
    assert plain["prompt_layout"]["source"] == "default"
    assert explicit["prompt_layout"]["source"] == "explicit"
    assert explicit["prompt_layout"]["blocks"] == plain["prompt_layout"]["blocks"]
    assert explicit["slots"] == plain["slots"]
    assert explicit["ledger"] == plain["ledger"]


def test_api_invalid_layout_422(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.post("/api/v1/debug/prompt-inspect", json={
        "messages": ["hi"],
        "prompt_layout": {"blocks": [{"block": "nope", "enabled": True}]},
    })
    assert resp.status_code == 422, resp.text


def test_api_prompt_manager_default_endpoint(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.get("/api/v1/debug/prompt-manager/default")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "default"
    assert body["blocks"] == layout_to_data(default_layout())["blocks"]


def test_api_disable_lore_drops_anchor(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    _, book_id, entries = seed_world(client)
    result = _inspect(client, lorebook_ids=[book_id], messages=["hello"],
                      prompt_layout=layout_payload(disabled={"lore_before", "lore_after"}))
    by_id = {s["slot_id"]: s for s in result["slots"]}
    anchor = by_id[f"lore/{entries['Anchor']}"]
    assert anchor["status"] == "discarded"
    assert anchor["reason"] == "prompt_manager_disabled"


def test_api_disable_system_still_composes(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    character, _, _ = seed_world(client)
    result = _inspect(client, character_id=character, messages=["hello"],
                      prompt_layout=layout_payload(disabled={"system"}))
    by_id = {s["slot_id"]: s for s in result["slots"]}
    slot = by_id["system/main"]
    assert slot["status"] == "discarded"
    assert slot["reason"] == "prompt_manager_disabled"
    assert slot["kind"] == "main_system"
