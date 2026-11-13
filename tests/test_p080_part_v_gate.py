"""P-080 Part V gate: a surgery drill script (branch, checkpoint,
swipe-storm, group scene) runs green; no operation loses data.

Roadmap line: *P-080 Part V gate: a surgery drill script
(branch, checkpoint, swipe-storm, group scene) runs green;
no operation loses data.*

This is the Part V gate battery, in the P-030 / P-048 / P-064
gate discipline. Part V is P-065..P-080: swipes, branches,
checkpoints, message actions, continue/impersonate, group
deepening, absent digest, search, metadata, databank,
provenance, undo, long-chat performance, live import,
greetings. The gate builds no new behaviour; it judges the
banked slices end to end through their own public contracts,
with ONE accounting discipline everywhere: an ACCOUNT is the
multiset of every string a chat holds (every swipe-deck entry
of every message plus every variant-history content), taken
through message_to_dict, and every operation must produce
exactly the account its contract promises -- copy operations
never mutate their source, copies carry full decks (the
P-078 contract), edits retain replaced text as variants,
deletes remove exactly their message, undo restores the
before-image account exactly.

Per-area "passes means" contracts:
- Area A (swipes + message actions, P-065/P-068): a swipe
  storm only grows the account and content == deck[swipe_id]
  at every stop; edit/move/copy-to-branch/pin each produce
  their exact promised account; delete removes exactly one.
- Area B (branches, P-066): fork prefix decks == source decks
  exactly; merge-back holds target history + branch suffix;
  neither parent changes.
- Area C (checkpoints, P-067): restore-as-new reproduces the
  checkpoint-time account exactly while the source keeps its
  later mutations.
- Area E (group scene, P-070/P-071 road): a room scene's
  posted lines are all present exactly once in order, the
  activation road names its speakers, and the surgery chat
  next door is untouched.
- Area F (undo, P-076): undo after edit and after append
  restores the prior account exactly; the journal cap is the
  pinned MAX_ENTRIES.
- Area G (long-chat, P-077): pages concatenated == the legacy
  full history, canonical-hash equal, at 1,200 messages.
- Area H (live import, P-078): an imported chat's decks are
  live -- fork and swipe surgery work on it with no loss.
- Area I (greetings, P-079): the greeting deck seeds as
  first-message swipes, quiet starts empty, seed-into-empty
  works, and swiping through the deck loses nothing.
- Area J (the drill): scripts/drill_p080_surgery.py runs
  green as a subprocess with all named steps OK.
- Hygiene: migration head stays 0041; the roadmap's Part V
  section spans P-065..P-080 continuously.

Clean-room note: the world below (Surgeryhall) is
fresh-authored for this gate (P-005 discipline); no
SillyTavern or Voxta source was inspected, and no real user
files are read. Plain pytest functions, no test classes.
One TestClient per test, sequential calls only (the shared
SQLite engine is not thread-safe).
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.chats import undo as undo_mod
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS

REPO = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "cards"
Z = "ZqxGate80"
GREET_FIRST = f"{Z} greet first."
GREET_ALTS = [f"{Z} greet alt one.", f"{Z} greet alt two."]
GREET_DECK = [GREET_FIRST] + GREET_ALTS


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


def _chat(client, title=f"{Z} Surgeryhall", **kw):
    r = client.post("/api/v1/chats", json={"title": title, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _msg(client, chat_id, content, role="user"):
    r = client.post(f"/api/v1/chats/{chat_id}/messages",
                    json={"role": role, "content": content})
    assert r.status_code == 201, r.text
    return r.json()


def _hist(client, chat_id):
    r = client.get(f"/api/v1/chats/{chat_id}/messages")
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list), data
    return data


def _account(history):
    bag = Counter()
    for m in history:
        bag.update(m["swipes"])
        for v in m.get("variant_history") or []:
            bag[v["content"]] += 1
    return bag


def _actives(history):
    return [m["content"] for m in history]


def _seed(client, n=5, title=None):
    chat = _chat(client, title or f"{Z} Surgeryhall")
    msgs = [_msg(client, chat["id"], f"{Z} seed {i}.",
                 role="user" if i % 2 == 0 else "assistant") for i in range(n)]
    return chat, msgs


def _swipe(client, chat_id, mid, content):
    r = client.post(f"/api/v1/chats/{chat_id}/messages/{mid}/swipes",
                    json={"content": content})
    assert r.status_code in (200, 201), r.text
    return r.json()


def _select(client, chat_id, mid, index):
    r = client.post(f"/api/v1/chats/{chat_id}/messages/{mid}/swipes/select",
                    json={"index": index})
    assert r.status_code == 200, r.text
    return r.json()


def _character(client, name=f"{Z} Keeper", first=GREET_FIRST, alts=GREET_ALTS):
    payload = {
        "spec": "chara_card_v2", "spec_version": "2.0", "name": name,
        "description": "A surgery-hall keeper.", "personality": "Calm.",
        "scenario": "A test hall.", "first_mes": first,
        "mes_example": "", "creator_notes": "", "system_prompt": "",
        "post_history_instructions": "", "alternate_greetings": list(alts),
        "tags": [], "creator": "test", "extensions": {},
    }
    r = client.post("/api/v1/characters", json={"card": payload})
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_a_swipe_storm_loses_nothing(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat, msgs = _seed(client, 4)
    cid = chat["id"]
    before = _account(_hist(client, cid))
    storm = {msgs[1]["id"]: 5, msgs[2]["id"]: 3}
    total = sum(before.values())
    for mid, n in storm.items():
        for k in range(n):
            _swipe(client, cid, mid, f"{Z} storm {mid[-4:]} {k}.")
        total += n
        h = _hist(client, cid)
        acc = _account(h)
        assert before <= acc and sum(acc.values()) == total
        row = next(m for m in h if m["id"] == mid)
        assert len(row["swipes"]) == n + 1
        for idx in range(n + 1):
            sel = _select(client, cid, mid, idx)
            assert sel["content"] == sel["swipes"][idx]
            assert sel["swipe_id"] == idx and sel["content"] == row["swipes"][idx]
    final = _hist(client, cid)
    assert all(m["content"] == m["swipes"][m["swipe_id"]] for m in final)
    assert before <= _account(final)


def test_a_message_actions_accounting(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat, msgs = _seed(client, 5)
    cid = chat["id"]
    ids = [m["id"] for m in msgs]
    base = _account(_hist(client, cid))
    r = client.patch(f"/api/v1/chats/{cid}/messages/{ids[1]}",
                     json={"content": f"{Z} seed 1 edited."})
    assert r.status_code == 200, r.text
    acc = _account(_hist(client, cid))
    assert acc == base + Counter({f"{Z} seed 1 edited.": 1})
    variants = client.get(f"/api/v1/chats/{cid}/messages/{ids[1]}/variants")
    assert variants.status_code == 200
    assert f"{Z} seed 1." in [v["content"] for v in variants.json()["variants"]]
    r = client.post(f"/api/v1/chats/{cid}/messages/{ids[4]}/move", json={"to_index": 0})
    assert r.status_code == 200, r.text
    h = _hist(client, cid)
    assert _account(h) == acc
    assert _actives(h)[0] == f"{Z} seed 4."
    assert [m["position"] for m in h] == [0, 1, 2, 3, 4]
    r = client.post(f"/api/v1/chats/{cid}/messages/{ids[2]}/copy-to-branch",
                    json={"title": f"{Z} copy branch"})
    assert r.status_code == 201, r.text
    assert _account(_hist(client, cid)) == acc
    target = r.json()["target_chat"]
    assert f"{Z} seed 2." in _actives(_hist(client, target["id"]))
    r = client.post(f"/api/v1/chats/{cid}/messages/{ids[0]}/pin")
    assert r.status_code == 201, r.text
    pinned = client.get(f"/api/v1/chats/{cid}/pinned-messages")
    assert [m["id"] for m in pinned.json()] == [ids[0]]
    assert _account(_hist(client, cid)) == acc
    doomed = next(m for m in _hist(client, cid) if m["id"] == ids[3])
    r = client.delete(f"/api/v1/chats/{cid}/messages/{ids[3]}")
    assert r.status_code == 200, r.text
    h = _hist(client, cid)
    assert _account(h) == acc - Counter(doomed["swipes"])
    assert len(h) == 4 and ids[3] not in [m["id"] for m in h]


def test_b_branch_fork_full_decks(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat, msgs = _seed(client, 4)
    cid = chat["id"]
    _swipe(client, cid, msgs[1]["id"], f"{Z} fork alt.")
    _select(client, cid, msgs[1]["id"], 1)
    src = _hist(client, cid)
    src_acc = _account(src)
    r = client.post(f"/api/v1/chats/{cid}/branches",
                    json={"message_id": msgs[2]["id"], "name": f"{Z} fork"})
    assert r.status_code == 201, r.text
    branch = r.json()
    br = _hist(client, branch["id"])
    assert len(br) == 3
    assert [m["swipes"] for m in br] == [m["swipes"] for m in src[:3]]
    assert [m["swipe_id"] for m in br] == [m["swipe_id"] for m in src[:3]]
    assert _account(_hist(client, cid)) == src_acc
    fam = client.get(f"/api/v1/chats/{cid}/branches")
    assert fam.status_code == 200
    assert branch["id"] in [c["id"] for c in fam.json()["family"]]


def test_b_merge_back_loses_nothing(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat, msgs = _seed(client, 4)
    cid = chat["id"]
    r = client.post(f"/api/v1/chats/{cid}/branches",
                    json={"message_id": msgs[1]["id"], "name": f"{Z} fork"})
    branch = r.json()
    _msg(client, branch["id"], f"{Z} branch suffix.", role="assistant")
    src_acc = _account(_hist(client, cid))
    br_acc = _account(_hist(client, branch["id"]))
    r = client.post(f"/api/v1/chats/{branch['id']}/merge-back", json={})
    assert r.status_code == 201, r.text
    merged = r.json()
    mh = _hist(client, merged["id"])
    assert _actives(mh) == _actives(_hist(client, cid)) + [f"{Z} branch suffix."]
    assert _account(_hist(client, cid)) == src_acc
    assert _account(_hist(client, branch["id"])) == br_acc


def test_c_checkpoint_restore_exact(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat, msgs = _seed(client, 3)
    cid = chat["id"]
    _swipe(client, cid, msgs[0]["id"], f"{Z} cp alt.")
    snap = _account(_hist(client, cid))
    r = client.post(f"/api/v1/chats/{cid}/checkpoints", json={"name": f"{Z} mark"})
    assert r.status_code == 201, r.text
    cp = r.json()
    _msg(client, cid, f"{Z} after cp.")
    client.patch(f"/api/v1/chats/{cid}/messages/{msgs[1]['id']}",
                 json={"content": f"{Z} edited after cp."})
    r = client.post(f"/api/v1/chats/{cid}/checkpoints/{cp['id']}/restore", json={})
    assert r.status_code == 201, r.text
    restored = r.json()
    assert restored["id"] != cid
    assert _account(_hist(client, restored["id"])) == snap
    src = _hist(client, cid)
    assert f"{Z} after cp." in _actives(src)
    assert _account(src) != snap


def test_e_group_scene_loses_nothing(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat, _msgs = _seed(client, 2)
    cid = chat["id"]
    guard = _account(_hist(client, cid))
    v2 = json.loads((FIXTURES / "v2.json").read_text())

    def mkchar(name):
        card = copy.deepcopy(v2)
        card["name"] = name
        r = client.post("/api/v1/characters", json={"card": card})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    a, b = mkchar(f"{Z} Asta"), mkchar(f"{Z} Bryn")
    r = client.post("/api/v1/groups", json={
        "name": f"{Z} Mead Hall", "member_character_ids": [a, b]})
    assert r.status_code == 201, r.text
    gid = r.json()["id"]
    r = client.patch(f"/api/v1/groups/{gid}", json={"speaker_policy": "list"})
    assert r.status_code == 200, r.text
    client.patch(f"/api/v1/groups/{gid}", json={"speaker_config": {"order": [a, b]}})
    r = client.put(f"/api/v1/groups/{gid}/deepening",
                   json={"allow_self_responses": True})
    assert r.status_code == 200, r.text
    lines = [f"{Z} group line {i}." for i in range(3)]
    for line in lines:
        r = client.post(f"/api/v1/groups/{gid}/messages",
                        json={"speaker": "user", "content": line})
        assert r.status_code == 201, r.text
    seq = []
    for _ in range(3):
        r = client.post(f"/api/v1/groups/{gid}/next", json={})
        assert r.status_code == 200, r.text
        seq.append(r.json()["speaker_id"])
    assert seq == [a, b, a]
    r = client.get(f"/api/v1/groups/{gid}/messages")
    assert r.status_code == 200, r.text
    texts = [m["content"] for m in r.json()]
    assert texts == lines
    assert _account(_hist(client, cid)) == guard


def test_f_undo_restores_accounts(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    chat, msgs = _seed(client, 3)
    cid = chat["id"]
    base = _account(_hist(client, cid))
    client.patch(f"/api/v1/chats/{cid}/messages/{msgs[0]['id']}",
                 json={"content": f"{Z} undone edit."})
    assert _account(_hist(client, cid)) != base
    r = client.post(f"/api/v1/chats/{cid}/undo", json={})
    assert r.status_code == 200, r.text
    assert _account(_hist(client, cid)) == base
    _msg(client, cid, f"{Z} undone append.")
    assert len(_hist(client, cid)) == 4
    r = client.post(f"/api/v1/chats/{cid}/undo", json={})
    assert r.status_code == 200, r.text
    assert _account(_hist(client, cid)) == base
    assert len(_hist(client, cid)) == 3


def test_f_undo_journal_cap_pin():
    assert undo_mod.MAX_ENTRIES == 50


async def _g_world(factory):
    from runmal.chats import service as svc
    from runmal.chats.service import message_to_dict
    from runmal.db.models import Chat, Message, User
    async with factory() as s:
        user = User(name="volmarr")
        s.add(user)
        await s.commit()
        uid = user.id
        chat = Chat(user_id=uid, title=f"{Z} long")
        s.add(chat)
        await s.flush()
        for i in range(1200):
            s.add(Message(chat_id=chat.id, role="user" if i % 2 == 0 else "assistant",
                          content=f"{Z} long {i}.", swipes_json=json.dumps([f"{Z} long {i}."]),
                          swipe_id=0, variant_history_json="[]", provenance_json="{}",
                          position=i))
        await s.commit()
        cid = chat.id
    async with factory() as s:
        full = await svc.get_history(s, uid, cid)
        joined, total = [], None
        for off in range(0, 1200, 100):
            page, total, _eo, _el = await svc.get_history_page(
                s, uid, cid, limit=100, offset=off)
            joined.extend(page)
        canon = lambda rows: hashlib.sha256(json.dumps(
            [message_to_dict(m) for m in rows], sort_keys=True).encode()).hexdigest()
        return total, canon(full), canon(joined), len(full)


def test_g_long_chat_paged_road(tmp_path):
    db_path = tmp_path / "g.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    total, full_hash, page_hash, n = asyncio.run(_g_world(factory))
    assert n == 1200 and total == 1200
    assert page_hash == full_hash


async def _h_world(factory):
    from runmal.chats import branches, liveimport, service as svc
    from runmal.chats.service import message_to_dict
    from runmal.db.models import User
    doc = "\n".join(json.dumps(r) for r in [
        {"character_name": "Old Bruni", "user_name": "Ferry Passenger",
         "create_date": "2026-10-01 @20h 00m 00s 000ms",
         "chat_metadata": {"integrity": "p080"}},
        {"name": "Old Bruni", "is_user": False, "is_system": False,
         "mes": f"{Z} imp one.", "send_date": "2026-10-01 @20h 00m 01s",
         "swipe_id": 0, "swipes": [f"{Z} imp one.", f"{Z} imp one alt."]},
        {"name": "Ferry Passenger", "is_user": True,
         "mes": f"{Z} imp two.", "send_date": "2026-10-01 @20h 01m 00s",
         "swipe_id": 0, "swipes": [f"{Z} imp two."]},
    ])
    async with factory() as s:
        user = User(name="volmarr")
        s.add(user)
        await s.commit()
        uid = user.id
    async with factory() as s:
        imported, _rep = await liveimport.import_chat_file(s, uid, doc)
        imp_id = imported.id
    async with factory() as s:
        rows = await svc.get_history(s, uid, imp_id)
        before = _account([message_to_dict(m) for m in rows])
        fork = await branches.fork_chat(s, uid, imp_id)
        fork_id = fork.id
    async with factory() as s:
        rows = await svc.get_history(s, uid, fork_id)
        fork_acc = _account([message_to_dict(m) for m in rows])
        first = rows[0]
        await svc.add_swipe(s, uid, fork_id, first.id, f"{Z} imp one alt 2.")
        rows = await svc.get_history(s, uid, imp_id)
        src_acc = _account([message_to_dict(m) for m in rows])
    return before, fork_acc, src_acc


def test_h_live_import_then_surgery(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "h.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    before, fork_acc, src_acc = asyncio.run(_h_world(factory))
    assert set(before) == {f"{Z} imp one.", f"{Z} imp one alt.", f"{Z} imp two."}
    assert fork_acc == before
    assert src_acc == before


def test_i_greeting_deck_view_and_seed_modes(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    char = _character(client)
    r = client.get(f"/api/v1/characters/{char['id']}/greetings")
    assert r.status_code == 200, r.text
    view = r.json()
    assert view["count"] == 3
    assert [g["text"] for g in view["greetings"]] == GREET_DECK
    assert [g["kind"] for g in view["greetings"]] == ["first", "alternate", "alternate"]
    chat = _chat(client, character_id=char["id"], greeting_mode="index", greeting_index=1)
    h = _hist(client, chat["id"])
    assert len(h) == 1
    assert h[0]["swipes"] == GREET_DECK and h[0]["swipe_id"] == 1
    assert h[0]["content"] == GREET_ALTS[0]
    quiet = _chat(client, title=f"{Z} quiet", character_id=char["id"], greeting_mode="quiet")
    assert _hist(client, quiet["id"]) == []


def test_i_greeting_swipe_through_loses_nothing(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    char = _character(client)
    chat = _chat(client, character_id=char["id"])
    h = _hist(client, chat["id"])
    assert len(h) == 1 and h[0]["swipes"] == GREET_DECK
    before = _account(h)
    mid = h[0]["id"]
    for idx in range(3):
        sel = _select(client, chat["id"], mid, idx)
        assert sel["content"] == GREET_DECK[idx]
    _swipe(client, chat["id"], mid, f"{Z} greet alt three.")
    after = _account(_hist(client, chat["id"]))
    assert before <= after
    assert after == before + Counter({f"{Z} greet alt three.": 1})


def test_i_quiet_seed_into_empty_and_undo(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    char = _character(client)
    chat = _chat(client, character_id=char["id"], greeting_mode="quiet")
    cid = chat["id"]
    assert _hist(client, cid) == []
    r = client.post(f"/api/v1/chats/{cid}/greeting", json={"mode": "index", "index": 2})
    assert r.status_code == 200, r.text
    assert r.json()["seeded"] is True
    h = _hist(client, cid)
    assert len(h) == 1 and h[0]["swipes"] == GREET_DECK
    assert h[0]["content"] == GREET_ALTS[1] and h[0]["swipe_id"] == 2
    r = client.post(f"/api/v1/chats/{cid}/undo", json={})
    assert r.status_code == 200, r.text
    assert _hist(client, cid) == []  # undoing the seed returns the chat to empty


def test_j_drill_script_runs_green(tmp_path):
    script = REPO / "scripts" / "drill_p080_surgery.py"
    assert script.exists()
    env = {"PYTHONPATH": str(REPO / "src"), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    proc = subprocess.run(
        [sys.executable, str(script), "--json"],
        capture_output=True, text=True, timeout=600, env=env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = None
    for line in proc.stdout.splitlines():
        if line.startswith("{"):
            payload = json.loads(line)
    assert payload is not None and payload["verdict"] == "PASS"
    names = {s["name"] for s in payload["steps"]}
    assert {"seed", "account", "swipe-storm", "branch", "checkpoint",
            "merge-back", "group", "undo", "import",
            "final-accounting"} <= names
    assert all(s["ok"] for s in payload["steps"])
    assert "DRILL P-080: PASS" in proc.stdout


def test_k_hygiene_migration_and_roadmap():
    assert MIGRATIONS[-1][0] == "0042"
    assert [m[0] for m in MIGRATIONS].count("0042") == 1  # P-205 banking heal: 0042 taken once, by P-205 m0042
    roadmap = (REPO / "docs" / "RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md").read_text()
    section = roadmap[roadmap.index("## Part V"):roadmap.index("## Part VI")]
    import re as _re
    ids = [int(m) for m in _re.findall(r"\*\*P-(\d+)\*\*", section)]
    assert sorted(ids) == list(range(65, 81))
