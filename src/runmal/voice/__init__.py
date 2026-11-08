"""Rúnmál real-time voice subsystem (Campaign V).

Layered, provider-isolated pieces (see docs/VOICE_ARCHITECTURE.md):

- ``audio``     — device enumeration, explicit role selection, capture /
  playback seams, 16 kHz mono ring buffer with pre-roll (S501).
- ``vad``       — voice-activity detection: frame/state/hysteresis (S502).
- ``stt``       — speech-to-text service seam + faster-whisper (S503).
- ``tts``       — text-to-speech service seam (S504); engines register
  in ``backends`` (TTS, ADR-0005) / ``stt_backends`` (STT, ADR-0006),
  install through ``install`` (one-button, user action only), and are
  license-audited per backend by ``license_audit``. Kokoro REMOVED.
- ``settings``  — persisted user backend defaults (voice_settings.json).
- ``orchestrator`` / ``turntaking`` / ``bargein`` — the live loop (S505-507).
- ``ledger``    — playback truth ledger (S508).
- ``support``   — echo / self-interruption support contract (S509).
- ``metrics``   — monotonic per-stage latency metrics (S510).
- ``profiles``  — per-character voice profiles (S512).
- ``session``   — voice sessions bound to a chat: settings resolved
  honestly at start, turns persisted with playback truth (P-101).
- ``live`` / ``live_router`` — the live voice host: per-session
  orchestrators wired into the app process (P-102).
- ``projection`` / ``projection_router`` — recorded turns landed
  in their chat as provenance-carrying messages (P-103).
- ``autoproject`` / ``autoproject_router`` — the async
  auto-projecting host: opted-in sessions project as their
  turns are recorded (P-104).
- ``mishearing`` / ``mishearing_router`` — STT word-confidence
  truth: low-confidence detection + replacement suggestions
  over the persisted evidence (P-105, VX-11).
- ``routing``   — persisted logical device routes (S513).
- ``latency``   — per-turn latency evidence derived from the
  orchestrator's clock-stamped transitions, persisted on the
  session record (P-110).
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
