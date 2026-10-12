"""S508 — Playback truth ledger: mid-chunk interruption NEVER records a
known-unplayed suffix as certainly heard; uncertainty is explicit when
alignment is insufficient."""

from __future__ import annotations

from runmal.voice import FRAME_SAMPLES
from runmal.voice.audio import floats_to_pcm16
from runmal.voice.ledger import PlaybackLedger
from runmal.voice.orchestrator import SimulatedClock
from runmal.voice.tts import AudioChunk


def chunk(text: str, index: int, seconds: float = 1.0, *, timings=True) -> AudioChunk:
    pcm = floats_to_pcm16([0.1] * int(seconds * 16000))
    words = text.split()
    step = seconds / len(words) if words else 0.0
    wt = tuple((w, i * step, (i + 1) * step) for i, w in enumerate(words)) if timings else ()
    return AudioChunk(pcm=pcm, text=text, index=index, word_timings=wt)


FRAMES_PER_SECOND = 16000 // FRAME_SAMPLES  # 31.25 -> use exact frame math below


def frames_for(seconds: float) -> int:
    return int(seconds * 16000 / FRAME_SAMPLES)


def test_completed_chunks_are_fully_certain():
    ledger = PlaybackLedger(clock=SimulatedClock())
    c0, c1 = chunk("Hello there.", 0), chunk("How are you?", 1)
    for c in (c0, c1):
        ledger.chunk_started(1, c)
        ledger.chunk_finished(1, c, c.total_frames if hasattr(c, "total_frames")
                                else frames_for(1.0))
    heard = ledger.heard_text(1, "Hello there. How are you?")
    assert heard.certain_text == "Hello there. How are you?"
    assert heard.is_fully_certain
    assert heard.history_text() == heard.certain_text


def test_mid_chunk_interruption_with_alignment_keeps_only_finished_words():
    ledger = PlaybackLedger(clock=SimulatedClock())
    c0 = chunk("one two three four", 0, seconds=4.0)  # 1 s per word
    ledger.chunk_started(9, c0)
    # Played 2.5 s: words one (0-1) and two (1-2) certainly heard; three
    # straddles the cut -> uncertain; four never reached -> uncertain too
    # (same chunk), and NOTHING of it may be certain.
    ledger.chunk_finished(9, c0, frames_for(2.5))
    heard = ledger.heard_text(9, "one two three four")
    assert heard.certain_text == "one two"
    assert heard.uncertain_text == "three four"
    assert "three" not in heard.certain_text
    assert not heard.is_fully_certain
    assert heard.history_text().startswith("one two [uncertain:")


def test_mid_chunk_interruption_without_alignment_is_fully_uncertain():
    ledger = PlaybackLedger(clock=SimulatedClock())
    c0 = chunk("alpha beta gamma", 0, seconds=3.0, timings=False)
    ledger.chunk_started(3, c0)
    ledger.chunk_finished(3, c0, frames_for(2.9))  # almost all played!
    heard = ledger.heard_text(3, "alpha beta gamma")
    # Even at 97% played, without alignment NOTHING is certain.
    assert heard.certain_text == ""
    assert heard.uncertain_text == "alpha beta gamma"


def test_unplayed_chunks_are_never_heard():
    ledger = PlaybackLedger(clock=SimulatedClock())
    full = "First sentence. Second sentence. Third sentence."
    c0 = chunk("First sentence.", 0)
    ledger.chunk_started(5, c0)
    ledger.chunk_finished(5, c0, frames_for(1.0))
    heard = ledger.heard_text(5, full)
    assert heard.certain_text == "First sentence."
    assert heard.unplayed_text == "Second sentence. Third sentence."
    assert "Second" not in heard.history_text()


def test_records_carry_timestamps_and_interruption_flags():
    ledger = PlaybackLedger(clock=SimulatedClock())
    c0 = chunk("timed chunk here", 0, seconds=2.0)
    record = ledger.chunk_started(2, c0)
    ledger.chunk_progress(2, frames_for(0.5))
    ledger.chunk_finished(2, c0, frames_for(0.5))
    assert record.started_at is not None and record.stopped_at is not None
    assert record.stopped_at >= record.started_at
    assert record.interrupted and not record.completed
    import pytest

    assert record.fraction_played == pytest.approx(15 / 62, abs=0.01)


def test_unknown_turn_reconstructs_to_unplayed():
    ledger = PlaybackLedger(clock=SimulatedClock())
    heard = ledger.heard_text(999, "never spoken")
    assert heard.certain_text == "" and heard.unplayed_text == "never spoken"
