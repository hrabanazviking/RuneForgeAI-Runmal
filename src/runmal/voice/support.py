"""Echo / self-interruption support contract (S509).

VOICE_ARCHITECTURE §7: speaker leakage can make the companion hear
itself and barge into its own speech. This module makes the support
contract EXPLICIT and testable:

Supported modes:

- ``HEADSET`` — user listens on headphones; acoustic leakage is
  negligible by construction. The primary supported path.
- ``SEPARATED_OUTPUT`` — companion output travels on its own channel
  (virtual cable / separate device) that is NOT part of the captured
  room mix, or is subtracted via :class:`SelfOutputSuppressor` using
  the known playback reference before VAD/STT.
- ``OPEN_SPEAKER_AEC`` — open speakers WITH a verified AEC in the
  actual route. Supported only when ``aec_verified`` is true for the
  route — an unverified "AEC notes" claim does not qualify (§7).

Unsupported — stated honestly, never silently degraded:

- ``OPEN_SPEAKER_RAW`` — open speakers, no AEC, shared capture: the
  companion WILL hear itself; live voice mode must refuse or warn, and
  this module's assessment says so in plain language.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from runmal.voice.audio import pcm16_to_floats


class SupportMode(StrEnum):
    HEADSET = "headset"
    SEPARATED_OUTPUT = "separated_output"
    OPEN_SPEAKER_AEC = "open_speaker_aec"
    OPEN_SPEAKER_RAW = "open_speaker_raw"


@dataclass(frozen=True)
class RouteFacts:
    """Observable facts about the actual audio route in use."""

    output_is_headset: bool = False
    output_on_separate_channel: bool = False  # virtual cable / own device
    capture_includes_output: bool = True  # room/game capture hears the output
    aec_in_route: bool = False
    aec_verified: bool = False  # verified on THIS route, not just present


@dataclass(frozen=True)
class SupportAssessment:
    mode: SupportMode
    supported: bool
    reason: str
    requirements: tuple[str, ...] = ()


def assess_support(facts: RouteFacts) -> SupportAssessment:
    """The support contract as a pure function of route facts."""
    if facts.output_is_headset:
        return SupportAssessment(
            SupportMode.HEADSET,
            True,
            "Headset output: acoustic self-leakage is negligible; "
            "barge-in VAD hears the user, not the companion.",
        )
    if facts.output_on_separate_channel and not facts.capture_includes_output:
        return SupportAssessment(
            SupportMode.SEPARATED_OUTPUT,
            True,
            "Companion output is on a channel excluded from capture; "
            "self-output cannot reach VAD/STT.",
        )
    if facts.output_on_separate_channel and facts.capture_includes_output:
        return SupportAssessment(
            SupportMode.SEPARATED_OUTPUT,
            True,
            "Companion output is separable: the known playback reference "
            "is subtracted/marked before VAD (SelfOutputSuppressor).",
            requirements=("run SelfOutputSuppressor on the capture path",),
        )
    if facts.aec_in_route and facts.aec_verified:
        return SupportAssessment(
            SupportMode.OPEN_SPEAKER_AEC, True, "Open speakers with AEC verified on this route."
        )
    if facts.aec_in_route and not facts.aec_verified:
        return SupportAssessment(
            SupportMode.OPEN_SPEAKER_RAW,
            False,
            "AEC is present but NOT verified on this route; per the "
            "architecture contract that is not support. Verify AEC on "
            "the real route or use a headset / separated output.",
            requirements=("verify AEC on the actual route", "or use headset mode"),
        )
    return SupportAssessment(
        SupportMode.OPEN_SPEAKER_RAW,
        False,
        "Open speakers without AEC on a shared capture are UNSUPPORTED: "
        "the companion would hear itself and self-interrupt. Use a "
        "headset or a separated (virtual-cable) output.",
        requirements=("headset", "or separated companion output"),
    )


class SelfOutputSuppressor:
    """Reference-based self-output separation for shared captures.

    Keeps a short history of the frames the companion is playing. An
    incoming capture frame that matches a recent playback frame (high
    normalized correlation, allowing attenuation) is classified as
    self-leakage and replaced with silence before VAD/STT; anything else
    passes through untouched. This is separation by KNOWN reference —
    not a general echo canceller, and it does not claim to be one.
    """

    def __init__(
        self,
        *,
        history_frames: int = 8,
        min_correlation: float = 0.9,
        min_reference_rms: float = 0.01,
    ):
        self.history_frames = history_frames
        self.min_correlation = min_correlation
        self.min_reference_rms = min_reference_rms
        self._reference: list = []
        self.suppressed_frames = 0
        self.passed_frames = 0

    def note_playback(self, frame: bytes) -> None:
        self._reference.append(pcm16_to_floats(frame))
        if len(self._reference) > self.history_frames:
            del self._reference[: len(self._reference) - self.history_frames]

    @staticmethod
    def _correlation(a, b) -> float:
        n = min(len(a), len(b))
        if n == 0:
            return 0.0
        dot = sum(a[i] * b[i] for i in range(n))
        na = sum(a[i] * a[i] for i in range(n)) ** 0.5
        nb = sum(b[i] * b[i] for i in range(n)) ** 0.5
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def process(self, frame: bytes) -> tuple[bytes, bool]:
        """Returns (frame_or_silence, was_self_output)."""
        values = pcm16_to_floats(frame)
        rms = (sum(v * v for v in values) / len(values)) ** 0.5 if values else 0.0
        if rms > 0:
            for reference in self._reference:
                ref_rms = (
                    (sum(v * v for v in reference) / len(reference)) ** 0.5 if reference else 0.0
                )
                if ref_rms < self.min_reference_rms:
                    continue
                if self._correlation(values, reference) >= self.min_correlation:
                    self.suppressed_frames += 1
                    return b"\x00" * len(frame), True
        self.passed_frames += 1
        return frame, False
