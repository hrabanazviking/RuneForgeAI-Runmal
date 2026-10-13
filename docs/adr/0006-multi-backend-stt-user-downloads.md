# ADR-0006 — Multi-backend STT with one-button user downloads

Status: Accepted
Date: 2026-10-13

## Context

ADR-0005 made TTS multi-backend with per-backend license admission and a
gate whose scope is the default shipped tree. Volmarr extended the same
philosophy to speech-to-text minutes later (2026-10-13):

> "Same with STT — make it so it can use a lot more options than it ships
> with, with one-button-touch options for the user to download whichever
> of the other ones by their own choosing under their own responsibility."

The shipped STT path is not in dispute: faster-whisper (small int8) is
already laptop-verified against its predeclared contract (WER 0.1111 ≤
0.25; RTF p50 0.8362 ≤ 1.0, purplelongship, 2026-10-13). What is missing
is breadth: the field of credible STT engines is wide, and users will
reasonably want them.

## Decision (Volmarr, 2026-10-13)

1. **STT is a multi-backend registry** behind the existing `STTBackend`
   seam (`runmal.voice.stt_backends`), mirroring the TTS model of
   ADR-0005 exactly: admission classes, per-backend audit, settings
   selection.
2. **Default shipped STT backend: faster-whisper.** The default shipped
   tree — STT + TTS defaults together — must audit green under the
   S504 gate (scope per ADR-0005 decision 4).
3. **Additional STT engines are user-downloadable options.** Registered
   at this landing: whisper.cpp, OpenAI Whisper (reference
   implementation), distil-whisper (via faster-whisper), Moonshine,
   NVIDIA Parakeet, NVIDIA Canary, Vosk, sherpa-ONNX STT models, Silero
   STT. Each installs **only** via an explicit one-button user action in
   settings — the tap is the user's own act, under their own
   responsibility. Nothing in this class is ever in the default install.
4. **Honesty requirements (acceptance criteria, not decoration):**
   settings shows the registry with the same notice pattern as
   user-installed TTS backends (not shipped with Rúnmál; user's own
   installation; that backend's own license terms apply); the
   per-backend audit runs on a user-downloaded backend's real tree and
   its verdict is **displayed as information**, never blocking a
   user-chosen backend; UI copy does not pre-claim any extra's license
   beyond the audit's own verdict; any extra the forge has not
   real-model-verified is labelled **"user-installed — not
   forge-verified"**.
5. **Settings gains a user-selectable default STT backend**, global,
   beside the default TTS backend selection.
6. **Bounded acceptance for the Campaign V landing:** registry +
   one-button machinery + audit-display proven end-to-end on
   purplelongship, with the mechanism proven on the smallest practical
   extra (distil-whisper — a model download through the already-shipped
   runtime). Remaining extras may ship registered-but-unverified under
   the honest label; verifying every extra's real model is explicitly
   *not* part of this landing.

## Consequences

- The one-button installer (`runmal.voice.install`) is shared machinery:
  a per-backend install plan (package installs and/or model downloads),
  executed only from the explicit settings action (or an explicit CLI
  invocation by the operator — the same act, in terminal form).
- Registered-but-unverified STT extras carry `forge_verified = False`
  in the registry; the label renders wherever the backend renders.
- As with TTS, the registry is extensible: new STT engines register a
  spec; the seam does not move.

Detailed contract: `docs/VOICE_ARCHITECTURE.md` §8, `docs/VOICE_LICENSE_MATRIX.md` (STT registry).
