"""P-050 Instruct templates battery.

Pins the instruct-template contract: builtin public formats as
data (golden renders), template_from_data validation, per-model
honest defaults, resolve precedence, the render path, and the
inspector/API surface (echo, rendered_tokens, 422s, no prompt
content in the trace, registry endpoints).
"""

import json

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.prompt.composer import ComposedMessage
from runmal.prompt.inspect import MAIN_SYSTEM_TEXT
from runmal.prompt.instruct import (
    MODEL_TEMPLATE_DEFAULTS,
    TEMPLATE_ORDER,
    default_template_for_model,
    get_template,
    list_templates,
    template_from_data,
    template_to_data,
)
from runmal.prompt.render import render_prompt
from runmal.prompt.service import resolve_template, template_echo
from runmal.tokens import estimate_tokens

MSGS = [
    ComposedMessage("system", "You are helpful.", "s"),
    ComposedMessage("user", "Hello there.", "u"),
    ComposedMessage("assistant", "General Kenobi.", "a"),
    ComposedMessage("user", "Again.", "u2"),
]


# ---------------- registry / data ----------------

def test_registry_order_and_names():
    assert TEMPLATE_ORDER == ("plain", "chatml", "llama3", "alpaca", "vicuna")
    assert [t.name for t in list_templates()] == list(TEMPLATE_ORDER)
    with pytest.raises(ValueError):
        get_template("nope")


def test_builtin_roundtrip_all():
    for template in list_templates():
        assert template_from_data(template_to_data(template)) == template


def test_plain_is_honest_default():
    plain = get_template("plain")
    assert plain.stop_strings == ()
    assert plain.bos == "" and plain.generation_prefix == ""
    for _, wrapper in plain.wrappers:
        assert wrapper.prefix == "" and wrapper.suffix == ""


def test_model_defaults_table_is_data():
    names = {t.name for t in list_templates()}
    for pattern, template_name in MODEL_TEMPLATE_DEFAULTS:
        assert pattern and template_name in names


@pytest.mark.parametrize("bad", [
    "chatml", [], {"name": ""}, {"name": 3}, {"name": "x", "bogus": 1},
    {"name": "x", "bos": 1},
    {"name": "x", "wrappers": []},
    {"name": "x", "wrappers": {"narrator": {"prefix": "", "suffix": ""}}},
    {"name": "x", "wrappers": {"user": {"prefix": 1}}},
    {"name": "x", "wrappers": {"user": {"prefix": "", "weird": ""}}},
    {"name": "x", "stop_strings": "</s>"},
    {"name": "x", "stop_strings": [1]},
])
def test_template_from_data_rejects(bad):
    with pytest.raises(ValueError):
        template_from_data(bad)


# ---------------- per-model defaults + resolve ----------------

@pytest.mark.parametrize("model,want", [
    ("meta-llama-3-8b-instruct", "llama3"),
    ("Llama3.1-70B", "llama3"),
    ("qwen2.5-7b", "chatml"),
    ("my-chatml-build", "chatml"),
    ("vicuna-13b-v1.5", "vicuna"),
    ("alpaca-lora", "alpaca"),
    ("some-unknown-model", "plain"),
    ("", "plain"),
    (None, "plain"),
])
def test_default_template_for_model(model, want):
    assert default_template_for_model(model).name == want


def test_resolve_precedence():
    template, source = resolve_template("chatml", "llama-3")
    assert (template.name, source) == ("chatml", "explicit")
    template, source = resolve_template(None, "llama-3-8b")
    assert (template.name, source) == ("llama3", "model_default")
    template, source = resolve_template(None, "unknown-x")
    assert (template.name, source) == ("plain", "default")
    template, source = resolve_template(None, None)
    assert (template.name, source) == ("plain", "default")
    custom = {"name": "mine", "wrappers": {"user": {"prefix": "U:", "suffix": ""}}, "stop_strings": ["END"]}
    template, source = resolve_template(custom, "llama-3")
    assert (template.name, source) == ("mine", "explicit")
    assert template.stop_strings == ("END",)
    with pytest.raises(ValueError):
        resolve_template("nope", None)
    assert template_echo(get_template("chatml"), "explicit") == {
        "name": "chatml", "source": "explicit",
        "stop_strings": ["<|im_end|>", "<|im_start|>"],
    }


# ---------------- golden renders ----------------

def test_render_chatml_golden():
    rendered = render_prompt(MSGS, get_template("chatml"))
    assert rendered.text == (
        "<|im_start|>system\nYou are helpful.<|im_end|>\n"
        "<|im_start|>user\nHello there.<|im_end|>\n"
        "<|im_start|>assistant\nGeneral Kenobi.<|im_end|>\n"
        "<|im_start|>user\nAgain.<|im_end|>\n"
        "<|im_start|>assistant\n"
    )
    assert rendered.stop_strings == ("<|im_end|>", "<|im_start|>")
    assert rendered.template_name == "chatml"


def test_render_llama3_golden():
    rendered = render_prompt(MSGS[:2], get_template("llama3"))
    assert rendered.text == (
        "<|begin_of_text|>"
        "<|start_header_id|>system<|end_header_id|>\n\nYou are helpful.<|eot_id|>"
        "<|start_header_id|>user<|end_header_id|>\n\nHello there.<|eot_id|>"
        "<|start_header_id|>assistant<|end_header_id|>\n\n"
    )
    assert rendered.stop_strings == ("<|eot_id|>", "<|end_of_text|>")


def test_render_plain_golden():
    rendered = render_prompt(MSGS[:2], get_template("plain"))
    assert rendered.text == "You are helpful.\n\nHello there."
    assert rendered.stop_strings == ()


def test_render_alpaca_golden():
    rendered = render_prompt(MSGS[:2], get_template("alpaca"))
    assert rendered.text == (
        "You are helpful.\n\n### Instruction:\nHello there.\n\n### Response:\n"
    )


def test_render_vicuna_preamble_only_without_system():
    vicuna = get_template("vicuna")
    with_system = render_prompt(MSGS[:2], vicuna)
    assert with_system.text == "You are helpful.\n\nUSER: Hello there.\nASSISTANT: "
    without = render_prompt(MSGS[1:2], vicuna)
    assert without.text.startswith(vicuna.preamble + "\n\nUSER: Hello there.")
    alpaca = get_template("alpaca")
    assert render_prompt(MSGS[1:2], alpaca).text.startswith(alpaca.preamble)


def test_render_dict_messages_and_unknown_role():
    rendered = render_prompt(
        [{"role": "user", "content": "hi"}, {"role": "narrator", "content": "lo"}],
        get_template("plain"),
    )
    assert rendered.text == "hi\n\nlo"


def test_render_custom_template_from_data():
    template = template_from_data({
        "name": "mine", "bos": "<s>",
        "wrappers": {"user": {"prefix": "[{role}] ", "suffix": " "}},
        "generation_prefix": "[{role}] ", "stop_strings": ["END"],
    })
    rendered = render_prompt([{"role": "user", "content": "hi"}], template)
    assert rendered.text == "<s>[user] hi [assistant] "
    assert rendered.stop_strings == ("END",)


# ---------------- inspector / API ----------------

def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _inspect(client, **kw):
    resp = client.post("/api/v1/debug/prompt-inspect", json=kw)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _expected_tokens(template_name, **kw):
    messages = [ComposedMessage("system", MAIN_SYSTEM_TEXT, "system/main")]
    if kw.get("messages"):
        messages.append(ComposedMessage("user", "\n".join(kw["messages"]), "history"))
    return estimate_tokens(render_prompt(messages, get_template(template_name)).text)


def test_api_default_plain_echo_and_tokens(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    result = _inspect(client, messages=["hello"])
    assert result["instruct_template"] == {
        "name": "plain", "source": "default", "stop_strings": [],
    }
    assert result["rendered_tokens"] == _expected_tokens("plain", messages=["hello"])
    assert result["rendered_tokens"] > 0


def test_api_model_default_and_explicit_override(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    by_model = _inspect(client, messages=["hello"], model_id="llama-3-8b")
    assert by_model["instruct_template"]["name"] == "llama3"
    assert by_model["instruct_template"]["source"] == "model_default"
    assert by_model["rendered_tokens"] == _expected_tokens("llama3", messages=["hello"])
    assert by_model["rendered_tokens"] != _expected_tokens("plain", messages=["hello"])
    explicit = _inspect(client, messages=["hello"], model_id="llama-3-8b", instruct_template="chatml")
    assert explicit["instruct_template"]["name"] == "chatml"
    assert explicit["instruct_template"]["source"] == "explicit"
    assert explicit["rendered_tokens"] == _expected_tokens("chatml", messages=["hello"])


def test_api_custom_template_dict(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    custom = {"name": "mine", "wrappers": {"user": {"prefix": "U:", "suffix": ""}}, "stop_strings": ["END"]}
    result = _inspect(client, messages=["hello"], instruct_template=custom)
    assert result["instruct_template"] == {
        "name": "mine", "source": "explicit", "stop_strings": ["END"],
    }


def test_api_unknown_template_422(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.post("/api/v1/debug/prompt-inspect", json={"instruct_template": "nope"})
    assert resp.status_code == 422
    resp = client.post("/api/v1/debug/prompt-inspect", json={"instruct_template": {"name": "x", "bogus": 1}})
    assert resp.status_code == 422


def test_api_trace_carries_no_prompt_content(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    result = _inspect(client, messages=["hello"], instruct_template="chatml")
    dumped = json.dumps(result)
    assert MAIN_SYSTEM_TEXT not in dumped
    # Stop strings are template metadata (declared data), not
    # content; the rendered framing AROUND content must not leak.
    assert "<|im_start|>system" not in dumped
    assert "<|im_start|>user" not in dumped


def test_api_registry_endpoints(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    listing = client.get("/api/v1/debug/instruct-templates")
    assert listing.status_code == 200
    templates = listing.json()["templates"]
    assert [t["name"] for t in templates] == list(TEMPLATE_ORDER)
    chatml = next(t for t in templates if t["name"] == "chatml")
    assert chatml["wrappers"]["user"]["prefix"] == "<|im_start|>{role}\n"
    default = client.get("/api/v1/debug/instruct-templates/default")
    assert default.json()["template"]["name"] == "plain"
    by_model = client.get("/api/v1/debug/instruct-templates/default", params={"model": "qwen2.5"})
    assert by_model.json()["template"] == {
        "name": "chatml", "source": "model_default",
        "stop_strings": ["<|im_end|>", "<|im_start|>"],
    }


def test_render_vicuna_full_golden_assistant_closed():
    rendered = render_prompt(MSGS, get_template("vicuna"))
    assert rendered.text == (
        "You are helpful.\n\nUSER: Hello there.\n"
        "ASSISTANT: General Kenobi.</s>\nUSER: Again.\nASSISTANT: "
    )


def test_render_assistant_last_still_opens_next_turn():
    rendered = render_prompt(MSGS[:3], get_template("chatml"))
    assert rendered.text.endswith(
        "<|im_start|>assistant\nGeneral Kenobi.<|im_end|>\n<|im_start|>assistant\n"
    )


def test_render_empty_conversation_is_bos_plus_generation_prefix():
    assert render_prompt([], get_template("chatml")).text == "<|im_start|>assistant\n"
    assert render_prompt([], get_template("llama3")).text == (
        "<|begin_of_text|><|start_header_id|>assistant<|end_header_id|>\n\n"
    )
    assert render_prompt([], get_template("plain")).text == ""
