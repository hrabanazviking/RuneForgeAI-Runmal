"""S502 — Silero VAD: hysteresis segmentation over fixture speech/noise/
silence meets the PREDECLARED contract in runmal.voice.vad.SEGMENTATION_CONTRACT
(recall/precision >= 0.90, onset <= 3 frames, offset <= 4 frames)."""

from __future__ import annotations

import math

import pytest

from runmal.voice import FRAME_SAMPLES
from runmal.voice.audio import floats_to_pcm16
from runmal.voice.vad import (
    SEGMENTATION_CONTRACT,
    EnergyVadModel,
    SileroVadModel,
    VadConfig,
    VadSegmenter,
    segmentation_metrics,
)


def frame(amplitude: float, *, tone: bool = False) -> bytes:
    if tone:
        return floats_to_pcm16(
            [amplitude * math.sin(2 * math.pi * 200 * i / 16000)
             for i in range(FRAME_SAMPLES)])
    return floats_to_pcm16([amplitude] * FRAME_SAMPLES)


SILENCE = frame(0.0)
NOISE = frame(0.03)  # fan/keyboard-level energy: below both thresholds
SPEECH = frame(0.5, tone=True)


def build_corpus() -> tuple[list[bytes], list[tuple[int, int]]]:
    """10 utterances with known spans, separated by silence+noise, plus
    transient bursts (2 loud frames) that must NOT become segments."""
    frames: list[bytes] = []
    expected: list[tuple[int, int]] = []
    frames.extend([SILENCE] * 5)
    for n in range(10):
        frames.extend([NOISE] * 4)
        frames.extend([SPEECH] * 2)  # transient burst: below min_speech
        frames.extend([NOISE] * 4)
        start = len(frames)
        frames.extend([SPEECH] * (12 + n))  # the real utterance
        expected.append((start, len(frames)))
        frames.extend([SILENCE] * 15)  # gap > hangover (10)
    return frames, expected


def test_fixture_segmentation_meets_predeclared_contract():
    frames, expected = build_corpus()
    segmenter = VadSegmenter(EnergyVadModel(), VadConfig())
    detected = segmenter.segment_stream(frames)
    metrics = segmentation_metrics(expected, detected)
    assert metrics["recall"] >= SEGMENTATION_CONTRACT["min_recall"], metrics
    assert metrics["precision"] >= SEGMENTATION_CONTRACT["min_precision"], metrics
    assert (metrics["max_onset_error_frames"]
            <= SEGMENTATION_CONTRACT["max_onset_error_frames"]), metrics
    assert (metrics["max_offset_error_frames"]
            <= SEGMENTATION_CONTRACT["max_offset_error_frames"]), metrics
    assert metrics["false_positive"] == 0  # transients/noise never segment


def test_pre_roll_prepends_audio_before_onset():
    segmenter = VadSegmenter(EnergyVadModel(), VadConfig(pre_roll_frames=8))
    frames = [SILENCE] * 20 + [SPEECH] * 10 + [SILENCE] * 15
    (segment,) = segmenter.segment_stream(frames)
    assert segment.onset_frame == 20
    assert segment.start_frame == 20 - 8
    assert len(segment.frames) == 8 + 10
    assert segment.audio == b"".join(segment.frames)


def test_hysteresis_gap_inside_speech_does_not_split():
    # A 6-frame dip below start but above end threshold stays one segment;
    # a dip to silence shorter than hangover also stays one segment.
    cfg = VadConfig(hangover_frames=10)
    segmenter = VadSegmenter(EnergyVadModel(), cfg)
    frames = [SPEECH] * 8 + [NOISE] * 6 + [SPEECH] * 8 + [SILENCE] * 20
    segments = segmenter.segment_stream(frames)
    assert len(segments) == 1


def test_short_burst_is_transient_not_speech():
    segmenter = VadSegmenter(EnergyVadModel(), VadConfig(min_speech_frames=3))
    frames = [SILENCE] * 5 + [SPEECH] * 2 + [SILENCE] * 20
    assert segmenter.segment_stream(frames) == []


def test_config_validation_and_tunability():
    with pytest.raises(ValueError):
        VadConfig(start_threshold=0.3, end_threshold=0.5).validate()
    segmenter = VadSegmenter(EnergyVadModel(), VadConfig(min_speech_frames=2))
    frames = [SILENCE] * 3 + [SPEECH] * 2 + [SILENCE] * 15
    assert len(segmenter.segment_stream(frames)) == 1  # tuned: 2 frames now count


def test_max_segment_cap_forces_close():
    segmenter = VadSegmenter(
        EnergyVadModel(), VadConfig(max_segment_frames=25, pre_roll_frames=0))
    segments = segmenter.segment_stream([SPEECH] * 60)
    assert len(segments) >= 2
    assert all(s.duration_frames <= 25 for s in segments)


def test_energy_model_is_deterministic():
    model = EnergyVadModel()
    assert model.probability(SPEECH) == model.probability(SPEECH) == 1.0
    assert model.probability(SILENCE) == 0.0
    assert model.probability(NOISE) < VadConfig().end_threshold


@pytest.mark.skipif(
    not __import__("pathlib").Path("/tmp/silero_vad.onnx").exists(),
    reason="tagged optional: real silero_vad.onnx not downloaded on this host")
def test_real_silero_model_loads_and_scores_silence_low():
    model = SileroVadModel("/tmp/silero_vad.onnx")
    assert model.probability(SILENCE) < 0.5
