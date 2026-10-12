"""S306 acceptance: connection + preset UI completion (integration).

Probe -> model list -> pick a model onto the profile; apply a preset to
a chat -> the generation request manifest shows the preset's params
compat-filtered for the active backend, mapped/dropped explicit.
"""

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.connections.service import ProbeOutcome
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_probe_models_and_model_picker_flow(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    profile = client.post(
        "/api/v1/connections",
        json={"name": "laptop", "backend": "ollama",
              "base_url": "http://localhost:11434"},
    ).json()

    def fake_prober(p):
        return ProbeOutcome(
            True, ["streaming", "local-models"], "fake ok",
            models=["gemma-heretic", "llama3.1"],
        )

    client.app.state.prober = fake_prober
    health = client.get(f"/api/v1/connections/{profile['id']}/health").json()
    assert health["models"] == ["gemma-heretic", "llama3.1"]
    assert health["capabilities"] == ["streaming", "local-models"]

    # the picker applies the chosen model onto the profile
    patched = client.patch(
        f"/api/v1/connections/{profile['id']}",
        json={"model": "llama3.1"},
    )
    assert patched.status_code == 200
    assert patched.json()["model"] == "llama3.1"
    assert client.get(f"/api/v1/connections/{profile['id']}").json()["model"] == "llama3.1"


def test_default_probe_fake_backend_lists_model(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    profile = client.post(
        "/api/v1/connections", json={"name": "stub", "backend": "fake"}
    ).json()
    health = client.get(f"/api/v1/connections/{profile['id']}/health").json()
    assert health["ok"] is True
    assert health["models"] == ["fake-echo"]


def test_preset_applied_generation_manifest(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    client.post(
        "/api/v1/connections",
        json={"name": "laptop", "backend": "ollama",
              "base_url": "http://localhost:11434", "model": "llama3.1"},
    )
    preset = client.post(
        "/api/v1/presets",
        json={"name": "saga", "params": {
            "temperature": 0.8, "max_tokens": 400,
            "repetition_penalty": 1.05, "frequency_penalty": 0.3}},
    ).json()
    chat = client.post("/api/v1/chats", json={"title": "Ford"}).json()

    # no preset yet: defined empty manifest
    empty = client.get(f"/api/v1/chats/{chat['id']}/generation-manifest")
    assert empty.status_code == 200
    assert empty.json()["preset"] is None
    assert empty.json()["params"] == {}

    applied = client.post(
        f"/api/v1/chats/{chat['id']}/preset", json={"preset_id": preset["id"]}
    )
    assert applied.status_code == 200
    assert applied.json()["preset_id"] == preset["id"]

    manifest = client.get(
        f"/api/v1/chats/{chat['id']}/generation-manifest"
    ).json()
    assert manifest["backend"] == "ollama"
    assert manifest["preset"]["name"] == "saga"
    assert manifest["params"]["num_predict"] == 400  # mapped
    assert manifest["params"]["repeat_penalty"] == 1.05  # mapped
    assert manifest["params"]["temperature"] == 0.8  # kept
    assert {(m["source"], m["dest"]) for m in manifest["mapped"]} == {
        ("max_tokens", "num_predict"),
        ("repetition_penalty", "repeat_penalty"),
    }
    assert [d["param"] for d in manifest["dropped"]] == ["frequency_penalty"]

    # clearing the preset returns to the empty manifest
    client.post(f"/api/v1/chats/{chat['id']}/preset", json={"preset_id": None})
    cleared = client.get(f"/api/v1/chats/{chat['id']}/generation-manifest").json()
    assert cleared["preset"] is None and cleared["params"] == {}


def test_preset_apply_errors(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    chat = client.post("/api/v1/chats", json={"title": "x"}).json()
    resp = client.post(
        f"/api/v1/chats/{chat['id']}/preset", json={"preset_id": "ghost"}
    )
    assert resp.status_code == 404
    resp = client.post("/api/v1/chats/ghost/preset", json={"preset_id": None})
    assert resp.status_code == 404
    resp = client.get("/api/v1/chats/ghost/generation-manifest")
    assert resp.status_code == 404


def test_ui_completion_markers(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    page = client.get("/connections")
    assert 'id="health-models"' in page.text  # model picker
    assert 'id="apply-model"' in page.text
    js = client.get("/static/connections.js")
    assert "PATCH" in js.text and "models" in js.text
    chat = client.get("/chat")
    assert 'id="preset-select"' in chat.text  # preset picker
    app = client.get("/static/app.js")
    assert "loadPresets" in app.text and "/preset" in app.text
