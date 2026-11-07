#!/usr/bin/env python3
"""P-077 bench: 10,000-message chat fluidity (BUDGET-P077).

Fixture (design Sec.0): seed 77077; one chat of exactly 10,000
messages, positions materialised 0..9999, alternating roles,
deterministic content mix, real swipe decks / variant history /
provenance documents; one 1,000-message control chat; 20 small
chats. Seeding is bulk ORM fixture construction; every MEASURED
op runs the real service roads (incl. serialisation).

Run:  taskset -c 2 python scripts/bench_p077_longchat.py --json
Budget BUDGET-P077 (stated pre-measurement, design Sec.1),
pinned single-core medians of 15 (3 warmups discarded):
  A latest page (100, serialised) <= 150 ms
  B deepest page <= 200 ms and deepest/latest <= 1.5
  C list_chats (21 chats) <= 300 ms
  D in-chat full-text search <= 500 ms
  E composer trim over 10k parts <= 500 ms
  F append at 10k <= 200 ms and append10k/append1k <= 2.0
Pi-equivalent = laptop median x4.0 derating (P-046), a
derating, never a Pi measurement.
"""
from __future__ import annotations
import argparse, asyncio, gc, json, platform, random, statistics, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
SEED = 77077
USER = "bench-user"
RARE_TERM = "zorblax"  # planted in exactly 5 messages
GATES = {"A_latest_page_ms": 150.0, "B_deepest_page_ms": 200.0,
         "B_ratio": 1.5, "C_list_chats_ms": 300.0,
         "D_search_ms": 500.0, "E_compose_ms": 500.0,
         "F_append_ms": 200.0, "F_ratio": 2.0}
VOCAB = [f"word{i:04d}" for i in range(800)]

def make_content(rng, idx):
    r = rng.random()
    if r < 0.70:
        n = rng.randint(10, 100)
    elif r < 0.90:
        n = rng.randint(100, 300)
    else:
        n = rng.randint(300, 500)
    words = rng.choices(VOCAB, k=n)
    if idx % 997 == 0:
        words += ["```python", "print(1)", "```"]
    if idx in (123, 2500, 5000, 7500, 9999):
        words.insert(3, RARE_TERM)
    return " ".join(words)

async def build_fixture(db_path):
    """Deterministic corpus; returns dict of ids + contents."""
    from runmal.db.base import create_db_engine, create_session_factory
    from runmal.db.migrate import migrate_to_head
    from runmal.db.models import Chat, Message, User
    from runmal.chats import provenance as prov_mod
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    factory = create_session_factory(engine)
    rng = random.Random(SEED)
    prov = prov_mod.dump_document(prov_mod.build_document(prov_mod.unknown_record()))
    contents = []
    async def seed():
        async with factory() as s:
            s.add(User(id=USER, name="Bench")); await s.flush()
            big = Chat(user_id=USER, title="Big chat")
            ctl = Chat(user_id=USER, title="Control chat")
            s.add_all([big, ctl]); await s.flush()
            smalls = []
            for i in range(20):
                c = Chat(user_id=USER, title=f"Small {i}")
                s.add(c); smalls.append(c)
            await s.flush()
            rows = []
            for idx in range(10000):
                content = make_content(rng, idx)
                contents.append(content)
                deck = [content]
                variants = "[]"
                if idx % 10 == 0:
                    deck = [content, content + " alt1", content + " alt2"]
                    variants = json.dumps([{ "content": content + " old"}])
                rows.append(Message(
                    chat_id=big.id, role="user" if idx % 2 == 0 else "assistant",
                    content=content, swipes_json=json.dumps(deck), swipe_id=0,
                    variant_history_json=variants, provenance_json=prov,
                    position=idx))
                if len(rows) >= 1000:
                    s.add_all(rows); rows = []
            if rows: s.add_all(rows)
            for idx in range(1000):
                c = make_content(rng, idx)
                s.add(Message(chat_id=ctl.id, role="user" if idx % 2 == 0 else "assistant",
                    content=c, swipes_json=json.dumps([c]), swipe_id=0,
                    variant_history_json="[]", provenance_json=prov, position=idx))
            for c in smalls:
                for j in range(5):
                    s.add(Message(chat_id=c.id, role="user", content=f"small note {j}",
                        swipes_json=json.dumps([f"small note {j}"]), swipe_id=0,
                        variant_history_json="[]", provenance_json=prov, position=j))
            await s.commit()
            return big.id, ctl.id
    big_id, ctl_id = await seed()
    return {"factory": factory, "big_id": big_id, "ctl_id": ctl_id,
            "contents": contents}

def _median_ms(samples):
    return round(statistics.median(samples) * 1000.0, 2)

async def _timed(factory, fn, reps=15, warmups=3):
    samples = []
    for i in range(reps + warmups):
        gc.collect()
        t0 = time.perf_counter()
        result = await fn(factory)
        dt = time.perf_counter() - t0
        if i >= warmups:
            samples.append(dt)
    return _median_ms(samples), result

async def run_bench(db_path):
    from runmal.chats import service, search as search_mod
    from runmal.chats.service import message_to_dict
    fx = await build_fixture(db_path)
    factory, big, ctl = fx["factory"], fx["big_id"], fx["ctl_id"]
    out = {}
    paged = hasattr(service, "get_history_page")
    out["paged_road"] = paged
    async def latest_page(f):
        async with f() as s:
            if paged:
                page = await service.get_history_page(s, USER, big, limit=100, tail=True)
                rows = page[0]
            else:  # BEFORE: the only road is the full load; page = its tail
                rows = (await service.get_history(s, USER, big))[-100:]
        return [message_to_dict(m) for m in rows]
    async def deepest_page(f):
        async with f() as s:
            if paged:
                page = await service.get_history_page(s, USER, big, limit=100, offset=0)
                rows = page[0]
            else:
                rows = (await service.get_history(s, USER, big))[:100]
        return [message_to_dict(m) for m in rows]
    async def legacy_full(f):
        async with f() as s:
            hist = await service.get_history(s, USER, big)
        return [message_to_dict(m) for m in hist]
    async def list_chats(f):
        async with f() as s:
            return await service.list_chats(s, USER)
    async def do_search(f):
        async with f() as s:
            return await search_mod.search_chats(s, USER, RARE_TERM, mode="fulltext", chat_id=big)
    out["A_latest_page_ms"], page = await _timed(factory, latest_page)
    out["page_latest_ids_head"] = [d["id"] for d in page[:2]]
    out["B_deepest_page_ms"], dpage = await _timed(factory, deepest_page)
    out["B_ratio"] = round(out["B_deepest_page_ms"] / max(out["A_latest_page_ms"], 0.01), 3)
    out["legacy_full_history_ms"], full = await _timed(factory, legacy_full, reps=5, warmups=1)
    out["legacy_full_bytes"] = len(json.dumps(full))
    out["C_list_chats_ms"], _ = await _timed(factory, list_chats)
    out["D_search_ms"], doc = await _timed(factory, do_search)
    out["search_total"] = doc["total"]; out["search_scanned"] = doc["scanned_messages"]
    # E: composer trim over the 10k parts (default estimator).
    from runmal.prompt.composer import compose
    from runmal.prompt.slots import Slot
    parts = tuple(fx["contents"])
    def compose_once():
        slot = Slot(id="hist", kind="history", role="user", splittable=True, parts=parts)
        return compose([slot], context_limit=8192, reserve_response=1024)
    samples = []
    for i in range(18):
        gc.collect(); t0 = time.perf_counter(); composed = compose_once()
        dt = time.perf_counter() - t0
        if i >= 3: samples.append(dt)
    out["E_compose_ms"] = _median_ms(samples)
    out["compose_trimmed"] = composed.manifest.included[0].trimmed_parts
    # F: appends at 10k and at 1k (each rep appends one message).
    async def append_big(f):
        async with f() as s:
            return await service.append_message(s, USER, big, "user", "bench append")
    async def append_ctl(f):
        async with f() as s:
            return await service.append_message(s, USER, ctl, "user", "bench append")
    out["F_append_ms"], _ = await _timed(factory, append_big)
    ctl_ms, _ = await _timed(factory, append_ctl)
    out["F_append_1k_ms"] = ctl_ms
    out["F_ratio"] = round(out["F_append_ms"] / max(ctl_ms, 0.01), 3)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--db", default="/tmp/p077_bench.db")
    args = ap.parse_args()
    db = Path(args.db)
    if db.exists(): db.unlink()
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip()
    results = asyncio.run(run_bench(db))
    header = {"machine": platform.machine(), "cpu": platform.processor() or "x86_64",
              "python": platform.python_version(), "git_sha": sha, "seed": SEED}
    verdicts = {}
    for key, gate in GATES.items():
        if key in results:
            verdicts[key] = "PASS" if results[key] <= gate else "FAIL"
    payload = {"header": header, "results": results, "gates": GATES, "verdicts": verdicts,
               "pi_equiv_note": "laptop median x4.0 = Pi-equivalent (derating, not a Pi measurement)"}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"P-077 bench seed={SEED} sha={sha[:8]} py={header['python']}")
        for k, v in results.items(): print(f"  {k}: {v}")
        for k, v in verdicts.items(): print(f"  GATE {k}: {v} (<= {GATES[k]})")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
