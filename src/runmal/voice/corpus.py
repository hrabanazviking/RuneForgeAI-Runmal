"""Fixed voice fixture corpus definitions (S503, reused by S514).

The corpus texts are FIXED — benchmarks are only reproducible if the
reference transcripts never drift. Audio is synthesized per-run by CMU
Flite (see stt.synthesize_flite_wav) so no binary fixtures are committed.
"""

from __future__ import annotations

from pathlib import Path

from runmal.voice.stt import CorpusItem, synthesize_flite_wav, wav_to_pcm

#: (name, reference text) — short, phonetically varied, fixed forever.
CORPUS_TEXTS: tuple[tuple[str, str], ...] = (
    ("greeting", "hello world this is a test of the voice system"),
    ("numbers", "the meeting is on tuesday at nine thirty in the morning"),
    ("directions", "turn left at the old bridge and walk toward the river"),
    ("weather", "rain will fall over the hills before the evening comes"),
    ("names", "yrsa keeps her runes in a small wooden box by the fire"),
)


def build_flite_corpus(workdir: Path, voice: str = "slt") -> list[CorpusItem]:
    """Synthesize the fixed corpus into ``workdir`` and load it as PCM."""
    workdir.mkdir(parents=True, exist_ok=True)
    items: list[CorpusItem] = []
    for name, text in CORPUS_TEXTS:
        wav = synthesize_flite_wav(text, workdir / f"{name}.wav", voice=voice)
        items.append(CorpusItem(name=name, pcm=wav_to_pcm(wav), reference_text=text))
    return items
