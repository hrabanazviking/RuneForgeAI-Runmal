"""P-018 acceptance: persona interop — ST-shaped persona files in/out.

Shapes rest on P-002's census (ST-08/ST-09, official public docs)
and P-005's authored corpus fixture. Personas authored fresh here.
"""

import json
from pathlib import Path

import pytest

from runmal.persona.interop import (
    DESCRIPTION_POSITIONS,
    PersonaParseError,
    UserPersona,
    export_persona,
    parse_persona,
    persona_description_slot,
)

CORPUS = Path(__file__).parent / "fixtures" / "interop" / "persona_st.json"


def test_corpus_fixture_imports_with_all_fields() -> None:
    persona = parse_persona(CORPUS.read_bytes())
    assert persona.name == "Ferry Passenger"
    assert persona.description.startswith("The community's tide-reader")
    assert "{{user}}" in persona.prompt
    assert persona.system_prompt == "" and persona.title == ""
    assert persona.description_position == "in_prompt"
    assert persona.position == 0  # legacy numeric preserved verbatim
    assert persona.depth is None and persona.role == ""


def test_corpus_round_trip_is_fixed_point() -> None:
    persona = parse_persona(CORPUS.read_bytes())
    once = export_persona(persona)
    twice = export_persona(parse_persona(once))
    assert once == twice
    assert parse_persona(once) == persona


def test_unknown_fields_survive_round_trip() -> None:
    data = json.loads(CORPUS.read_bytes())
    data["x_future_flag"] = {"nested": [1, "two", None, True]}
    persona = parse_persona(data)
    out = json.loads(export_persona(persona))
    assert out["x_future_flag"] == {"nested": [1, "two", None, True]}


def test_export_never_fabricates_depth_or_role() -> None:
    out = json.loads(export_persona(parse_persona(CORPUS.read_bytes())))
    assert "depth" not in out and "role" not in out
    assert "description_depth" not in out and "description_role" not in out


def test_all_canonical_positions_normalize() -> None:
    for position in DESCRIPTION_POSITIONS:
        persona = parse_persona({"name": "P", "description_position": position})
        assert persona.description_position == position
    none_p = parse_persona({"name": "P", "description_position": "none"})
    assert none_p.description_position == "disabled"
    assert parse_persona({"name": "P"}).description_position == "in_prompt"


def test_unknown_position_is_rejected_not_reinterpreted() -> None:
    with pytest.raises(PersonaParseError):
        parse_persona({"name": "P", "description_position": "sideways"})


def test_in_chat_depth_and_role() -> None:
    persona = parse_persona(
        {
            "name": "P",
            "description": "In-chat text.",
            "description_position": "in_chat",
            "depth": "3",
            "role": "user",
        }
    )
    assert persona.depth == 3 and persona.role == "user"
    slot = persona_description_slot(persona)
    assert slot is not None and slot.depth == 3 and slot.role == "user"
    assert slot.content == "In-chat text."
    out = json.loads(export_persona(persona))
    assert out["depth"] == 3 and out["role"] == "user"


def test_bad_depth_and_role_are_rejected() -> None:
    with pytest.raises(PersonaParseError):
        parse_persona({"name": "P", "depth": -1})
    with pytest.raises(PersonaParseError):
        parse_persona({"name": "P", "depth": "deep"})
    with pytest.raises(PersonaParseError):
        parse_persona({"name": "P", "role": "narrator"})
    assert parse_persona({"name": "P", "depth": None}).depth is None


def test_missing_name_and_bad_json_are_rejected() -> None:
    with pytest.raises(PersonaParseError):
        parse_persona({"description": "nameless"})
    with pytest.raises(PersonaParseError):
        parse_persona(b"{not json")
    with pytest.raises(PersonaParseError):
        parse_persona(b"[1, 2]")


def test_disabled_and_empty_descriptions_make_no_slot() -> None:
    disabled = UserPersona(name="P", description="Text.", description_position="disabled")
    assert persona_description_slot(disabled) is None
    assert persona_description_slot(UserPersona(name="P")) is None


def test_in_prompt_and_authors_note_slots() -> None:
    in_prompt = persona_description_slot(
        UserPersona(name="P", description="Prompt text.")
    )
    assert in_prompt is not None and in_prompt.kind == "persona"
    assert in_prompt.depth is None and in_prompt.content == "Prompt text."
    top = persona_description_slot(
        UserPersona(name="P", description="AN.", description_position="authors_note_top")
    )
    bottom = persona_description_slot(
        UserPersona(name="P", description="AN.", description_position="authors_note_bottom")
    )
    assert top is not None and bottom is not None
    assert top.kind == bottom.kind == "authors_note"
    assert top.order < bottom.order


def test_existing_card_persona_assembly_untouched() -> None:
    # S110's character-card persona assembly keeps its own contract.
    from runmal.cards.models import CharacterCard
    from runmal.persona import build_slot_manifest

    card = CharacterCard(name="Yrsa", description="A card.")
    assert build_slot_manifest(card) == {"description": "A card."}
