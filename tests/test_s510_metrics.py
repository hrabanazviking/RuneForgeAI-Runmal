"""S510 — Latency metrics: every complete turn yields a coherent timing
chain; impossible orderings are flagged; p50/p95 math is exact."""

from __future__ import annotations

import pytest

from runmal.voice.metrics import (
    MetricsCollector,
    Stage,
    TurnTiming,
    percentile,
)
from runmal.voice.orchestrator import SimulatedClock

CHAIN = [Stage.VAD_SPEECH_ON, Stage.ENDPOINT, Stage.STT_FINAL,
         Stage.LLM_FIRST_TOKEN, Stage.FIRST_SYNTH_CHUNK, Stage.TTS_FIRST_AUDIO,
         Stage.PLAYBACK_START, Stage.PLAYBACK_END]


def full_timing(turn_id: int, start: float = 10.0, step: float = 0.1) -> TurnTiming:
    timing = TurnTiming(turn_id)
    for i, stage in enumerate(CHAIN):
        timing.record(stage, start + i * step)
    return timing


def test_complete_turn_chain_is_coherent():
    timing = full_timing(1)
    assert timing.validate() == []
    assert timing.duration("stt") == pytest.approx(0.1)
    assert timing.duration("end_to_end_first_audio") == pytest.approx(0.6)


def test_impossible_ordering_is_flagged_not_hidden():
    timing = full_timing(1)
    timing.record(Stage.STT_FINAL, 0.5)  # before ENDPOINT: impossible
    problems = timing.validate()
    assert any("impossible ordering" in p for p in problems)


def test_missing_stage_is_flagged():
    timing = full_timing(1)
    del timing.stages[Stage.TTS_FIRST_AUDIO]
    assert any("missing stage" in p for p in timing.validate())
    # Partial chains are allowed when completeness is not required.
    assert timing.validate(require_complete=False) == []


def test_interruption_chain_rules():
    timing = full_timing(1)
    timing.record(Stage.INTERRUPTION_DETECTED, 10.65)
    problems = timing.validate()
    assert any("without playback_stopped" in p for p in problems)
    timing.record(Stage.PLAYBACK_STOPPED, 10.60)  # stopped BEFORE detected
    assert any("before interruption" in p for p in timing.validate())
    timing.record(Stage.PLAYBACK_STOPPED, 10.70)
    assert timing.validate() == []
    assert timing.duration("interruption_stop") == pytest.approx(0.05)


def test_percentile_nearest_rank_exact():
    values = [float(i) for i in range(1, 101)]
    assert percentile(values, 50) == 50.0
    assert percentile(values, 95) == 95.0
    assert percentile([3.0], 95) == 3.0
    with pytest.raises(ValueError):
        percentile([], 50)


def test_collector_report_p50_p95_and_no_violations():
    collector = MetricsCollector(clock=SimulatedClock(step=0.05))
    for turn_id in (1, 2, 3):
        collector.begin_turn(turn_id)
        for stage in CHAIN:
            collector.record(turn_id, stage)
    report = collector.report()
    assert report.turns == 3
    assert report.violations == []
    assert report.series["stt"]["n"] == 3
    assert report.series["stt"]["p50"] == pytest.approx(0.05)
    assert report.series["end_to_end_first_audio"]["p95"] == pytest.approx(0.30)
    as_dict = report.to_dict()
    assert as_dict["turns"] == 3 and "series" in as_dict


def test_report_surfaces_violations_from_bad_turns():
    collector = MetricsCollector(clock=SimulatedClock())
    timing = collector.begin_turn(9)
    timing.record(Stage.PLAYBACK_END, 1.0)  # a lone, out-of-chain stage
    report = collector.report()
    assert report.violations  # missing stages named in the report
    assert any("turn 9" in v for v in report.violations)
