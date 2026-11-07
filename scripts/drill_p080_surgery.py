#!/usr/bin/env python3
"""P-080 drill: chat surgery composition gate (Part V).

Deterministic, service-layer only (no REST, no live generation):
seed -> account -> swipe-storm -> branch -> checkpoint ->
merge-back -> group scene -> undo -> live import -> final
accounting. Every step asserts the accountancy contract: a
Counter over all swipe-deck strings plus variant-history strings
(active content is deck[swipe_id], counted as a deck string; the
helper asserts content == deck[swipe_id] for every message).
Fork contract (P-078 fix): branch copies carry the FULL deck,
swipe_id, variant history and provenance -- decks of the forked
prefix must equal the source decks exactly.
Run: PYTHONPATH=src python scripts/drill_p080_surgery.py --json
"""
from __future__ import annotations
import argparse, asyncio, json, os, sys, tempfile
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
P = "ZqxDrill80"
ST: dict = {}
FACTORY = None
TMP: Path | None = None

def account_from(hist) -> Counter:
    from runmal.chats.service import message_to_dict
    c: Counter = Counter()
    for m in hist:
        d = message_to_dict(m)
        assert d["content"] == d["swipes"][d["swipe_id"]], "deck invariant broken"
        for s in d["swipes"]:
            c[s] += 1
        for v in d["variant_history"]:
            if isinstance(v, dict) and isinstance(v.get("content"), str):
                c[v["content"]] += 1
    return c

async def hist_of(cid):
    from runmal.chats import service as svc
    async with FACTORY() as s:
        h = await svc.get_history(s, ST["user"], cid)
    assert h is not None, f"chat missing: {cid}"
    return h

async def account(cid) -> Counter:
    return account_from(await hist_of(cid))

async def actives(cid):
    return [m.content for m in await hist_of(cid)]

async def msg_of(cid, mid):
    for m in await hist_of(cid):
        if m.id == mid:
            return m
    raise AssertionError(f"message {mid} not in chat {cid}")

async def step_seed():
    from runmal.chats import service as svc
    from runmal.db.models import User
    async with FACTORY() as s:
        u = User(name=f"{P} User"); s.add(u); await s.commit(); ST["user"] = u.id
    async with FACTORY() as s:
        chat = await svc.create_chat(s, ST["user"], f"{P} source")
    ST["source"] = chat.id
    ST["seed_texts"] = [f"{P} seed{i} message {i}" for i in range(6)]
    ids = []
    for i, text in enumerate(ST["seed_texts"]):
        role = "user" if i % 2 == 0 else "assistant"
        async with FACTORY() as s:
            m = await svc.append_message(s, ST["user"], ST["source"], role, text)
        ids.append(m.id)
    ST["seed_ids"] = ids
    h = await hist_of(ST["source"])
    assert [m.content for m in h] == ST["seed_texts"], "seed contents mismatch"
    assert [m.role for m in h] == ["user", "assistant"] * 3, "seed roles mismatch"
    return f"chat={ST['source'][:8]} messages=6 roles alternate"

async def step_account():
    h = await hist_of(ST["source"])
    acc = account_from(h)
    assert len(h) == 6, "seed history must have 6 messages"
    for m in h:
        from runmal.chats.service import message_to_dict
        d = message_to_dict(m)
        assert d["swipes"] == [d["content"]], "append must seed a 1-entry deck"
        assert d["variant_history"] == [], "fresh message must have no variants"
    assert set(acc) == set(ST["seed_texts"]) and sum(acc.values()) == 6, "seed account mismatch"
    ST["seed_account"] = acc
    return f"distinct={len(acc)} total={sum(acc.values())}"

async def step_swipe_storm():
    from runmal.chats import service as svc
    targets = [ST["seed_ids"][1], ST["seed_ids"][3]]
    added = 0
    for t, mid in enumerate(targets):
        for k in range(3):
            alt = f"{P} alt t{t} k{k}"
            async with FACTORY() as s:
                m = await svc.add_swipe(s, ST["user"], ST["source"], mid, alt)
            assert m is not None and m.content == alt, "add_swipe must activate the new alternate"
            added += 1
    assert added >= 6, "storm must add >= 6 alternates"
    acc_mid = await account(ST["source"])
    assert not (ST["seed_account"] - acc_mid), "account after adds must be a superset of seed"
    for mid in targets:
        from runmal.chats.service import message_to_dict
        deck = message_to_dict(await msg_of(ST["source"], mid))["swipes"]
        assert len(deck) == 4, f"deck should hold 4, got {len(deck)}"
        for idx in range(len(deck)):
            async with FACTORY() as s:
                m = await svc.select_swipe(s, ST["user"], ST["source"], mid, index=idx)
            assert m is not None and m.swipe_id == idx, f"swipe_id must be {idx}"
            assert m.content == deck[idx], f"content must equal deck[{idx}]"
            fresh = await msg_of(ST["source"], mid)
            assert fresh.content == deck[idx] and fresh.swipe_id == idx, "stored selection mismatch"
    acc = await account(ST["source"])
    assert not (ST["seed_account"] - acc), "account after selects must still cover seed"
    return f"added={added} targets=2 selects verified per index"

async def step_branch():
    from runmal.chats import branches, service as svc
    from runmal.chats.service import message_to_dict
    src_before = await account(ST["source"])
    hist = await hist_of(ST["source"])
    async with FACTORY() as s:
        br = await branches.fork_chat(s, ST["user"], ST["source"], hist[2].id)
    assert br is not None, "fork returned None"
    ST["branch"] = br.id; ST["fork_index"] = br.branch_fork_index
    assert ST["fork_index"] == 3, f"fork_index must be 3, got {ST['fork_index']}"
    assert await account(ST["source"]) == src_before, "fork must not change source account"
    bh = await hist_of(ST["branch"])
    assert len(bh) == 3, "branch must hold the 3-message prefix"
    for src_m, br_m in zip(hist[:3], bh):
        sd, bd = message_to_dict(src_m), message_to_dict(br_m)
        assert bd["swipes"] == sd["swipes"], "P-078: branch deck must equal source deck exactly"
        assert bd["swipe_id"] == sd["swipe_id"], "branch swipe_id must equal source"
        assert bd["variant_history"] == sd["variant_history"], "branch variants must equal source"
        assert bd["content"] == sd["content"], "branch active must equal source active"
    assert account_from(bh) == account_from(hist[:3]), "branch prefix account must equal source prefix"
    ST["branch_suffix_texts"] = [f"{P} branch suffix0", f"{P} branch suffix1"]
    for i, text in enumerate(ST["branch_suffix_texts"]):
        role = "assistant" if i % 2 == 0 else "user"
        async with FACTORY() as s:
            await svc.append_message(s, ST["user"], ST["branch"], role, text)
    assert await account(ST["source"]) == src_before, "branch appends must not change source"
    return "decks equal exactly for prefix; source unchanged; suffix=2 appended"

async def step_checkpoint():
    from runmal.chats import checkpoints, service as svc
    cp_account = await account(ST["branch"])
    async with FACTORY() as s:
        meta = await checkpoints.create_checkpoint(
            s, ST["user"], ST["branch"], f"{P} cp", base_dir=TMP)
    assert meta is not None, "checkpoint returned None"
    ST["cp_id"] = meta["id"]
    bh = await hist_of(ST["branch"])
    assert meta["message_count"] == len(bh), "checkpoint message_count mismatch"
    mut_append = f"{P} branch-mut append"
    mut_edit = f"{P} branch-mut edited suffix0"
    async with FACTORY() as s:
        await svc.append_message(s, ST["user"], ST["branch"], "user", mut_append)
    async with FACTORY() as s:
        edited = await svc.edit_message(s, ST["user"], ST["branch"], bh[3].id, mut_edit)
    assert edited is not None and edited.content == mut_edit, "branch edit failed"
    mut_account = await account(ST["branch"])
    assert mut_account != cp_account, "mutation must change the branch account"
    async with FACTORY() as s:
        restored = await checkpoints.restore_checkpoint(
            s, ST["user"], ST["branch"], ST["cp_id"], base_dir=TMP)
    assert restored is not None, "restore returned None"
    ST["restored"] = restored.id
    assert await account(ST["restored"]) == cp_account, "restored account must equal checkpoint-time exactly"
    racc = await account(ST["restored"])
    assert mut_append not in racc and mut_edit not in racc, "restored chat must not carry mutations"
    assert await account(ST["branch"]) == mut_account, "mutated chat must keep its mutations"
    return f"checkpoint={ST['cp_id'][:8]} restored={ST['restored'][:8]} account exact"

async def step_merge_back():
    from runmal.chats import branches
    src_acc = await account(ST["source"]); br_acc = await account(ST["branch"])
    async with FACTORY() as s:
        merged = await branches.merge_back(s, ST["user"], ST["branch"])
    assert merged is not None, "merge_back returned None"
    ST["merged"] = merged.id
    bh = await hist_of(ST["branch"])
    suffix_act = [m.content for m in bh[ST["fork_index"]:]]
    assert suffix_act, "branch suffix must be non-empty"
    expected = await actives(ST["source"]) + suffix_act
    got = await actives(ST["merged"])
    assert got == expected, f"merged actives mismatch: {got} != {expected}"
    assert await account(ST["source"]) == src_acc, "merge must not change source account"
    assert await account(ST["branch"]) == br_acc, "merge must not change branch account"
    return f"merged={ST['merged'][:8]} actives={len(got)} (source {len(got)-len(suffix_act)} + suffix {len(suffix_act)})"

async def step_group():
    from runmal.characters import service as chars
    from runmal.groupchat import store as gstore
    watched = ["source", "branch", "merged"]
    before = {k: await account(ST[k]) for k in watched}
    def card(name, personality):
        return {"spec": "chara_card_v2", "spec_version": "2.0", "name": name,
                "description": f"{P} group member", "personality": personality,
                "scenario": f"{P} hall", "first_mes": f"{P} hail from {name}",
                "mes_example": "<START>Yo<END>", "creator_notes": "drill",
                "system_prompt": "You are a drill member.",
                "post_history_instructions": "Stay in the scene.",
                "tags": ["drill"], "creator": "p080", "extensions": {}}
    name1, name2 = f"{P} Asta", f"{P} Bryn"
    async with FACTORY() as s:
        c1 = await chars.create_character(s, ST["user"], card(name1, "Bold."))
        c2 = await chars.create_character(s, ST["user"], card(name2, "Calm."))
    async with FACTORY() as s:
        g = await gstore.create_group(s, ST["user"], f"{P} Hall", [c1.id, c2.id])
    gid = g.id; ST["group"] = gid
    posts = [("user", f"{P} group user line"),
             (c1.id, f"{P} group asta line"),
             (c2.id, f"{P} group bryn line")]
    for speaker, text in posts:
        async with FACTORY() as s:
            m = await gstore.append_message(s, ST["user"], gid, speaker, text)
        assert m is not None and m.content == text, "group append failed"
    async with FACTORY() as s:
        msgs = await gstore.list_messages(s, ST["user"], gid)
    assert msgs is not None and len(msgs) == 3, f"transcript must hold 3, got {len(msgs or [])}"
    counts = Counter(m.content for m in msgs)
    for _speaker, text in posts:
        assert counts[text] == 1, f"posted text must appear exactly once: {text}"
    by_text = {m.content: m for m in msgs}
    u = by_text[posts[0][1]]; a = by_text[posts[1][1]]; b = by_text[posts[2][1]]
    assert u.role == "user" and u.speaker_id is None, "user speaker not preserved"
    assert a.role == "assistant" and a.speaker_id == c1.id and a.speaker_name == name1, "asta speaker not preserved"
    assert b.role == "assistant" and b.speaker_id == c2.id and b.speaker_name == name2, "bryn speaker not preserved"
    for k in watched:
        assert await account(ST[k]) == before[k], f"group scene must not touch {k} account"
    return f"group={gid[:8]} transcript=3 speakers preserved; surgery accounts untouched"

async def step_undo():
    from runmal.chats import service as svc, undo as undo_mod
    pre = await account(ST["source"])
    h = await hist_of(ST["source"])
    edited_text = f"{P} undo edited"
    async with FACTORY() as s:
        edited = await svc.edit_message(s, ST["user"], ST["source"], h[0].id, edited_text)
    assert edited is not None and edited.content == edited_text, "source edit failed"
    mid = await account(ST["source"])
    assert mid != pre and edited_text in mid, "edit must change the account"
    async with FACTORY() as s:
        res = await undo_mod.undo_last(s, ST["user"], ST["source"], base_dir=TMP)
    assert res is not None, "undo_last returned None"
    assert res.get("undone") == "message.edit", f"undo must undo the edit, got {res.get('undone')}"
    post = await account(ST["source"])
    assert post == pre, "undo must restore the pre-edit account exactly"
    return f"undone={res.get('undone')} seq={res.get('seq')} account exact"

async def step_import():
    from runmal.chats import liveimport, service as svc
    from runmal.chats.service import message_to_dict
    char = f"{P} Imp Char"; uname = f"{P} Imp User"
    imp0 = f"{P} imp0 mes"; imp0alt = f"{P} imp0 alt"
    imp1 = f"{P} imp1 mes"; imp2 = f"{P} imp2 mes"
    def jl(*recs):
        return "\n".join(json.dumps(r) for r in recs)
    doc = jl(
        {"character_name": char, "user_name": uname,
         "create_date": "2026-10-01 @20h 00m 00s 000ms",
         "chat_metadata": {"integrity": "p080"}},
        {"name": char, "is_user": False, "is_system": False, "mes": imp0,
         "send_date": "2026-10-01 @20h 00m 01s", "swipe_id": 0,
         "swipes": [imp0, imp0alt], "extra": {"api": "corpus", "model": "corpus-model"}},
        {"name": uname, "is_user": True, "mes": imp1,
         "send_date": "2026-10-01 @20h 01m 00s", "swipe_id": 0, "swipes": [imp1]},
        {"name": char, "is_user": False, "mes": imp2,
         "send_date": "2026-10-01 @20h 01m 30s", "swipe_id": 0, "swipes": [imp2]})
    async with FACTORY() as s:
        chat, report = await liveimport.import_chat_file(s, ST["user"], doc)
    ST["imported"] = chat.id
    assert report.messages_imported == 3, f"imported must be 3, got {report.messages_imported}"
    assert report.swipe_alternates_preserved >= 1, "import must preserve swipe alternates"
    acc = await account(ST["imported"])
    for t in (imp0, imp0alt, imp1, imp2):
        assert acc[t] >= 1, f"imported string missing from live account: {t}"
    async with FACTORY() as s:
        await svc.append_message(s, ST["user"], ST["imported"], "user", f"{P} imp append")
    h = await hist_of(ST["imported"]); first = h[0]
    post_alt = f"{P} imp post alt"
    async with FACTORY() as s:
        m = await svc.add_swipe(s, ST["user"], ST["imported"], first.id, post_alt)
    assert m is not None and m.content == post_alt, "add_swipe on imported chat failed"
    deck = message_to_dict(await msg_of(ST["imported"], first.id))["swipes"]
    assert post_alt in deck and imp0 in deck and imp0alt in deck, "imported deck must grow, not replace"
    async with FACTORY() as s:
        m = await svc.select_swipe(s, ST["user"], ST["imported"], first.id, index=0)
    assert m is not None and m.content == deck[0] == imp0, "select on imported chat failed"
    return f"imported=3 alternates_preserved={report.swipe_alternates_preserved} append+swipe OK"

async def step_final():
    union: set = set()
    for k in ("source", "branch", "merged", "restored"):
        union |= set((await account(ST[k])).keys())
    parts = []; missing = []
    for t in ST["seed_texts"]:
        present = t in union
        parts.append(f"{t}={'present' if present else 'MISSING'}")
        if not present:
            missing.append(t)
    assert not missing, f"seed strings lost: {missing}"
    return "; ".join(parts)

STEPS = [("seed", step_seed), ("account", step_account),
         ("swipe-storm", step_swipe_storm), ("branch", step_branch),
         ("checkpoint", step_checkpoint), ("merge-back", step_merge_back),
         ("group", step_group), ("undo", step_undo),
         ("import", step_import), ("final-accounting", step_final)]

async def run_all():
    global FACTORY, TMP
    TMP = Path(tempfile.mkdtemp(prefix="runmal_p080_"))
    os.environ["RUNMAL_DATA_DIR"] = str(TMP)
    from runmal.db.base import create_db_engine, create_session_factory
    from runmal.db.migrate import migrate_to_head
    db = TMP / "drill.db"
    migrate_to_head(db)
    FACTORY = create_session_factory(create_db_engine(db))
    steps = []; failed = None
    for name, fn in STEPS:
        try:
            detail = await fn()
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            steps.append({"name": name, "ok": False, "detail": detail})
            print(f"STEP {name} FAIL {detail}", flush=True)
            failed = name; break
        steps.append({"name": name, "ok": True, "detail": detail})
        print(f"STEP {name} OK {detail}", flush=True)
    return steps, failed

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    steps, failed = asyncio.run(run_all())
    verdict = "PASS" if failed is None and len(steps) == len(STEPS) else "FAIL"
    if verdict == "PASS":
        print(f"DRILL P-080: PASS ({len(steps)} steps)")
    else:
        print(f"DRILL P-080: FAIL (step {failed})")
    if args.json:
        print(json.dumps({"steps": steps, "verdict": verdict}))
    return 0 if verdict == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
