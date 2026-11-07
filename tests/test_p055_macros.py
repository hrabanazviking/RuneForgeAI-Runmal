"""P-055 acceptance: macros — the documented text-macro engine.

Pins the slice's honesty contract: the full registry expands from
caller-supplied data under a fixed clock; random macros follow the
P-036 seeded-RNG discipline (a roll that exists is recorded and
reproducible; the unseeded path is labelled unseeded); unknown and
malformed macros never silently vanish and never pass through
disguised (preserved verbatim + reported, or refused in strict
mode); variables work on a copy and never mutate the caller's map.
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.prompt.macros import (
    MACROS,
    MacroContext,
    MacroError,
    expand_macros,
    list_macros,
)

FIXED = datetime(2026, 10, 12, 21, 47, 3)  # a Monday


def ctx(**kw):
    base = dict(char_name="Yrsa", user_name="Volmarr", now=FIXED)
    base.update(kw)
    return MacroContext(**base)


# -- registry -------------------------------------------------------

def test_registry_covers_the_roadmap_set():
    names = [m["name"] for m in list_macros()]
    for required in (
        "char", "user", "time", "date", "random", "roll",
        "getvar", "setvar", "original", "weekday",
    ):
        assert required in names
    assert len(names) == len(MACROS) == len(set(names))
    for row in list_macros():
        assert row["description"] and row["syntax"] and row["kind"]


# -- identity & clock -----------------------------------------------

def test_identity_macros_expand_from_context():
    out = expand_macros(
        "{{char}} greets {{user}} ({{persona}}); model={{model}} chat={{chatId}}",
        ctx(persona_name="The Walker", model="aesir-7b", chat_id="c-9"),
    )
    assert out.text == "Yrsa greets Volmarr (The Walker); model=aesir-7b chat=c-9"
    assert out.report.unknown == [] and out.report.errors == []
    assert [e.name for e in out.report.expansions] == [
        "char", "user", "persona", "model", "chatid",
    ]


def test_persona_falls_back_to_user_name():
    assert expand_macros("{{persona}}", ctx()).text == "Volmarr"


def test_last_message_family():
    out = expand_macros(
        "{{lastMessage}}|{{lastUserMessage}}|{{lastCharMessage}}",
        ctx(last_message="hm", last_user_message="hi", last_char_message="hail"),
    )
    assert out.text == "hm|hi|hail"


def test_case_and_whitespace_tolerance():
    out = expand_macros("{{ CHAR }} / {{User}}", ctx())
    assert out.text == "Yrsa / Volmarr"


def test_clock_macros_are_deterministic_under_fixed_now():
    out = expand_macros(
        "{{time}} {{isotime}} {{date}} {{datetime}} {{weekday}} "
        "{{year}}-{{month}}-{{day}} {{hour}}:{{minute}}:{{second}}",
        ctx(),
    )
    assert out.text == (
        "21:47 21:47:03 2026-10-12 2026-10-12 21:47:03 Monday "
        "2026-10-12 21:47:03"
    )


def test_original_is_the_pre_expansion_text():
    text = "wrap: {{original}}"
    assert expand_macros(text, ctx()).text == "wrap: wrap: {{original}}"
    out = expand_macros("{{original}}", ctx(original_text="seed text"))
    assert out.text == "seed text"


def test_expanded_values_are_never_rescanned():
    out = expand_macros("{{char}}", ctx(char_name="{{user}}"))
    assert out.text == "{{user}}"
    assert out.report.unknown == []


def test_angle_aliases_expand_and_can_be_disabled():
    assert expand_macros("<char> & <USER>", ctx()).text == "Yrsa & Volmarr"
    out = expand_macros("<char>", ctx(expand_angle_aliases=False))
    assert out.text == "<char>"


def test_escaped_macro_renders_literally():
    out = expand_macros(r"\{{char}} vs {{char}}", ctx())
    assert out.text == "{{char}} vs Yrsa"
    assert [e.name for e in out.report.expansions] == ["char"]


def test_unclosed_braces_are_not_a_macro_token():
    out = expand_macros("a {{char b {{", ctx())
    assert out.text == "a {{char b {{"
    assert out.report.unknown == [] and out.report.errors == []


# -- transforms -------------------------------------------------------

def test_transform_and_utility_macros():
    out = expand_macros(
        "{{upper::ab c}}|{{lower::AB C}}|{{reverse::abc}}|"
        "x{{newline::2}}y|a{{comment::note}}b|{{newline}}",
        ctx(),
    )
    assert out.text == "AB C|ab c|cba|x\n\ny|ab|\n"


def test_malformed_newline_is_preserved_and_reported():
    out = expand_macros("{{newline::many}}", ctx())
    assert out.text == "{{newline::many}}"
    assert len(out.report.errors) == 1 and "newline" in out.report.errors[0]


# -- variables --------------------------------------------------------

def test_variables_round_trip_within_one_pass():
    out = expand_macros(
        "{{setvar::mood::calm}}mood={{getvar::mood}}"
        "{{addvar::score::2}}{{addvar::score::3}}",
        ctx(variables={"score": 10}),
    )
    assert out.text == "mood=calm"
    assert out.report.variables == {"score": 15, "mood": "calm"}


def test_caller_variable_map_is_never_mutated():
    mine = {"score": 1}
    expand_macros("{{setvar::mood::x}}{{addvar::score::4}}", ctx(variables=mine))
    assert mine == {"score": 1}


def test_getvar_of_unset_variable_is_an_error_never_a_silent_empty():
    out = expand_macros("[{{getvar::nope}}]", ctx())
    assert out.text == "[{{getvar::nope}}]"
    assert len(out.report.errors) == 1 and "nope" in out.report.errors[0]
    with pytest.raises(MacroError):
        expand_macros("{{getvar::nope}}", ctx(), strict=True)


def test_addvar_on_non_numeric_variable_is_malformed():
    out = expand_macros("{{addvar::mood::1}}", ctx(variables={"mood": "calm"}))
    assert out.text == "{{addvar::mood::1}}"
    assert len(out.report.errors) == 1


# -- unknown / strict -------------------------------------------------

def test_unknown_macros_are_preserved_and_reported_never_disguised():
    out = expand_macros("{{char}} feels {{mood}} under {{moon_phase}}", ctx())
    assert out.text == "Yrsa feels {{mood}} under {{moon_phase}}"
    assert out.report.unknown == ["{{mood}}", "{{moon_phase}}"]


def test_strict_mode_refuses_and_names_every_problem():
    with pytest.raises(MacroError) as caught:
        expand_macros("{{mood}} and {{newline::many}}", ctx(), strict=True)
    message = str(caught.value)
    assert "{{mood}}" in message and "newline" in message


def test_strict_mode_passes_clean_text():
    out = expand_macros("{{char}} at {{time}}", ctx(), strict=True)
    assert out.text == "Yrsa at 21:47"


def test_empty_macro_is_malformed_not_vanished():
    out = expand_macros("a{{}}b", ctx())
    assert out.text == "a{{}}b"
    assert len(out.report.errors) == 1


# -- random: the P-036 honesty pattern --------------------------------

def test_random_pick_is_seeded_reproducible_and_recorded():
    text = "omen: {{random::raven::wolf::storm}}"
    first = expand_macros(text, ctx(seed=42, roll_context="chat-1"))
    second = expand_macros(text, ctx(seed=42, roll_context="chat-1"))
    assert first.text == second.text
    assert len(first.report.rolls) == 1
    roll = first.report.rolls[0]
    assert roll.seeded is True and roll.seed == 42
    assert roll.choices == ("raven", "wolf", "storm")
    assert roll.chosen_index in (0, 1, 2)
    assert roll.outcome == first.text.removeprefix("omen: ")
    assert 0.0 <= roll.roll < 1.0


def test_random_roll_depends_on_context_and_occurrence():
    text = "{{random::a::b::c::d::e::f}} {{random::a::b::c::d::e::f}}"
    one = expand_macros(text, ctx(seed=7, roll_context="tick-1"))
    two = expand_macros(text, ctx(seed=7, roll_context="tick-2"))
    assert [r.roll for r in one.report.rolls] != [r.roll for r in two.report.rolls]
    rolls = one.report.rolls
    assert rolls[0].occurrence == 0 and rolls[1].occurrence == 1
    assert rolls[0].roll != rolls[1].roll


def test_unseeded_random_is_labelled_unseeded():
    out = expand_macros("{{random::only}}", ctx())
    assert out.text == "only"
    roll = out.report.rolls[0]
    assert roll.seeded is False and roll.seed is None


def test_random_without_choices_is_malformed():
    out = expand_macros("{{random}}", ctx(seed=1))
    assert out.text == "{{random}}"
    assert len(out.report.errors) == 1 and out.report.rolls == []


def test_dice_roll_is_seeded_reproducible_and_recorded():
    first = expand_macros("{{roll::2d6+1}}", ctx(seed=99, roll_context="duel"))
    second = expand_macros("{{roll::2d6+1}}", ctx(seed=99, roll_context="duel"))
    assert first.text == second.text
    roll = first.report.rolls[0]
    assert len(roll.dice) == 2 and all(1 <= d <= 6 for d in roll.dice)
    assert int(first.text) == sum(roll.dice) + 1
    assert roll.seeded is True


def test_dice_roll_bounds_and_bad_specs():
    out = expand_macros("{{roll::d20}}", ctx(seed=3))
    assert 1 <= int(out.text) <= 20 and len(out.report.rolls[0].dice) == 1
    for bad in ("{{roll::2x6}}", "{{roll::0d6}}", "{{roll::2d1}}", "{{roll::}}"):
        bad_out = expand_macros(bad, ctx(seed=3))
        assert bad_out.text == bad and len(bad_out.report.errors) == 1


def test_result_dict_is_json_shaped_and_complete():
    out = expand_macros("{{random::a::b}}", ctx(seed=5))
    data = out.to_dict()
    assert data["text"] in ("a", "b")
    assert data["report"]["rolls"][0]["algorithm"] == "runmal-p055-macro-v1"
    assert data["report"]["expansions"][0]["name"] == "random"


# -- API ---------------------------------------------------------------

def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_macros_api_lists_registry_and_expands(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    listed = client.get("/api/v1/tools/macros")
    assert listed.status_code == 200
    assert "random" in [row["name"] for row in listed.json()]
    expanded = client.post(
        "/api/v1/tools/macros/expand",
        json={
            "text": "{{char}} picks {{random::a::b}}",
            "char": "Yrsa",
            "seed": 42,
            "roll_context": "api",
        },
    )
    assert expanded.status_code == 200
    body = expanded.json()
    assert body["text"].startswith("Yrsa picks ")
    assert body["report"]["rolls"][0]["seeded"] is True


def test_macros_api_strict_failure_is_a_visible_422(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    refused = client.post(
        "/api/v1/tools/macros/expand",
        json={"text": "{{mood}}", "strict": True},
    )
    assert refused.status_code == 422
    assert "{{mood}}" in refused.json()["detail"]
