"""P-057 Post-history instructions battery (TESTER).

Pins the post-history contract: the instructions as validated data
(defaults, strict rejection), the baseline-last slot, composer
position (after history, including with no history), prompt-manager
citizenship (managed block, default order 909, disable drops,
pre-P-057 layout fill-in), the per-chat API (default on create,
round-trip, isolation, 404, 422, and an event log that never
carries instruction text), chat_to_dict defensive reads, the
inspector wiring (S214: chat slot after history, character
fallback, chat precedence, metadata-only echo, text NOWHERE in an
inspect result), and PROVISIONAL migration 0035
(chats.post_history_json).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.chats.service import chat_to_dict
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Chat
from runmal.prompt.composer import compose
from runmal.prompt.manager import (
    BLOCK_KINDS,
    BLOCK_ORDER,
    apply_layout,
    block_for_kind,
    default_layout,
    layout_from_data,
    layout_to_data,
)
from runmal.prompt.post_history import (
    PostHistoryInstructions,
    has_content,
    instructions_from_data,
    instructions_to_data,
    slot_for,
)
from runmal.prompt.slots import make_slot

CTX = dict(context_limit=4096, reserve_response=512)
DEFAULT_PH = {"text": "", "enabled": True, "role": "system"}
SECRET = "ZqxPostHistorySecret57"

# ---------------- pure: defaults + round-trip ----------------

def test_ph_defaults_from_none_and_empty():
    assert PostHistoryInstructions() == PostHistoryInstructions(
        text="", enabled=True, role="system"
    )
    assert instructions_from_data(None) == PostHistoryInstructions()
    assert instructions_from_data({}) == PostHistoryInstructions()
    assert instructions_to_data(PostHistoryInstructions()) == DEFAULT_PH
    assert instructions_to_data(instructions_from_data(None)) == DEFAULT_PH


def test_ph_partial_data_fills_defaults():
    ph = instructions_from_data({"text": "hi"})
    assert ph.text == "hi"
    assert (ph.enabled, ph.role) == (True, "system")
    ph = instructions_from_data({"role": "user", "enabled": False})
    assert (ph.text, ph.enabled, ph.role) == ("", False, "user")


def test_ph_round_trip_full():
    data = {"text": "Stay in character.", "enabled": False, "role": "assistant"}
    ph = instructions_from_data(data)
    assert instructions_to_data(ph) == data
    assert instructions_from_data(instructions_to_data(ph)) == ph
    assert instructions_from_data(json.loads(json.dumps(data))) == ph

# ---------------- pure: validation rejects ----------------

@pytest.mark.parametrize("bad", [
    {"bogus": 1},
    {"text": "x", "extra": None},
    {"text": 42},
    {"text": None},
    {"enabled": "yes"},
    {"enabled": 1},
    {"enabled": 0},
    {"role": "narrator"},
    {"role": ""},
    {"role": None},
])
def test_ph_from_data_rejects(bad):
    with pytest.raises(ValueError):
        instructions_from_data(bad)


@pytest.mark.parametrize("bad", ["x", 42, 3.5, ["text"], True])
def test_ph_from_data_rejects_non_dict(bad):
    with pytest.raises(ValueError):
        instructions_from_data(bad)


def test_ph_direct_construction_rejects():
    with pytest.raises(ValueError):
        PostHistoryInstructions(text=42)
    with pytest.raises(ValueError):
        PostHistoryInstructions(enabled="yes")
    with pytest.raises(ValueError):
        PostHistoryInstructions(enabled=1)
    with pytest.raises(ValueError):
        PostHistoryInstructions(role="narrator")
    with pytest.raises(ValueError):
        PostHistoryInstructions(role="")

# ---------------- pure: has_content / slot_for ----------------

@pytest.mark.parametrize("ph,expected", [
    (PostHistoryInstructions(text=""), False),
    (PostHistoryInstructions(text="   \n\t "), False),
    (PostHistoryInstructions(text="x", enabled=False), False),
    (PostHistoryInstructions(text="", enabled=False), False),
    (PostHistoryInstructions(text=" x "), True),
    (PostHistoryInstructions(text="x", enabled=True), True),
])
def test_ph_has_content(ph, expected):
    assert has_content(ph) is expected


def test_ph_slot_for_none_without_content():
    assert slot_for(PostHistoryInstructions(text=""), "chat") is None
    assert slot_for(PostHistoryInstructions(text="   "), "chat") is None
    assert slot_for(PostHistoryInstructions(text="x", enabled=False), "chat") is None
    assert slot_for(PostHistoryInstructions(text=""), "character") is None


@pytest.mark.parametrize("source", ["user", "", "system", None, "CHAT"])
def test_ph_slot_for_rejects_bad_source(source):
    # Source is validated BEFORE the content check: a bad source
    # raises even for instructions that would produce no slot.
    with pytest.raises(ValueError):
        slot_for(PostHistoryInstructions(text="T"), source)
    with pytest.raises(ValueError):
        slot_for(PostHistoryInstructions(text=""), source)


def test_ph_slot_for_chat_fields():
    slot = slot_for(PostHistoryInstructions(text="T"), "chat")
    assert slot is not None
    assert slot.kind == "post_history"
    assert slot.id == "post_history/chat"
    assert slot.provenance == "chat:post_history"
    assert slot.role == "system"
    assert slot.content == "T"
    assert slot.depth is None
    assert slot.order == 9  # baseline-last: BASELINE_INDEX["post_history"]


def test_ph_slot_for_character_fields_and_role():
    slot = slot_for(PostHistoryInstructions(text="T", role="user"), "character")
    assert slot is not None
    assert slot.kind == "post_history"
    assert slot.id == "post_history/character"
    assert slot.provenance == "character:post_history"
    assert slot.role == "user"
    assert slot.order == 9

# ---------------- composer position ----------------

def _history_slot(parts):
    return make_slot(
        "history", "user", "", id="history", splittable=True, parts=tuple(parts)
    )


def test_compose_post_history_last_after_history():
    ph = slot_for(PostHistoryInstructions(text="LAST WORD"), "chat")
    assert ph is not None
    composed = compose([_history_slot(["m1", "m2", "m3"]), ph], **CTX)
    assert [(m.slot_id, m.role, m.content) for m in composed.messages] == [
        ("history", "user", "m1\nm2\nm3"),
        ("post_history/chat", "system", "LAST WORD"),
    ]


def test_compose_post_history_without_history_still_emitted_last():
    # No history slot at all: the slot still composes, last by its
    # baseline order (after a system slot), even when handed to the
    # composer first.
    system = make_slot("main_system", "system", "SYS", id="system/main", required=True)
    ph = slot_for(PostHistoryInstructions(text="TAIL", role="user"), "chat")
    assert ph is not None
    composed = compose([ph, system], **CTX)
    assert [(m.slot_id, m.role, m.content) for m in composed.messages] == [
        ("system/main", "system", "SYS"),
        ("post_history/chat", "user", "TAIL"),
    ]

# ---------------- prompt-manager citizenship ----------------

def _layout_with(order=None, disabled=()):
    names = list(order) if order is not None else list(BLOCK_ORDER)
    return layout_from_data(
        [{"block": n, "enabled": n not in disabled} for n in names]
    )


def test_manager_block_citizenship():
    assert block_for_kind("post_history") == "post_history"
    assert BLOCK_KINDS["post_history"] == ("post_history",)
    assert len(BLOCK_ORDER) == 10
    assert BLOCK_ORDER[-1] == "post_history"
    layout = default_layout()
    assert [b.block for b in layout.blocks] == list(BLOCK_ORDER)
    assert all(b.enabled for b in layout.blocks)
    assert layout_from_data(layout_to_data(layout)) == layout


def test_manager_default_layout_order_909():
    ph = slot_for(PostHistoryInstructions(text="T"), "chat")
    assert ph is not None
    kept, dropped = apply_layout([ph], default_layout())
    assert dropped == []
    assert len(kept) == 1
    assert kept[0].order == 909  # block position 9 * 100 + baseline 9


def test_manager_disabled_block_drops_slot():
    ph = slot_for(PostHistoryInstructions(text="T"), "chat")
    assert ph is not None
    kept, dropped = apply_layout([ph], _layout_with(disabled={"post_history"}))
    assert kept == []
    assert [s.id for s in dropped] == ["post_history/chat"]


def test_manager_authors_note_first_post_history_still_last():
    order = ["authors_note"] + [b for b in BLOCK_ORDER if b != "authors_note"]
    slots = [
        _history_slot(["m1", "m2"]),
        slot_for(PostHistoryInstructions(text="TAIL"), "chat"),
        make_slot("authors_note", "system", "NOTE", id="authors_note/chat"),
    ]
    kept, dropped = apply_layout(slots, _layout_with(order=order))
    assert dropped == []
    composed = compose(kept, **CTX)
    assert [m.slot_id for m in composed.messages] == [
        "authors_note/chat", "history", "post_history/chat",
    ]


def test_manager_pre_p057_layout_fills_post_history_at_end():
    # A stored 9-block layout written before P-057 (no post_history
    # entry) must fill the block in, enabled, at the end.
    old_names = [b for b in BLOCK_ORDER if b != "post_history"]
    assert len(old_names) == 9
    layout = layout_from_data([{"block": n} for n in old_names])
    assert [b.block for b in layout.blocks] == list(BLOCK_ORDER)
    assert layout.blocks[-1].block == "post_history"
    assert layout.blocks[-1].enabled is True
    ph = slot_for(PostHistoryInstructions(text="T"), "chat")
    kept, dropped = apply_layout([ph], layout)
    assert dropped == [] and kept[0].order == 909

# ---------------- API harness ----------------

def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _make_chat(client, title="Hall"):
    resp = client.post("/api/v1/chats", json={"title": title})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _set_ph(client, chat_id, payload):
    resp = client.post(f"/api/v1/chats/{chat_id}/post-history", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _get_ph(client, chat_id):
    resp = client.get(f"/api/v1/chats/{chat_id}/post-history")
    assert resp.status_code == 200, resp.text
    return resp.json()

# ---------------- API: per-chat post-history ----------------

def test_create_chat_carries_default_post_history(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = _make_chat(client)
    assert created["post_history"] == DEFAULT_PH
    fetched = client.get(f"/api/v1/chats/{created['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["post_history"] == DEFAULT_PH
    assert _get_ph(client, created["id"]) == DEFAULT_PH


def test_post_history_round_trip_via_get(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _make_chat(client)["id"]
    payload = {"text": "Answer as the harbourmaster.", "enabled": True, "role": "user"}
    updated = _set_ph(client, chat_id, payload)
    assert updated["post_history"] == payload
    assert _get_ph(client, chat_id) == payload
    fetched = client.get(f"/api/v1/chats/{chat_id}").json()
    assert fetched["post_history"] == payload


def test_post_history_per_chat_isolation(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    first = _make_chat(client, "One")["id"]
    second = _make_chat(client, "Two")["id"]
    ph_a = {"text": "Instructions A", "enabled": True, "role": "system"}
    ph_b = {"text": "Instructions B", "enabled": False, "role": "assistant"}
    _set_ph(client, first, ph_a)
    _set_ph(client, second, ph_b)
    assert _get_ph(client, first) == ph_a
    assert _get_ph(client, second) == ph_b


def test_post_history_missing_chat_404(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.post("/api/v1/chats/missing/post-history", json={"text": "x"})
    assert resp.status_code == 404, resp.text
    resp = client.get("/api/v1/chats/missing/post-history")
    assert resp.status_code == 404, resp.text


def test_post_history_invalid_role_422_stores_nothing(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _make_chat(client)["id"]
    resp = client.post(
        f"/api/v1/chats/{chat_id}/post-history",
        json={"text": "x", "enabled": True, "role": "narrator"},
    )
    assert resp.status_code == 422, resp.text
    # A refused payload stores nothing: still the default.
    assert _get_ph(client, chat_id) == DEFAULT_PH


def test_post_history_event_log_carries_no_text(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _make_chat(client)["id"]
    payload = {"text": SECRET + " hold the last word.", "enabled": True, "role": "user"}
    _set_ph(client, chat_id, payload)
    resp = client.get(f"/api/v1/chats/{chat_id}/events")
    assert resp.status_code == 200, resp.text
    events = resp.json()
    changed = [e for e in events if e["kind"] == "post_history.changed"]
    assert len(changed) == 1
    assert changed[0]["data"] == {"enabled": True, "role": "user"}
    assert SECRET not in json.dumps(events)
    assert payload["text"] not in json.dumps(events)

# ---------------- chat_to_dict defensive reads ----------------

def test_chat_to_dict_post_history_defaults_and_stored():
    stamp = datetime(2026, 11, 7, tzinfo=UTC)
    empty = Chat(
        id="chat-empty", user_id="user-1", title="T",
        post_history_json="{}", created_at=stamp,
    )
    assert chat_to_dict(empty)["post_history"] == DEFAULT_PH
    bare = Chat(id="chat-bare", user_id="user-1", title="T", created_at=stamp)
    assert chat_to_dict(bare)["post_history"] == DEFAULT_PH
    unset = Chat(
        id="chat-unset", user_id="user-1", title="T",
        post_history_json=None, created_at=stamp,
    )
    assert chat_to_dict(unset)["post_history"] == DEFAULT_PH
    corrupt = Chat(
        id="chat-corrupt", user_id="user-1", title="T",
        post_history_json="{not json", created_at=stamp,
    )
    assert chat_to_dict(corrupt)["post_history"] == DEFAULT_PH
    invalid = Chat(
        id="chat-invalid", user_id="user-1", title="T",
        post_history_json=json.dumps({"text": "x", "role": "narrator"}),
        created_at=stamp,
    )
    assert chat_to_dict(invalid)["post_history"] == DEFAULT_PH
    stored = {"text": "Kept.", "enabled": False, "role": "assistant"}
    filled = Chat(
        id="chat-filled", user_id="user-1", title="T",
        post_history_json=json.dumps(stored), created_at=stamp,
    )
    assert chat_to_dict(filled)["post_history"] == stored

# ---------------- inspector ----------------

def _inspect(client, **kw):
    resp = client.post("/api/v1/debug/prompt-inspect", json=kw)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _layout_disabling(block):
    return {
        "blocks": [
            {"block": name, "enabled": name != block} for name in BLOCK_ORDER
        ]
    }


def _slot(result, slot_id):
    by_id = {s["slot_id"]: s for s in result["slots"]}
    assert slot_id in by_id, result["slots"]
    return by_id[slot_id]


def _make_character(client, ph_text, name="Sigrun"):
    payload = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "name": name,
        "description": "A test seer.",
        "personality": "Calm.",
        "scenario": "A test hall.",
        "first_mes": "Hail!",
        "mes_example": "",
        "creator_notes": "",
        "system_prompt": "",
        "post_history_instructions": ph_text,
        "alternate_greetings": [],
        "tags": [],
        "creator": "test",
        "extensions": {},
    }
    resp = client.post("/api/v1/characters", json={"card": payload})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def test_inspect_chat_slot_after_history_text_nowhere(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _make_chat(client)["id"]
    _set_ph(client, chat_id, {
        "text": SECRET + " hold the last word.", "enabled": True, "role": "user",
    })
    result = _inspect(client, chat_id=chat_id, messages=["m1", "m2", "m3"])
    slot = _slot(result, "post_history/chat")
    assert slot["status"] == "included"
    assert slot["kind"] == "post_history"
    assert slot["role"] == "user"
    assert slot["provenance"] == "chat:post_history"
    # Trace order is composition order: the post-history slot comes
    # AFTER the history slot.
    ids = [s["slot_id"] for s in result["slots"]]
    assert ids.index("post_history/chat") > ids.index("history")
    assert result["post_history"] == {
        "present": True, "enabled": True, "role": "user", "source": "chat",
    }
    # S214: the instruction text appears NOWHERE in the result.
    assert SECRET not in json.dumps(result)


def test_inspect_character_fallback(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    char = _make_character(client, SECRET + " from the card.")
    chat_id = _make_chat(client)["id"]  # chat itself carries nothing
    result = _inspect(
        client, chat_id=chat_id, character_id=char["id"], messages=["m1", "m2"]
    )
    slot = _slot(result, "post_history/character")
    assert slot["status"] == "included"
    assert slot["kind"] == "post_history"
    assert slot["provenance"] == "character:post_history"
    ids = [s["slot_id"] for s in result["slots"]]
    assert ids.index("post_history/character") > ids.index("history")
    assert "post_history/chat" not in ids
    assert result["post_history"] == {
        "present": True, "enabled": True, "role": "system", "source": "character",
    }
    assert SECRET not in json.dumps(result)


def test_inspect_chat_precedence_over_character(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    char_secret = "ZqxCharacterCardSecret57"
    char = _make_character(client, char_secret + " from the card.")
    chat_id = _make_chat(client)["id"]
    _set_ph(client, chat_id, {
        "text": SECRET + " from the chat.", "enabled": True, "role": "assistant",
    })
    result = _inspect(
        client, chat_id=chat_id, character_id=char["id"], messages=["m1"]
    )
    ph_slots = [s for s in result["slots"] if s["kind"] == "post_history"]
    assert [s["slot_id"] for s in ph_slots] == ["post_history/chat"]
    assert result["post_history"] == {
        "present": True, "enabled": True, "role": "assistant", "source": "chat",
    }
    assert SECRET not in json.dumps(result)
    assert char_secret not in json.dumps(result)


def test_inspect_disabled_chat_falls_back_to_character(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    char = _make_character(client, SECRET + " from the card.", name="Fallbacka")
    chat_id = _make_chat(client)["id"]
    _set_ph(client, chat_id, {
        "text": "ZqxDisabledChatSecret57", "enabled": False, "role": "user",
    })
    result = _inspect(
        client, chat_id=chat_id, character_id=char["id"], messages=["m1"]
    )
    slot = _slot(result, "post_history/character")
    assert slot["status"] == "included"
    assert "post_history/chat" not in [s["slot_id"] for s in result["slots"]]
    assert result["post_history"] == {
        "present": True, "enabled": True, "role": "system", "source": "character",
    }
    assert SECRET not in json.dumps(result)
    assert "ZqxDisabledChatSecret57" not in json.dumps(result)


def test_inspect_empty_and_disabled_match_no_instructions(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    plain = _make_chat(client, "Plain")["id"]
    empty = _make_chat(client, "Empty")["id"]
    _set_ph(client, empty, {"text": "   ", "enabled": True, "role": "system"})
    disabled = _make_chat(client, "Disabled")["id"]
    _set_ph(client, disabled, {"text": SECRET, "enabled": False, "role": "system"})
    results = {
        name: _inspect(client, chat_id=cid, messages=["m1", "m2"])
        for name, cid in (("plain", plain), ("empty", empty), ("disabled", disabled))
    }
    id_lists = {
        name: [s["slot_id"] for s in r["slots"]] for name, r in results.items()
    }
    assert id_lists["empty"] == id_lists["plain"]
    assert id_lists["disabled"] == id_lists["plain"]
    assert "post_history/chat" not in id_lists["plain"]
    for result in results.values():
        assert result["post_history"]["present"] is False
    assert SECRET not in json.dumps(results["disabled"])


def test_inspect_layout_disabled_discards_slot(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _make_chat(client)["id"]
    _set_ph(client, chat_id, {"text": SECRET, "enabled": True, "role": "system"})
    result = _inspect(
        client, chat_id=chat_id, messages=["m1", "m2"],
        prompt_layout=_layout_disabling("post_history"),
    )
    slot = _slot(result, "post_history/chat")
    assert slot["status"] == "discarded"
    assert slot["reason"] == "prompt_manager_disabled"
    # The echo reports the pre-layout resolution honestly.
    assert result["post_history"]["present"] is True
    assert result["post_history"]["source"] == "chat"
    assert SECRET not in json.dumps(result)


def test_inspect_no_chat_no_character_echo_none(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    result = _inspect(client, messages=["hi"])
    assert result["post_history"] == {
        "present": False, "enabled": True, "role": "system", "source": "none",
    }
    assert not [s for s in result["slots"] if s["kind"] == "post_history"]


def test_inspect_missing_chat_404(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/api/v1/debug/prompt-inspect", json={"chat_id": "missing", "messages": ["hi"]}
    )
    assert resp.status_code == 404, resp.text


def test_inspect_corrupt_chat_json_falls_back_to_character(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat = _make_chat(client)
    char = _make_character(client, SECRET + " from the card.", name="Corrupta")
    conn = sqlite3.connect(tmp_path / "test.db")
    try:
        conn.execute(
            "UPDATE chats SET post_history_json = ? WHERE id = ?",
            ("{not json", chat["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    result = _inspect(
        client, chat_id=chat["id"], character_id=char["id"], messages=["m1"]
    )
    slot = _slot(result, "post_history/character")
    assert slot["status"] == "included"
    assert result["post_history"]["source"] == "character"
    assert SECRET not in json.dumps(result)


def test_inspect_disabled_chat_echo_reports_chat_candidate(tmp_path, monkeypatch):
    # Design P057_DESIGN section 5, precedence rule (3): when a chat
    # was loaded, its blank/disabled candidate IS the resolved value
    # when nothing else has content, and the echo reports that
    # candidate with source "chat" and the chat's own enabled/role.
    client = make_client(tmp_path, monkeypatch)
    chat_id = _make_chat(client)["id"]
    _set_ph(client, chat_id, {"text": SECRET, "enabled": False, "role": "user"})
    result = _inspect(client, chat_id=chat_id, messages=["m1"])
    assert "post_history/chat" not in [s["slot_id"] for s in result["slots"]]
    assert result["post_history"] == {
        "present": False, "enabled": False, "role": "user", "source": "chat",
    }
    assert SECRET not in json.dumps(result)

# ---------------- migration: PROVISIONAL 0035 ----------------

def test_migration_head_is_0035_provisional(tmp_path):
    # Head pin healed at P-065 banking: head moved 0035 -> 0036.
    assert MIGRATIONS[-1][0] == "0036"
    assert "PROVISIONAL" in MIGRATIONS[-1][1]
    db_path = tmp_path / "m.db"
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0036"
    assert current_revision(db_path) == "0036"
    assert migrate_to_head(db_path) == []  # idempotent
    assert current_revision(db_path) == "0036"


def test_migration_0035_adds_post_history_column(tmp_path):
    db_path = tmp_path / "m.db"
    migrate_to_head(db_path)
    conn = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(chats)")}
    finally:
        conn.close()
    assert "post_history_json" in columns
