"""S511 — Voice UI island + campaign hardening: device selector, role
assignment with REMAP surfacing, status/waveform endpoints, the page,
and the license scan staying green over the declared voice tree."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.voice.audio import AudioDevice, FixtureDeviceProvider, RingBuffer
from runmal.voice.install import InstallPlan, is_installed
from runmal.voice.license_audit import FORBIDDEN_DISTRIBUTIONS, audit_distributions
from runmal.voice.router import waveform_levels


def make_client(tmp_path, monkeypatch, provider=None):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    app = create_app(factory)
    if provider is not None:
        app.state.voice_provider = provider
    client = TestClient(app)
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_devices_endpoint_enumerates(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    data = client.get("/api/v1/voice/devices").json()
    ids = {d["device_id"] for d in data["devices"]}
    assert "fix-mic" in ids and "fix-cable" in ids


def test_role_assignment_round_trip_and_persistence(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    res = client.put("/api/v1/voice/roles/user_mic", json={"device_id": "fix-mic"})
    assert res.status_code == 200
    roles = client.get("/api/v1/voice/roles").json()
    assert roles["assignments"]["user_mic"]["device_id"] == "fix-mic"
    assert roles["resolution"]["user_mic"]["status"] == "ok"
    # Persisted to the data dir: a fresh client sees the same assignment.
    client2 = make_client(tmp_path, monkeypatch)
    roles2 = client2.get("/api/v1/voice/roles").json()
    assert roles2["assignments"]["user_mic"]["device_id"] == "fix-mic"


def test_role_assignment_rejects_absent_and_wrong_direction(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    missing = client.put("/api/v1/voice/roles/user_mic", json={"device_id": "gone"})
    assert missing.status_code == 404  # never silently defaulted
    wrong = client.put("/api/v1/voice/roles/user_mic", json={"device_id": "fix-headset"})
    assert wrong.status_code == 400
    unknown = client.put("/api/v1/voice/roles/nope", json={"device_id": "fix-mic"})
    assert unknown.status_code == 404


def test_missing_saved_device_surfaces_remap_in_api_and_page(tmp_path, monkeypatch):
    provider = FixtureDeviceProvider()
    client = make_client(tmp_path, monkeypatch, provider)
    assert client.put("/api/v1/voice/roles/user_mic",
                      json={"device_id": "fix-mic"}).status_code == 200
    provider.set_devices([d for d in provider.list_devices()
                          if d.device_id != "fix-mic"])  # unplug the mic
    resolution = client.get("/api/v1/voice/roles").json()["resolution"]
    assert resolution["user_mic"]["status"] == "remap_required"
    assert resolution["user_mic"]["device_id"] is None
    page = client.get("/voice").text
    assert "remap-warning" in page and "hidden" not in page.split(
        'id="remap-warning"')[1].split(">")[0]


def test_voice_page_renders_selectors_and_waveform(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    page = client.get("/voice")
    assert page.status_code == 200
    for role in ("user_mic", "user_playback", "companion_output",
                 "room_capture", "monitor"):
        assert f'name="{role}"' in page.text
    assert 'id="waveform"' in page.text
    assert "Fixture Microphone" in page.text


def test_status_endpoint_reports_state_and_waveform(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    app_ring = RingBuffer()
    from runmal.voice.audio import floats_to_pcm16

    app_ring.push(floats_to_pcm16([0.5] * 16000))
    client.app.state.voice_ring = app_ring
    data = client.get("/api/v1/voice/status").json()
    assert data["state"] == "LISTENING"
    assert len(data["waveform"]) == 48
    assert max(data["waveform"]) > 0.4


def test_waveform_levels_math():
    assert waveform_levels([], buckets=4) == [0.0] * 4
    levels = waveform_levels([0, 16384, 0, -32768], buckets=2)
    assert levels == [0.5, 1.0]


def test_license_scan_stays_green_over_declared_voice_tree():
    """Campaign hardening: the pyproject voice extras contain no
    forbidden distribution, and the runtime tree audit passes.
    Kokoro/misaki are GONE from the declared tree (ADR-0005)."""
    pyproject = Path("pyproject.toml").read_text()
    voice_block = pyproject.split("voice = [", 1)[1].split("]", 1)[0]
    names = re.findall(r'"([A-Za-z0-9_.-]+)', voice_block)
    lowered = {n.lower().replace("_", "-") for n in names}
    assert not (lowered & FORBIDDEN_DISTRIBUTIONS), lowered
    assert "misaki" not in lowered
    report = audit_distributions({
        "numpy": "BSD-3-Clause", "onnxruntime": "MIT",
        "sounddevice": "MIT", "faster-whisper": "MIT",
        "ctranslate2": "MIT",
    })
    assert report.passed, report.summary()


def test_voice_api_requires_auth(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    client.headers.clear()
    assert client.get("/api/v1/voice/devices").status_code == 401
    # The page itself is public (loopback boundary), like /memories.
    assert client.get("/voice").status_code == 200


def test_extra_device_directions_kept_straight(tmp_path, monkeypatch):
    provider = FixtureDeviceProvider(devices=[
        AudioDevice("only-in", "Solo Mic", "input", "fixture")])
    client = make_client(tmp_path, monkeypatch, provider)
    page = client.get("/voice").text
    # No output devices exist: output selects render empty, not faked.
    assert "Solo Mic" in page


# ------------------------------------------------- backends (ADR-0005/6)

def test_backends_endpoint_lists_registry_with_honest_labels(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    data = client.get("/api/v1/voice/backends").json()
    tts = {e["key"]: e for e in data["tts"]}
    assert tts["cosyvoice"]["default_shipped"] is True
    assert tts["cosyvoice"]["notice"] == ""  # shipped: no user-install notice
    assert tts["cosyvoice"]["thresholds"]["max_first_audio_p50_s"] == 1.5
    assert tts["chatterbox"]["thresholds"]["max_first_audio_p50_s"] == 4.0
    assert tts["kitten"]["default_shipped"] is False
    assert "Not shipped with Rúnmál" in tts["kitten"]["notice"]
    assert tts["kitten"]["unverified_label"] == \
        "user-installed — not forge-verified"
    assert tts["piper"]["installable"] is True  # user's own one-button choice
    stt = {e["key"]: e for e in data["stt"]}
    assert stt["faster-whisper"]["default_shipped"] is True
    assert stt["faster-whisper"]["verified"] is True
    assert stt["distil-whisper"]["verified"] is True  # mechanism-proof extra
    assert stt["moonshine"]["installable"] is False  # registered, no recipe
    assert stt["moonshine"]["unverified_label"] == \
        "user-installed — not forge-verified"
    assert data["defaults"] == {"tts_backend": "cosyvoice",
                                "stt_backend": "faster-whisper"}


def test_install_endpoint_refuses_unverified_and_unknown(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    refused = client.post("/api/v1/voice/backends/stt/moonshine/install")
    assert refused.status_code == 200
    assert refused.json()["status"] == "refused"  # explains; nothing runs
    missing = client.post("/api/v1/voice/backends/tts/nope/install")
    assert missing.status_code == 404


def test_is_installed_probes_vendor_checkout_for_git_backends(
        tmp_path, monkeypatch):
    # Git-checkout backends (CosyVoice) are not on sys.path in a fresh
    # process; the probe must look in the vendor dir, or a completed
    # install reads as missing (purplelongship evidence, 2026-10-13).
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    plan = InstallPlan(
        key="cosyvoice", kind="tts", probe_import="cosyvoice",
        git_checkout=("https://example.invalid/CosyVoice.git", "abc",
                      "CosyVoice"))
    assert not is_installed(plan)
    pkg = tmp_path / "vendor" / "CosyVoice" / "cosyvoice"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    assert is_installed(plan)


def test_settings_defaults_round_trip_and_validation(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    res = client.put("/api/v1/voice/settings/defaults",
                     json={"tts_backend": "chatterbox"})
    assert res.status_code == 200 and res.json()["tts_backend"] == "chatterbox"
    assert (tmp_path / "voice_settings.json").exists()
    client2 = make_client(tmp_path, monkeypatch)
    defaults = client2.get("/api/v1/voice/settings/defaults").json()
    assert defaults["tts_backend"] == "chatterbox"  # persisted across clients
    bad = client.put("/api/v1/voice/settings/defaults",
                     json={"tts_backend": "kokoro-onnx"})
    assert bad.status_code == 400  # the removed engine is not selectable


def test_voice_page_renders_backends_panel_with_notices(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    page = client.get("/voice").text
    assert 'id="voice-backends"' in page
    assert "CosyVoice" in page and "Kitten" in page
    assert "Not shipped with Rúnmál" in page
    assert "user-installed — not forge-verified" in page


def test_voice_settings_store_tolerant_load(tmp_path, monkeypatch):
    from runmal.voice.settings import VoiceSettings, settings_path

    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    settings = VoiceSettings.load()
    assert settings.tts_backend == "cosyvoice"
    assert settings.stt_backend == "faster-whisper"
    settings.set_tts_backend("piper")
    settings.save()
    assert VoiceSettings.load().tts_backend == "piper"
    settings_path().write_text("{corrupt")
    assert VoiceSettings.load().tts_backend == "cosyvoice"  # never bricks
