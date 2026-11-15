"""R-10 acceptance (live): the persona + lore flows against the
real engine, in-process — a keyworded entry assigned to the
chat's character through a scope fires in the layered
lore-preview when the sample carries the keyword and stays
silent without it; the user-name and chat-persona round trips
land on the real roads."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from runmal.desktop.client import DesktopSession, RunmalClient
from runmal.desktop.engine import EngineHandle, EngineState
from runmal.desktop.lore_logic import LoreFlow, schema_fields
from runmal.desktop.persona_logic import PersonaFlow


@pytest.fixture()
def engine(tmp_path: Path, monkeypatch) -> Iterator[EngineHandle]:
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    handle = EngineHandle()
    assert handle.start(timeout=30.0).state is EngineState.RUNNING
    try:
        yield handle
    finally:
        handle.stop()


def make_flows(engine: EngineHandle) -> tuple[LoreFlow, PersonaFlow, RunmalClient]:
    session = DesktopSession.from_local_credential(engine.base_url)
    client = RunmalClient(session)
    return LoreFlow(client), PersonaFlow(client), client


CARD = {
    "name": "Gate Keeper",
    "description": "Guards the high pass.",
    "personality": "Calm, dry, kind.",
    "scenario": "A mountain pass above the tree line.",
    "system_prompt": "You guard the high pass.",
    "first_mes": "Well met, traveller. The pass is open.",
}


def test_lore_scope_fires_in_layered_preview(engine: EngineHandle) -> None:
    lore, _persona, client = make_flows(engine)
    keeper = client.create_character(dict(CARD), name="Gate Keeper")
    chat = client.create_chat(title="Lore gate", character_id=keeper.id)
    schema = lore.schema()
    book_fields = schema_fields(schema, "book")
    entry_fields = schema_fields(schema, "entry")
    # The real census drives the forms: 6 book fields, 21 entry
    # fields, activation_kind derived.
    assert len(book_fields) == 6
    assert len(entry_fields) == 21
    assert [f.name for f in entry_fields if f.derived] == ["activation_kind"]

    book = lore.save_book(None, book_fields, {
        "name": "Gate World", "description": "", "scan_depth": 4,
        "token_budget": None, "scan_mode": "depth",
        "scan_external_context": False,
    }, None)
    entry = lore.save_entry(book.id, None, entry_fields, {
        "name": "Ember fact",
        "content": "The gate ember remembers every traveller.",
        "keys": ["ember"], "secondary_keys": [],
        "selective_logic": "and_any", "inclusion_group": "",
        "group_weight": 100, "probability": 100, "priority": 100,
        "position": "before_char", "depth": None, "role": "system",
        "enabled": True, "constant": False, "vectorised": False,
        "case_sensitive": False, "whole_word": True,
        "sticky_prompts": 0, "cooldown_prompts": 0, "delay_prompts": 0,
    }, None)
    assert entry.id

    scope = lore.assign_scope(book.id, "character", keeper.id)
    assert scope.scope_kind == "character"

    rows, summaries, _shadowed = lore.preview_chat(
        chat.id, ["tell me about the ember at the gate"]
    )
    fired = [r for r in rows if r.entry_id == entry.id]
    assert fired and fired[0].status == "included"
    assert "ember" in fired[0].matched_primary
    assert any(s.scope == "character" and s.included >= 1 for s in summaries)

    rows, _summaries, _shadowed = lore.preview_chat(
        chat.id, ["a quiet evening, nothing more"]
    )
    quiet = [r for r in rows if r.entry_id == entry.id]
    assert quiet and quiet[0].status == "not_triggered"

    # The book's own preview agrees.
    own = lore.preview_book(book.id, ["ember?"])
    assert own and own[0].status == "included"


def test_persona_roads_round_trip(engine: EngineHandle) -> None:
    _lore, persona, client = make_flows(engine)
    state = persona.set_user_name("Volmarr")
    assert state.is_set and state.name == "Volmarr"
    state = persona.user_name()
    assert state.is_set and state.name == "Volmarr"
    state = persona.set_user_name("")
    assert not state.is_set and state.name == "User"

    keeper = client.create_character(dict(CARD), name="Gate Keeper")
    other = client.create_character(
        dict(CARD), name="Mask Bearer"
    )
    chat = client.create_chat(title="Persona gate", character_id=keeper.id)
    view = persona.chat_persona(chat.id)
    assert view.present and view.character_id == keeper.id
    view = persona.set_chat_persona(chat.id, other.id)
    assert view.present and view.character_id == other.id
    view = persona.set_chat_persona(chat.id, None)
    assert not view.present
