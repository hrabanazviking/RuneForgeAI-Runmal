"""Audio plumbing (S501).

Builds (ROADMAP S501): device enumeration, explicit role selection,
capture/playback, 16 kHz mono ring buffer / pre-roll.

Acceptance: loopback fixture / manual tagged test; a missing saved device
produces a REMAP state rather than a silent OS-default switch
(INV-022: audio routing is explicit — accidental OS defaults are not a
stable production contract).

Design:

- All audio is PCM16 little-endian mono at :data:`SAMPLE_RATE` unless a
  type says otherwise. Frames are ``bytes`` of ``2 * FRAME_SAMPLES``.
- Hardware access sits behind :class:`DeviceProvider`. Tests inject
  :class:`FixtureDeviceProvider`; production uses
  :class:`SoundDeviceProvider` (lazy ``sounddevice`` import, optional
  dependency) — no module in this package imports sounddevice at module
  scope, so the fixture suite runs headless with no audio stack.
- Role selection is *persisted descriptive metadata* (device id + name +
  host API). Resolution never substitutes the OS default for a missing
  saved device: the role enters ``REMAP_REQUIRED`` and the caller must
  re-pick explicitly.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from array import array
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from runmal.voice import FRAME_SAMPLES, SAMPLE_RATE

BYTES_PER_SAMPLE = 2  # PCM16


def frame_bytes(samples: int = FRAME_SAMPLES) -> int:
    return samples * BYTES_PER_SAMPLE


def floats_to_pcm16(values: list[float]) -> bytes:
    """Clamp float samples in [-1, 1] to PCM16 LE bytes."""
    out = array("h")
    for v in values:
        clipped = max(-1.0, min(1.0, v))
        out.append(int(clipped * 32767))
    if out.itemsize != 2:  # pragma: no cover - exotic platforms
        raise RuntimeError("array('h') is not 16-bit on this platform")
    if array("h", [1]).tobytes() != b"\x01\x00":  # pragma: no cover
        swapped = array("h")
        swapped.frombytes(out.tobytes())
        swapped.byteswap()
        out = swapped
    return out.tobytes()


def pcm16_to_floats(data: bytes) -> array:
    """Decode PCM16 LE bytes to floats in [-1, 1]."""
    values = array("h")
    values.frombytes(data[: len(data) - (len(data) % 2)])
    return array("f", (v / 32768.0 for v in values))


# ---------------------------------------------------------------- devices


@dataclass(frozen=True)
class AudioDevice:
    """One enumerated audio endpoint (descriptive, provider-owned id)."""

    device_id: str
    name: str
    direction: str  # "input" | "output"
    host_api: str = ""
    max_channels: int = 1
    sample_rates: tuple[int, ...] = (SAMPLE_RATE,)
    is_system_default: bool = False

    def supports_voice_format(self) -> bool:
        return SAMPLE_RATE in self.sample_rates and self.max_channels >= 1

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "name": self.name,
            "direction": self.direction,
            "host_api": self.host_api,
            "max_channels": self.max_channels,
            "sample_rates": list(self.sample_rates),
            "is_system_default": self.is_system_default,
        }


class CaptureSource(ABC):
    """A opened capture stream: yields PCM16 frames on demand."""

    @abstractmethod
    def read_frame(self) -> bytes | None:
        """Return one frame of PCM16, or None when the source is dry."""

    def close(self) -> None:  # noqa: B027 - intentional no-op default
        pass


class PlaybackSink(ABC):
    """An opened playback stream."""

    @abstractmethod
    def write_frame(self, frame: bytes) -> None:
        """Queue one PCM16 frame for playback."""

    def close(self) -> None:  # noqa: B027 - intentional no-op default
        pass


class DeviceProvider(ABC):
    """Enumeration + stream factory seam (fixture or real hardware)."""

    provider_key: str = "abstract"

    @abstractmethod
    def list_devices(self) -> list[AudioDevice]:
        """Enumerate currently present devices."""

    @abstractmethod
    def open_capture(self, device_id: str) -> CaptureSource:
        """Open capture on an enumerated input device id."""

    @abstractmethod
    def open_playback(self, device_id: str) -> PlaybackSink:
        """Open playback on an enumerated output device id."""

    def find(self, device_id: str) -> AudioDevice | None:
        for device in self.list_devices():
            if device.device_id == device_id:
                return device
        return None


class DeviceUnavailableError(RuntimeError):
    """Raised when opening a device id that is not currently present."""


# ------------------------------------------------------- fixture provider


class FixtureCapture(CaptureSource):
    """Scripted capture: replays queued frames, then silence (dry=None
    only when ``pad_silence`` is False)."""

    def __init__(self, frames: list[bytes], *, pad_silence: bool = False):
        self._frames = list(frames)
        self._pad_silence = pad_silence
        self.closed = False

    def read_frame(self) -> bytes | None:
        if self._frames:
            return self._frames.pop(0)
        if self._pad_silence:
            return b"\x00" * frame_bytes()
        return None

    def close(self) -> None:
        self.closed = True


class FixturePlayback(PlaybackSink):
    """Recording playback sink; optionally wired to a loopback capture."""

    def __init__(self, loopback: FixtureCapture | None = None):
        self.frames: list[bytes] = []
        self._loopback = loopback
        self.closed = False

    def write_frame(self, frame: bytes) -> None:
        self.frames.append(frame)
        if self._loopback is not None:
            self._loopback._frames.append(frame)

    def close(self) -> None:
        self.closed = True

    @property
    def samples_written(self) -> int:
        return sum(len(f) // BYTES_PER_SAMPLE for f in self.frames)


class FixtureDeviceProvider(DeviceProvider):
    """Deterministic in-memory provider for tests and headless runs.

    ``loopback=True`` wires every playback sink into subsequently opened
    captures, modelling a hardware loopback cable.
    """

    provider_key = "fixture"

    def __init__(
        self,
        devices: list[AudioDevice] | None = None,
        *,
        capture_frames: list[bytes] | None = None,
        loopback: bool = False,
    ):
        self._devices = list(devices if devices is not None else _default_fixture_devices())
        self._capture_frames = list(capture_frames or [])
        self._loopback = loopback
        self.last_capture: FixtureCapture | None = None
        self.last_playback: FixturePlayback | None = None

    def set_devices(self, devices: list[AudioDevice]) -> None:
        """Simulate hot-plug / unplug between enumerations."""
        self._devices = list(devices)

    def list_devices(self) -> list[AudioDevice]:
        return list(self._devices)

    def _require(self, device_id: str, direction: str) -> AudioDevice:
        device = self.find(device_id)
        if device is None or device.direction != direction:
            raise DeviceUnavailableError(f"{direction} device not present: {device_id}")
        return device

    def open_capture(self, device_id: str) -> CaptureSource:
        self._require(device_id, "input")
        self.last_capture = FixtureCapture(list(self._capture_frames))
        return self.last_capture

    def open_playback(self, device_id: str) -> PlaybackSink:
        self._require(device_id, "output")
        sink = FixturePlayback(loopback=self.last_capture if self._loopback else None)
        self.last_playback = sink
        return sink


def _default_fixture_devices() -> list[AudioDevice]:
    return [
        AudioDevice("fix-mic", "Fixture Microphone", "input", "fixture", is_system_default=True),
        AudioDevice("fix-headset", "Fixture Headset", "output", "fixture", is_system_default=True),
        AudioDevice("fix-cable", "Fixture Virtual Cable", "output", "fixture"),
        AudioDevice("fix-room", "Fixture Room Capture", "input", "fixture"),
    ]


# -------------------------------------------------- sounddevice provider


class SoundDeviceProvider(DeviceProvider):
    """Real hardware via PortAudio (``sounddevice``, optional dependency).

    Import failure raises :class:`DeviceUnavailableError` with the reason —
    callers fall back to fixtures/headless explicitly, never silently.
    """

    provider_key = "sounddevice"

    def __init__(self):
        try:
            import sounddevice as sd
        except Exception as exc:  # ImportError / OSError (no PortAudio)
            raise DeviceUnavailableError(f"sounddevice unavailable: {exc}") from exc
        self._sd = sd

    def list_devices(self) -> list[AudioDevice]:
        sd = self._sd
        default_in, default_out = sd.default.device
        devices: list[AudioDevice] = []
        host_apis = sd.query_hostapis()
        for idx, raw in enumerate(sd.query_devices()):
            host = host_apis[raw["hostapi"]]["name"] if raw.get("hostapi") is not None else ""
            rate = int(raw.get("default_samplerate") or SAMPLE_RATE)
            if raw["max_input_channels"] > 0:
                devices.append(
                    AudioDevice(
                        device_id=f"sd:{idx}:in",
                        name=raw["name"],
                        direction="input",
                        host_api=host,
                        max_channels=int(raw["max_input_channels"]),
                        sample_rates=(rate,),
                        is_system_default=(idx == default_in),
                    )
                )
            if raw["max_output_channels"] > 0:
                devices.append(
                    AudioDevice(
                        device_id=f"sd:{idx}:out",
                        name=raw["name"],
                        direction="output",
                        host_api=host,
                        max_channels=int(raw["max_output_channels"]),
                        sample_rates=(rate,),
                        is_system_default=(idx == default_out),
                    )
                )
        return devices

    @staticmethod
    def _index(device_id: str, direction: str) -> int:
        parts = device_id.split(":")
        if (
            len(parts) != 3
            or parts[0] != "sd"
            or parts[2] != ("in" if direction == "input" else "out")
        ):
            raise DeviceUnavailableError(f"not a sounddevice {direction} id: {device_id}")
        return int(parts[1])

    def open_capture(self, device_id: str) -> CaptureSource:
        idx = self._index(device_id, "input")
        if self.find(device_id) is None:
            raise DeviceUnavailableError(f"device not present: {device_id}")
        stream = self._sd.RawInputStream(
            samplerate=SAMPLE_RATE, blocksize=FRAME_SAMPLES, device=idx, channels=1, dtype="int16"
        )
        stream.start()
        return _SoundDeviceCapture(stream)

    def open_playback(self, device_id: str) -> PlaybackSink:
        idx = self._index(device_id, "output")
        if self.find(device_id) is None:
            raise DeviceUnavailableError(f"device not present: {device_id}")
        stream = self._sd.RawOutputStream(
            samplerate=SAMPLE_RATE, blocksize=FRAME_SAMPLES, device=idx, channels=1, dtype="int16"
        )
        stream.start()
        return _SoundDevicePlayback(stream)


class _SoundDeviceCapture(CaptureSource):
    def __init__(self, stream):
        self._stream = stream

    def read_frame(self) -> bytes | None:
        data, _overflowed = self._stream.read(FRAME_SAMPLES)
        return bytes(data)

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()


class _SoundDevicePlayback(PlaybackSink):
    def __init__(self, stream):
        self._stream = stream

    def write_frame(self, frame: bytes) -> None:
        self._stream.write(frame)

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()


# ------------------------------------------------------------------- roles


class DeviceRole(StrEnum):
    USER_MIC = "user_mic"
    USER_PLAYBACK = "user_playback"
    COMPANION_OUTPUT = "companion_output"
    ROOM_CAPTURE = "room_capture"
    MONITOR = "monitor"

    @property
    def direction(self) -> str:
        return "input" if self in (DeviceRole.USER_MIC, DeviceRole.ROOM_CAPTURE) else "output"


@dataclass(frozen=True)
class SavedDeviceRef:
    """Persisted descriptive identity of a chosen device."""

    device_id: str
    name: str = ""
    host_api: str = ""

    @classmethod
    def of(cls, device: AudioDevice) -> SavedDeviceRef:
        return cls(device_id=device.device_id, name=device.name, host_api=device.host_api)

    def to_dict(self) -> dict:
        return {"device_id": self.device_id, "name": self.name, "host_api": self.host_api}

    @classmethod
    def from_dict(cls, data: dict) -> SavedDeviceRef:
        return cls(
            device_id=str(data.get("device_id", "")),
            name=str(data.get("name", "")),
            host_api=str(data.get("host_api", "")),
        )


class RoleStatus(StrEnum):
    OK = "ok"
    UNASSIGNED = "unassigned"
    REMAP_REQUIRED = "remap_required"  # saved device is gone — NEVER auto-default


@dataclass(frozen=True)
class RoleResolution:
    role: DeviceRole
    status: RoleStatus
    device: AudioDevice | None = None  # set only when status is OK
    saved: SavedDeviceRef | None = None

    @property
    def usable(self) -> bool:
        return self.status is RoleStatus.OK and self.device is not None


@dataclass
class RoleMap:
    """Explicit role → device selection, persistable as JSON."""

    assignments: dict[DeviceRole, SavedDeviceRef] = field(default_factory=dict)

    def assign(self, role: DeviceRole, device: AudioDevice) -> None:
        if device.direction != role.direction:
            raise ValueError(f"{role} needs a {role.direction} device, got {device.direction}")
        self.assignments[role] = SavedDeviceRef.of(device)

    def unassign(self, role: DeviceRole) -> None:
        self.assignments.pop(role, None)

    def resolve(self, provider: DeviceProvider) -> dict[DeviceRole, RoleResolution]:
        """Resolve every role against the CURRENT enumeration.

        A saved device that is missing (or present with the wrong
        direction) resolves to REMAP_REQUIRED with ``device=None`` — the
        OS default is never substituted (INV-022).
        """
        present = {d.device_id: d for d in provider.list_devices()}
        out: dict[DeviceRole, RoleResolution] = {}
        for role in DeviceRole:
            saved = self.assignments.get(role)
            if saved is None:
                out[role] = RoleResolution(role, RoleStatus.UNASSIGNED)
                continue
            device = present.get(saved.device_id)
            if device is None or device.direction != role.direction:
                out[role] = RoleResolution(role, RoleStatus.REMAP_REQUIRED, saved=saved)
            else:
                out[role] = RoleResolution(role, RoleStatus.OK, device=device, saved=saved)
        return out

    def to_dict(self) -> dict:
        return {role.value: ref.to_dict() for role, ref in self.assignments.items()}

    @classmethod
    def from_dict(cls, data: dict) -> RoleMap:
        out = cls()
        for key, value in (data or {}).items():
            try:
                role = DeviceRole(key)
            except ValueError:
                continue  # unknown role from a newer version: ignore, don't crash
            if isinstance(value, dict) and value.get("device_id"):
                out.assignments[role] = SavedDeviceRef.from_dict(value)
        return out

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True))

    @classmethod
    def load(cls, path: Path) -> RoleMap:
        if not path.exists():
            return cls()
        return cls.from_dict(json.loads(path.read_text()))


# ------------------------------------------------------------- ring buffer


class RingBuffer:
    """Fixed-capacity PCM16 ring buffer at 16 kHz mono with pre-roll.

    Retains the most recent ``capacity_ms`` of audio; ``pre_roll(ms)``
    returns the tail of what was captured BEFORE a trigger moment — the
    audio a VAD/endpointing decision needs to not clip word onsets.
    Overflow drops the oldest samples and counts them honestly.
    """

    def __init__(self, capacity_ms: int = 2000):
        if capacity_ms <= 0:
            raise ValueError("capacity_ms must be positive")
        self.capacity_samples = SAMPLE_RATE * capacity_ms // 1000
        self._buf = array("h", bytes(2 * self.capacity_samples))
        self._write = 0
        self._size = 0
        self.total_written = 0
        self.dropped_samples = 0

    def push(self, data: bytes) -> None:
        samples = array("h")
        samples.frombytes(data[: len(data) - (len(data) % 2)])
        self.push_samples(samples)

    def push_samples(self, samples: array) -> None:
        for value in samples:
            self._buf[self._write] = value
            self._write = (self._write + 1) % self.capacity_samples
            if self._size < self.capacity_samples:
                self._size += 1
            else:
                self.dropped_samples += 1
            self.total_written += 1

    def __len__(self) -> int:
        return self._size

    def snapshot(self) -> array:
        """All retained samples in chronological order (int16 array)."""
        out = array("h")
        if self._size < self.capacity_samples:
            out.extend(self._buf[: self._size])
        else:
            out.extend(self._buf[self._write :])
            out.extend(self._buf[: self._write])
        return out

    def tail_samples(self, count: int) -> array:
        snap = self.snapshot()
        if count >= len(snap):
            return snap
        return snap[len(snap) - count :]

    def pre_roll(self, duration_ms: int) -> bytes:
        """The last ``duration_ms`` of captured audio as PCM16 bytes."""
        count = min(self._size, SAMPLE_RATE * duration_ms // 1000)
        return self.tail_samples(count).tobytes()

    def clear(self) -> None:
        self._write = 0
        self._size = 0
