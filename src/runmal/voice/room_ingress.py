"""VRChat room-audio ingress (S611) — PC-host capture into STT.

The last Campaign VI piece, and deliberately NOT OSC: OSC carries
control and text; room audio is sound. On a PCVR setup the room's
audio (other participants, game sound) is mixed by the PC, and the
user routes that mix — typically through a virtual audio cable — to
the device bound to the S513 ``room_ingress`` logical route. This
module pumps frames from that route, separates the companion's own
voice, and hands clean speech to STT.

Self-output separation (acceptance: room audio reaches STT
"excluding/marking known self-output"):

- The companion's playback is not a mystery signal: the S508
  PlaybackLedger holds the exact clock spans of every chunk she
  played. Any capture frame overlapping a playback span (plus a
  small guard band for cable latency) is marked
  ``contains_self_output``.
- Default policy EXCLUDE drops marked frames before STT — she never
  transcribes herself and answers her own voice. MARK_ONLY keeps the
  frames, flagged, for diagnostics and future consumers.
- Overlap is computed on ONE clock: the ledger's clock and the
  ingress clock must be the same time source (both default to
  ``time.monotonic``); a still-playing chunk (open ledger record)
  marks everything from its start onward.

Platform honesty: this is a PC-HOST path. A standalone Quest headset
has no supported way to hand its room mix to another process — the
Quest path is UNSUPPORTED and docs/bridges/VRCHAT_ROOM_AUDIO.md says
so plainly. PCVR (Quest via Link/Air Link to the PC, Index, any
SteamVR setup) is the supported shape.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from runmal.voice import SAMPLE_RATE
from runmal.voice.audio import CaptureSource, DeviceProvider
from runmal.voice.ledger import PlaybackLedger
from runmal.voice.routing import RouteKind, RouteStore
from runmal.voice.stt import STTBackend, Transcript


class SelfOutputPolicy(StrEnum):
    EXCLUDE = "exclude"  # default: marked frames never reach STT
    MARK_ONLY = "mark_only"  # keep frames, flagged, for other consumers


@dataclass(frozen=True)
class IngressFrame:
    pcm: bytes
    captured_at: float  # ingress-clock timestamp of the frame start
    contains_self_output: bool = False

    @property
    def duration_s(self) -> float:
        return (len(self.pcm) // 2) / SAMPLE_RATE


@dataclass(frozen=True)
class IngressTranscript:
    transcript: Transcript
    frames_total: int
    frames_self_output: int  # marked frames seen in the window
    frames_excluded: int  # marked frames actually dropped by policy


class RoomIngress:
    """Frame pump over the room_ingress route with self-output policy."""

    def __init__(
        self,
        provider: DeviceProvider,
        route_store: RouteStore,
        ledger: PlaybackLedger,
        stt: STTBackend,
        *,
        clock: Callable[[], float] = time.monotonic,
        policy: SelfOutputPolicy = SelfOutputPolicy.EXCLUDE,
        guard_s: float = 0.05,
    ):
        self._provider = provider
        self._routes = route_store
        self._ledger = ledger
        self._stt = stt
        self._clock = clock
        self._policy = policy
        self._guard_s = guard_s
        self._source: CaptureSource | None = None
        self.frames_read = 0
        self.frames_marked = 0
        self.frames_excluded = 0

    # ------------------------------------------------------------ lifecycle

    def open(self) -> None:
        """Open capture on the room_ingress route. Raises RuntimeError
        when the route is unassigned or its device is missing — the
        S513 rule: explicit failure, never a silent substitute."""
        self._source = self._routes.open_capture(self._provider, RouteKind.ROOM_INGRESS)

    def close(self) -> None:
        if self._source is not None:
            self._source.close()
            self._source = None

    # ------------------------------------------------------------ frames

    def _is_self_output(self, start: float, end: float) -> bool:
        for span_start, span_end in self._ledger.playback_spans():
            lo = span_start - self._guard_s
            hi = None if span_end is None else span_end + self._guard_s
            if start < (hi if hi is not None else float("inf")) and end > lo:
                return True
        return False

    def read_frame(self) -> IngressFrame | None:
        """Read one frame; None when the source is dry or not open."""
        if self._source is None:
            return None
        captured_at = self._clock()
        pcm = self._source.read_frame()
        if pcm is None:
            return None
        frame = IngressFrame(
            pcm=pcm,
            captured_at=captured_at,
            contains_self_output=self._is_self_output(
                captured_at, captured_at + (len(pcm) // 2) / SAMPLE_RATE
            ),
        )
        self.frames_read += 1
        if frame.contains_self_output:
            self.frames_marked += 1
        return frame

    def drain(self, max_frames: int) -> list[IngressFrame]:
        frames: list[IngressFrame] = []
        for _ in range(max_frames):
            frame = self.read_frame()
            if frame is None:
                break
            frames.append(frame)
        return frames

    # ------------------------------------------------------------ STT

    def transcribe_window(self, frames: list[IngressFrame]) -> IngressTranscript | None:
        """Transcribe one window of frames under the self-output
        policy. Returns None when nothing transcribable remains
        (empty window, or every frame excluded as self-output) — the
        caller hears silence, never the companion transcribing
        herself."""
        kept: list[bytes] = []
        marked = excluded = 0
        for frame in frames:
            if frame.contains_self_output:
                marked += 1
                if self._policy is SelfOutputPolicy.EXCLUDE:
                    excluded += 1
                    continue
            kept.append(frame.pcm)
        self.frames_excluded += excluded
        if not kept:
            return None
        transcript = self._stt.transcribe(b"".join(kept), SAMPLE_RATE)
        return IngressTranscript(
            transcript=transcript,
            frames_total=len(frames),
            frames_self_output=marked,
            frames_excluded=excluded,
        )
