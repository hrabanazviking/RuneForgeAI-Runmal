"""S501 — Audio plumbing: enumeration, explicit roles, ring buffer/pre-roll,
loopback fixture; missing saved device -> REMAP, never silent OS default."""

from __future__ import annotations

import pytest

from runmal.voice import FRAME_SAMPLES, SAMPLE_RATE
from runmal.voice.audio import (
    AudioDevice,
    DeviceRole,
    DeviceUnavailableError,
    FixtureDeviceProvider,
    RingBuffer,
    RoleMap,
    RoleStatus,
    SoundDeviceProvider,
    floats_to_pcm16,
    frame_bytes,
    pcm16_to_floats,
)


def tone_frame(amplitude: float = 0.5) -> bytes:
    return floats_to_pcm16([amplitude] * FRAME_SAMPLES)


def test_enumeration_lists_fixture_devices_with_directions():
    provider = FixtureDeviceProvider()
    devices = provider.list_devices()
    assert {d.device_id for d in devices} == {
        "fix-mic", "fix-headset", "fix-cable", "fix-room"}
    mic = provider.find("fix-mic")
    assert mic.direction == "input" and mic.supports_voice_format()
    assert provider.find("nope") is None


def test_open_missing_device_raises_not_defaults():
    provider = FixtureDeviceProvider()
    with pytest.raises(DeviceUnavailableError):
        provider.open_capture("gone")
    with pytest.raises(DeviceUnavailableError):
        provider.open_playback("fix-mic")  # wrong direction


def test_explicit_role_selection_and_resolution_ok():
    provider = FixtureDeviceProvider()
    roles = RoleMap()
    roles.assign(DeviceRole.USER_MIC, provider.find("fix-mic"))
    roles.assign(DeviceRole.COMPANION_OUTPUT, provider.find("fix-cable"))
    resolved = roles.resolve(provider)
    assert resolved[DeviceRole.USER_MIC].status is RoleStatus.OK
    assert resolved[DeviceRole.USER_MIC].device.device_id == "fix-mic"
    assert resolved[DeviceRole.ROOM_CAPTURE].status is RoleStatus.UNASSIGNED


def test_assign_wrong_direction_rejected():
    provider = FixtureDeviceProvider()
    with pytest.raises(ValueError):
        RoleMap().assign(DeviceRole.USER_MIC, provider.find("fix-headset"))


def test_missing_saved_device_is_remap_never_silent_default():
    provider = FixtureDeviceProvider()
    roles = RoleMap()
    roles.assign(DeviceRole.USER_MIC, provider.find("fix-mic"))
    # Simulate the saved mic being unplugged before the next run. Another
    # input (the OS default room mic) IS present — it must NOT be picked.
    provider.set_devices([d for d in provider.list_devices()
                          if d.device_id != "fix-mic"])
    resolved = roles.resolve(provider)
    entry = resolved[DeviceRole.USER_MIC]
    assert entry.status is RoleStatus.REMAP_REQUIRED
    assert entry.device is None  # no silent substitution happened
    assert entry.saved.device_id == "fix-mic"


def test_role_map_json_round_trip(tmp_path):
    provider = FixtureDeviceProvider()
    roles = RoleMap()
    roles.assign(DeviceRole.USER_MIC, provider.find("fix-mic"))
    path = tmp_path / "roles.json"
    roles.save(path)
    loaded = RoleMap.load(path)
    assert loaded.assignments[DeviceRole.USER_MIC].device_id == "fix-mic"
    assert loaded.resolve(provider)[DeviceRole.USER_MIC].status is RoleStatus.OK
    assert RoleMap.load(tmp_path / "absent.json").assignments == {}
    # Unknown roles from a newer file are ignored, not fatal.
    assert RoleMap.from_dict({"future_role": {"device_id": "x"}}).assignments == {}


def test_ring_buffer_pre_roll_returns_audio_before_trigger():
    ring = RingBuffer(capacity_ms=2000)
    for i in range(10):  # 320 ms of distinct-amplitude frames
        ring.push(floats_to_pcm16([i / 100.0] * FRAME_SAMPLES))
    pre = ring.pre_roll(64)  # last 2 frames
    values = pcm16_to_floats(pre)
    assert len(pre) == 2 * frame_bytes()
    assert values[0] == pytest.approx(0.08, abs=0.001)
    assert values[-1] == pytest.approx(0.09, abs=0.001)
    assert len(ring) == 10 * FRAME_SAMPLES


def test_ring_buffer_overflow_drops_oldest_and_counts():
    ring = RingBuffer(capacity_ms=32)  # exactly one frame of capacity
    ring.push(tone_frame(0.1))
    ring.push(tone_frame(0.9))
    snap = pcm16_to_floats(ring.snapshot().tobytes())
    assert snap[0] == pytest.approx(0.9, abs=0.001)
    assert ring.dropped_samples == FRAME_SAMPLES
    assert ring.total_written == 2 * FRAME_SAMPLES


def test_ring_buffer_is_16khz_mono_sized():
    ring = RingBuffer(capacity_ms=1000)
    assert ring.capacity_samples == SAMPLE_RATE


def test_loopback_fixture_round_trip():
    provider = FixtureDeviceProvider(loopback=True)
    capture = provider.open_capture("fix-mic")
    playback = provider.open_playback("fix-headset")
    frame = tone_frame(0.25)
    playback.write_frame(frame)
    assert capture.read_frame() == frame
    assert provider.last_playback.samples_written == FRAME_SAMPLES


def test_capture_playback_via_roles_end_to_end():
    provider = FixtureDeviceProvider(capture_frames=[tone_frame(0.3)])
    roles = RoleMap()
    roles.assign(DeviceRole.USER_MIC, provider.find("fix-mic"))
    resolved = roles.resolve(provider)
    assert resolved[DeviceRole.USER_MIC].usable
    source = provider.open_capture(resolved[DeviceRole.USER_MIC].device.device_id)
    ring = RingBuffer()
    ring.push(source.read_frame())
    assert len(ring) == FRAME_SAMPLES


@pytest.mark.manual
def test_sounddevice_provider_manual():
    """Tagged manual/hardware test: real enumeration where PortAudio and
    the sounddevice package exist; skipped (not failed) anywhere else."""
    try:
        provider = SoundDeviceProvider()
    except DeviceUnavailableError as exc:
        pytest.skip(f"sounddevice unavailable on this host: {exc}")
    devices = provider.list_devices()
    assert isinstance(devices, list)  # may be empty on a device-less host
    for device in devices:
        assert device.direction in ("input", "output")


def test_device_dict_shape_is_json_safe():
    device = AudioDevice("x", "X Mic", "input", "fixture", sample_rates=(16000, 44100))
    data = device.to_dict()
    assert data["sample_rates"] == [16000, 44100]
    assert device.supports_voice_format()
