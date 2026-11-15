"""R-09 acceptance (live engine): the Connections & Generation
roads against the real in-process engine on a fresh data dir —
profile CRUD with write-only secrets, preset CRUD/import/export,
bundle + override + resolve, and the headline proof: a composed
turn whose recorded backend request carries the applied
preset's temperature (the R-03 recording-backend pattern).

No Qt here (the widgets are driven by
``scripts/desktop_r09_proof.py`` and ``test_r09_desktop_window.py``).
"""

import pytest

from runmal.backends.events import Done, TextDelta
from runmal.backends.fake import FakeChatBackend
from runmal.desktop.client import DesktopSession, RunmalClient
from runmal.desktop.engine import EngineHandle, EngineState
from runmal.desktop.settings_logic import SettingsFlow, effective_rows

CANARY = "CANARY-LIVE-51bd-never-echo"

CARD = {
    "name": "Gate Keeper",
    "description": "Guards the high pass.",
    "personality": "Calm, dry, kind.",
    "scenario": "A mountain pass above the tree line.",
    "system_prompt": "You guard the high pass.",
    "first_mes": "Well met, traveller. The pass is open.",
}


@pytest.fixture()
def live_engine(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    handle = EngineHandle()
    assert handle.start(timeout=30.0).state is EngineState.RUNNING
    yield handle
    handle.stop()


def make_client(handle) -> RunmalClient:
    return RunmalClient(DesktopSession.from_local_credential(handle.base_url))


class RecordingBackend(FakeChatBackend):
    """The R-03 pattern: a FakeChatBackend subclass that records
    the exact messages + SamplingParams it is handed."""

    def __init__(self, captured: dict):
        super().__init__(chunks=("recorded",))
        self.captured = captured

    async def chat_stream(self, messages, params, cancel, *, structured=None):
        self.captured["messages"] = list(messages)
        self.captured["params"] = params
        yield TextDelta("recorded reply")
        yield Done("stop", None)


def test_profiles_and_secrets_on_real_engine(live_engine) -> None:
    client = make_client(live_engine)
    try:
        flow = SettingsFlow(client)
        profile = flow.save_profile(
            None,
            name="Hearth",
            chat_backend="fake",
            chat_model="fake-1",
            chat_key=CANARY,
        )
        assert profile.has_chat_secret is True
        # INV-023 on the real engine: the canary is in no payload.
        assert CANARY not in repr(client.list_backend_profiles())
        assert CANARY not in repr(client.get_backend_profile(profile.id))
        probe = flow.probe(profile.id)
        assert probe.ok is True
        assert "Hearth" in probe.words
        cleared = flow.save_profile(
            profile.id, name="Hearth", chat_backend="fake", chat_key=""
        )
        assert cleared.has_chat_secret is False
        assert flow.delete_profile(profile.id) is True
        assert client.list_backend_profiles() == []
    finally:
        client.close()


def test_presets_bundles_resolve_on_real_engine(live_engine) -> None:
    client = make_client(live_engine)
    try:
        flow = SettingsFlow(client)
        preset = flow.save_preset(
            None,
            name="Warm",
            params={"temperature": 0.9, "vendor_flag": True},
        )
        assert preset.params["vendor_flag"] is True
        exported = flow.export_preset(preset.id)
        assert isinstance(exported, dict)
        bundle = flow.save_bundle(
            None, name="Story", sampler={"temperature": 0.3, "top_k": 40}
        )
        character = client.create_character(dict(CARD), name="Gate Keeper")
        chat = client.create_chat(
            title="Resolve chat", character_id=character.id
        )
        flow.set_override(
            "chat",
            chat.id,
            bundle.id,
            overrides={"sampler": {"temperature": 0.7}},
        )
        view = flow.resolve(chat_id=chat.id)
        assert view is not None
        rows = {
            label: (value, source)
            for label, value, source in effective_rows(view)
        }
        assert rows["Temperature (creativity)"] == ("0.7", "chat")
        assert rows["Top K (word shortlist)"] == ("40", "bundle")
        assert flow.delete_override("chat", chat.id) is True
        assert flow.resolve(chat_id=chat.id) is None
    finally:
        client.close()


def test_composed_turn_carries_applied_preset_temperature(
    live_engine, monkeypatch
) -> None:
    client = make_client(live_engine)
    try:
        flow = SettingsFlow(client)
        captured: dict = {}
        backend = RecordingBackend(captured)

        from runmal.backends import profiles as profiles_mod

        async def fake_build(session, profile):
            return backend

        monkeypatch.setattr(profiles_mod, "build_chat_backend", fake_build)

        character = client.create_character(dict(CARD), name="Gate Keeper")
        chat = client.create_chat(
            title="Gate chat", character_id=character.id
        )
        profile = flow.save_profile(
            None, name="Hearth", chat_backend="fake", chat_model="fake-1"
        )
        flow.pin_profile(chat.id, profile.id)
        preset = flow.save_preset(
            None, name="Warm", params={"temperature": 0.9}
        )
        flow.apply_preset(chat.id, preset.id)
        client.append_message(chat.id, role="user", content="I seek passage.")
        reply = client.generate_composed(chat.id)
        assert "recorded" in reply.text
        params = captured["params"]
        assert params.temperature == pytest.approx(0.9)
    finally:
        client.close()
