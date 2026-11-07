"""P-066 Branches battery (team-01).

Pins the branch contract: fork a chat at any message (prefix copy,
inclusive; whole-chat and empty-chat forks legal), branches listed
as a named family, branches named, merge-back ALWAYS as a new
branch (target history + divergent suffix), and the
never-destructive law (no operation mutates or deletes a source;
a branch outlives its deleted parent).

Migration: PROVISIONAL 0037 (chats branch lineage columns).
0036 (P-065) banked first and stands beneath 0037 in the chain;
this battery pins the head at 0037 and pins that 0036 is present
in the applied chain (pins healed at P-066 banking; re-pinned at
P-068 banking -- 0037 now stands at [-2] beneath the head 0038).
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.chats.branches import branch_info
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _chat(client, title="Saga"):
    r = client.post("/api/v1/chats", json={"title": title})
    assert r.status_code == 201, r.text
    return r.json()


def _msg(client, chat_id, content, role="user"):
    r = client.post(f"/api/v1/chats/{chat_id}/messages", json={"role": role, "content": content})
    assert r.status_code == 201, r.text
    return r.json()


def _history(client, chat_id):
    r = client.get(f"/api/v1/chats/{chat_id}/messages")
    assert r.status_code == 200, r.text
    return r.json()


def _contents(client, chat_id):
    return [m["content"] for m in _history(client, chat_id)]


def _fork(client, chat_id, **body):
    return client.post(f"/api/v1/chats/{chat_id}/branches", json=body)


def _seed_chat(client, title="Saga", contents=("one", "two", "three", "four")):
    chat = _chat(client, title)
    msgs = [_msg(client, chat["id"], c) for c in contents]
    return chat, msgs


# ---------------- migration: PROVISIONAL 0037 ----------------

def test_migration_head_is_0037_provisional(tmp_path):
    # Banking heal (P-068 banking): 0037 stood at [-2] beneath the
    # then-head 0038 (P-068, renumbered from provisional 0039);
    # P-073 banking heal: 0037 now stands at [-3] beneath the
    # new head 0039 (P-073 chat metadata); the
    # 0037 pins are kept at their merged positions and the head is
    # pinned too, so nothing is left unasserted.
    assert MIGRATIONS[-4][0] == "0037"
    assert "PROVISIONAL" in MIGRATIONS[-4][1]
    assert MIGRATIONS[-1][0] == "0040"
    db_path = tmp_path / "m.db"
    applied = migrate_to_head(db_path)
    assert applied[-4] == "0037"
    assert applied[-5] == "0036"
    assert "0036" in applied  # P-065 banked first; 0036 stands beneath 0037
    assert current_revision(db_path) == "0040"
    assert migrate_to_head(db_path) == []  # idempotent


def test_migration_0037_adds_branch_columns(tmp_path):
    db_path = tmp_path / "m.db"
    migrate_to_head(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(chats)")}
    finally:
        conn.close()
    assert {
        "branch_parent_id",
        "branch_fork_message_id",
        "branch_fork_index",
        "branch_kind",
        "branch_merge_of_json",
    } <= cols


def _apply_up_to(db_path, revision: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "revision TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        for rev, _desc, module in MIGRATIONS:
            if rev > revision:
                break
            module.upgrade(conn)
            conn.execute(
                "INSERT INTO schema_migrations (revision, applied_at) VALUES (?, ?)",
                (rev, "test"),
            )
            conn.commit()
    finally:
        conn.close()


def test_migration_0037_upgrades_from_0035_with_root_defaults(tmp_path):
    db_path = tmp_path / "m.db"
    _apply_up_to(db_path, "0035")
    assert current_revision(db_path) == "0035"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("INSERT INTO users (id, name, created_at) VALUES ('u1', 'U', '2026-01-01')")
        conn.execute("INSERT INTO chats (id, user_id, title, created_at) VALUES ('c1', 'u1', 'Old', '2026-01-01')")
        conn.commit()
    finally:
        conn.close()
    assert migrate_to_head(db_path) == ["0036", "0037", "0038", "0039", "0040"]
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT branch_kind, branch_merge_of_json, branch_parent_id FROM chats WHERE id='c1'"
        ).fetchone()
    finally:
        conn.close()
    assert row == ("root", "[]", None)


# ---------------- branch sub-document ----------------

def test_root_chat_branch_document(app_client):
    chat = _chat(app_client)
    assert chat["branch"] == {
        "kind": "root",
        "parent_id": None,
        "fork_message_id": None,
        "fork_index": None,
        "merge_of": [],
        "is_branch": False,
    }


def test_branch_info_defensive_on_legacy_object():
    legacy = SimpleNamespace(id="x")  # no branch attributes at all
    info = branch_info(legacy)
    assert info["kind"] == "root"
    assert info["is_branch"] is False
    assert info["merge_of"] == []


# ---------------- fork ----------------

def test_fork_at_message_copies_prefix_inclusive(app_client):
    chat, msgs = _seed_chat(app_client)
    r = _fork(app_client, chat["id"], message_id=msgs[1]["id"])
    assert r.status_code == 201, r.text
    branch = r.json()
    assert branch["id"] != chat["id"]
    assert branch["message_count"] == 2
    assert branch["title"] == "Saga (branch)"
    assert branch["branch"] == {
        "kind": "fork",
        "parent_id": chat["id"],
        "fork_message_id": msgs[1]["id"],
        "fork_index": 2,
        "merge_of": [],
        "is_branch": True,
    }
    copied = _history(app_client, branch["id"])
    assert [m["content"] for m in copied] == ["one", "two"]
    source_ids = {m["id"] for m in msgs}
    assert all(m["id"] not in source_ids for m in copied)  # fresh ids
    # original timestamps preserved, so order reproduces exactly
    # (compared read-vs-read: creation responses carry +00:00, stored
    # rows read back naive -- a pre-existing app-wide quirk)
    source_read = _history(app_client, chat["id"])
    assert [m["created_at"] for m in copied] == [m["created_at"] for m in source_read[:2]]


def test_fork_whole_chat_default(app_client):
    chat, msgs = _seed_chat(app_client)
    r = _fork(app_client, chat["id"])
    assert r.status_code == 201, r.text
    branch = r.json()
    assert branch["message_count"] == 4
    assert branch["branch"]["fork_message_id"] is None
    assert branch["branch"]["fork_index"] == 4
    assert _contents(app_client, branch["id"]) == ["one", "two", "three", "four"]


def test_fork_at_first_and_last_message(app_client):
    chat, msgs = _seed_chat(app_client)
    first = _fork(app_client, chat["id"], message_id=msgs[0]["id"]).json()
    assert _contents(app_client, first["id"]) == ["one"]
    last = _fork(app_client, chat["id"], message_id=msgs[-1]["id"]).json()
    assert _contents(app_client, last["id"]) == ["one", "two", "three", "four"]


def test_fork_empty_chat_is_legal(app_client):
    chat = _chat(app_client, "Empty")
    r = _fork(app_client, chat["id"])
    assert r.status_code == 201, r.text
    branch = r.json()
    assert branch["message_count"] == 0
    assert branch["branch"]["fork_index"] == 0


def test_fork_with_name_and_blank_name_refused(app_client):
    chat, msgs = _seed_chat(app_client)
    named = _fork(app_client, chat["id"], message_id=msgs[0]["id"], name="What if")
    assert named.status_code == 201, named.text
    assert named.json()["title"] == "What if"
    blank = _fork(app_client, chat["id"], name="   ")
    assert blank.status_code == 422, blank.text


def test_fork_bad_message_and_missing_chat(app_client):
    chat, msgs = _seed_chat(app_client)
    other, other_msgs = _seed_chat(app_client, "Other", ("x",))
    assert _fork(app_client, chat["id"], message_id="nope").status_code == 422
    # a message id from ANOTHER chat is not a fork point here
    assert _fork(app_client, chat["id"], message_id=other_msgs[0]["id"]).status_code == 422
    assert _fork(app_client, "missing-chat").status_code == 404


def test_fork_is_never_destructive_and_histories_diverge(app_client):
    chat, msgs = _seed_chat(app_client)
    branch = _fork(app_client, chat["id"], message_id=msgs[1]["id"]).json()
    _msg(app_client, branch["id"], "branch-only")
    _msg(app_client, chat["id"], "source-only")
    assert _contents(app_client, chat["id"]) == ["one", "two", "three", "four", "source-only"]
    assert _contents(app_client, branch["id"]) == ["one", "two", "branch-only"]


def test_fork_of_branch(app_client):
    chat, msgs = _seed_chat(app_client)
    branch = _fork(app_client, chat["id"], message_id=msgs[2]["id"]).json()
    _msg(app_client, branch["id"], "b4")
    b_hist = _history(app_client, branch["id"])
    grandchild = _fork(app_client, branch["id"], message_id=b_hist[1]["id"]).json()
    assert grandchild["branch"]["parent_id"] == branch["id"]
    assert grandchild["branch"]["fork_index"] == 2
    assert _contents(app_client, grandchild["id"]) == ["one", "two"]


def test_fork_carries_chat_settings(app_client):
    chat, msgs = _seed_chat(app_client)
    note = {"text": "Stay sharp.", "depth": 2, "frequency": 1, "enabled": True, "role": "system"}
    r = app_client.post(f"/api/v1/chats/{chat['id']}/authors-note", json=note)
    assert r.status_code == 200, r.text
    ph = {"text": "End on a hook.", "enabled": True, "role": "system"}
    r = app_client.post(f"/api/v1/chats/{chat['id']}/post-history", json=ph)
    assert r.status_code == 200, r.text
    branch = _fork(app_client, chat["id"], message_id=msgs[0]["id"]).json()
    fetched = app_client.get(f"/api/v1/chats/{branch['id']}").json()
    assert fetched["authors_note"]["text"] == "Stay sharp."
    assert fetched["post_history"]["text"] == "End on a hook."
    assert fetched["character_id"] == chat["character_id"]


def test_fork_events_recorded_on_both_chats(app_client):
    chat, msgs = _seed_chat(app_client)
    branch = _fork(app_client, chat["id"], message_id=msgs[1]["id"]).json()
    src_events = app_client.get(f"/api/v1/chats/{chat['id']}/events").json()
    forked = [e for e in src_events if e["kind"] == "branch.forked"]
    assert len(forked) == 1
    assert forked[0]["data"]["branch_id"] == branch["id"]
    assert forked[0]["data"]["fork_index"] == 2
    br_events = app_client.get(f"/api/v1/chats/{branch['id']}/events").json()
    created = [e for e in br_events if e["kind"] == "branch.created"]
    assert len(created) == 1
    assert created[0]["data"]["parent_id"] == chat["id"]
    assert created[0]["data"]["copied_messages"] == 2
    # the source's message events are NOT copied into the branch log
    assert not [e for e in br_events if e["kind"] == "message.appended"]


# ---------------- family listing + naming ----------------

def _family(client, chat_id):
    r = client.get(f"/api/v1/chats/{chat_id}/branches")
    assert r.status_code == 200, r.text
    return r.json()


def test_family_listing_names_every_member(app_client):
    chat, msgs = _seed_chat(app_client)
    b1 = _fork(app_client, chat["id"], message_id=msgs[1]["id"], name="Alpha").json()
    b2 = _fork(app_client, chat["id"], message_id=msgs[3]["id"], name="Beta").json()
    _msg(app_client, b1["id"], "a3")
    b1_hist = _history(app_client, b1["id"])
    d1 = _fork(app_client, b1["id"], message_id=b1_hist[2]["id"], name="Alpha-2").json()
    fam = _family(app_client, b1["id"])
    assert fam["root"]["id"] == chat["id"]
    assert [a["id"] for a in fam["ancestors"]] == [chat["id"]]
    assert fam["self"]["title"] == "Alpha"
    assert [c["title"] for c in fam["children"]] == ["Alpha-2"]
    assert [c["id"] for c in fam["descendants"]] == [d1["id"]]
    family_ids = {c["id"] for c in fam["family"]}
    assert family_ids == {chat["id"], b1["id"], b2["id"], d1["id"]}
    root_fam = _family(app_client, chat["id"])
    assert root_fam["ancestors"] == []
    assert {c["id"] for c in root_fam["children"]} == {b1["id"], b2["id"]}
    assert {c["id"] for c in root_fam["descendants"]} == {b1["id"], b2["id"], d1["id"]}
    assert app_client.get("/api/v1/chats/missing/branches").status_code == 404


def test_rename_branch_touches_only_itself(app_client):
    chat, msgs = _seed_chat(app_client)
    branch = _fork(app_client, chat["id"], message_id=msgs[0]["id"]).json()
    r = app_client.post(f"/api/v1/chats/{branch['id']}/branch-name", json={"name": "Renamed branch"})
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Renamed branch"
    assert app_client.get(f"/api/v1/chats/{chat['id']}").json()["title"] == "Saga"
    events = app_client.get(f"/api/v1/chats/{branch['id']}/events").json()
    assert [e for e in events if e["kind"] == "branch.renamed"]
    blank = app_client.post(f"/api/v1/chats/{branch['id']}/branch-name", json={"name": "  "})
    assert blank.status_code == 422
    assert app_client.post("/api/v1/chats/missing/branch-name", json={"name": "X"}).status_code == 404


def test_branch_outlives_deleted_parent(app_client):
    chat, msgs = _seed_chat(app_client)
    branch = _fork(app_client, chat["id"], message_id=msgs[1]["id"]).json()
    assert app_client.delete(f"/api/v1/chats/{chat['id']}").status_code == 200
    fetched = app_client.get(f"/api/v1/chats/{branch['id']}")
    assert fetched.status_code == 200, fetched.text
    assert _contents(app_client, branch["id"]) == ["one", "two"]
    fam = _family(app_client, branch["id"])
    assert fam["root"]["id"] == branch["id"]  # chain ends at the survivor
    assert fam["ancestors"] == []


# ---------------- merge-back ----------------

def _merge(client, branch_id, **body):
    return client.post(f"/api/v1/chats/{branch_id}/merge-back", json=body)


def test_merge_back_creates_new_branch_with_divergent_suffix(app_client):
    chat, msgs = _seed_chat(app_client)
    branch = _fork(app_client, chat["id"], message_id=msgs[1]["id"]).json()
    _msg(app_client, branch["id"], "branch-three")
    _msg(app_client, branch["id"], "branch-four")
    r = _merge(app_client, branch["id"])
    assert r.status_code == 201, r.text
    merged = r.json()
    assert merged["id"] not in {chat["id"], branch["id"]}
    assert merged["branch"]["kind"] == "merge"
    assert merged["branch"]["parent_id"] == chat["id"]
    assert merged["branch"]["merge_of"] == [chat["id"], branch["id"]]
    assert merged["branch"]["fork_index"] == 4
    assert _contents(app_client, merged["id"]) == [
        "one", "two", "three", "four", "branch-three", "branch-four",
    ]
    # never destructive: both sources byte-identical afterwards
    assert _contents(app_client, chat["id"]) == ["one", "two", "three", "four"]
    assert _contents(app_client, branch["id"]) == ["one", "two", "branch-three", "branch-four"]
    # and the merged branch joins the target's family as its child
    fam = _family(app_client, chat["id"])
    assert merged["id"] in {c["id"] for c in fam["children"]}


def test_merge_back_explicit_target_appends_whole_branch(app_client):
    chat, msgs = _seed_chat(app_client)
    branch = _fork(app_client, chat["id"], message_id=msgs[0]["id"]).json()
    _msg(app_client, branch["id"], "extra")
    target, _tm = _seed_chat(app_client, "Target", ("t1", "t2"))
    r = _merge(app_client, branch["id"], target_id=target["id"], name="Reunion")
    assert r.status_code == 201, r.text
    merged = r.json()
    assert merged["title"] == "Reunion"
    assert merged["branch"]["parent_id"] == target["id"]
    assert _contents(app_client, merged["id"]) == ["t1", "t2", "one", "extra"]


def test_merge_back_refusals(app_client):
    chat, msgs = _seed_chat(app_client)
    branch = _fork(app_client, chat["id"], message_id=msgs[-1]["id"]).json()
    # nothing divergent yet
    assert _merge(app_client, branch["id"]).status_code == 422
    # self-merge
    assert _merge(app_client, branch["id"], target_id=branch["id"]).status_code == 422
    # a root chat has no parent target
    assert _merge(app_client, chat["id"]).status_code == 422
    # missing branch / missing target
    assert _merge(app_client, "missing").status_code == 404
    _msg(app_client, branch["id"], "new")
    assert _merge(app_client, branch["id"], target_id="missing").status_code == 404
    # blank name
    assert _merge(app_client, branch["id"], name=" ").status_code == 422


def test_merge_events_and_default_title(app_client):
    chat, msgs = _seed_chat(app_client)
    branch = _fork(app_client, chat["id"], message_id=msgs[1]["id"], name="Side").json()
    _msg(app_client, branch["id"], "side-three")
    merged = _merge(app_client, branch["id"]).json()
    assert merged["title"] == "Saga + Side (merged)"
    br_events = app_client.get(f"/api/v1/chats/{branch['id']}/events").json()
    merged_evs = [e for e in br_events if e["kind"] == "branch.merged"]
    assert len(merged_evs) == 1
    assert merged_evs[0]["data"]["merged_into"] == merged["id"]
    assert merged_evs[0]["data"]["suffix_messages"] == 1
    m_events = app_client.get(f"/api/v1/chats/{merged['id']}/events").json()
    created = [e for e in m_events if e["kind"] == "branch.created"]
    assert created and created[0]["data"]["kind"] == "merge"
    assert created[0]["data"]["merge_of"] == [chat["id"], branch["id"]]


def test_service_level_fork_preserves_speaker_snapshot(app_client):
    import asyncio

    from runmal.chats import branches as branches_mod
    from runmal.chats import service as chats_service
    from runmal.db.models import User

    async def run():
        import os
        from pathlib import Path

        db_path = Path(os.environ["RUNMAL_DATA_DIR"]) / "svc.db"
        migrate_to_head(db_path)
        engine = create_db_engine(db_path)
        factory = create_session_factory(engine)
        async with factory() as session:
            session.add(User(id="u-svc", name="Svc"))
            await session.commit()
            chat = await chats_service.create_chat(session, "u-svc", "SvcChat")
            await chats_service.append_message(
                session, "u-svc", chat.id, "assistant", "hello",
                speaker_id="char-1", speaker_name="Astrid",
            )
            await chats_service.append_message(session, "u-svc", chat.id, "user", "hi")
            branch = await branches_mod.fork_chat(session, "u-svc", chat.id)
            history = await chats_service.get_history(session, "u-svc", branch.id)
            return [(m.role, m.content, m.speaker_id, m.speaker_name) for m in history]

    rows = asyncio.run(run())
    assert rows == [
        ("assistant", "hello", "char-1", "Astrid"),
        ("user", "hi", None, None),
    ]


# ---------------- tester-round additions ----------------

def _svc_run(coro_fn):
    import asyncio
    import os
    from pathlib import Path

    async def runner():
        db_path = Path(os.environ["RUNMAL_DATA_DIR"]) / "svc2.db"
        migrate_to_head(db_path)
        engine = create_db_engine(db_path)
        factory = create_session_factory(engine)
        async with factory() as session:
            return await coro_fn(session)

    return asyncio.run(runner())


def test_service_cross_user_isolation(app_client):
    from runmal.chats import branches as b
    from runmal.chats import service as s
    from runmal.db.models import User

    async def run(session):
        session.add_all([User(id="u-a", name="A"), User(id="u-b", name="B")])
        await session.commit()
        chat = await s.create_chat(session, "u-a", "A chat")
        msg = await s.append_message(session, "u-a", chat.id, "user", "secret")
        # B cannot fork, list, rename, or merge A's chat
        assert await b.fork_chat(session, "u-b", chat.id) is None
        assert await b.list_branch_family(session, "u-b", chat.id) is None
        assert await b.rename_branch(session, "u-b", chat.id, "hijack") is None
        assert await b.merge_back(session, "u-b", chat.id) is None
        # A forks; B cannot merge A's branch into anything either
        branch = await b.fork_chat(session, "u-a", chat.id)
        assert await b.merge_back(session, "u-b", branch.id) is None
        # nor merge it as a target from B's own chat
        b_chat = await s.create_chat(session, "u-b", "B chat")
        assert await b.merge_back(session, "u-b", b_chat.id, target_id=branch.id) is None
        return chat.title

    assert _svc_run(run) == "A chat"  # title untouched by B's rename attempt


def test_service_fork_carries_preset_and_backend_ids(app_client):
    from runmal.chats import branches as b
    from runmal.chats import service as s
    from runmal.db.models import User

    async def run(session):
        session.add(User(id="u-p", name="P"))
        await session.commit()
        chat = await s.create_chat(session, "u-p", "Pinned")
        chat.preset_id = "preset-1"
        chat.backend_profile_id = "profile-1"
        await session.commit()
        await s.append_message(session, "u-p", chat.id, "user", "hi")
        branch = await b.fork_chat(session, "u-p", chat.id)
        return branch.preset_id, branch.backend_profile_id, branch.character_id

    assert _svc_run(run) == ("preset-1", "profile-1", None)


def test_family_excludes_unrelated_chats(app_client):
    chat, msgs = _seed_chat(app_client)
    branch = _fork(app_client, chat["id"], message_id=msgs[0]["id"]).json()
    stranger, _sm = _seed_chat(app_client, "Stranger", ("zzz",))
    fam = _family(app_client, branch["id"])
    assert stranger["id"] not in {c["id"] for c in fam["family"]}
    assert stranger["id"] not in {c["id"] for c in _family(app_client, chat["id"])["family"]}


def test_fork_after_edit_copies_edited_content(app_client):
    chat, msgs = _seed_chat(app_client)
    r = app_client.patch(
        f"/api/v1/chats/{chat['id']}/messages/{msgs[1]['id']}", json={"content": "two-edited"}
    )
    assert r.status_code == 200, r.text
    branch = _fork(app_client, chat["id"], message_id=msgs[1]["id"]).json()
    copied = _history(app_client, branch["id"])
    assert [m["content"] for m in copied] == ["one", "two-edited"]
    source_read = _history(app_client, chat["id"])
    assert copied[1]["updated_at"] == source_read[1]["updated_at"]
    assert copied[1]["updated_at"] is not None


def test_merge_twice_creates_two_distinct_branches(app_client):
    chat, msgs = _seed_chat(app_client)
    branch = _fork(app_client, chat["id"], message_id=msgs[1]["id"]).json()
    _msg(app_client, branch["id"], "diverge")
    m1 = _merge(app_client, branch["id"]).json()
    m2 = _merge(app_client, branch["id"]).json()
    assert m1["id"] != m2["id"]
    assert _contents(app_client, m1["id"]) == _contents(app_client, m2["id"])
    assert _contents(app_client, branch["id"]) == ["one", "two", "diverge"]
    assert _contents(app_client, chat["id"]) == ["one", "two", "three", "four"]


def test_merge_result_is_forkable_and_family_coherent(app_client):
    chat, msgs = _seed_chat(app_client)
    branch = _fork(app_client, chat["id"], message_id=msgs[1]["id"]).json()
    _msg(app_client, branch["id"], "diverge")
    merged = _merge(app_client, branch["id"]).json()
    m_hist = _history(app_client, merged["id"])
    child = _fork(app_client, merged["id"], message_id=m_hist[0]["id"]).json()
    assert child["branch"]["parent_id"] == merged["id"]
    fam = _family(app_client, child["id"])
    assert fam["root"]["id"] == chat["id"]
    assert [a["id"] for a in fam["ancestors"]] == [chat["id"], merged["id"]]


def test_family_walk_terminates_on_handcrafted_cycle(app_client):
    from runmal.chats import branches as b
    from runmal.chats import service as s
    from runmal.db.models import User

    async def run(session):
        session.add(User(id="u-c", name="C"))
        await session.commit()
        a = await s.create_chat(session, "u-c", "A")
        c = await s.create_chat(session, "u-c", "C")
        a.branch_parent_id = c.id
        c.branch_parent_id = a.id
        await session.commit()
        fam = await b.list_branch_family(session, "u-c", a.id)
        return fam["chat_id"] if fam else None

    assert _svc_run(run) is not None  # returns; the guard terminates the walk
