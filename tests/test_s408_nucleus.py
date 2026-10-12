"""S408 (roadmap): memory nucleus.

Acceptance: prompt trace shows nucleus inclusion and budget behavior
(integrates with the S214 trace).
"""

from __future__ import annotations

from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import User
from runmal.memory.nucleus import get_nucleus, nucleus_slot, set_nucleus
from runmal.prompt.composer import compose
from runmal.prompt.slots import make_slot
from runmal.prompt.trace import build_trace, trace_to_dict


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def seed(factory):
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        uid = user.id
        await set_nucleus(session, uid, None,
                          ["Volmarr is a Norse pagan priest."])
        await set_nucleus(session, uid, "char-a",
                          ["Yrsa is a seidhr witch of the Uppsala forests."])
        await session.commit()
        return uid


async def test_nucleus_curation_and_scope(tmp_path):
    factory = make_factory(tmp_path)
    uid = await seed(factory)
    async with factory() as session:
        user_level = await get_nucleus(session, uid)
        assert [m.content for m in user_level] == ["Volmarr is a Norse pagan priest."]
        char_level = await get_nucleus(session, uid, "char-a")
        assert len(char_level) == 2  # user-level + character-level
        other = await get_nucleus(session, uid, "char-b")
        assert [m.content for m in other] == ["Volmarr is a Norse pagan priest."]
        assert all(m.pinned and m.stability == 1.0 for m in char_level)
        # Re-curation replaces the character set atomically.
        await set_nucleus(session, uid, "char-a", ["Yrsa tends the herb garden."])
        await session.commit()
        char_level = await get_nucleus(session, uid, "char-a")
        assert [m.content for m in char_level] == [
            "Volmarr is a Norse pagan priest.", "Yrsa tends the herb garden."]


async def test_trace_shows_nucleus_inclusion_and_budget(tmp_path):
    factory = make_factory(tmp_path)
    uid = await seed(factory)
    async with factory() as session:
        memories = await get_nucleus(session, uid, "char-a")
    slot = nucleus_slot(memories, "char-a")
    assert slot is not None and slot.kind == "memory_nucleus"
    slots = [
        make_slot("main_system", "system", "You are Runmal.", required=True, id="sys"),
        slot,
        make_slot("post_history", "system", "x" * 4000, id="too-big"),
    ]
    composed = compose(slots, context_limit=512, reserve_response=64)
    trace = trace_to_dict(build_trace(composed, slots))
    nucleus_entries = [s for s in trace["slots"] if s["kind"] == "memory_nucleus"]
    assert nucleus_entries and nucleus_entries[0]["status"] == "included"
    assert trace["memory_slots"] == [
        {"slot_id": "nucleus/char-a", "kind": "memory_nucleus", "status": "included"}]
    big = [s for s in trace["slots"] if s["slot_id"] == "too-big"]
    assert big and big[0]["status"] == "discarded"  # budget behavior visible
    assert nucleus_slot([], "char-a") is None
