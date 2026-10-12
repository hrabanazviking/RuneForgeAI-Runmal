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

### TTS
- synthesize text chunk;
- streaming/chunked audio where supported;
- voice profile metadata;
- cancellation;
- optional timing alignment.

Per-character voice profiles reference TTS backend + voice + parameters rather than hard-coding a specific engine.

## 9. Licensing gate

Voice dependencies require a dependency-tree audit before adoption. A permissively licensed model or wrapper is not sufficient if runtime dependencies pull incompatible packages.

The current Kokoro direction remains a candidate, but phonemization/runtime dependencies must be verified before S504 is accepted. Do not postpone this to final voice hardening.

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

## 12. VRChat implication

OSC controls/events are not the same thing as hearing room voice. Whole-room listening on PCVR requires an explicit audio-ingress route from the host machine. Treat that as its own bridge/audio slice, not as an assumed property of OSC.