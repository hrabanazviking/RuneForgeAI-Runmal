# P-091 — TTS/STT as plugins (Part VI, Extensions Row)

Roadmap line, verbatim: "P-091 TTS/STT as plugins too: the founding voice stack refactored behind the same API (proof the API is real)."

Clean-room line: built entirely from Rúnmál's own in-tree contracts — the P-081 Plugin API v1 citizen pattern, the P-082 sandbox stance, and the founding S503/S504 voice seams — with no outside source read and no file downloaded (see the P-091 entry appended to `docs/CLEAN_ROOM_LOG_2026-10-30.md`).

Base: `47a960f`. Migration head: 0041. No migration taken.

## 1. What landed

Two new plugin citizens, and nothing else in the tree changed shape:

- `src/runmal/plugins/tts.py` — plugin id `runmal.tts`, version `1.0.0`, Plugin API v1.
- `src/runmal/plugins/stt.py` — plugin id `runmal.stt`, version `1.0.0`, Plugin API v1.
- Battery: `tests/test_p091_voice_plugins.py` (52 tests; see §6).

Each citizen wraps one founding voice seam, unchanged, through its existing abstract base class: the TTS citizen drives a host-wired `TTSBackend` (the S504 seam) and the STT citizen drives a host-wired `STTBackend` (the S503 seam). The engines are NOT rewritten. The existing voice routes and voice behaviour are untouched; the citizens are a second, plugin-shaped road to the same seams, which is the point of the roadmap line — the founding stack fits behind the same API as every later citizen, so the API is proven real rather than plugin-only.

The matched surface, identical for both citizens:

- Capabilities: `chat.events`, `ui.slots`.
- Permissions: `chat.read`, `ui.contribute`. `chat.write` is NOT declared by either citizen.
- Sandbox: both citizens declare only v1 surface permissions, so the derived resource grant set is EMPTY — and the battery proves it empty for both. The voice engine is host wiring, never a grant and never manifest data.
- UI contributions: one `settings.panel` slot each — TTS: label "Text to Speech", order 90, route `tts`; STT: label "Speech to Text", order 91, route `stt`.
- Registration is `register_plugin`-only, exported by each module (`register_plugin(registry, backend=None, *, config=None, enable=False)`). `build_registry` / `create_app` are unchanged: a boot registry stays empty unless a host explicitly registers a citizen.

## 2. Explicit actions only

Voice work happens only when a caller explicitly invokes an action. Events never synthesize and never transcribe, and no event name was invented for this slice: the Plugin API v1 event vocabulary (`PLUGIN_EVENTS`) stays closed in v1, and both citizens declare only names already in it.

Explicit roads:

- TTS `synthesize(text, voice=None, chat_id=None, *, speaking_rate=None)` — synthesize the given text through the wired backend.
- TTS `audition(voice=None, *, text=None, chat_id=None)` — hear a voice: with no text, the wired backend's own audition/sample road; with text, synthesis of that text in that voice.
- TTS introspection: `list_voices()` and `model_info()` pass through to the wired backend; `speech_status()` and `last_result()` read the citizen's in-memory per-chat state and never call the backend.
- STT `transcribe(pcm, sample_rate=16000, chat_id=None)` — transcribe the given PCM audio through the wired backend.
- STT introspection: `health()` and `model_info()` pass through to the wired backend; `transcription_status()` and `last_transcript()` read the citizen's in-memory per-chat state and never call the backend.

Event behaviour (observation and housekeeping only):

| Citizen | Declared events | What an event does |
|---|---|---|
| `runmal.tts` | `message.created`, `chat.deleted` | `message.created` records metadata only — a per-chat count and the last message's id, role and content length, with the observation timestamp; the message text itself is never stored, and the event NEVER synthesizes. `chat.deleted` clears that chat's stored state. |
| `runmal.stt` | `chat.deleted` | Housekeeping only: `chat.deleted` clears that chat's stored state. No event transcribes — the STT citizen declares no message event at all. |

Neither citizen declares prompt hooks. Voice is not prompt text: a transcript or a synthesis is produced by an explicit action and consumed as data, not silently folded into a prompt. For the same reason there is no `message.spoken`-style completion event and no transcription event in v1 — adding one would mean inventing vocabulary the closed v1 event set does not have; that is an API v2 question, deferred in §7.

A registered-but-not-enabled citizen receives no events, as the battery proves for TTS.

## 3. Honesty

Default wiring for both citizens is a deterministic fake, and it is labelled as one everywhere it appears:

- TTS: `backend=None` selects a fresh `FakeTTSBackend`. Results carry `road == "fake"` (the fake's backend key is `fake-tts`), and the fake's model/voice identifiers are the fake's own, never a real engine's name.
- STT: `backend=None` selects a fresh `FakeSTTBackend`. Results carry `road == "fake"` (the fake's backend key is `fake-stt`). The fake's scripted transcript is a test fixture, never presented as a real transcription.
- For a real-shaped backend wired by the host, the road label is that backend's own key — the label follows the wiring, it is never upgraded by the citizen.
- A backend that is unavailable or fails is wrapped and reported as a failure (`TtsPluginError` / `SttPluginError`); it is never silently replaced by the fake and never faked into a success. A failed call stores nothing and preserves any prior stored result.
- Validation precedes the backend: bad input is refused before any backend call is made.

Honest correction to the founding-stack story, stated plainly: Kokoro was REMOVED by the S504 license gate and is not named as a citizen default anywhere in this slice. The founding defaults are the HOST's wiring choices, unchanged by this slice: the founding TTS default is CosyVoice and the founding STT default is faster-whisper (small, int8). The citizens wrap the S503/S504 seams, so any host-wired backend — including those founding defaults — is driven unchanged; the citizens themselves choose no real engine.

Real backends are host wiring via `register_plugin`. In this slice's tests, real-shaped backends are exercised only through fakes and test doubles. The honest road for verifying real engines remains the voice stack's own S503/S504 verification — this slice claims no new real-engine verification of its own.

## 4. Parity and the seam facts

Byte-parity law: for the same input, a citizen's result carries the wired backend's output byte-for-byte, exactly as a direct call to that backend would produce it. The battery asserts this parity against direct calls to the fake backends, and again through custom host-wired backends, for both citizens. The citizen adds its result envelope (`plugin_id`, `road`, and status fields) around the backend's output; it does not re-encode, resample, trim, or otherwise alter the audio bytes or the transcript.

Seam facts, as built:

- Sentinel law: the fake TTS backend emits no final sentinel chunk; a real backend's sentinel chunk passes through verbatim; no sentinel is ever fabricated by the citizen.
- Sample-rate split: TTS rates are carried per chunk from the backend (the fake speaks at 16000 Hz; the native road at 24000 Hz), while STT works at its 16000 Hz canonical rate, with a caller-supplied `sample_rate` passed through to the backend unchanged.
- Speaking rate: `synthesize` accepts an optional `speaking_rate`, validates it, and reaches the backend through the seam correction recorded in the P-091 design (§3.6 step 5), stated openly here: `synthesize_all` cannot forward a rate (it materialises `synthesize(text, voice)` at the default rate), so at the default rate of 1.0 the citizen drives `synthesize_all`, and at any other rate it materialises `backend.synthesize(text, resolved, speaking_rate=<rate>)` itself — the rate reaches the seam's core method, never a dead parameter.
- STT factory kwargs: scripted fakes with specific text/language are constructed directly (`FakeSTTBackend(text=..., language=...)`) in tests, rather than routed through a factory the seam does not have.
- Async and duck-typed backends are both accepted: awaitable backend results are unwrapped, and a backend that satisfies the seam's shape is driven without requiring registration in any voice registry. Registering the citizens changes neither the founding voice registries nor their defaults.

## 5. Storage / migration

Per-chat state is in memory only, on the citizen instance: each citizen keeps the latest result per chat (for TTS, the latest synthesis/audition result plus the metadata-only `message.created` observation; for STT, the latest transcription result). `chat.deleted` clears that chat's state in both citizens. This state is lost on restart, stated plainly — nothing in this slice persists voice results.

NO migration: the migration head stays at 0041, and the battery asserts both the declared head and the live current revision on a fresh database. No table, file store, or durable voice store was added.

## 6. Battery

Battery file: `tests/test_p091_voice_plugins.py` — 52 passed as run (log: `hidden_files/p091_battery.log`).

What the 52 cover, by group:

- Manifest and surface: both manifests match the design verbatim, round-trip, and register; the matched surface is exact (`chat.write` absent); no prompt hooks declared; no invented event names; both citizens co-register in one registry.
- Sandbox and boot: both citizens' sandbox grants are EMPTY; the migration head stays 0041; a boot registry stays empty without explicit registration; the citizens do not change the founding voice registries or defaults.
- Configuration and registration: config validation for both citizens, lenient manifest-config loading, and `register_plugin` backend precedence.
- TTS roads: default wiring labelled fake; byte-parity with the direct fake backend; result shape; no fabricated sentinel, and a real sentinel passing through verbatim; custom-backend parity; speaking rate threaded and validated; voice argument forms; audition through the backend sample; voices/model introspection; async and duck-typed backends; status shapes; validation before the backend; failure storing nothing and preserving the prior result; an unavailable backend wrapped, never faked.
- STT roads: default wiring labelled fake; byte-parity with the direct fake backend; a scripted fake via direct construction; custom-backend parity; sample-rate pass-through; PCM validation before the backend; health and model info; an async backend unwrapped; failure storing nothing and preserving the prior result; status shapes.
- Events: TTS `message.created` records metadata only and never synthesizes; no STT event transcribes; `chat.deleted` clears state in each citizen and in both together; a registered-but-not-enabled citizen receives no events.

Neighbour-suite and full-suite counts are not pre-stated in this doc: they are recorded from the run logs in the slice evidence (`hidden_files/P091_EVIDENCE.md`) when the slice is finished, never estimated here.

## 7. Deferred, deliberately

- An HTTP surface for the citizens (the citizens are in-process plugin citizens in v1; the founding voice HTTP routes are untouched and remain the HTTP road).
- A slots hook offering an already-produced transcript's text as context (only text a user explicitly produced could ever be offered, and only under a future design).
- Per-chat opt-in for voice actions.
- A `message.spoken`-style completion event — an API v2 question, since the v1 event vocabulary is closed.
- Streaming synthesis through the citizen: `synthesize_stream` / barge-in stays with the orchestrator, which is untouched by this slice.
