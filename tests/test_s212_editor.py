"""S212 acceptance: persona/scenario/greeting editor UI/API integration.

Edits persist through the Campaign I character service, validation errors
surface as visible 422s, greeting variants round-trip exactly, and
unknown card fields/extensions survive an editor save (INV-009).
"""

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.cards import import_card
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head

FIXTURES = Path(__file__).parent / "fixtures" / "cards"
V2_CARD = json.loads((FIXTURES / "v2.json").read_text())


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client, db_path


def create_char(client):
    return client.post("/api/v1/characters", json={"card": V2_CARD}).json()["id"]


def test_editor_get_shows_card_fields(tmp_path, monkeypatch) -> None:
    client, _ = make_client(tmp_path, monkeypatch)
    char_id = create_char(client)
    view = client.get(f"/api/v1/characters/{char_id}/editor")
    assert view.status_code == 200
    body = view.json()
    assert body["description"] == V2_CARD["description"]
    assert body["personality"] == V2_CARD["personality"]
    assert body["scenario"] == V2_CARD["scenario"]
    assert body["first_mes"] == V2_CARD["first_mes"]
    assert body["alternate_greetings"] == V2_CARD["alternate_greetings"]


def test_editor_edits_persist_and_greetings_round_trip(tmp_path, monkeypatch) -> None:
    client, _ = make_client(tmp_path, monkeypatch)
    char_id = create_char(client)
    new_greetings = ["Hail, wanderer.", "The fire is lit; sit.", ""]
    patched = client.patch(
        f"/api/v1/characters/{char_id}/editor",
        json={
            "personality": "Gruff but kind.",
            "scenario": "A smithy at dusk.",
            "alternate_greetings": new_greetings,
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["alternate_greetings"] == new_greetings
    view = client.get(f"/api/v1/characters/{char_id}/editor").json()
    assert view["personality"] == "Gruff but kind."
    assert view["scenario"] == "A smithy at dusk."
    assert view["alternate_greetings"] == new_greetings  # exact round trip
    # untouched fields keep their values
    assert view["description"] == V2_CARD["description"]
    assert view["first_mes"] == V2_CARD["first_mes"]


def test_editor_save_preserves_unknown_fields(tmp_path, monkeypatch) -> None:
    client, db_path = make_client(tmp_path, monkeypatch)
    char_id = create_char(client)
    client.patch(
        f"/api/v1/characters/{char_id}/editor",
        json={"description": "Edited description."},
    )
    conn = sqlite3.connect(db_path)
    (card_json,) = conn.execute(
        "SELECT card_json FROM characters WHERE id = ?", (char_id,)
    ).fetchone()
    card = import_card(card_json.encode(), "card.json")
    assert card.description == "Edited description."
    assert card.raw.get("x_custom_unknown") is not None  # INV-009
    assert card.extensions == V2_CARD["extensions"]


def test_editor_validation_errors_are_visible(tmp_path, monkeypatch) -> None:
    client, _ = make_client(tmp_path, monkeypatch)
    char_id = create_char(client)
    # non-string greeting element -> pydantic 422 with detail
    bad = client.patch(
        f"/api/v1/characters/{char_id}/editor",
        json={"alternate_greetings": ["fine", 42]},
    )
    assert bad.status_code == 422
    assert bad.json()["detail"]
    # too many greetings -> service 422 with a readable message
    many = client.patch(
        f"/api/v1/characters/{char_id}/editor",
        json={"alternate_greetings": ["g"] * 51},
    )
    assert many.status_code == 422
    assert "50" in many.json()["detail"]
    # oversized text field -> 422
    big = client.patch(
        f"/api/v1/characters/{char_id}/editor",
        json={"description": "x" * 32001},
    )
    assert big.status_code == 422
    # failed edits changed nothing
    view = client.get(f"/api/v1/characters/{char_id}/editor").json()
    assert view["description"] == V2_CARD["description"]


def test_editor_unknown_character_404(tmp_path, monkeypatch) -> None:
    client, _ = make_client(tmp_path, monkeypatch)
    assert client.get("/api/v1/characters/nope/editor").status_code == 404
    assert client.patch(
        "/api/v1/characters/nope/editor", json={"personality": "x"}
    ).status_code == 404


def test_editor_ui_page(tmp_path, monkeypatch) -> None:
    client, _ = make_client(tmp_path, monkeypatch)
    page = client.get("/editor")
    assert page.status_code == 200
    for marker in ('id="editor-form"', 'id="f-description"', 'id="f-personality"',
                   'id="f-scenario"', 'id="f-first-mes"', 'id="greetings-list"',
                   'id="error-banner"', "editor.js"):
        assert marker in page.text, marker
    js = client.get("/static/editor.js")
    assert js.status_code == 200
    assert "/editor" in js.text and "alternate_greetings" in js.text
