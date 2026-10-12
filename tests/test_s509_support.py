"""S509 — Echo/self-interruption support contract: supported modes pass
the companion-speaking + room-noise fixture; unsupported modes are
stated honestly, never silently degraded."""

from __future__ import annotations

import math

from runmal.voice import FRAME_SAMPLES
from runmal.voice.audio import floats_to_pcm16
from runmal.voice.support import (
    RouteFacts,
    SelfOutputSuppressor,
    SupportMode,
    assess_support,
)
from runmal.voice.vad import EnergyVadModel, VadConfig, VadSegmenter


def tone(amplitude: float, freq: float = 200.0) -> bytes:
    return floats_to_pcm16(
        [amplitude * math.sin(2 * math.pi * freq * i / 16000)
         for i in range(FRAME_SAMPLES)])


COMPANION = tone(0.5, 180.0)  # companion's own voice frame
USER = tone(0.5, 320.0)  # a different voice (orthogonal-ish in fixture)
ROOM_NOISE = tone(0.03, 90.0)


def test_headset_mode_is_supported():
    assessment = assess_support(RouteFacts(output_is_headset=True))
    assert assessment.supported and assessment.mode is SupportMode.HEADSET


def test_separated_output_modes_are_supported():
    excluded = assess_support(RouteFacts(
        output_on_separate_channel=True, capture_includes_output=False))
    assert excluded.supported and excluded.mode is SupportMode.SEPARATED_OUTPUT
    shared = assess_support(RouteFacts(
        output_on_separate_channel=True, capture_includes_output=True))
    assert shared.supported and shared.requirements  # suppressor required


def test_open_speaker_without_verified_aec_is_unsupported_honestly():
    raw = assess_support(RouteFacts())
    assert not raw.supported and raw.mode is SupportMode.OPEN_SPEAKER_RAW
    assert "UNSUPPORTED" in raw.reason
    unverified = assess_support(RouteFacts(aec_in_route=True, aec_verified=False))
    assert not unverified.supported  # "AEC notes" are not acceptance (§7)
    verified = assess_support(RouteFacts(aec_in_route=True, aec_verified=True))
    assert verified.supported and verified.mode is SupportMode.OPEN_SPEAKER_AEC


def test_suppressor_removes_companion_leakage_but_passes_user():
    suppressor = SelfOutputSuppressor()
    suppressor.note_playback(COMPANION)
    leakage = floats_to_pcm16(  # companion heard back at 30% through speakers
        [0.3 * v for v in
         [math.sin(2 * math.pi * 180.0 * i / 16000) * 0.5 for i in range(FRAME_SAMPLES)]])
    out, was_self = suppressor.process(leakage)
    assert was_self and out == b"\x00" * len(leakage)
    out, was_self = suppressor.process(USER)
    assert not was_self and out == USER
    out, was_self = suppressor.process(ROOM_NOISE)
    assert not was_self and out == ROOM_NOISE


def test_supported_mode_passes_companion_speaking_plus_noise_fixture():
    """The §11 fixture: companion speaking while room noise plays must
    NOT self-interrupt in a supported mode. Headset: leakage ~zero, so
    the mic path sees only noise. Separated+suppressor: leakage is
    removed by reference. Both feed a VAD that must find no user speech."""
    segmenter = VadSegmenter(EnergyVadModel(), VadConfig())
    # Headset path: capture = room noise only.
    segments = segmenter.segment_stream([ROOM_NOISE] * 40)
    assert segments == []

    suppressor = SelfOutputSuppressor()
    segmenter2 = VadSegmenter(EnergyVadModel(), VadConfig())
    heard = []
    for _ in range(40):
        suppressor.note_playback(COMPANION)
        leakage = floats_to_pcm16(
            [0.3 * 0.5 * math.sin(2 * math.pi * 180.0 * i / 16000)
             for i in range(FRAME_SAMPLES)])
        cleaned, _ = suppressor.process(leakage)
        heard.extend(segmenter2.feed(cleaned))
    heard.extend(segmenter2.flush())
    assert heard == []  # the companion never "hears itself" as user speech
    assert suppressor.suppressed_frames == 40
