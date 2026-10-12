"""S307 acceptance: macro/variable helper.

Inserted variables resolve in previews (char/user/original + clock
variables, deterministic under a fixed clock); unknown variables are
visibly flagged and preserved; the tools UI carries the chip helper.
"""

from datetime import datetime

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.prompt.variables import list_variables, resolve_variables

FIXED = datetime(2026, 10, 12, 21, 47)  # a Monday


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_registry_lists_the_variable_model():
    names = [v["name"] for v in list_variables()]
    assert names == ["char", "user", "original", "time", "date", "weekday"]
    for v in list_variables():
        assert v["description"]


def test_inserted_variables_resolve():
    text = "{{char}} greets {{user}} at {{time}} on {{weekday}}, {{date}}."
    out = resolve_variables(text, char_name="Yrsa", user_name="Volmarr", now=FIXED)
    assert out.text == "Yrsa greets Volmarr at 21:47 on Monday, 2026-10-12."
    assert out.resolved == ["char", "user", "time", "weekday", "date"]
    assert out.unknown == []


def test_case_insensitive_and_original():
    out = resolve_variables("{{CHAR}}!", char_name="Yrsa", now=FIXED)
    assert out.text == "Yrsa!"
    original = "wrap: {{original}}"
    out = resolve_variables(original, now=FIXED)
    assert out.text == "wrap: wrap: {{original}}"


def test_unknown_variables_flagged_and_preserved():
    out = resolve_variables(
        "{{char}} feels {{mood}} under a {{moon_phase}} moon.",
        char_name="Yrsa", now=FIXED,
    )
    assert out.text == "Yrsa feels {{mood}} under a {{moon_phase}} moon."
    assert out.unknown == ["mood", "moon_phase"]
    assert out.resolved == ["char"]


def test_variables_api_and_preview(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    registry = client.get("/api/v1/tools/variables")
    assert registry.status_code == 200
    assert {v["name"] for v in registry.json()} >= {"char", "user", "time"}
    preview = client.post(
        "/api/v1/tools/resolve",
        json={"text": "{{char}} & {{user}} & {{nope}}",
              "char": "Bryn", "user": "Volmarr"},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["text"] == "Bryn & Volmarr & {{nope}}"
    assert body["unknown"] == ["nope"]


def test_tools_ui_has_helper(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    page = client.get("/tools")
    for marker in ('id="variable-chips"', 'id="resolve-btn"',
                   'id="unknown-vars"', 'id="v-char"', 'id="v-user"'):
        assert marker in page.text, marker
    js = client.get("/static/tools.js")
    assert "/api/v1/tools/variables" in js.text
    assert "/api/v1/tools/resolve" in js.text
    assert "var-chip" in js.text
