"""S110 acceptance: persona prompt assembly, golden slot manifests."""

from pathlib import Path

from runmal.cards import import_card
from runmal.cards.models import CharacterCard
from runmal.persona import (
    SLOT_ORDER,
    build_slot_manifest,
    render_system_prompt,
    substitute_macros,
)

FIXTURES = Path(__file__).parent / "fixtures" / "cards"


def load(name: str):
    return import_card((FIXTURES / name).read_bytes(), name)


def test_golden_manifest_v2() -> None:
    manifest = build_slot_manifest(load("v2.json"))
    assert manifest == {
        "system_prompt": "You are Test.",
        "description": "A v2 test card.",
        "personality": "Playful.",
        "scenario": "A test hall.",
        "mes_example": "<START>Yo<END>",
        "post_history_instructions": "Stay in character.",
    }
    assert list(manifest) == list(SLOT_ORDER)  # canonical order


def test_golden_manifest_v3() -> None:
    manifest = build_slot_manifest(load("v3.json"))
    assert manifest == {
        "description": "A v3 test card.",
        "personality": "Wise.",
        "scenario": "A test fjord.",
    }


def test_metadata_and_greetings_excluded() -> None:
    manifest = build_slot_manifest(load("v2.json"))
    for excluded in (
        "creator_notes",
        "tags",
        "creator",
        "first_mes",
        "alternate_greetings",
        "character_book",
        "extensions",
    ):
        assert excluded not in manifest
    assert "notes" not in render_system_prompt(manifest)  # creator_notes stays out
    assert "forge" not in render_system_prompt(manifest)  # creator stays out


def test_render_system_prompt_golden() -> None:
    manifest = build_slot_manifest(load("v2.json"))
    assert render_system_prompt(manifest) == (
        "You are Test.\n\n"
        "A v2 test card.\n\n"
        "Playful.\n\n"
        "A test hall.\n\n"
        "<START>Yo<END>\n\n"
        "Stay in character."
    )


def test_macros_char_user() -> None:
    card = CharacterCard(name="Yrsa", description="I am {{char}}, friend of {{user}}.")
    manifest = build_slot_manifest(card, user_name="Volmarr")
    assert manifest == {"description": "I am Yrsa, friend of Volmarr."}


def test_macros_case_insensitive() -> None:
    assert substitute_macros("{{CHAR}} and {{User}}", "Yrsa", "Volmarr") == "Yrsa and Volmarr"


def test_macro_original_expands_to_raw_text() -> None:
    out = substitute_macros("I am {{char}}. {{original}}", "Yrsa")
    assert out == "I am Yrsa. I am {{char}}. {{original}}"


def test_unknown_macros_left_alone() -> None:
    assert substitute_macros("keep {{foo}} intact", "Yrsa") == "keep {{foo}} intact"


def test_empty_slots_omitted() -> None:
    card = CharacterCard(name="Bare")
    assert build_slot_manifest(card) == {}
    assert render_system_prompt({}) == ""
