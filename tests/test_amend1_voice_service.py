"""Amendment 1 - voice saving from Runmal + per-character voice.

Engine roads: the speech-service voice registry proxy (config-
driven base URL, no hardcoded address), the S512 character voice
profile read/write roads, and the character audition road that
synthesizes with the resolved profile engaged. Webface: the w08
compositions the Voice tab and Characters picker ride.
"""
from __future__ import annotations

import asyncio
import base64

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import Character
from runmal.db.owners import get_or_create_owner
from runmal.voice import service_voices
from runmal.webface import w08


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    app = create_app(factory)
    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {get_or_create_credential()}"})
    return client, factory


def seed_character(factory, name="Asta"):
    async def go():
        async with factory() as session:
            owner = await get_or_create_owner(session)
            char = Character(user_id=owner.id, name=name, card_json="{}")
            session.add(char)
            await session.commit()
            return owner.id, char.id
    return asyncio.run(go())


def test_service_root_is_config_driven(monkeypatch):
    monkeypatch.setenv("RUNMAL_SPEECH_BASE_URL", "http://127.0.0.1:8910/v1")
    assert service_voices.service_root_url() == "http://127.0.0.1:8910"
    monkeypatch.delenv("RUNMAL_SPEECH_BASE_URL")
    with pytest.raises(service_voices.SpeechServiceError):
        service_voices.service_root_url()
    with pytest.raises(service_voices.SpeechServiceError):
        service_voices.register_service_voice("", "x", "eA==")


def test_registry_proxy_routes(tmp_path, monkeypatch):
    client, _f = make_client(tmp_path, monkeypatch)
    seen = {}
    import runmal.voice.router as router_mod
    monkeypatch.setattr(router_mod._service_voices, "list_service_voices",
                        lambda: [{"name": "proof-piper", "transcript": "t", "duration_s": 3.19}])
    def fake_register(name, transcript, audio_b64):
        seen.update(name=name, transcript=transcript, audio_b64=audio_b64)
        return {"name": name, "duration_s": 1.0}
    monkeypatch.setattr(router_mod._service_voices, "register_service_voice", fake_register)
    res = client.get("/api/v1/voice/service-voices")
    assert res.status_code == 200 and res.json()["names"] == ["proof-piper"]
    res = client.post("/api/v1/voice/service-voices", json={
        "name": "new-voice", "transcript": "hello", "audio_b64": "eA=="})
    assert res.status_code == 201 and seen["name"] == "new-voice"


def test_character_voice_profile_round_trip_and_audition(tmp_path, monkeypatch):
    client, factory = make_client(tmp_path, monkeypatch)
    _owner, cid = seed_character(factory)
    res = client.get(f"/api/v1/voice/characters/{cid}/voice-profile")
    assert res.status_code == 200
    assert res.json()["stored"] is None
    assert res.json()["resolved"]["voice_id"] == "cosyvoice-zero-shot"  # fallback
    res = client.put(f"/api/v1/voice/characters/{cid}/voice-profile", json={
        "tts_backend": "fake-tts", "voice_id": "fake-voice"})
    assert res.status_code == 200, res.text
    assert res.json()["stored"]["voice_id"] == "fake-voice"
    assert res.json()["resolved"]["tts_backend"] == "fake-tts"
    res = client.post(f"/api/v1/voice/characters/{cid}/audition", json={"text": "Hello."})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["resolved"]["voice_id"] == "fake-voice" and body["pcm_bytes"] > 0
    assert base64.b64decode(body["audio_b64"])
    res = client.put(f"/api/v1/voice/characters/{cid}/voice-profile", json={
        "tts_backend": "mystery", "voice_id": "x"})
    assert res.status_code == 400
    res = client.delete(f"/api/v1/voice/characters/{cid}/voice-profile")
    assert res.json()["removed"] is True
    assert res.json()["resolved"]["voice_id"] == "cosyvoice-zero-shot"


class _FakeEngine:
    def __init__(self): self.calls = []
    def request(self, method, path, json_body=None, params=None, files=None, data=None):
        self.calls.append((method, path, json_body))
        if path.endswith("/voice-profile") and method == "PUT":
            return {"stored": json_body, "resolved": {"tts_backend": "openai", "voice_id": json_body["voice_id"]}}
        if path == "/api/v1/voice/service-voices" and method == "POST":
            return {"name": json_body["name"]}
        if path.endswith("/audition"):
            return {"resolved": {"voice_id": "proof-piper"}, "pcm_bytes": 10, "audio_b64": "eA=="}
        raise AssertionError(path)


def test_webface_flows():
    eng = _FakeEngine()
    out = w08.set_character_voice(eng, "c1", "proof-piper")
    assert eng.calls[-1][2] == {"tts_backend": "openai", "voice_id": "proof-piper"}
    assert out["resolved"]["voice_id"] == "proof-piper"
    out = w08.set_character_voice(eng, "c1", "")
    assert eng.calls[-1][2] == {"tts_backend": "openai", "voice_id": "default"}
    out = w08.register_service_voice(eng, "n", "t", b"x")
    assert base64.b64decode(eng.calls[-1][2]["audio_b64"]) == b"x"
    out = w08.character_audition(eng, "c1", "hi")
    assert out["has_audio"] is True and "audio_b64" not in out
    assert w08.service_voice_line({"name": "v", "duration_s": 2.0, "transcript": "hi"}).startswith("v · reference")
