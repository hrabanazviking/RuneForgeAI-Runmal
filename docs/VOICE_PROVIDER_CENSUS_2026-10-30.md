# P-010 — Voice Provider Census (2026-10-30)

*Which speech-to-text and text-to-speech services the two mirrors
plug, judged one by one against Rúnmál's licence gate — the
founding survey's method (`docs/TTS_ENGINE_SURVEY.md`,
2026-10-13), refreshed for the 2026 field. This census builds
nothing; it gives Part I's gate (P-014) and the later voice work a
provider ledger that rests on papers, not brand names.*

## Method, sources, and the clean-room boundary

- **Mirror side, SillyTavern:** the provider list is
  SillyTavern's **official public TTS documentation page**
  (`docs.sillytavern.app/extensions/tts/`), read in full on
  2026-10-30. It names 16 TTS providers in its selection list,
  plus an **OpenAI-compatible** provider named in the same page's
  voice-map note — 17 in all. **No source code and no
  source-derived analysis was used** (third-party source-derived
  provider lists exist and name more; they are not census
  evidence under the clean-room law, §2 of the roadmap).
  SillyTavern's **STT** surface (P-002 row ST-63) is **not
  enumerated** in the official documentation read for P-002 or
  for this census: no provider names are recorded for it, and
  none are invented here. That is a surveyed-but-not-enumerated
  flag, carried to §5.
- **Mirror side, Voxta:** the provider names are those the
  P-003 census already attested from Voxta's official public
  site, documentation, and release notes: **STT** (VX-14) —
  OpenAI, WhisperLive, AssemblyAI, Deepgram, Voxta Cloud;
  **TTS** — ElevenLabs (named "11Labs" as a high-quality TTS in
  Voxta's official Cloud Credits FAQ) and Voxta Cloud itself.
  Voxta's official documentation read does **not** enumerate a
  full TTS provider catalogue; that too is recorded as
  surveyed-but-not-enumerated, not filled in from unofficial
  mirrors.
- **The gate, stated exactly** (`docs/VOICE_LICENSE_MATRIX.md`
  scope line, Volmarr 2026-10-13): the licence gate guards
  **only what Rúnmál ships by default**. Two judgement classes
  follow:
  - **SHIP** — a local engine/model Rúnmál would distribute.
    Judged by the founding survey's method: code licence and
    *weights* licence separately, the G2P/eSpeak trap, the
    non-commercial-weights trap. Permissive-only or it fails.
  - **CONNECT** — a cloud or user-run service the *user*
    connects with their own key or their own server. Nothing
    ships, so no shipped-artifact licence arises; under the
    interoperability principle these are judged wanted or
    unwanted on product grounds (and P-008's verdicts bind
    where the same service was already judged for chat).
  User-installed engines sit between the classes: Rúnmál ships
  only its own adapter code, the audit verdict displays as
  information, and the user's choice governs (ADR-0005/0006).
- **Rúnmál side:** the tree's own registries, read this census —
  TTS (`src/runmal/voice/backends.py`): `cosyvoice` (default,
  admitted 2026-10-13), `chatterbox` / `kitten` / `piper`
  (user-installed), `fake-tts`; the removed `kokoro-onnx` is
  recorded in the license matrix. STT
  (`src/runmal/voice/stt_backends.py`): `faster-whisper`
  (default, cleared), `distil-whisper` (verified extra), and
  `whisper-cpp`, `openai-whisper`, `moonshine`, `parakeet`,
  `canary`, `vosk`, `sherpa-onnx-stt`, `silero-stt` registered
  unverified, plus `fake-stt`. VAD: Silero VAD (MIT, cleared) —
  a *different artifact* from Silero TTS, and its papers clear
  nothing but itself.

## Verdict vocabulary

- **HAVE** — Rúnmál already carries it in the relevant class.
- **PASS-SHIP** — passes the ship gate on the founding survey's
  papers.
- **FAIL-SHIP** — fails the ship gate (named trap in the row);
  reachable at most as a user-installed / user-run choice.
- **WANTED-CONNECT** — wanted as a user-key / user-server
  connection; nothing ships.
- **WANTED-GENERIC** — wanted, and the wanted build is the one
  generic OpenAI-compatible speech shape, not a per-brand
  adapter (kin to P-008's chat verdict).
- **REVERIFY** — the artifact's papers were not verified in
  this census or the founding survey; it cannot pass any gate
  until they are.
- **UNWANTED** — judged not wanted, reason in the row; P-008
  verdicts inherited where the service is the same.
- **DEPRECATED** — the mirror itself marks it deprecated.

## §1 TTS providers (18 distinct judged)

SillyTavern names 17, Voxta adds Voxta Cloud (ElevenLabs is
named by both and counted once).

| Provider | Class | Verdict | Grounds |
|---|---|---|---|
| AllTalk | user-run local server (aggregator) | WANTED-CONNECT | A server the user runs themselves; Rúnmál would ship nothing. Its bundled engines are judged separately — its headline cloning engine is XTTS (FAIL-SHIP, below). Interop with a user-run speech server is the interoperability principle's home ground. |
| Azure TTS | cloud | WANTED-CONNECT | Microsoft's neural voices behind the user's own Azure key. Nothing ships. (The same voice family as Edge, below, with an SLA and per-character billing.) |
| Coqui-TTS | local, via deprecated Extras API | DEPRECATED | SillyTavern's own page marks it deprecated. Its model zoo (Tacotron family, Bark) needs no new verdict: Bark already fails the founding survey (disputed papers, not real-time). No adapter wanted for a deprecated route. |
| Edge | cloud (free, no key) | WANTED-CONNECT | Microsoft Edge voices served via Azure at no cost. Nothing ships; the no-key free tier makes it the lowest-friction cloud voice in either mirror. |
| Electron Hub | cloud aggregator | UNWANTED | P-008 judged Electron Hub UNWANTED (bespoke) for chat and the verdict inherits: OpenRouter already fills Rúnmál's router slot. If its speech endpoint is OpenAI-shaped it rides the generic adapter (§3) with no new code. |
| ElevenLabs | cloud | WANTED-CONNECT | **The only TTS provider both mirrors name.** The quality benchmark of the field (founding survey §5 records blind-preference comparisons, vendor-commissioned). User's subscription, user's key; nothing ships. First among the cloud connectors in §5's recommendation. |
| Google Translate | cloud (free) | WANTED-CONNECT | One free voice per language via Google's translate endpoint. Flagged honestly: that endpoint is undocumented as a TTS API, so this is a fragile connection, not a foundation. |
| Google Gemini TTS | cloud | WANTED-CONNECT | Gemini TTS models via an AI Studio key. The same page also offers a Vertex AI key route; P-008 judged Vertex UNWANTED (bespoke enterprise machinery) and that half inherits — AI Studio is the wanted route. A 2026-field addition since the founding survey. |
| Kokoro | browser-local engine | FAIL-SHIP | The founding survey's headline failure: Apache code and weights, GPL-3.0 eSpeak phonemization at the English heart. Rúnmál already removed `kokoro-onnx` from the product on exactly these papers (2026-10-13). Running in the user's browser is the user's choice; Rúnmál ships no adapter and no artifact. |
| MiniMax | cloud | WANTED-CONNECT | API-key cloud TTS; a 2026-field addition to SillyTavern's list since the founding survey era. Nothing ships. |
| NovelAI ("Novel") | cloud, subscription | UNWANTED | P-008 judged NovelAI UNWANTED for chat (bespoke, proprietary, subscription, no founding demand) and the TTS incarnation inherits the verdict. Re-opens only on Volmarr's word. |
| OpenAI | cloud | WANTED-GENERIC | OpenAI's TTS models. Wanted — through the generic speech shape (§3), not a bespoke adapter, exactly as P-008 ruled for OpenAI chat. |
| Pollinations | cloud gateway (free) | WANTED-GENERIC | Free, rate-limited gateway access to OpenAI TTS models. No adapter of its own: it is reached *through* the OpenAI shape, so the generic verdict covers it whole. |
| OpenAI-compatible | generic local/cloud shape | WANTED-GENERIC | **The key gap, voice edition.** SillyTavern's escape hatch — any server speaking the common speech shape. Rúnmál has no generic speech adapter at all (its TTS/STT backends are per-engine); §3 sizes what one build covers. |
| Silero | local server | REVERIFY | Silero *TTS* model papers were not verified in the founding survey and are not verified here. Rúnmál's cleared Silero artifact is the **VAD** model (MIT) — a different artifact whose papers clear nothing else (the survey's per-artifact law). No gate pass, no adapter, until the exact TTS artifacts are read. |
| System | OS platform voices | WANTED-CONNECT | The operating system's own TTS engine, if one exists. Nothing ships and no key exists; a platform connection is the cheapest possible fallback voice. Rúnmál has none today. |
| XTTS | user-run local server | FAIL-SHIP | Founding survey: code MPL-2.0 (excluded from the shipped tree by policy), weights under the Coqui Public Model License — non-commercial. A user running their own XTTS server is their choice; Rúnmál ships nothing toward it beyond what the generic shape (§3) happens to reach. |
| Voxta Cloud | cloud, subscription | UNWANTED | P-008 judged Voxta Cloud UNWANTED and P-004 judged VX-01 DELIBERATELY-DIFFERENT (no cloud/subscription tier; the sovereign replacement stands). Its TTS/STT incarnation inherits both. |

**TTS totals: 18 judged — 8 WANTED-CONNECT, 3 WANTED-GENERIC,
2 FAIL-SHIP, 3 UNWANTED, 1 REVERIFY, 1 DEPRECATED.**

## §2 STT providers (5 distinct judged)

All five are Voxta's (VX-14). SillyTavern's STT providers are
not enumerated in its official documentation (see Method) and
contribute no rows.

| Provider | Class | Verdict | Grounds |
|---|---|---|---|
| OpenAI | cloud | WANTED-GENERIC | Voxta transcribes through OpenAI's Whisper API. The `/audio/transcriptions` shape is the field's de-facto generic STT shape (local servers serve it too), so the generic verdict applies as for TTS. Distinct from Rúnmál's registered `openai-whisper` extra, which is the *local reference implementation* — a user-downloadable model, not this cloud service. |
| WhisperLive | user-run local server | REVERIFY | A live-transcription server the user runs. Its papers were not verified in the founding survey (which cleared the faster-whisper *runtime* and Whisper weights Rúnmál ships — different artifacts) and are not verified here. User-server interop is wanted in principle; the REVERIFY flag must clear before any adapter work names it. |
| AssemblyAI | cloud | WANTED-CONNECT | Commercial transcription API, user's key; nothing ships. |
| Deepgram | cloud | WANTED-CONNECT | Commercial transcription API at its Nova V3 / Flux generation in Voxta's current line (VX-14). User's key; nothing ships. |
| Voxta Cloud | cloud, subscription | UNWANTED | Inherits §1: P-008 UNWANTED, VX-01 DELIBERATELY-DIFFERENT. |

**STT totals: 5 judged — 1 WANTED-GENERIC, 2 WANTED-CONNECT,
1 REVERIFY, 1 UNWANTED.**

**Census totals: 23 distinct mirror voice providers judged —
10 WANTED-CONNECT, 4 WANTED-GENERIC, 2 FAIL-SHIP, 4 UNWANTED,
2 REVERIFY, 1 DEPRECATED, 0 HAVE, 0 PASS-SHIP.** The zeroes are
findings, not omissions: no provider either mirror names is in
Rúnmál's shipped or registered set under the same name and
class, and no *new* local engine the mirrors plug passes the
ship gate on papers already read — the mirrors' local-TTS
headline acts (Kokoro, XTTS) are precisely the founding
survey's two most famous failures.

## §3 The generic speech shape (the §1/§2 key gap)

Four of the 23 rows are WANTED-GENERIC, and they are the
highest-leverage rows in the census: **one generic
OpenAI-compatible speech adapter** — synthesis and transcription
behind Rúnmál's existing `TTSBackend` / `STTBackend` seams,
configured by base URL + key like the Aesir chat adapter (whose
shape P-009 audited) — covers OpenAI TTS, OpenAI STT,
Pollinations, and the OpenAI-compatible provider slot itself,
and reaches user-run local servers (AllTalk, XTTS servers)
insofar as they serve the common shape, without Rúnmál shipping
or endorsing their engines. This is P-008's chat finding
repeated in the voice domain: the mirrors' breadth is mostly
*one shape with many nameplates*. Parts II–VI of the roadmap
contain no voice-provider slice, so this build is flagged
**NO HOME** for the P-014 gate, kin to P-008's generic chat
adapter and P-009's Aesir binding repair — the gate may
recommend the three as one generic-adapter family.

## §4 Vice versa — Rúnmál's voice field against the mirrors

- **CosyVoice 2 (Rúnmál's admitted default)** is named by
  *neither* mirror's official documentation read for this
  census. Rúnmál's ship-gate PASS stands on the founding
  survey and the 2026-10-13 real-tree audit, not on mirror
  parity — parity was never its claim. The P-006 open fact
  rides along: on the shipped CPU build CosyVoice's measured
  performance misses its predeclared thresholds (RTF p50 6.42
  vs 1.0, `docs/BENCHMARKS.md`), which is precisely why §1's
  cloud connectors matter — they are the latency relief valve
  for a sovereign default that is honest about its CPU cost.
- **Chatterbox** (Rúnmál user-installed, forge-verified recipe)
  is likewise absent from SillyTavern's official TTS page as
  read; it appears only in source-derived third-party lists,
  which this census does not use. No parity claim either way.
- **Rúnmál's STT field is broader than the mirrors' named
  STT**: beyond the shipped faster-whisper default it registers
  distil-whisper (verified), whisper.cpp, Moonshine, Parakeet,
  Canary, Vosk, sherpa-ONNX STT, and Silero STT as
  user-downloadable extras (ADR-0006) — none of them named by
  either mirror's official documentation read here.
- **Silero, mirror-flipped:** the mirrors plug Silero as a
  *TTS* server; Rúnmál ships Silero as its *VAD* (MIT, cleared).
  Same brand, different artifacts, different papers — the
  census records the flip because it is exactly the confusion
  the founding survey's per-artifact law exists to prevent.

## §5 The 2026 refresh and the honest flags

- **Refreshed since the founding survey (2026-10-13):** the
  mirrors' own lists moved — SillyTavern's current page adds
  Gemini TTS, MiniMax, Electron Hub, and Pollinations to the
  field the founding era knew, and Voxta's STT line now runs
  Deepgram at Nova V3 / Flux. All are judged above.
- **New field entrant, judged pre-emptively:** Mistral's
  **Voxtral TTS** (released March 2026; 4B, voice adaptation
  from ~3 s of audio) carries **CC-BY-NC-4.0 weights** —
  FAIL-SHIP under the gate if it is ever proposed, by the
  non-commercial-weights trap. Neither mirror is recorded
  plugging it in the sources read here. (Evidence class:
  secondary reporting of the model's Hugging Face card, read
  2026-10-30 — flagged as such; the verdict would be re-read
  against the card itself before any slice acted on it.)
- **Surveyed-but-not-enumerated (2):** SillyTavern's STT
  provider list and Voxta's full TTS provider catalogue are
  not enumerated in the official public documentation read
  for P-002/P-003 or this census. Both are recorded as open
  reading, not filled from unofficial or source-derived
  lists. If a later slice needs them, the road is the
  mirrors' own published materials or Volmarr's word — never
  their source code.
- **No provider was installed, called, or subscribed to** by
  this census. Every CONNECT verdict is a judgement about a
  future user-key adapter, not a claim of a working
  integration; every SHIP verdict rests on the founding
  survey's papers and the license matrix, re-read this census,
  not on new installs.

## §6 Recommendations to the P-014 gate

1. **Generic OpenAI-compatible speech adapter** (TTS + STT):
   WANTED-GENERIC ×4, **NO HOME** in Parts II–VI — first
   recommendation, kin to P-008's chat adapter (§3).
2. **Cloud voice connectors, ElevenLabs first** (the only
   provider both mirrors name), then Azure / Edge / Gemini /
   MiniMax for TTS and Deepgram / AssemblyAI for STT, all as
   user-key CONNECT adapters shipping nothing: **NO HOME** in
   Parts II–VI as written.
3. **REVERIFY before any adapter work:** Silero TTS artifacts
   and WhisperLive's papers — exact artifacts, read directly.
4. **Closed unless papers change:** Kokoro and XTTS
   (FAIL-SHIP), Electron Hub / NovelAI / Voxta Cloud voice
   services (UNWANTED, inheriting P-008), Coqui-TTS route
   (DEPRECATED by its own mirror).
