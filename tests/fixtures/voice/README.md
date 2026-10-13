# Voice fixture corpus — provenance

The STT/TTS fixture corpora are **generated on the test host**, never
committed as binaries.

## STT corpus (S503/S514)

- Texts: fixed in `src/runmal/voice/corpus.py` (`CORPUS_TEXTS`) — five
  short English utterances with exact reference transcripts.
- Voice: CMU Flite `slt` voice, synthesized through ffmpeg's `flite`
  source filter (`flite=text='...':voice=slt`), resampled to 16 kHz mono
  PCM16 WAV by ffmpeg itself.
- License: CMU Flite is distributed under a permissive BSD-style license
  (Carnegie Mellon University). ffmpeg is invoked as an external system
  tool; Rúnmál ships no ffmpeg code or binaries.
- Why synthetic speech: the reference transcript is known *exactly*, so
  WER is measured against ground truth with no human transcription step
  and no third-party recording license to audit. Flite speech is robotic;
  WER against it is a *baseline floor*, not a claim about human speech —
  benchmark reports must say so (see docs/BENCHMARKS.md, Campaign V).

## TTS corpus (S504/S514)

- Texts: fixed in `src/runmal/voice/tts.py` (`TTS_CORPUS_TEXTS`).
- Synthesized per registered backend (ADR-0005: CosyVoice by default,
  Chatterbox/Kitten/Piper as user-installed backends; the deterministic
  fake in fixture runs); outputs are checked
  for non-silence, duration sanity and first-audio latency — TTS has no
  reference waveform, so quality gates are structural, not invented
  perceptual scores. (The corpus's first line also serves as the
  transcript of the default CosyVoice zero-shot prompt asset.)
