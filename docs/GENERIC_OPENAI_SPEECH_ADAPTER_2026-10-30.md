# F-03 — Generic OpenAI-Compatible Speech Adapter (2026-10-30)

*Part I follow-on F-03, homed by the P-014 gate from P-010's
first recommendation: "synthesis and transcription behind the
existing TTS/STT seams, covering the 4 WANTED-GENERIC voice
rows." This record is that build. No external source was
consulted and no mirror was read for this slice: the wire
shape is the common speech surface the P-010 census already
recorded from the mirrors' official documentation, built
behind Rúnmál's own seams in F-01's adapter pattern.*

## What was built

- **Adapter pair** — `src/runmal/voice/openai_compat.py`:
  `OpenAICompatibleTTSBackend` (TTS seam, `name="openai"`) and
  `OpenAICompatibleSTTBackend` (STT seam,
  `backend_key="openai"`), sharing one sync client and one
  error discipline. The key is `openai` in both namespaces —
  the modalities are independent (BACKEND_CONTRACT §1), as
  with F-01's chat/embeddings pair.
- **TTS** — `POST /audio/speech` with JSON `{model, input,
  voice, response_format, speed}`, asking for
  `response_format="pcm"`: the surface's raw format (PCM16
  little-endian mono at 24 kHz, headerless), so chunks carry
  the returned bytes unmodified at `sample_rate=24000` — no
  transcoding is claimed and none happens. Text is split by
  the seam's own sentence splitter, one request per piece
  (first piece playable while the rest synthesize; every
  piece far below the per-request input limit), and the
  stream ends with the seam's explicit `is_final` sentinel.
  The caller's `voice_id` wins; the speaking rate is clipped
  to the served 0.25–4.0 range as `speed`.
- **STT** — `POST /audio/transcriptions` as multipart form:
  the caller's PCM16 mono audio framed as WAV by the stdlib
  `wave` module (the surface takes files, not raw PCM), with
  `{model, response_format="verbose_json", language?}`. The
  reply's segments and words normalize into the seam's
  `Transcript` / `TranscriptSegment` / `TranscriptWord`; a
  reply without segments becomes one segment spanning the
  audio, and an unserved word probability stays at the
  seam's neutral default — no invented precision.
- **Registry + factory wiring** — both registries gained an
  `openai` spec and both factories build the adapters
  (`build_tts_backend("openai")`, `build_stt_backend("openai")`),
  so the persisted voice settings and per-character voice
  profiles can select the adapter on either seam. The STT
  entry is distinct from the registered `openai-whisper`
  entry, which remains the *local reference implementation*,
  registered-but-unverified, exactly as before.

## Class: a connection, not an install

P-010 judged these rows CONNECT: the user connects a service
with their own key or their own server, and Rúnmál ships
only its own adapter code — no shipped-artifact licence
arises, and no GPL-tainted engine is involved or implied.
The registry specs therefore carry **disabled install
plans**: there is nothing to download, and the plan's note
is the configuration instruction the install button explains
instead of running anything. Configuration is constructor
arguments, falling back to the environment (`OPENAI_API_KEY`
for the key, `RUNMAL_SPEECH_BASE_URL` for a non-OpenAI
endpoint); the default base URL is OpenAI's API, pinned
equal to F-01's chat default by test so the two generic
adapters cannot drift. The key travels only as an
Authorization header — never in a payload, an error, or a
fixture (INV-023) — and error messages are generic-worded
by status, never echoing a response body.

## Coverage claim, stated exactly

The 4 WANTED-GENERIC rows of P-010 (OpenAI TTS, OpenAI STT,
Pollinations, and the OpenAI-compatible provider slot) are
covered **by this one adapter pair, wherever the named
service offers the OpenAI-compatible speech surface** — the
exact claim P-010 made for the build. User-run servers that
serve the common shape (the census's AllTalk / XTTS-server
rows) are reached insofar as they serve it, without Rúnmál
shipping or endorsing their engines. No bespoke per-brand
adapter was built, and **no live endpoint was called**: the
proof is fixture transports in
`tests/test_f03_openai_speech.py` (11 tests). The census's
closing entry is §7 of
`docs/VOICE_PROVIDER_CENSUS_2026-10-30.md`, appended — its
original verdicts stand as the record of the gap. The
WANTED-CONNECT cloud connectors (ElevenLabs first) remain
queued to the Part VII definition queue, per the gate.

## Deliberately updated pins

- `tests/test_p010_voice_provider_census.py` pinned the
  pre-F-03 registries and instructed the closing slice
  implicitly by its docstring ("a future voice slice must
  update the census deliberately"): its registry tuples now
  record the `openai` entries appended on both seams.
- `tests/test_s504_tts.py` pinned the TTS known-backend set
  exactly; it now includes `openai`, with its connect class
  asserted beside the others.
No other pin needed to move: the `KNOWN_* == registry +
fake` formulas, the shipped-default lists (CosyVoice /
faster-whisper only), and the predeclared thresholds all
stand unchanged.

## What this slice does not do

- It calls no live endpoint and proves no named service's
  current surface; a configured endpoint is the user's act.
- It builds none of the WANTED-CONNECT per-brand connectors
  (Part VII queue) and clears neither REVERIFY row (Silero
  TTS, WhisperLive — no adapter work names them).
- It streams no live microphone audio to the endpoint: the
  STT seam is whole-utterance transcription, as shipped.
- It touches no README.md and pushes nothing; banking is
  local.
