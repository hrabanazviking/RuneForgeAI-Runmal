# Rúnmál Voice Architecture

The voice subsystem is a real-time state machine, not a text chatbot with speech bolted on.

## 1. Pipeline

```text
microphone / room-audio input
    ↓
pre-roll ring buffer
    ↓
VAD
    ↓
utterance segmentation / endpointing
    ↓
STT partials + final
    ↓
turn coordinator
    ↓
Prompt Composer + ChatBackend
    ↓
streaming sentence/chunk assembler
    ↓
TTS
    ↓
playback queue
    ↓
audio device / virtual cable / companion output
```

Barge-in runs in parallel while the companion is speaking.

## 2. Explicit states

The orchestrator should expose inspectable states such as:

- `LISTENING`
- `USER_SPEAKING`
- `FINALIZING_STT`
- `THINKING`
- `SYNTHESIZING`
- `SPEAKING`
- `INTERRUPTING`
- `ERROR_RECOVERY`

Transitions are logged with monotonic timestamps for latency measurement.

## 3. Barge-in

Confirmed user speech while the companion is speaking generates one interruption event that propagates to:

1. active LLM stream;
2. sentence/chunk assembly;
3. queued and in-flight TTS synthesis;
4. playback queue/device.

Short backchannels/noise do not necessarily interrupt. Thresholds are configurable and tested against fixture audio.

## 4. Playback truth ledger

Generated text is not automatically equivalent to heard text.

Each synthesized audio chunk records:

- source turn ID;
- source text span;
- synthesis chunk ID;
- audio duration/samples;
- playback start timestamp;
- playback stop/completion timestamp;
- interrupted flag.

History stores a **spoken/heard representation derived from playback evidence**, not simply the full generated response. If interruption occurs inside a synthesis chunk and exact word alignment is unavailable, Rúnmál must represent uncertainty conservatively rather than claiming unplayed words were heard.

Possible strategies include smaller TTS chunks, word/phoneme timing where available, and a `played_text_prefix` plus uncertainty marker. The contract is truthfulness, not pretending waveform position maps perfectly to characters.

## 5. Endpointing

VAD answers "is speech occurring?" Endpointing answers "did the user finish the turn?"

Use a configurable silence hangover and retain enough state to cancel preemptive generation if the user resumes speaking.

Latency tuning is measured empirically on target hardware. Numbers in research documents are hypotheses until benchmarked locally.

## 6. Audio devices and routing

Rúnmál must enumerate and persist explicit logical roles:

- user microphone;
- user playback/headset;
- companion output/virtual cable;
- room/game audio capture where supported;
- optional monitor device.

Device IDs may change across boots/OS updates, so configuration should retain stable descriptive metadata and surface remapping when a saved device disappears.

## 7. Echo/self-interruption

Speaker leakage can cause the companion to hear itself and barge into its own speech.

Initial support must make one of these contracts explicit:

- **headset-first supported mode**, where acoustic leakage is minimized; or
- a verified AEC/audio-routing implementation for open-speaker use.

"AEC notes" alone are not an acceptance criterion for production room-audio support.

For virtual-cable/game use, keep the companion's own generated channel separable from captured room audio wherever possible so the system can subtract/ignore known self-output before VAD/STT.

## 8. Provider interfaces

Voice providers are replaceable services:

### STT
- partial/final transcript events;
- confidence/timestamps when available;
- cancellation;
- language/model metadata.

**Multi-backend registry (ADR-0006).** STT mirrors the TTS model exactly. Backends register a spec in `runmal.voice.stt_backends` behind the `STTBackend` seam, and the user selects the **default STT backend in settings**. The **default shipped backend is faster-whisper** (small int8; contract verified on purplelongship). Additional engines — whisper.cpp, OpenAI Whisper, distil-whisper, Moonshine, NVIDIA Parakeet, NVIDIA Canary, Vosk, sherpa-ONNX STT models, Silero STT — are **user-downloadable options**: each installs only via an explicit one-button user action in settings, under the user's own responsibility (ADR-0005 scope). Their per-backend audit verdicts are displayed as information and never block a user-chosen backend; extras the forge has not real-model-verified carry the label **"user-installed — not forge-verified"** wherever they render.

### TTS
- synthesize text chunk;
- streaming/chunked audio where supported;
- voice profile metadata;
- cancellation;
- optional timing alignment.

Per-character voice profiles reference TTS backend + voice + parameters rather than hard-coding a specific engine.

**Multi-backend registry (ADR-0005).** There is no single TTS engine. Concrete backends register a spec in `runmal.voice.backends` (key, admission class, factory) behind the `TTSBackend` seam, and the user selects the **default TTS backend in settings**; a persona's voice profile (S512) may name a different registered backend per character. Two admission classes exist:

- **default (shipped)** — installed with Rúnmál's voice feature; the backend's real installed tree must pass the S504 license audit before it is selectable. Shipped at Campaign V rework: `cosyvoice` (native streaming), `chatterbox` (sentence-chunk streaming built at the seam).
- **user-installed** — Rúnmál ships only its own adapter code; the backend installs solely on the user's explicit per-backend install action. Shipped as adapters: `kitten`, `piper`. Their audit verdict is computed and displayed as information; it never blocks the user's own installation (see §9).

The registry is extensible by design: a future backend — including a first-party engine — registers a spec and an admission class; nothing else in the voice pipeline changes.

## 9. Licensing gate

Voice dependencies require a dependency-tree audit before adoption. A permissively licensed model or wrapper is not sufficient if runtime dependencies pull incompatible packages.

Since Volmarr's 2026-10-13 rulings (ADR-0005), the gate is **per-backend admission** with an explicit scope:

> "Backends a user installs themselves are the user's own choice — the gate guards only what Rúnmál ships by default."

- The **default shipped tree** (default install + default backends: CosyVoice, and Chatterbox with `pykakasi` excluded by curated install) must audit green against the real installed environment; a default backend whose tree fails is not selectable, in code, before synthesis is possible.
- **User-installed backends** (Kitten, Piper) are the user's own choice: adapters ship, installation is an explicit user action, the settings/audition UI carries the honest not-shipped-by-Rúnmál notice, and the audit verdict for such a backend is displayed as information only.

History, so the reasoning is not lost: the originally selected single path (Kokoro-82M via independent ONNX + Misaki G2P) **failed this gate at the Campaign V landing** — `misaki[en]` directly requires the forbidden eSpeak-NG carriers `espeakng-loader` + `phonemizer-fork` — and Kokoro was **removed from the product** by Volmarr's ruling. The full field survey behind the replacement registry is `docs/TTS_ENGINE_SURVEY.md`; per-backend evidence lives in `docs/VOICE_LICENSE_MATRIX.md`. Do not postpone per-backend re-audit to final voice hardening: any backend's version change returns it to reverify.

## 10. Metrics

Record at least:

- VAD speech-on latency;
- endpoint hangover;
- STT final latency;
- LLM time-to-first-token;
- time-to-first-synthesizable chunk;
- TTS time-to-first-audio;
- playback start;
- end-to-end user-end-of-turn → first-audio;
- interruption detection → playback stop.

Report p50/p95 plus hardware/software configuration.

## 11. Benchmark fixtures

Voice tests should include:

- clean speech;
- speech with keyboard/fan/game noise;
- short backchannels;
- cough/transient noise;
- user interrupting companion mid-sentence;
- companion speaking while room audio plays;
- missing/disconnected audio device;
- long synthesis cancelled during generation.

## 13. Implementation status (Campaign V)

- **S501 Audio plumbing** — `src/runmal/voice/audio.py`: `DeviceProvider`
  seam (fixture provider for headless tests; `SoundDeviceProvider` via the
  optional `sounddevice`/PortAudio package, imported lazily), `AudioDevice`
  enumeration, `RoleMap` explicit role selection persisted as descriptive
  JSON (`SavedDeviceRef`), and a 16 kHz mono PCM16 `RingBuffer` with
  pre-roll. Resolution follows INV-022: a missing saved device yields
  `REMAP_REQUIRED` with no device bound — the OS default is *offered* by
  enumeration but never silently substituted. Audio format contract for
  the whole campaign: PCM16 LE mono @ 16 kHz, 512-sample (32 ms) frames.
- **S502 VAD** — `voice/vad.py`: hysteresis segmenter (start/end
  thresholds, min-speech, hangover, pre-roll) over a `VadModel` seam; the
  real model is Silero's official ONNX graph via onnxruntime (tagged
  optional), tests use a deterministic energy fixture model. Predeclared
  segmentation contract lives in `SEGMENTATION_CONTRACT`.
- **S503 STT** — `voice/stt.py` + `voice/corpus.py`: `STTBackend` seam,
  faster-whisper `small` int8 baseline with word timestamps (tagged
  optional), fixed Flite-synthesized fixture corpus, WER/RTF contract
  predeclared in `STT_CONTRACT`.
- **S504 TTS + license gate** — `voice/tts.py` (seam), `voice/backends.py`
  (registry), `voice/license_audit.py` (per-backend admission),
  `voice/install.py` (curated per-backend installs): multi-backend TTS
  per ADR-0005. Default shipped backends: **CosyVoice 2** (native
  streaming) and **Chatterbox** (sentence-chunk streaming at the seam;
  `pykakasi` excluded by dependency surgery; PerTh watermark ships as
  upstream, recorded in the matrix). User-installed optional backends:
  **Kitten** and **Piper** adapters (install on explicit user action;
  audit verdict informational). The originally selected Kokoro/Misaki
  path failed the gate at the first landing attempt and was **removed**
  (see §9). The default backend is user-selectable in settings; output
  is resampled to the 16 kHz pipeline format; streaming honors
  cancellation.
- **S505–S507 Loop** — `voice/orchestrator.py` (explicit state machine,
  deterministic simulated transitions), `voice/turntaking.py` (endpoint
  hangover, preemptive finalize, resume cancellation), `voice/bargein.py`
  (one interruption event → LLM/TTS/playback arms; backchannels
  tolerated; predeclared 100 ms stop budget).
- **S508 Playback truth ledger** — `voice/ledger.py`: per-chunk playback
  records; heard-text reconstruction is conservative (INV-020).
- **S509 Support contract** — `voice/support.py`: supported modes are
  HEADSET, SEPARATED_OUTPUT and OPEN_SPEAKER_AEC (AEC *verified on the
  route*). **Open speakers without verified AEC on a shared capture are
  UNSUPPORTED** — the companion would hear itself; the assessment says
  so plainly and live voice must not silently degrade into that mode.
  `SelfOutputSuppressor` separates known self-output by playback
  reference where the route is separable.

## 12. VRChat implication

OSC controls/events are not the same thing as hearing room voice. Whole-room listening on PCVR requires an explicit audio-ingress route from the host machine. Treat that as its own bridge/audio slice, not as an assumed property of OSC.