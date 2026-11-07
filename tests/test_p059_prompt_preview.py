"""P-059 Prompt preview battery.

Pins the prompt-preview contract: the pure build_preview payload
(exact keys, wire shape, slot ids, token count, stop strings), the
one-renderer rule (preview text is the inspect pipeline's render,
never a second rendering that could drift), the per-backend rows
pinned against the capability matrix, the API surface (opt-in on
prompt-inspect, dedicated prompt-preview endpoint, 422 on unknown
backend), the S214 boundary (content lives ONLY under
prompt_preview; slots/ledger stay content-free even with preview
on), the author's note appearing in the preview by design while
staying out of the slots, and the empty-message preview.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.backends.capabilities import capability_matrix
from runmal.backends.messages import ChatMessage
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.prompt import build_preview as exported_build_preview
from runmal.prompt.composer import ComposedMessage, compose
from runmal.prompt.inspect import MAIN_SYSTEM_TEXT
from runmal.prompt.instruct import get_template
from runmal.prompt.preview import (
    KNOWN_BACKENDS,
    build_preview,
    known_backend_keys,
    preview_from_composed,
)
from runmal.prompt.render import render_prompt
from runmal.prompt.slots import make_slot
from runmal.tokens import estimate_tokens

PREVIEW_KEYS = {
    "available", "backend_key", "model_id", "form", "messages",
    "wire_messages", "text", "template_name", "stop_strings",
    "rendered_tokens", "note",
}
BACKEND_KEYS = ["fake", "ollama", "openrouter", "aesir", "openai"]
USER_SECRET = "ZqxPreviewUserSecret59 unique words"
NOTE_TEXT = "ZqxAuthorsNotePreview59 hold the scene."
CTX = dict(context_limit=4096, reserve_response=512)


# ---------------- 1. pure build_preview ----------------

def test_init_export_is_build_preview():
    assert exported_build_preview is build_preview


def test_build_preview_exact_shape_and_wire():
    messages = [
        ComposedMessage("system", "You are helpful.", "system/main"),
        ChatMessage("user", "Hello there."),
        {"role": "assistant", "content": "General Kenobi."},
    ]
    rendered = render_prompt(messages, get_template("chatml"))
    preview = build_preview(
        messages, rendered, backend_key="fake", model_id="model-x"
    )
    assert set(preview.keys()) == PREVIEW_KEYS
    assert preview["available"] is True
    assert preview["backend_key"] == "fake"
    assert preview["model_id"] == "model-x"
    assert preview["form"] == "structured_messages"
    assert preview["messages"] == [
        {"role": "system", "content": "You are helpful.",
         "slot_id": "system/main"},
        {"role": "user", "content": "Hello there.", "slot_id": None},
        {"role": "assistant", "content": "General Kenobi.",
         "slot_id": None},
    ]
    # slot_id present for ComposedMessage, None for ChatMessage/dict.
    assert preview["messages"][0]["slot_id"] == "system/main"
    assert preview["messages"][1]["slot_id"] is None
    assert preview["messages"][2]["slot_id"] is None
    # wire_messages are exactly ChatMessage.to_dict() dicts.
    assert preview["wire_messages"] == [
        ChatMessage("system", "You are helpful.").to_dict(),
        ChatMessage("user", "Hello there.").to_dict(),
        ChatMessage("assistant", "General Kenobi.").to_dict(),
    ]
    for wire in preview["wire_messages"]:
        assert set(wire.keys()) == {"role", "content"}
    assert preview["text"] == rendered.text
    assert preview["template_name"] == "chatml" == rendered.template_name
    # stop_strings passthrough from the chatml render.
    assert preview["stop_strings"] == list(rendered.stop_strings)
    assert preview["stop_strings"] == ["<|im_end|>", "<|im_start|>"]
    assert preview["rendered_tokens"] == estimate_tokens(preview["text"])
    assert preview["rendered_tokens"] == estimate_tokens(rendered.text)
    assert isinstance(preview["note"], str) and preview["note"]


def test_build_preview_defaults_backend_and_model_none():
    messages = [ComposedMessage("user", "hi", "history")]
    rendered = render_prompt(messages, get_template("plain"))
    preview = build_preview(messages, rendered)
    assert set(preview.keys()) == PREVIEW_KEYS
    assert preview["backend_key"] is None
    assert preview["model_id"] is None
    assert preview["available"] is True
    assert preview["stop_strings"] == []


# ---------------- 2. one-renderer rule ----------------

def _compose_sample():
    slots = [
        make_slot("main_system", "system", MAIN_SYSTEM_TEXT,
                  required=True, id="system/main"),
        make_slot("history", "user", "", id="history",
                  splittable=True, parts=("hello", "again")),
    ]
    return compose(slots, **CTX)


def test_preview_text_is_the_one_render_no_drift():
    composed = _compose_sample()
    rendered = render_prompt(composed.messages, get_template("chatml"))
    preview = build_preview(composed.messages, rendered)
    assert preview["text"] == rendered.text
    # A second render of the same composed messages is identical:
    # deterministic, no drift between preview and pipeline.
    rendered2 = render_prompt(composed.messages, get_template("chatml"))
    assert rendered2.text == rendered.text
    assert rendered2 == rendered
    preview2 = build_preview(composed.messages, rendered2)
    assert preview2 == preview
    assert preview2["text"] == preview["text"]
    # preview_from_composed passes composed.messages through.
    via_helper = preview_from_composed(composed, rendered)
    assert via_helper == preview
    via_dict = preview_from_composed(
        {"messages": composed.messages}, rendered
    )
    assert via_dict == preview


# ---------------- 3. backend rows ----------------

@pytest.mark.parametrize("key", BACKEND_KEYS)
def test_backend_row(key):
    messages = [ComposedMessage("user", "hi", "history")]
    rendered = render_prompt(messages, get_template("plain"))
    preview = build_preview(messages, rendered, backend_key=key)
    assert preview["available"] is True
    assert preview["form"] == "structured_messages"
    assert preview["backend_key"] == key
    assert key in preview["note"]


def test_known_backends_pin_against_capability_matrix():
    matrix_keys = {
        row["backend_key"] for row in capability_matrix()["backends"]
    }
    assert known_backend_keys() == KNOWN_BACKENDS
    assert KNOWN_BACKENDS == matrix_keys
    assert matrix_keys == set(BACKEND_KEYS)


def test_unknown_backend_raises_value_error():
    messages = [ComposedMessage("user", "hi", "history")]
    rendered = render_prompt(messages, get_template("plain"))
    with pytest.raises(ValueError):
        build_preview(messages, rendered, backend_key="nope")


# ---------------- API harness (copied from p050/p056) ----------------

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


def _preview(client, **kw):
    resp = client.post("/api/v1/debug/prompt-preview", json=kw)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _make_chat(client, title="Hall"):
    resp = client.post("/api/v1/chats", json={"title": title})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _set_note(client, chat_id, payload):
    resp = client.post(f"/api/v1/chats/{chat_id}/authors-note", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _expected_text(template_name, user_messages):
    messages = [ComposedMessage("system", MAIN_SYSTEM_TEXT, "system/main")]
    if user_messages:
        messages.append(
            ComposedMessage("user", "\n".join(user_messages), "history")
        )
    return render_prompt(messages, get_template(template_name)).text


# ---------------- 4. prompt-inspect opt-in ----------------

def test_inspect_without_include_preview_no_key_no_leak(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    result = _inspect(client, messages=["hello"], instruct_template="chatml")
    assert "prompt_preview" not in result
    dumped = json.dumps(result)
    assert MAIN_SYSTEM_TEXT not in dumped
    assert "<|im_start|>system" not in dumped
    assert "<|im_start|>user" not in dumped


def test_inspect_with_include_preview_exact_render(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    result = _inspect(
        client, messages=["hello"], include_preview=True,
        instruct_template="chatml",
    )
    preview = result["prompt_preview"]
    assert set(preview.keys()) == PREVIEW_KEYS
    assert preview["text"] == _expected_text("chatml", ["hello"])
    assert preview["rendered_tokens"] == result["rendered_tokens"]
    assert preview["rendered_tokens"] == estimate_tokens(preview["text"])
    assert preview["template_name"] == result["instruct_template"]["name"]
    assert preview["template_name"] == "chatml"
    assert preview["messages"][0]["slot_id"] == "system/main"
    assert preview["messages"][0]["content"] == MAIN_SYSTEM_TEXT
    assert preview["wire_messages"][0] == {
        "role": "system", "content": MAIN_SYSTEM_TEXT,
    }
    assert any("hello" in w["content"] for w in preview["wire_messages"])
    assert all(w["content"] for w in preview["wire_messages"])


# ---------------- 5. dedicated prompt-preview endpoint ----------------

def test_preview_endpoint_always_includes_preview(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    result = _preview(client, messages=["hello"])
    assert "prompt_preview" in result
    preview = result["prompt_preview"]
    assert preview["available"] is True
    assert preview["backend_key"] is None
    assert "hello" in preview["text"]


def test_preview_endpoint_backend_key_echoed(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    result = _preview(client, messages=["hi"], backend_key="ollama")
    assert result["prompt_preview"]["backend_key"] == "ollama"
    assert "ollama" in result["prompt_preview"]["note"]


def test_unknown_backend_422_on_both_endpoints(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/api/v1/debug/prompt-preview",
        json={"messages": ["hi"], "backend_key": "nope"},
    )
    assert resp.status_code == 422, resp.text
    resp = client.post(
        "/api/v1/debug/prompt-inspect",
        json={"messages": ["hi"], "include_preview": True,
              "backend_key": "nope"},
    )
    assert resp.status_code == 422, resp.text


# ---------------- 6. S214 with preview ON ----------------

def test_s214_slots_and_ledger_carry_no_content_with_preview_on(
    tmp_path, monkeypatch
):
    client = make_client(tmp_path, monkeypatch)
    result = _inspect(
        client, messages=[USER_SECRET], include_preview=True,
        instruct_template="chatml",
    )
    slots_dump = json.dumps(result["slots"])
    ledger_dump = json.dumps(result["ledger"])
    for secret in (USER_SECRET, MAIN_SYSTEM_TEXT):
        assert secret not in slots_dump
        assert secret not in ledger_dump
    # Content lives ONLY under prompt_preview (sanity: it is there).
    preview = result["prompt_preview"]
    assert USER_SECRET in preview["text"]
    assert MAIN_SYSTEM_TEXT in preview["text"]
    assert any(USER_SECRET in m["content"] for m in preview["messages"])


# ---------------- 7. author's note by design ----------------

def test_authors_note_appears_in_preview_not_in_slots(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = _make_chat(client)["id"]
    _set_note(client, chat_id, {
        "text": NOTE_TEXT, "depth": 4, "frequency": 1,
        "enabled": True, "role": "system",
    })
    result = _preview(client, chat_id=chat_id, messages=["hi"])
    preview = result["prompt_preview"]
    assert any(NOTE_TEXT in m["content"] for m in preview["messages"])
    assert NOTE_TEXT in preview["text"]
    assert any(
        m["slot_id"] == "authors_note/chat" for m in preview["messages"]
    )
    assert NOTE_TEXT not in json.dumps(result["slots"])


# ---------------- 8. empty / no-message preview ----------------

def test_empty_messages_preview_is_system_only_plain(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    result = _preview(client, messages=[])
    preview = result["prompt_preview"]
    assert preview["messages"] == [
        {"role": "system", "content": MAIN_SYSTEM_TEXT,
         "slot_id": "system/main"}
    ]
    assert preview["wire_messages"] == [
        {"role": "system", "content": MAIN_SYSTEM_TEXT}
    ]
    expected = render_prompt(
        [ComposedMessage("system", MAIN_SYSTEM_TEXT, "system/main")],
        get_template("plain"),
    ).text
    assert preview["text"] == expected
    assert preview["template_name"] == "plain"
    assert preview["rendered_tokens"] == estimate_tokens(expected)
