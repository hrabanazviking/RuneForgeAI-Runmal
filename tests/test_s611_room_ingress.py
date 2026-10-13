"""S611 acceptance: VRChat room-audio ingress.

Room audio captured on the PC host (S513 room_ingress route) reaches
STT; frames overlapping the companion's own playback — known exactly
from the S508 ledger — are marked contains_self_output and excluded
by default policy; an unassigned/missing route fails explicitly,
never silently (INV-022). Fake devices throughout; the live PCVR
procedure is documented in docs/bridges/VRCHAT_ROOM_AUDIO.md.
"""

from __future__ import annotations

import pytest

from runmal.voice.audio import FixtureDeviceProvider
from runmal.voice.ledger import PlaybackLedger
from runmal.voice.room_ingress import RoomIngress, SelfOutputPolicy
from runmal.voice.routing import RouteKind, RouteStore
from runmal.voice.stt import FakeSTTBackend
from runmal.voice.tts import AudioChunk

FRAME = b"\x01\x00" * 512  # one 512-sample PCM16 frame (32 ms)


class Clock:
    def __init__(self, now: float = 100.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


class SpySTT(FakeSTTBackend):
    def __init__(self):
        super().__init__(text="room words here")
        self.received: list[int] = []

    def transcribe(self, pcm: bytes, sample_rate: int = 16000):
        self.received.append(len(pcm))
        return super().transcribe(pcm, sample_rate)


def _rig(frames: list[bytes], clock: Clock, policy=SelfOutputPolicy.EXCLUDE):
    provider = FixtureDeviceProvider(capture_frames=frames)
    store = RouteStore()
    room = next(d for d in provider.list_devices() if d.device_id == "fix-room")
    store.set_route(RouteKind.ROOM_INGRESS, room)
    ledger = PlaybackLedger(clock=clock)
    stt = SpySTT()
    ingress = RoomIngress(provider, store, ledger, stt, clock=clock, policy=policy)
    ingress.open()
    return ingress, ledger, stt, provider


def _play(ledger: PlaybackLedger, clock: Clock, start: float, end: float | None) -> None:
    chunk = AudioChunk(index=0, text="her words", pcm=FRAME * 4)
    clock.now = start
    ledger.chunk_started(7, chunk)
    if end is not None:
        clock.now = end
        ledger.chunk_finished(7, chunk, frames_played=4)


def test_unassigned_route_fails_explicitly() -> None:
    clock = Clock()
    provider = FixtureDeviceProvider(capture_frames=[FRAME])
    ingress = RoomIngress(
        provider, RouteStore(), PlaybackLedger(clock=clock), SpySTT(), clock=clock
    )
    with pytest.raises(RuntimeError, match="room_ingress"):
        ingress.open()


def test_missing_device_fails_explicitly() -> None:
    clock = Clock()
    provider = FixtureDeviceProvider(capture_frames=[FRAME])
    store = RouteStore()
    room = next(d for d in provider.list_devices() if d.device_id == "fix-room")
    store.set_route(RouteKind.ROOM_INGRESS, room)
    provider.set_devices([d for d in provider.list_devices() if d.device_id != "fix-room"])
    ingress = RoomIngress(provider, store, PlaybackLedger(clock=clock), SpySTT(), clock=clock)
    with pytest.raises(RuntimeError, match="device_missing"):
        ingress.open()


def test_clean_room_audio_reaches_stt() -> None:
    clock = Clock(100.0)
    ingress, _, stt, _ = _rig([FRAME, FRAME, FRAME], clock)
    frames = ingress.drain(10)
    assert len(frames) == 3
    assert not any(f.contains_self_output for f in frames)
    result = ingress.transcribe_window(frames)
    assert result is not None
    assert result.transcript.text == "room words here"
    assert stt.received == [len(FRAME) * 3]  # every frame reached STT
    assert result.frames_self_output == 0 and result.frames_excluded == 0


def test_self_output_frames_are_marked_and_excluded() -> None:
    clock = Clock(99.1)
    ingress, ledger, stt, _ = _rig([FRAME, FRAME, FRAME, FRAME], clock)
    _play(ledger, clock, start=99.0, end=99.5)  # she spoke 99.0–99.5
    frames = []
    for at in (99.10, 99.30, 100.00, 100.04):  # two inside her span, two after
        clock.now = at
        frame = ingress.read_frame()
        assert frame is not None
        frames.append(frame)
    assert [f.contains_self_output for f in frames] == [True, True, False, False]
    result = ingress.transcribe_window(frames)
    assert result is not None
    assert stt.received == [len(FRAME) * 2]  # only the clean frames reached STT
    assert result.frames_self_output == 2 and result.frames_excluded == 2


def test_mark_only_policy_keeps_flagged_frames() -> None:
    clock = Clock(99.1)
    ingress, ledger, stt, _ = _rig([FRAME, FRAME], clock, policy=SelfOutputPolicy.MARK_ONLY)
    _play(ledger, clock, start=99.0, end=99.5)
    frames = []
    for at in (99.10, 100.00):
        clock.now = at
        frames.append(ingress.read_frame())
    result = ingress.transcribe_window(frames)
    assert result is not None
    assert stt.received == [len(FRAME) * 2]  # nothing dropped
    assert result.frames_self_output == 1 and result.frames_excluded == 0


def test_window_of_pure_self_output_transcribes_nothing() -> None:
    clock = Clock(99.1)
    ingress, ledger, stt, _ = _rig([FRAME, FRAME], clock)
    _play(ledger, clock, start=99.0, end=99.5)
    frames = [ingress.read_frame(), ingress.read_frame()]
    assert ingress.transcribe_window(frames) is None
    assert stt.received == []  # STT never saw her own voice
    assert ingress.transcribe_window([]) is None


def test_still_playing_chunk_marks_everything_after_its_start() -> None:
    clock = Clock(100.0)
    ingress, ledger, _, _ = _rig([FRAME], clock)
    _play(ledger, clock, start=99.9, end=None)  # started, not finished
    clock.now = 101.0
    frame = ingress.read_frame()
    assert frame is not None and frame.contains_self_output


def test_guard_band_covers_cable_latency() -> None:
    clock = Clock(100.0)
    ingress, ledger, _, _ = _rig([FRAME, FRAME], clock)
    _play(ledger, clock, start=99.0, end=99.5)
    clock.now = 99.53  # 30 ms after she stopped: inside the 50 ms guard
    assert ingress.read_frame().contains_self_output
    clock.now = 101.0  # well clear
    assert not ingress.read_frame().contains_self_output
