"""P-056 Author's note depth battery (BUILDER-3/TESTER).

Pins the author's-note contract: the note as validated data
(defaults, strict rejection, frequency activity, the depth slot),
the composer splice at depth 0 / mid-history / beyond-history,
the per-chat API (default on create, round-trip, isolation, 404,
422, and an event log that never carries note text), the
inspector wiring (S214: the trace and the authors_note echo carry
metadata only -- note text appears NOWHERE in an inspect result),
and PROVISIONAL migration 0034 (chats.authors_note_json).
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
from runmal.prompt.authors_note import (
    FREQUENCY_REASON,
    AuthorsNote,
    has_content,
    is_active_for,
    note_from_data,
    note_to_data,
    slot_for,
)
from runmal.prompt.composer import compose
from runmal.prompt.manager import BLOCK_ORDER
from runmal.prompt.slots import make_slot

CTX = dict(context_limit=4096, reserve_response=512)
DEFAULT_NOTE = {
    "text": "", "depth": 4, "frequency": 1, "enabled": True, "role": "system",
}
SECRET = "ZqxAuthorsNoteSecret42"

# ---------------- pure: defaults + round-trip ----------------

def test_note_defaults_from_none_and_empty():
    assert AuthorsNote() == AuthorsNote(
        text="", depth=4, frequency=1, enabled=True, role="system"
    )
    assert note_from_data(None) == AuthorsNote()
    assert note_from_data({}) == AuthorsNote()
    assert note_to_data(AuthorsNote()) == DEFAULT_NOTE
    assert note_to_data(note_from_data(None)) == DEFAULT_NOTE


def test_note_partial_data_fills_defaults():
    note = note_from_data({"text": "hi"})
    assert note.text == "hi"
    assert (note.depth, note.frequency, note.enabled, note.role) == (
        4, 1, True, "system",
    )


def test_note_round_trip_full():
    data = {
        "text": "Keep it terse.", "depth": 2, "frequency": 3,
        "enabled": False, "role": "assistant",
    }
    note = note_from_data(data)
    assert note_to_data(note) == data
    assert note_from_data(note_to_data(note)) == note
    assert note_from_data(json.loads(json.dumps(data))) == note


# ---------------- pure: validation rejects ----------------

@pytest.mark.parametrize("bad", [
    {"depth": -1},
    {"depth": True},
    {"depth": 1.5},
    {"depth": "2"},
    {"frequency": 0},
    {"frequency": -3},
    {"frequency": True},
    {"frequency": 2.0},
    {"bogus": 1},
    {"text": "x", "extra": None},
    {"role": "narrator"},
    {"role": ""},
    {"enabled": "yes"},
    {"enabled": 1},
    {"text": 42},
])
def test_note_from_data_rejects(bad):
    with pytest.raises(ValueError):
        note_from_data(bad)


@pytest.mark.parametrize("bad", ["note", 42, 3.5, ["text"], True])
def test_note_from_data_rejects_non_dict(bad):
    with pytest.raises(ValueError):
        note_from_data(bad)


def test_authors_note_direct_construction_rejects():
    with pytest.raises(ValueError):
        AuthorsNote(depth=-1)
    with pytest.raises(ValueError):
        AuthorsNote(depth=True)
    with pytest.raises(ValueError):
        AuthorsNote(frequency=0)
    with pytest.raises(ValueError):
        AuthorsNote(role="narrator")
    with pytest.raises(ValueError):
        AuthorsNote(enabled="yes")

# ---------------- pure: has_content / activity / slot ----------------

@pytest.mark.parametrize("note,expected", [
    (AuthorsNote(text=""), False),
    (AuthorsNote(text="   \n\t "), False),
    (AuthorsNote(text="x", enabled=False), False),
    (AuthorsNote(text="", enabled=False), False),
    (AuthorsNote(text=" x "), True),
    (AuthorsNote(text="x", enabled=True), True),
])
def test_has_content(note, expected):
    assert has_content(note) is expected


# Frequency truth table for counts 0..6: frequency 1 fires on every
# composition; frequency N fires exactly when count % N == 0 (the
# zero-message composition is a multiple of every N, so it fires).
_FREQ_TABLE = {
    1: [True, True, True, True, True, True, True],
    2: [True, False, True, False, True, False, True],
    3: [True, False, False, True, False, False, True],
}


@pytest.mark.parametrize("frequency", [1, 2, 3])
def test_is_active_for_frequency_table(frequency):
    note = AuthorsNote(text="n", frequency=frequency)
    for count in range(7):
        assert is_active_for(note, count) is _FREQ_TABLE[frequency][count], (
            frequency, count,
        )


def test_is_active_for_silent_notes_never_fire():
    for count in range(7):
        assert is_active_for(AuthorsNote(text="  "), count) is False
        assert is_active_for(AuthorsNote(text="n", enabled=False), count) is False


def test_is_active_for_rejects_bad_count():
    note = AuthorsNote(text="n")
    with pytest.raises(ValueError):
        is_active_for(note, True)
    with pytest.raises(ValueError):
        is_active_for(note, -1)


def test_slot_for_none_when_inactive():
    assert slot_for(AuthorsNote(text=""), 4) is None
    assert slot_for(AuthorsNote(text="   "), 4) is None
    assert slot_for(AuthorsNote(text="n", enabled=False), 4) is None
    assert slot_for(AuthorsNote(text="n", frequency=2), 3) is None


def test_slot_for_active_fields():
    slot = slot_for(AuthorsNote(text="T", depth=3), 5)
    assert slot is not None
    assert slot.kind == "authors_note"
    assert slot.id == "authors_note/chat"
    assert slot.depth == 3
    assert slot.role == "system"
    assert slot.content == "T"
    assert slot.provenance == "chat:authors_note"


def test_slot_for_role_user_honoured():
    slot = slot_for(AuthorsNote(text="T", depth=0, role="user"), 2)
    assert slot is not None
    assert slot.role == "user" and slot.depth == 0

# ---------------- composer: depth splice positions ----------------

def _compose_with_note(depth, parts, text="NOTE", role="system"):
    history = make_slot(
        "history", "user", "", id="history", splittable=True, parts=tuple(parts)
    )
    note = slot_for(AuthorsNote(text=text, depth=depth, role=role), len(parts))
    assert note is not None
    composed = compose([history, note], **CTX)
    return [(m.slot_id, m.role, m.content) for m in composed.messages]


def test_compose_depth_zero_lands_after_all_history():
    assert _compose_with_note(0, ["m1", "m2", "m3"]) == [
        ("history", "user", "m1\nm2\nm3"),
        ("authors_note/chat", "system", "NOTE"),
    ]


def test_compose_depth_two_splices_two_from_end():
    assert _compose_with_note(2, ["m1", "m2", "m3", "m4"]) == [
        ("history", "user", "m1\nm2"),
        ("authors_note/chat", "system", "NOTE"),
        ("history", "user", "m3\nm4"),
    ]


def test_compose_depth_beyond_history_lands_before_history():
    assert _compose_with_note(9, ["m1", "m2"]) == [
        ("authors_note/chat", "system", "NOTE"),
        ("history", "user", "m1\nm2"),
    ]


def test_compose_depth_note_role_honoured():
    assert _compose_with_note(1, ["m1", "m2"], role="assistant") == [
        ("history", "user", "m1"),
        ("authors_note/chat", "assistant", "NOTE"),
        ("history", "user", "m2"),
    ]


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


def _set_note(client, chat_id, payload):
    resp = client.post(f"/api/v1/chats/{chat_id}/authors-note", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _get_note(client, chat_id):
    resp = client.get(f"/api/v1/chats/{chat_id}/authors-note")
    assert resp.status_code == 200, resp.text
    return resp.json()

# ---------------- API: per-chat author's note ----------------

def test_create_chat_carries_default_note(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = _make_chat(client)
    assert created["authors_note"] == DEFAULT_NOTE
    fetched = client.get(f"/api/v1/chats/{created['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["authors_note"] == DEFAULT_NOTE
    assert _get_note(client, created["id"]) == DEFAULT_NOTE


def test_authors_note_round_trip_via_get(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _make_chat(client)["id"]
    payload = {
        "text": "Stay in third person; keep scenes short.",
        "depth": 2, "frequency": 2, "enabled": True, "role": "user",
    }
    updated = _set_note(client, chat_id, payload)
    assert updated["authors_note"] == payload
    assert _get_note(client, chat_id) == payload
    fetched = client.get(f"/api/v1/chats/{chat_id}").json()
    assert fetched["authors_note"] == payload


def test_authors_note_per_chat_isolation(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    first = _make_chat(client, "One")["id"]
    second = _make_chat(client, "Two")["id"]
    note_a = {"text": "Note A", "depth": 0, "frequency": 1,
              "enabled": True, "role": "system"}
    note_b = {"text": "Note B", "depth": 5, "frequency": 3,
              "enabled": False, "role": "assistant"}
    _set_note(client, first, note_a)
    _set_note(client, second, note_b)
    assert _get_note(client, first) == note_a
    assert _get_note(client, second) == note_b


def test_authors_note_missing_chat_404(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/api/v1/chats/missing/authors-note", json={"text": "x"}
    )
    assert resp.status_code == 404, resp.text
    resp = client.get("/api/v1/chats/missing/authors-note")
    assert resp.status_code == 404, resp.text


@pytest.mark.parametrize("bad", [
    {"depth": -1},
    {"frequency": 0},
    {"role": "narrator"},
])
def test_authors_note_invalid_payloads_422(tmp_path, monkeypatch, bad):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _make_chat(client)["id"]
    resp = client.post(f"/api/v1/chats/{chat_id}/authors-note", json=bad)
    assert resp.status_code == 422, resp.text
    # A refused payload stores nothing: the note is still the default.
    assert _get_note(client, chat_id) == DEFAULT_NOTE

def test_authors_note_event_log_carries_no_text(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _make_chat(client)["id"]
    payload = {
        "text": SECRET + " hold the scene.", "depth": 2, "frequency": 2,
        "enabled": True, "role": "system",
    }
    _set_note(client, chat_id, payload)
    resp = client.get(f"/api/v1/chats/{chat_id}/events")
    assert resp.status_code == 200, resp.text
    events = resp.json()
    changed = [e for e in events if e["kind"] == "authors_note.changed"]
    assert len(changed) == 1
    assert changed[0]["data"] == {
        "depth": 2, "frequency": 2, "enabled": True,
    }
    assert SECRET not in json.dumps(events)
    assert payload["text"] not in json.dumps(events)


def test_chat_to_dict_default_when_no_note_stored():
    stamp = datetime(2026, 11, 7, tzinfo=UTC)
    bare = Chat(
        id="chat-bare", user_id="user-1", title="T",
        authors_note_json="{}", created_at=stamp,
    )
    assert chat_to_dict(bare)["authors_note"] == DEFAULT_NOTE
    unset = Chat(
        id="chat-unset", user_id="user-1", title="T",
        authors_note_json=None, created_at=stamp,
    )
    assert chat_to_dict(unset)["authors_note"] == DEFAULT_NOTE
    stored = {
        "text": "Kept.", "depth": 1, "frequency": 1,
        "enabled": True, "role": "user",
    }
    filled = Chat(
        id="chat-filled", user_id="user-1", title="T",
        authors_note_json=json.dumps(stored), created_at=stamp,
    )
    assert chat_to_dict(filled)["authors_note"] == stored


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

def test_inspect_active_note_included_text_nowhere(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _make_chat(client)["id"]
    _set_note(client, chat_id, {
        "text": SECRET + " hold the scene.", "depth": 1, "frequency": 1,
        "enabled": True, "role": "user",
    })
    result = _inspect(client, chat_id=chat_id, messages=["m1", "m2", "m3"])
    slot = _slot(result, "authors_note/chat")
    assert slot["status"] == "included"
    assert slot["kind"] == "authors_note"
    assert slot["role"] == "user"
    assert result["authors_note"] == {
        "present": True, "active": True, "depth": 1, "frequency": 1,
        "enabled": True, "message_count": 3, "source": "chat",
    }
    # S214: the note text appears NOWHERE in the serialized result.
    assert SECRET not in json.dumps(result)


def test_inspect_frequency_silence_discards(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _make_chat(client)["id"]
    _set_note(client, chat_id, {
        "text": SECRET, "depth": 1, "frequency": 2,
        "enabled": True, "role": "system",
    })
    result = _inspect(client, chat_id=chat_id, messages=["m1", "m2", "m3"])
    slot = _slot(result, "authors_note/chat")
    assert slot["status"] == "discarded"
    assert slot["reason"] == FREQUENCY_REASON == "authors_note_frequency"
    assert slot["kind"] == "authors_note"
    echo = result["authors_note"]
    assert echo["active"] is False and echo["present"] is True
    assert echo["frequency"] == 2 and echo["message_count"] == 3
    assert echo["source"] == "chat"
    assert SECRET not in json.dumps(result)


def test_inspect_frequency_due_includes(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _make_chat(client)["id"]
    _set_note(client, chat_id, {
        "text": SECRET, "depth": 1, "frequency": 2,
        "enabled": True, "role": "system",
    })
    result = _inspect(
        client, chat_id=chat_id, messages=["m1", "m2", "m3", "m4"]
    )
    slot = _slot(result, "authors_note/chat")
    assert slot["status"] == "included"
    assert result["authors_note"]["active"] is True
    assert result["authors_note"]["message_count"] == 4
    assert SECRET not in json.dumps(result)

def test_inspect_empty_and_disabled_match_no_note(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    plain = _make_chat(client, "Plain")["id"]
    empty = _make_chat(client, "Empty")["id"]
    _set_note(client, empty, {
        "text": "   ", "depth": 1, "frequency": 1,
        "enabled": True, "role": "system",
    })
    disabled = _make_chat(client, "Disabled")["id"]
    _set_note(client, disabled, {
        "text": SECRET, "depth": 1, "frequency": 1,
        "enabled": False, "role": "system",
    })
    results = {
        name: _inspect(client, chat_id=cid, messages=["m1", "m2"])
        for name, cid in (
            ("plain", plain), ("empty", empty), ("disabled", disabled),
        )
    }
    id_lists = {
        name: [s["slot_id"] for s in r["slots"]]
        for name, r in results.items()
    }
    # No note content reaches composition in any of the three: the
    # trace is exactly the no-note trace.
    assert id_lists["empty"] == id_lists["plain"]
    assert id_lists["disabled"] == id_lists["plain"]
    assert "authors_note/chat" not in id_lists["plain"]
    for result in results.values():
        assert result["authors_note"]["active"] is False
        assert result["authors_note"]["present"] is False
    assert SECRET not in json.dumps(results["disabled"])


def test_inspect_layout_disabled_note_discards(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _make_chat(client)["id"]
    _set_note(client, chat_id, {
        "text": SECRET, "depth": 1, "frequency": 1,
        "enabled": True, "role": "system",
    })
    result = _inspect(
        client, chat_id=chat_id, messages=["m1", "m2"],
        prompt_layout=_layout_disabling("authors_note"),
    )
    slot = _slot(result, "authors_note/chat")
    assert slot["status"] == "discarded"
    assert slot["reason"] == "prompt_manager_disabled"
    assert SECRET not in json.dumps(result)


def test_inspect_no_chat_echo_source_none(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    result = _inspect(client, messages=["hi"])
    assert result["authors_note"] == {
        "present": False, "active": False, "depth": 4, "frequency": 1,
        "enabled": True, "message_count": 1, "source": "none",
    }
    assert "authors_note/chat" not in [s["slot_id"] for s in result["slots"]]


# ---------------- migration: PROVISIONAL 0034 ----------------

def test_migration_head_is_0034_provisional(tmp_path):
    # Head pin healed at P-057 banking: head moved 0034 -> 0035.
    # Head pin healed at P-065 banking: head moved 0035 -> 0036.
    assert MIGRATIONS[-1][0] == "0042"
    db_path = tmp_path / "m.db"
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0042"
    assert current_revision(db_path) == "0042"
    assert migrate_to_head(db_path) == []  # idempotent
    assert current_revision(db_path) == "0042"


def test_migration_0034_adds_authors_note_column(tmp_path):
    db_path = tmp_path / "m.db"
    migrate_to_head(db_path)
    conn = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(chats)")}
    finally:
        conn.close()
    assert "authors_note_json" in columns
