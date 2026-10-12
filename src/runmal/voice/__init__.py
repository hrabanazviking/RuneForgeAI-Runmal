"""Rúnmál real-time voice subsystem (Campaign V).

Layered, provider-isolated pieces (see docs/VOICE_ARCHITECTURE.md):

- ``audio``     — device enumeration, explicit role selection, capture /
  playback seams, 16 kHz mono ring buffer with pre-roll (S501).
- ``vad``       — voice-activity detection: frame/state/hysteresis (S502).
- ``stt``       — speech-to-text service seam + faster-whisper (S503).
- ``tts``       — text-to-speech service seam + license-gated Kokoro (S504).
- ``orchestrator`` / ``turntaking`` / ``bargein`` — the live loop (S505-507).
- ``ledger``    — playback truth ledger (S508).
- ``support``   — echo / self-interruption support contract (S509).
- ``metrics``   — monotonic per-stage latency metrics (S510).
- ``profiles``  — per-character voice profiles (S512).
- ``routing``   — persisted logical device routes (S513).
- ``benchmark`` — reproducible voice benchmark harness (S514).

Core modules are stdlib-only: heavy runtime packages (numpy, onnxruntime,
ctranslate2, sounddevice) are imported lazily inside the real adapters so
the deterministic fixture paths always run in the plain test suite.
"""

from __future__ import annotations

SAMPLE_RATE = 16000
CHANNELS = 1
FRAME_SAMPLES = 512  # 32 ms at 16 kHz — the Silero VAD frame size.
FRAME_MS = FRAME_SAMPLES * 1000 // SAMPLE_RATE
