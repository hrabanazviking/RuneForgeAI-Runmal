"""R-12 acceptance (live): the four flows against the real
engine, in-process — a memory seeded through the engine's own
service reads back through the browser flow with provenance;
a scenario created through the flow binds to an empty chat
and seeds its bootstrap lines; a real send's prompt trace
explains its slots (the lore slot included, with its trigger);
the macro registry and compose preview answer for real."""

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest

from runmal.desktop.client import DesktopSession, RunmalClient
from runmal.desktop.compose_logic import ComposeFlow
from runmal.desktop.engine import EngineHandle, EngineState
from runmal.desktop.inspector_logic import InspectorFlow, slot_lines
from runmal.desktop.memory_logic import MemoryFlow
from runmal.desktop.scenario_logic import ScenarioFlow

CARD = {
    "name": "Gate Keeper",
    "description": "Guards the high pass.",
    "personality": "Calm, dry, kind.",
    "scenario": "A mountain pass above the tree line.",
    "system_prompt": "You guard the high pass.",
    "first_mes": "Well met, traveller. The pass is open.",
}


def seed_memory(data_dir: Path) -> None:
    """Seed one memory through the engine's own service, before
    the engine starts (the S410 pattern)."""
    from runmal.db.base import create_db_engine, create_session_factory
    from runmal.db.migrate import migrate_to_head
    from runmal.db.owners import get_or_create_owner
    from runmal.memory import service

    db_path = data_dir / "runmal.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    factory = create_session_factory(engine)

    async def go() -> None:
        async with factory() as session:
            owner = await get_or_create_owner(session)
            await service.create_memory(
                session,
                owner.id,
                content="The gate bell rings at dusk.",
                subject="gate bell",
                predicate="rings_at",
                scope="witnesses",
                witnesses=("char-a",),
                extractor={"kind": "fake", "model": "fx"},
                sources=(("message", "m1", "chat-1"),),
            )
            await session.commit()

    asyncio.run(go())


@pytest.fixture()
def engine(tmp_path: Path, monkeypatch) -> Iterator[EngineHandle]:
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    seed_memory(tmp_path)
    handle = EngineHandle()
    assert handle.start(timeout=30.0).state is EngineState.RUNNING
    try:
        yield handle
    finally:
        handle.stop()


def make_client(engine: EngineHandle) -> RunmalClient:
    session = DesktopSession.from_local_credential(engine.base_url)
    return RunmalClient(session)


def test_memory_browser_reads_seeded_memory(engine: EngineHandle) -> None:
    flow = MemoryFlow(make_client(engine))
    rows = flow.search(q="gate bell")
    assert len(rows) == 1
    assert rows[0].subject == "gate bell"
    detail = flow.detail(rows[0].id)
    assert detail["content"] == "The gate bell rings at dusk."
    assert detail["sources"], "provenance sources must ride along"
    assert "graph" in detail
    assert flow.search(q="no such words") == []


def test_scenario_bind_seeds_chat(engine: EngineHandle) -> None:
    client = make_client(engine)
    flow = ScenarioFlow(client)
    # Binding requires an EMPTY chat: a character chat starts
    # with its greeting, so the stage chat has no character.
    chat = client.create_chat(title="Empty stage")
    scenario = flow.create(
        {
            "name": "Gate Watch",
            "description": "A night at the pass.",
            "scenario_text": "Snow closes in.",
            "flow": "chat",
            "bootstrap_messages": [
                {"kind": "message", "role": "assistant",
                 "text": "The watch begins."}
            ],
        }
    )
    binding = flow.bind(scenario, chat.id)
    assert binding
    opened = client.get_chat(chat.id)
    assert opened is not None
    messages = client.list_chat_messages(chat.id)
    contents = [m.content for m in messages]
    assert "The watch begins." in contents
    assert flow.chat_binding(chat.id)
    flow.unbind(chat.id)


def test_inspector_trace_explains_a_real_send(engine: EngineHandle) -> None:
    from runmal.desktop.chat_logic import ChatFlow
    from runmal.desktop.lore_logic import LoreFlow

    client = make_client(engine)
    inspector = InspectorFlow(client)
    lore = LoreFlow(client)
    keeper = client.create_character(dict(CARD), name="Gate Keeper")
    profile = client.create_backend_profile(
        "Demo", "fake", chat_model="fake-1"
    )
    assert profile.id
    from runmal.desktop.lore_logic import schema_fields

    schema = lore.schema()
    book_fields = schema_fields(schema, "book")
    entry_fields = schema_fields(schema, "entry")
    book = lore.save_book(None, book_fields, {
        "name": "Gate World", "description": "", "scan_depth": 4,
        "token_budget": None, "scan_mode": "depth",
        "scan_external_context": False,
    }, None)
    entry = lore.save_entry(book.id, None, entry_fields, {
        "name": "Ember fact",
        "content": "Embers remember every fire.",
        "keys": ["ember"], "secondary_keys": [],
        "selective_logic": "and_any", "inclusion_group": "",
        "group_weight": 100, "probability": 100, "priority": 100,
        "position": "before_char", "depth": None, "role": "system",
        "enabled": True, "constant": False, "vectorised": False,
        "case_sensitive": False, "whole_word": True,
        "sticky_prompts": 0, "cooldown_prompts": 0, "delay_prompts": 0,
    }, None)
    assert entry.id
    lore.assign_scope(book.id, "character", keeper.id)
    chat = client.create_chat(title="Gate chat", character_id=keeper.id)
    chat_flow = ChatFlow(client)
    chat_flow.open_chat(chat.id)
    result = chat_flow.send_turn(chat.id, "Tell me about the ember at the gate.")
    assert result is not None
    trace = inspector.trace(
        chat.id,
        character_id=keeper.id,
        messages=["Tell me about the ember at the gate."],
    )
    lines = slot_lines(trace)
    assert lines, "the trace must name its slots"
    lore_lines = [line for line in lines if line.startswith("lore")]
    assert lore_lines, f"expected lore slots in: {lines}"
    assert any(
        "Included" in line for line in lore_lines
    ), f"the ember entry should be included: {lore_lines}"
    assert any(
        'triggered by "ember"' in line for line in lore_lines
    ), f"the slot must name its trigger key: {lore_lines}"
    from runmal.desktop.inspector_logic import lore_account_words

    account = lore_account_words(trace)
    assert account and "tokens used" in account[0], (
        f"the lore account must render: {account}"
    )
    overview = inspector.overview(chat.id)
    assert isinstance(overview, dict) and overview


def test_macros_and_compose_live(engine: EngineHandle) -> None:
    flow = ComposeFlow(make_client(engine))
    macros = flow.macros()
    assert macros and any(m.get("name") == "char" for m in macros)
    expanded = flow.expand("{{char}} stands watch.", char="Gate Keeper")
    text = expanded.get("text") or expanded.get("expanded") or ""
    assert "Gate Keeper" in text
    result = flow.compose(system="Be kind.", history=["Hello there"])
    assert result.get("messages"), "compose must produce messages"
