"""P-071 Absent-character digest battery (team-03).

A returning character receives an extractive digest of what it
missed: presence is a per-chat event-log fact (presence.left /
presence.returned, metadata only, never message text), the digest
is built on demand from the real stored transcript, excerpts are
content[:excerpt_chars] with a truncated flag and NO ellipsis, and
entries are the FIRST max_entries missed in transcript order with
missed_count == len(entries) + omitted_count.

No migration taken by P-071: head was 0038 on its base (0039 in
the merged tree after P-073 banking), provisional 0040 is
NOT used.
"""

from __future__ import annotations

import copy
import inspect
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.characters import service as characters
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import ChatEvent, User
from runmal.groupchat import store

FIXTURES = Path(__file__).parent / "fixtures" / "cards"
V2_CARD = json.loads((FIXTURES / "v2.json").read_text())
SECRET = "ZqxAbsentSecret71"
BASE_TIME = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)


# ---------------- harness (mirrors test_s210_group_chats) ----------------


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0040"
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def make_character(client, name):
    card = copy.deepcopy(V2_CARD)
    card["name"] = name
    created = client.post("/api/v1/characters", json={"card": card})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def make_group(client, name="Mead Hall", members=()):
    resp = client.post("/api/v1/groups", json={"name": name, "member_character_ids": list(members)})
    assert resp.status_code == 201, resp.text
    return resp.json()


def post_msg(client, gid, speaker, content):
    resp = client.post(f"/api/v1/groups/{gid}/messages", json={"speaker": speaker, "content": content})
    assert resp.status_code == 201, resp.text
    return resp.json()


def leave(client, gid, cid):
    return client.post(f"/api/v1/groups/{gid}/members/{cid}/leave")


def do_return(client, gid, cid, **kwargs):
    return client.post(f"/api/v1/groups/{gid}/members/{cid}/return", **kwargs)


def preview(client, gid, cid, **kwargs):
    return client.get(f"/api/v1/groups/{gid}/members/{cid}/digest", **kwargs)


def presence_list(client, gid):
    resp = client.get(f"/api/v1/groups/{gid}/presence")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body, list)  # bare list, not wrapped
    return body


def record_for(records, cid):
    matches = [r for r in records if r["character_id"] == cid]
    assert len(matches) == 1, records
    return matches[0]


def speaker_counts(digest):
    return {(row["speaker_id"], row["speaker_name"]): row["count"] for row in digest["by_speaker"]}


def room_events(client, chat_id):
    resp = client.get(f"/api/v1/chats/{chat_id}/events")
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------- 1. migration head pin ----------------


def test_no_migration_head_pin(tmp_path, monkeypatch):
    assert MIGRATIONS[-1][0] == "0040"
    # P-075 banking heal: 0040 now exists exactly once and is P-075's
    # m0040_message_provenance -- still none from P-071.
    assert [rev for rev, _desc, _mod in MIGRATIONS].count("0040") == 1
    assert MIGRATIONS[-1][2].__name__.endswith("m0040_message_provenance")
    client = make_client(tmp_path, monkeypatch)  # asserts applied head internally
    assert client is not None
    db_path = tmp_path / "again.db"
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0040"


# ---------------- 2. pure builder ----------------


def fake_msg(mid, speaker_id, speaker_name, content, minute=0):
    role = "user" if speaker_id is None else "assistant"
    return SimpleNamespace(
        id=mid,
        role=role,
        content=content,
        speaker_id=speaker_id,
        speaker_name=speaker_name,
        created_at=BASE_TIME + timedelta(minutes=minute),
        position=None,
    )


def build(window, **overrides):
    """Call presence.build_digest tolerantly: pass only the kwargs the
    builder actually declares (its exact parameter names are builder
    1's choice; the digest DOCUMENT shape is the pinned contract)."""
    from runmal.groupchat.presence import build_digest

    values = {
        "character_id": "bryn-id",
        "returning_character_id": "bryn-id",
        "character_name": "Bryn",
        "returning_character_name": "Bryn",
        "group_id": "group-1",
        "chat_id": "chat-1",
        "group_name": "Mead Hall",
        "absent_since": BASE_TIME,
        "max_entries": 50,
        "excerpt_chars": 200,
        "anchor_message_id": "m0",
        "anchor_message_count": 1,
        "resolution": "by_id",
        "window_resolution": "by_id",
        "delivered": False,
    }
    values.update(overrides)
    sig = inspect.signature(build_digest)
    params = sig.parameters
    kwargs = {}
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        kwargs = dict(values)
    else:
        kwargs = {k: v for k, v in values.items() if k in params}
    positional = [n for n, p in params.items() if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)]
    if positional and positional[0] not in kwargs:
        return build_digest(window, **kwargs)
    kwargs[positional[0]] = window
    return build_digest(**kwargs)


def test_pure_by_speaker_order_sums_and_own_excluded():
    window = [
        fake_msg("m1", "una-id", "Una", "first", 1),
        fake_msg("m2", None, None, "user words", 2),
        fake_msg("m3", "una-id", "Una", "second", 3),
        fake_msg("m4", "bryn-id", "Bryn", "my own note", 4),
        fake_msg("m5", "kol-id", "Kol", "kol speaks", 5),
    ]
    digest = build(window)
    assert digest["kind"] == "extractive_digest"
    assert digest["digest_version"] == "extractive-1"
    assert digest["missed_count"] == 4
    assert digest["own_messages_in_window"] == 1
    # first-appearance order: Una, then user, then Kol; Bryn excluded
    assert [(r["speaker_id"], r["speaker_name"], r["count"]) for r in digest["by_speaker"]] == [
        ("una-id", "Una", 2),
        (None, "user", 1),
        ("kol-id", "Kol", 1),
    ]
    assert sum(r["count"] for r in digest["by_speaker"]) == digest["missed_count"]
    assert [e["message_id"] for e in digest["entries"]] == ["m1", "m2", "m3", "m5"]
    assert digest["window"]["first_missed_message_id"] == "m1"
    assert digest["window"]["last_missed_message_id"] == "m5"
    assert digest["omitted_count"] == 0
    assert digest["empty"] is False


def test_pure_excerpt_exact_at_cap_and_over():
    from runmal.groupchat.presence import excerpt_text

    exact = "x" * 20
    over = "y" * 21
    for text, cap, want_trunc in ((exact, 20, False), (over, 20, True)):
        result = excerpt_text(text, cap)
        if isinstance(result, tuple):
            excerpt, truncated = result
        else:
            excerpt, truncated = result, len(text) > cap
        assert excerpt == text[:cap]
        assert len(excerpt) == cap
        assert truncated is want_trunc
    digest = build([fake_msg("m1", "una-id", "Una", over, 1)], excerpt_chars=20)
    entry = digest["entries"][0]
    assert entry["excerpt"] == over[:20]
    assert entry["truncated"] is True
    digest2 = build([fake_msg("m1", "una-id", "Una", exact, 1)], excerpt_chars=20)
    assert digest2["entries"][0]["excerpt"] == exact
    assert digest2["entries"][0]["truncated"] is False


def test_pure_entry_cap_omitted_and_invariant():
    window = [fake_msg(f"m{i}", "una-id", "Una", f"msg {i}", i) for i in range(1, 6)]
    digest = build(window, max_entries=2)
    assert digest["missed_count"] == 5
    assert [e["message_id"] for e in digest["entries"]] == ["m1", "m2"]  # FIRST N retained
    assert digest["omitted_count"] == 3
    assert digest["missed_count"] == len(digest["entries"]) + digest["omitted_count"]


def test_pure_empty_window():
    digest = build([])
    assert digest["empty"] is True
    assert digest["missed_count"] == 0
    assert digest["entries"] == []
    assert digest["by_speaker"] == []
    assert digest["omitted_count"] == 0
    assert digest["window"]["first_missed_message_id"] is None
    assert digest["window"]["last_missed_message_id"] is None
    low = digest["text"].lower()
    assert "nothing" in low or "no messages" in low or "0 messages" in low


def test_pure_text_uses_capped_excerpts():
    tail = "TAILBEYONDCAP"
    content = "A" * 60 + tail
    digest = build([fake_msg("m1", "una-id", "Una", content, 1)], excerpt_chars=50)
    assert tail not in digest["text"]
    assert "A" * 51 not in digest["text"]
    assert digest["entries"][0]["excerpt"] == "A" * 50


def test_pure_user_coalescing():
    window = [
        fake_msg("m1", None, None, "one", 1),
        fake_msg("m2", None, None, "two", 2),
    ]
    digest = build(window)
    assert [(r["speaker_id"], r["speaker_name"], r["count"]) for r in digest["by_speaker"]] == [(None, "user", 2)]
    assert [e["speaker_name"] for e in digest["entries"]] == ["user", "user"]
    assert [e["speaker_id"] for e in digest["entries"]] == [None, None]


def test_pure_digest_prompt_message_shape():
    from runmal.groupchat.presence import digest_prompt_message

    digest = build([fake_msg("m1", "una-id", "Una", "harbour news", 1)])
    message = digest_prompt_message(digest)
    assert isinstance(message, dict)
    assert message["role"] == "system"
    assert "Bryn" in message["content"]
    assert digest["text"] in message["content"]


# ---------------- 3. API happy path ----------------


def test_api_happy_path_leave_preview_return(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    bryn = make_character(client, "Bryn")
    una = make_character(client, "Una")
    kol = make_character(client, "Kol")
    group = make_group(client, members=[bryn, una, kol])
    gid, chat_id = group["id"], group["chat_id"]

    post_msg(client, gid, una, "harbour at dawn")
    last = post_msg(client, gid, "user", "bring the rope")

    resp = leave(client, gid, bryn)
    assert resp.status_code == 200, resp.text
    record = resp.json()
    assert record["group_id"] == gid
    assert record["chat_id"] == chat_id
    assert record["character_id"] == bryn
    assert record["character_name"] == "Bryn"
    assert record["present"] is False
    assert record["absent_since"]
    assert record["last_seen_message_id"] == last["id"]
    assert record["message_count_at_leave"] == 2
    assert record["missed_count"] == 0

    m1 = post_msg(client, gid, una, "wind rising")
    m2 = post_msg(client, gid, "user", "noted")
    m3 = post_msg(client, gid, una, "sails up")

    records = presence_list(client, gid)
    bryn_rec = record_for(records, bryn)
    assert bryn_rec["present"] is False
    assert bryn_rec["missed_count"] == 3
    assert bryn_rec["last_seen_message_id"] == last["id"]
    assert record_for(records, una)["present"] is True
    assert record_for(records, kol)["present"] is True

    resp = preview(client, gid, bryn)
    assert resp.status_code == 200, resp.text
    digest = resp.json()
    assert digest["kind"] == "extractive_digest"
    assert digest["digest_version"] == "extractive-1"
    assert digest["group_id"] == gid
    assert digest["chat_id"] == chat_id
    assert digest["group_name"] == "Mead Hall"
    assert digest["character_id"] == bryn
    assert digest["character_name"] == "Bryn"
    assert digest["absent_since"]
    assert digest["built_at"]
    assert digest["delivered"] is False
    assert digest["missed_count"] == 3
    assert digest["own_messages_in_window"] == 0
    assert speaker_counts(digest) == {(una, "Una"): 2, (None, "user"): 1}
    window = digest["window"]
    assert window["resolution"] == "by_id"
    assert window["anchor_message_id"] == last["id"]
    assert window["anchor_message_count"] == 2
    assert window["first_missed_message_id"] == m1["id"]
    assert window["last_missed_message_id"] == m3["id"]
    assert window["missed_count"] == 3
    assert [e["message_id"] for e in digest["entries"]] == [m1["id"], m2["id"], m3["id"]]
    assert digest["entries"][0]["excerpt"] == "wind rising"
    assert digest["entries"][0]["truncated"] is False
    assert digest["entries"][1]["speaker_id"] is None
    assert digest["entries"][1]["speaker_name"] == "user"
    assert digest["entries"][1]["role"] == "user"
    assert digest["omitted_count"] == 0
    assert digest["empty"] is False
    assert "Bryn" in digest["text"]

    resp = do_return(client, gid, bryn)
    assert resp.status_code == 200, resp.text
    delivered = resp.json()
    assert delivered["delivered"] is True
    assert delivered["missed_count"] == 3
    assert delivered["window"]["first_missed_message_id"] == m1["id"]
    assert delivered["window"]["last_missed_message_id"] == m3["id"]
    assert delivered["window"]["resolution"] == "by_id"

    records = presence_list(client, gid)
    assert all(r["present"] is True for r in records)
    assert do_return(client, gid, bryn).status_code == 422


# ---------------- 4. leave on empty room ----------------


def test_leave_on_empty_room_from_start(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    bryn = make_character(client, "Bryn")
    una = make_character(client, "Una")
    group = make_group(client, members=[bryn, una])
    gid = group["id"]
    record = leave(client, gid, bryn).json()
    assert record["last_seen_message_id"] is None
    assert record["message_count_at_leave"] == 0
    post_msg(client, gid, una, "first while away")
    post_msg(client, gid, "user", "second while away")
    digest = do_return(client, gid, bryn).json()
    assert digest["window"]["resolution"] == "from_start"
    assert digest["window"]["anchor_message_id"] is None
    assert digest["missed_count"] == 2
    assert len(digest["entries"]) == 2


# ---------------- 5. return with nothing missed ----------------


def test_return_with_nothing_missed(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    bryn = make_character(client, "Bryn")
    una = make_character(client, "Una")
    group = make_group(client, members=[bryn, una])
    gid = group["id"]
    post_msg(client, gid, una, "before leave")
    assert leave(client, gid, bryn).status_code == 200
    digest = do_return(client, gid, bryn).json()
    assert digest["empty"] is True
    assert digest["missed_count"] == 0
    assert digest["entries"] == []
    assert digest["by_speaker"] == []
    assert do_return(client, gid, bryn).status_code == 422  # absence closed


# ---------------- 6. double leave + single event ----------------


def test_double_leave_422_and_one_left_event(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    bryn = make_character(client, "Bryn")
    una = make_character(client, "Una")
    group = make_group(client, members=[bryn, una])
    gid, chat_id = group["id"], group["chat_id"]
    assert leave(client, gid, bryn).status_code == 200
    assert leave(client, gid, bryn).status_code == 422
    events = room_events(client, chat_id)
    left = [e for e in events if e["kind"] == "presence.left" and e["data"].get("character_id") == bryn]
    assert len(left) == 1


# ---------------- 7. non-member / unknown / missing group ----------------


def test_non_member_unknown_and_missing_group(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    bryn = make_character(client, "Bryn")
    una = make_character(client, "Una")
    kol = make_character(client, "Kol")  # real character, not a member
    group = make_group(client, members=[bryn, una])
    gid = group["id"]
    for cid in (kol, "no-such-character"):
        assert leave(client, gid, cid).status_code == 422, cid
        assert do_return(client, gid, cid).status_code == 422, cid
        assert preview(client, gid, cid).status_code == 422, cid
    # digest / return while present (member who never left) -> 422
    assert preview(client, gid, bryn).status_code == 422
    assert do_return(client, gid, bryn).status_code == 422
    for call in (
        lambda: leave(client, "no-such-group", bryn),
        lambda: do_return(client, "no-such-group", bryn),
        lambda: preview(client, "no-such-group", bryn),
        lambda: client.get("/api/v1/groups/no-such-group/presence"),
    ):
        assert call().status_code == 404


# ---------------- 8. deleted anchor fallback ----------------


def test_deleted_anchor_fallback_exact(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    bryn = make_character(client, "Bryn")
    una = make_character(client, "Una")
    group = make_group(client, members=[bryn, una])
    gid, chat_id = group["id"], group["chat_id"]
    post_msg(client, gid, una, "M1")
    post_msg(client, gid, "user", "M2")
    m3 = post_msg(client, gid, una, "M3")
    record = leave(client, gid, bryn).json()
    assert record["last_seen_message_id"] == m3["id"]
    deleted = client.delete(f"/api/v1/chats/{chat_id}/messages/{m3['id']}")
    assert deleted.status_code == 200, deleted.text
    m4 = post_msg(client, gid, una, "M4")
    digest = do_return(client, gid, bryn).json()
    assert digest["window"]["resolution"] == "by_count_fallback"
    assert digest["missed_count"] == 1
    assert [e["message_id"] for e in digest["entries"]] == [m4["id"]]


# ---------------- 9. fallback hard variant (documented approximation) ----------------


def test_deleted_anchor_fallback_hard_variant(tmp_path, monkeypatch):
    # Documented approximation: with D pre-window deletions the
    # count fallback loses the earliest D-1 missed messages. Here
    # D=2 (anchor M4 and M2 both deleted), so M5 is lost to the
    # shift and only M6 is delivered -- pinned, not "fixed".
    client = make_client(tmp_path, monkeypatch)
    bryn = make_character(client, "Bryn")
    una = make_character(client, "Una")
    group = make_group(client, members=[bryn, una])
    gid, chat_id = group["id"], group["chat_id"]
    post_msg(client, gid, una, "M1")
    m2 = post_msg(client, gid, "user", "M2")
    post_msg(client, gid, una, "M3")
    m4 = post_msg(client, gid, "user", "M4")
    record = leave(client, gid, bryn).json()
    assert record["last_seen_message_id"] == m4["id"]
    assert record["message_count_at_leave"] == 4
    assert client.delete(f"/api/v1/chats/{chat_id}/messages/{m4['id']}").status_code == 200
    assert client.delete(f"/api/v1/chats/{chat_id}/messages/{m2['id']}").status_code == 200
    post_msg(client, gid, una, "M5")
    m6 = post_msg(client, gid, una, "M6")
    digest = do_return(client, gid, bryn).json()
    assert digest["window"]["resolution"] == "by_count_fallback"
    assert digest["missed_count"] == 1
    assert [e["message_id"] for e in digest["entries"]] == [m6["id"]]
    assert digest["entries"][0]["excerpt"] == "M6"


# ---------------- 10. remove + re-add keeps the absence ----------------


def test_remove_and_readd_still_returns(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    bryn = make_character(client, "Bryn")
    una = make_character(client, "Una")
    group = make_group(client, members=[bryn, una])
    gid = group["id"]
    post_msg(client, gid, una, "before leave")
    assert leave(client, gid, bryn).status_code == 200
    w1 = post_msg(client, gid, una, "while away one")
    removed = client.delete(f"/api/v1/groups/{gid}/members/{bryn}")
    assert removed.status_code == 200, removed.text
    # Removed from the roster: she is not a member, so return refuses.
    assert do_return(client, gid, bryn).status_code == 422
    w2 = post_msg(client, gid, una, "while removed")
    readded = client.post(f"/api/v1/groups/{gid}/members", json={"character_id": bryn})
    assert readded.status_code == 201, readded.text
    digest = do_return(client, gid, bryn).json()
    # Messages posted during the removal period are in the window:
    # presence events live on the room chat, not the membership row.
    assert digest["missed_count"] == 2
    assert [e["message_id"] for e in digest["entries"]] == [w1["id"], w2["id"]]


# ---------------- 11. own messages in window ----------------


def test_own_messages_in_window_not_missed(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    bryn = make_character(client, "Bryn")
    una = make_character(client, "Una")
    group = make_group(client, members=[bryn, una])
    gid = group["id"]
    post_msg(client, gid, una, "before leave")
    assert leave(client, gid, bryn).status_code == 200
    own = post_msg(client, gid, bryn, "bryn speaks while absent")  # absence does not gate speech
    assert own["speaker_id"] == bryn
    unas = post_msg(client, gid, una, "una while away")
    digest = do_return(client, gid, bryn).json()
    assert digest["missed_count"] == 1
    assert digest["own_messages_in_window"] == 1
    assert [e["message_id"] for e in digest["entries"]] == [unas["id"]]
    assert digest["window"]["first_missed_message_id"] == unas["id"]
    assert digest["window"]["last_missed_message_id"] == unas["id"]
    assert speaker_counts(digest) == {(una, "Una"): 1}


# ---------------- 12. second absence cycle ----------------


def test_second_absence_cycle_only_new_window(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    bryn = make_character(client, "Bryn")
    una = make_character(client, "Una")
    group = make_group(client, members=[bryn, una])
    gid = group["id"]
    post_msg(client, gid, una, "cycle one before")
    assert leave(client, gid, bryn).status_code == 200
    post_msg(client, gid, una, "cycle one missed")
    first = do_return(client, gid, bryn).json()
    assert first["missed_count"] == 1
    post_msg(client, gid, una, "between cycles one")
    anchor = post_msg(client, gid, "user", "between cycles two")
    record = leave(client, gid, bryn).json()
    assert record["last_seen_message_id"] == anchor["id"]
    fresh = post_msg(client, gid, una, "cycle two missed")
    second = do_return(client, gid, bryn).json()
    assert second["missed_count"] == 1
    assert second["window"]["anchor_message_id"] == anchor["id"]
    assert second["window"]["resolution"] == "by_id"
    assert [e["message_id"] for e in second["entries"]] == [fresh["id"]]
    assert second["entries"][0]["excerpt"] == "cycle two missed"


# ---------------- 14. caps validation ----------------


def test_return_caps_validation_and_defaults(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    bryn = make_character(client, "Bryn")
    una = make_character(client, "Una")
    group = make_group(client, members=[bryn, una])
    gid = group["id"]
    post_msg(client, gid, una, "before leave")
    assert leave(client, gid, bryn).status_code == 200
    post_msg(client, gid, una, "while away")
    for body in ({"max_entries": 0}, {"max_entries": 501}, {"excerpt_chars": 10}, {"excerpt_chars": 5001}):
        resp = do_return(client, gid, bryn, json=body)
        assert resp.status_code == 422, (body, resp.text)
    # The failed validations closed nothing: a body-less return still
    # succeeds on the defaults (50 entries / 200 chars).
    resp = do_return(client, gid, bryn)
    assert resp.status_code == 200, resp.text
    assert resp.json()["missed_count"] == 1
    assert resp.json()["delivered"] is True


def test_return_max_entries_cap_omitted(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    bryn = make_character(client, "Bryn")
    una = make_character(client, "Una")
    group = make_group(client, members=[bryn, una])
    gid = group["id"]
    assert leave(client, gid, bryn).status_code == 200
    ids = [post_msg(client, gid, una, f"missed {i}")["id"] for i in range(3)]
    digest = do_return(client, gid, bryn, json={"max_entries": 1}).json()
    assert digest["missed_count"] == 3
    assert [e["message_id"] for e in digest["entries"]] == [ids[0]]
    assert digest["omitted_count"] == 2
    assert digest["missed_count"] == len(digest["entries"]) + digest["omitted_count"]


# ---------------- 15. preview is non-mutating ----------------


def test_preview_non_mutating(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    bryn = make_character(client, "Bryn")
    una = make_character(client, "Una")
    group = make_group(client, members=[bryn, una])
    gid = group["id"]
    post_msg(client, gid, una, "before leave")
    assert leave(client, gid, bryn).status_code == 200
    post_msg(client, gid, una, "missed one")
    post_msg(client, gid, "user", "missed two")
    first = preview(client, gid, bryn).json()
    second = preview(client, gid, bryn).json()
    first.pop("built_at", None)
    second.pop("built_at", None)
    assert first == second  # identical apart from built_at
    assert first["missed_count"] == 2
    assert record_for(presence_list(client, gid), bryn)["present"] is False
    late = post_msg(client, gid, una, "between preview and return")
    digest = do_return(client, gid, bryn).json()
    assert digest["missed_count"] == 3
    assert digest["window"]["last_missed_message_id"] == late["id"]


# ---------------- service-level helpers ----------------


def make_factory(tmp_path):
    db_path = tmp_path / "svc.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def make_user(factory, name="volmarr"):
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


async def make_service_group(factory, user_id, member_names=("Bryn", "Una")):
    async with factory() as session:
        ids = []
        for name in member_names:
            card = copy.deepcopy(V2_CARD)
            card["name"] = name
            character = await characters.create_character(session, user_id, card)
            ids.append(character.id)
        group = await store.create_group(session, user_id, "Mead Hall", ids)
        described = await store.describe_group(session, user_id, group.id)
    return described["id"], described["chat_id"], ids


async def svc_presence(fn, session, user_id, group_id, character_id=None):
    """Call a presence service function tolerantly: supply the digest
    sizing kwargs only when the function declares them."""
    sig = inspect.signature(fn)
    kwargs = {}
    if "max_entries" in sig.parameters:
        kwargs["max_entries"] = 50
    if "excerpt_chars" in sig.parameters:
        kwargs["excerpt_chars"] = 200
    if character_id is None:
        return await fn(session, user_id, group_id, **kwargs)
    return await fn(session, user_id, group_id, character_id, **kwargs)


# ---------------- 13. metadata-only events (service level) ----------------


async def test_service_events_are_metadata_only(tmp_path):
    from runmal.groupchat import presence

    factory = make_factory(tmp_path)
    user = await make_user(factory)
    gid, chat_id, (bryn, una) = await make_service_group(factory, user)
    async with factory() as session:
        await store.append_message(session, user, gid, una, f"news {SECRET} here")
        record = await svc_presence(presence.mark_absent, session, user, gid, bryn)
        assert record["present"] is False
        await store.append_message(session, user, gid, una, f"more {SECRET} while away")
        digest = await svc_presence(presence.mark_returned, session, user, gid, bryn)
        assert digest["missed_count"] == 1
        assert SECRET in digest["entries"][0]["excerpt"]  # digest itself is transcript-derived
        rows = (await session.execute(select(ChatEvent).where(ChatEvent.chat_id == chat_id))).scalars().all()
    presence_events = [e for e in rows if e.kind.startswith("presence.")]
    assert {e.kind for e in presence_events} == {"presence.left", "presence.returned"}
    allowed_keys = {
        "character_id", "character_name", "group_id", "chat_id",
        "last_seen_message_id", "message_count_at_leave",
        "anchor_message_id", "anchor_message_count", "missed_count",
        "first_missed_message_id", "last_missed_message_id",
        "window_first_message_id", "window_last_message_id",
        "absent_since", "returned_at", "own_messages_in_window", "resolution",
    }
    for event in presence_events:
        assert SECRET not in event.data  # no message text in event payloads, ever
        data = json.loads(event.data)
        assert set(data) <= allowed_keys, data
        assert all(isinstance(v, (str, int, type(None))) for v in data.values())


# ---------------- 16. cross-user isolation (service level) ----------------


async def test_service_cross_user_isolation(tmp_path):
    from runmal.groupchat import presence

    factory = make_factory(tmp_path)
    user = await make_user(factory)
    other = await make_user(factory, "intruder")
    gid, _chat_id, (bryn, _una) = await make_service_group(factory, user)
    async with factory() as session:
        # Foreign group resolves to None (group-missing only), never raises,
        # and writes no event for a group the caller does not own.
        assert await svc_presence(presence.mark_absent, session, other, gid, bryn) is None
        assert await svc_presence(presence.list_presence, session, other, gid) is None
        assert await svc_presence(presence.missed_digest, session, other, gid, bryn) is None
        assert await svc_presence(presence.mark_absent, session, user, "missing-group", bryn) is None
        assert await svc_presence(presence.list_presence, session, user, "missing-group") is None
        # The owner's view is untouched by the foreign probes.
        records = await svc_presence(presence.list_presence, session, user, gid)
        assert records is not None
        assert all(r["present"] is True for r in records)
