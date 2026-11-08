"""P-077 acceptance: long-chat performance — 10k-message chats
stay fluid (the founding UI campaign's standards held).

Contract under test (docs/LONG_CHAT_PERFORMANCE_2026-11-07.md,
hidden_files/P077_DESIGN.md, BUDGET-P077):
- Paged history road: service.get_history_page + limit/offset/
  tail params on GET /chats/{id}/messages. No params = the
  legacy full list, byte-identical. Pages concatenated in
  order == the legacy road, canonical-JSON sha256 equal.
- Append fast path: a SQL density aggregate decides; positions
  exactly dense 0..N-1 skip the load+renumber, ANY irregularity
  (duplicates, gaps, mixed NULLs) falls back to the exact old
  road. Same position assignment + event shape either way.
- Migration PROVISIONAL 0041: composite covering index
  ix_messages_chat_position (chat_id, position, created_at,
  id) — the density aggregate and the paged ORDER BY stream
  from it instead of per-row table lookups + TEMP B-TREE.
- Composer splittable trim: the estimate_tokens fast path
  (prefix sums) returns byte-identical output to the original
  drop-oldest loop; custom counters keep the loop verbatim.
- Search pre-filter: _could_match is a necessary condition
  only — search results are identical to the unfiltered scan,
  including adversarial stemming cases.
- Bench gates themselves live in scripts/bench_p077_longchat.py
  + hidden_files/P077_BENCH_*.txt (P-046 discipline: budget in
  evidence, battery carries only loose tripwires).
Fixtures mirror test_p075_message_provenance.py.
"""

import asyncio
import hashlib
import json
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.chats import search as search_mod
from runmal.chats import service as svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Chat, ChatEvent, Message, User
from runmal.prompt.composer import compose
from runmal.prompt.slots import Slot
from runmal.tokens import estimate_tokens

EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0041"  # P-077 PROVISIONAL migration
    engine = create_db_engine(db_path)
    factory = create_session_factory(engine)
    client = TestClient(create_app(factory))
    client.factory = factory  # same DB, for service-layer seeding
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def make_factory(tmp_path):
    db_path = tmp_path / "svc.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


def run(coro):
    return asyncio.run(coro)


async def _seed_user(factory):
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        return user.id


async def _seed_chat(factory, user_id, positions, base=EPOCH):
    """One chat whose messages carry the given positions (None =
    legacy row), created_at strictly increasing in list order."""
    async with factory() as session:
        chat = Chat(user_id=user_id, title="seeded")
        session.add(chat)
        await session.flush()
        ids = []
        for i, pos in enumerate(positions):
            msg = Message(
                chat_id=chat.id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"message {i} zorblax" if i % 97 == 0 else f"message {i}",
                swipes_json=json.dumps([f"message {i}"]),
                swipe_id=0,
                variant_history_json="[]",
                provenance_json="{}",
                position=pos,
                created_at=base + timedelta(seconds=i),
            )
            session.add(msg)
            await session.flush()
            ids.append(msg.id)
        await session.commit()
        return chat.id, ids


def _canon(dicts):
    return hashlib.sha256(
        json.dumps(dicts, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


# ----------------------------------------------------------------
# Migration
# ----------------------------------------------------------------


def test_migration_0041_provisional_index(tmp_path):
    assert MIGRATIONS[-1][0] == "0041"
    assert "PROVISIONAL" in MIGRATIONS[-1][1]
    db_path = tmp_path / "m.db"
    migrate_to_head(db_path)
    conn = sqlite3.connect(db_path)
    try:
        names = {row[1] for row in conn.execute("PRAGMA index_list(messages)")}
        assert "ix_messages_chat_position" in names
        cols = [
            row[2]
            for row in conn.execute("PRAGMA index_info(ix_messages_chat_position)")
        ]
        assert cols == ["chat_id", "position", "created_at", "id"]
    finally:
        conn.close()


# ----------------------------------------------------------------
# Paged history == legacy history (frozen-oracle equivalence)
# ----------------------------------------------------------------


def test_pages_concatenate_to_legacy_materialised(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await _seed_user(factory)
        chat_id, _ids = await _seed_chat(factory, uid, list(range(250)))
        async with factory() as s:
            legacy = [svc.message_to_dict(m) for m in await svc.get_history(s, uid, chat_id)]
            pages = []
            for offset in (0, 100, 200):
                page, total, eff_off, eff_lim = await svc.get_history_page(
                    s, uid, chat_id, limit=100, offset=offset
                )
                assert total == 250 and eff_off == offset and eff_lim == 100
                pages.extend(svc.message_to_dict(m) for m in page)
            tail, total, eff_off, _ = await svc.get_history_page(
                s, uid, chat_id, limit=100, tail=True
            )
            assert total == 250 and eff_off == 150
            tail_dicts = [svc.message_to_dict(m) for m in tail]
        assert _canon(pages) == _canon(legacy)
        assert _canon(tail_dicts) == _canon(legacy[-100:])
        # Deepest page == the legacy head, byte-identical.
        assert _canon(pages[:100]) == _canon(legacy[:100])

    run(main())


def test_pages_concatenate_to_legacy_null_positions(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await _seed_user(factory)
        chat_id, _ids = await _seed_chat(factory, uid, [None] * 120)
        async with factory() as s:
            legacy = [svc.message_to_dict(m) for m in await svc.get_history(s, uid, chat_id)]
            got = []
            offset = 0
            while True:
                page, total, eff_off, _ = await svc.get_history_page(
                    s, uid, chat_id, limit=50, offset=offset
                )
                got.extend(svc.message_to_dict(m) for m in page)
                offset += len(page)
                if offset >= total or not page:
                    break
        assert _canon(got) == _canon(legacy)

    run(main())


def test_history_page_router_shapes(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)

    created = client.post("/api/v1/chats", json={"title": "router chat"})
    assert created.status_code in (200, 201), created.text
    cid = created.json()["id"]
    for i in range(5):
        r = client.post(
            f"/api/v1/chats/{cid}/messages",
            json={"role": "user", "content": f"line {i}"},
        )
        assert r.status_code in (200, 201), r.text

    legacy = client.get(f"/api/v1/chats/{cid}/messages")
    assert legacy.status_code == 200
    assert isinstance(legacy.json(), list) and len(legacy.json()) == 5

    page = client.get(f"/api/v1/chats/{cid}/messages?limit=2&offset=0")
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 5 and body["limit"] == 2 and body["offset"] == 0
    assert body["has_more"] is True and len(body["messages"]) == 2
    assert [m["id"] for m in body["messages"]] == [m["id"] for m in legacy.json()[:2]]

    tail = client.get(f"/api/v1/chats/{cid}/messages?limit=2&tail=true")
    tbody = tail.json()
    assert tbody["offset"] == 3 and tbody["has_more"] is False
    assert [m["id"] for m in tbody["messages"]] == [m["id"] for m in legacy.json()[-2:]]

    # Offset alone (no limit) is a paged request, never the
    # legacy list: the offset must be honoured in paged shape.
    off = client.get(f"/api/v1/chats/{cid}/messages?offset=3")
    assert off.status_code == 200
    obody = off.json()
    assert isinstance(obody, dict) and obody["total"] == 5
    assert obody["offset"] == 3 and obody["has_more"] is False
    assert [m["id"] for m in obody["messages"]] == [m["id"] for m in legacy.json()[3:]]

    missing = client.get("/api/v1/chats/nope/messages?limit=2")
    assert missing.status_code == 404


# ----------------------------------------------------------------
# Append: fast path + exact fallback
# ----------------------------------------------------------------


async def _history_ids_positions(factory, uid, chat_id):
    async with factory() as s:
        msgs = await svc.get_history(s, uid, chat_id)
        return [(m.id, m.position) for m in msgs]


def test_append_fast_path_dense(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await _seed_user(factory)
        chat_id, _ = await _seed_chat(factory, uid, list(range(50)))
        before = dict(await _history_ids_positions(factory, uid, chat_id))
        async with factory() as s:
            msg = await svc.append_message(s, uid, chat_id, "user", "one more")
            new_id, new_pos = msg.id, msg.position
        after = dict(await _history_ids_positions(factory, uid, chat_id))
        assert new_pos == 50
        # Fast path touched nothing that already existed.
        for mid, pos in before.items():
            assert after[mid] == pos
        async with factory() as s:
            events = (
                await s.execute(
                    select(ChatEvent).where(
                        ChatEvent.chat_id == chat_id,
                        ChatEvent.kind == svc.EVENT_MESSAGE_APPENDED,
                    )
                )
            ).scalars().all()
        assert any(e.message_id == new_id for e in events)

    run(main())


@pytest.mark.parametrize(
    "positions",
    [
        [0, 0, 2],          # duplicate
        [0, 2],             # gap
        [1, 2, 3],          # dense but not zero-based
        [None, 1],          # mixed legacy + materialised
        [0, 1, 7, 3],       # out of order + gap
        [5],                # single irregular
    ],
)
def test_append_fallback_on_irregular_positions(tmp_path, positions):
    factory = make_factory(tmp_path)

    async def main():
        uid = await _seed_user(factory)
        chat_id, _ = await _seed_chat(factory, uid, list(positions))
        before_order = [mid for mid, _ in await _history_ids_positions(factory, uid, chat_id)]
        async with factory() as s:
            msg = await svc.append_message(s, uid, chat_id, "user", "one more")
        after = await _history_ids_positions(factory, uid, chat_id)
        after_ids = [mid for mid, _ in after]
        after_pos = sorted(p for _, p in after)
        # The exact old road: whole chat renumbered in display
        # order, new message last at len(existing).
        assert after_pos == list(range(len(positions) + 1))
        assert after_ids[: len(positions)] == before_order
        assert after_ids[-1] == msg.id
        assert dict(after)[msg.id] == len(positions)

    run(main())


def test_append_legacy_all_null_and_empty(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await _seed_user(factory)
        legacy_id, _ = await _seed_chat(factory, uid, [None, None, None])
        async with factory() as s:
            msg = await svc.append_message(s, uid, legacy_id, "user", "one more")
        assert msg.position is None
        after = await _history_ids_positions(factory, uid, legacy_id)
        assert all(p is None for _, p in after)

        async with factory() as s:
            chat = await svc.create_chat(s, uid, "empty")
            first = await svc.append_message(s, uid, chat.id, "user", "first")
        assert first.position is None

    run(main())


# ----------------------------------------------------------------
# Composer trim: fast path == the original loop (oracle in-test)
# ----------------------------------------------------------------


def _oracle_trim(parts, budget_remaining, count):
    parts = list(parts)
    trimmed = 0
    while parts and count("\n".join(parts)) > budget_remaining:
        parts.pop(0)
        trimmed += 1
    return parts, trimmed


def _compose_history(parts, budget, counter=None):
    slot = Slot(
        id="hist", kind="history", role="user", splittable=True,
        parts=tuple(parts),
    )
    return compose(
        [slot], context_limit=budget + 1024, reserve_response=1024,
        counter=counter,
    )


def test_composer_fast_path_matches_oracle():
    parts = []
    for i in range(2000):
        if i % 11 == 0:
            parts.append("")
        elif i % 7 == 0:
            parts.append("x" * 997)
        else:
            parts.append(f"part {i} " + "word " * (i % 40))
    for budget in (50, 500, 5000, 20000):
        expected_parts, expected_trimmed = _oracle_trim(
            parts, budget, estimate_tokens
        )
        result = _compose_history(parts, budget)
        if not expected_parts:
            assert len(result.manifest.included) == 0
            assert result.manifest.discarded[0].slot_id == "hist"
            continue
        assert len(result.messages) == 1
        assert result.messages[0].content == "\n".join(expected_parts)
        assert result.manifest.included[0].trimmed_parts == expected_trimmed


def test_composer_custom_counter_keeps_loop():
    def word_count(text):
        return max(1, len(text.split()))

    parts = [f"alpha beta {i}" for i in range(300)] + ["", "gamma delta"]
    for budget in (30, 120, 400):
        expected_parts, expected_trimmed = _oracle_trim(parts, budget, word_count)
        result = _compose_history(parts, budget, counter=word_count)
        if not expected_parts:
            assert len(result.manifest.included) == 0
            continue
        assert result.messages[0].content == "\n".join(expected_parts)
        assert result.manifest.included[0].trimmed_parts == expected_trimmed


# ----------------------------------------------------------------
# Search pre-filter: necessary condition, results unchanged
# ----------------------------------------------------------------


def test_could_match_is_necessary_for_scoring():
    # (content word, query word): both must stem to the same
    # token. The stemmer strips ONE suffix and is not confluent
    # (stem("cross") == "cros" but stem("crosses") == "cross"),
    # so pairs are chosen on the stemmer's real behaviour.
    cases = [
        ("dragons", "dragon"),      # content strips trailing s
        ("walking", "walk"),        # content strips ing
        ("crosses", "crosses"),    # both strip es -> cross
        ("slowly", "slow"),         # content strips ly
        ("classes", "classes"),     # both strip es -> class
        ("dragon", "dragon"),
        ("zorblax", "zorblax"),
        ("fjords", "fjord"),
    ]
    for raw, query in cases:
        qtokens = search_mod._dedup(search_mod.tokenise(query))
        assert len(qtokens) == 1
        assert search_mod.score_fulltext(qtokens, f"the {raw} rests") is not None
        assert search_mod._could_match(qtokens, f"the {raw} rests") is True
    # Provably-None messages are the only ones skipped.
    qtokens = search_mod._dedup(search_mod.tokenise("zorblax"))
    assert search_mod.score_fulltext(qtokens, "nothing relevant here") is None
    assert search_mod._could_match(qtokens, "nothing relevant here") is False
    # A token that merely CONTAINS the query term mid-word scores
    # None and is skipped: tokenisation never splits it out.
    assert search_mod.score_fulltext(qtokens, "azorblax b") is None
    assert search_mod._could_match(qtokens, "azorblax b") is False


def test_search_results_unchanged_with_prefilter(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await _seed_user(factory)
        chat_id, _ = await _seed_chat(factory, uid, list(range(300)))
        async with factory() as s:
            doc = await search_mod.search_chats(
                s, uid, "zorblax", mode="fulltext", chat_id=chat_id
            )
        # zorblax planted at i % 97 == 0 -> i = 0, 97, 194, 291.
        assert doc["total"] == 4
        assert doc["scanned_messages"] == 300

    run(main())


# ----------------------------------------------------------------
# Loose tripwires only (strict gates live in the bench/evidence)
# ----------------------------------------------------------------


def test_longchat_tripwires(tmp_path):
    factory = make_factory(tmp_path)

    async def main():
        uid = await _seed_user(factory)
        chat_id, _ = await _seed_chat(factory, uid, list(range(3000)))

        async def latest_page():
            async with factory() as s:
                page, total, _, _ = await svc.get_history_page(
                    s, uid, chat_id, limit=100, tail=True
                )
                return [svc.message_to_dict(m) for m in page]

        async def legacy_full():
            async with factory() as s:
                hist = await svc.get_history(s, uid, chat_id)
                return [svc.message_to_dict(m) for m in hist]

        t0 = time.perf_counter()
        page = await latest_page()
        page_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        full = await legacy_full()
        full_s = time.perf_counter() - t0
        assert len(page) == 100 and len(full) == 3000
        # Tripwire (not the budget): a page must be far cheaper
        # than the whole history and nowhere near a second.
        assert page_s < 1.0
        assert page_s < full_s

        samples = []
        for _ in range(5):
            async with factory() as s:
                t0 = time.perf_counter()
                await svc.append_message(s, uid, chat_id, "user", "tripwire")
                samples.append(time.perf_counter() - t0)
        samples.sort()
        assert samples[len(samples) // 2] < 0.2  # BUDGET-P077 F absolute

    run(main())
