# Rúnmál Voice License Matrix

Rúnmál's project policy is a permissive-only distributed voice stack. The exact license of **every shipped artifact** matters: application code, Python/native dependencies, model weights, voices, phonemizer data and bundled binaries.

This file is a release/build gate, not legal advice. Re-verify exact versions upstream before adoption/distribution.

## Scope — what the gate guards (Volmarr, 2026-10-13)

> "Backends a user installs themselves are the user's own choice — the gate guards only what Rúnmál ships by default."

This scope line applies **Rúnmál's interoperability principle** (Volmarr, 2026-10-13; full text in `docs/VOICE_ARCHITECTURE.md` §9): *always give the user free-will, choice, trust, but they are responsible for what they add — and we make apps that can play nice with outside tools of whatever kind.* Ship clean lawful defaults; user additions are user choice under user responsibility; design for interop with outside tools of any kind.

- The S504 gate guards the **default shipped tree**: the default install plus the default TTS backends (**CosyVoice**, and **Chatterbox with pykakasi excluded**). That tree must audit green against the real installed environment before the voice campaign ships.
- **User-installed backends are the user's own choice.** For backends in that class (Kitten, Piper), Rúnmál ships only its own Apache-2.0 adapter code. Installation happens only on the user's explicit per-backend install action — never in the default install. The settings/audition UI must show an honest notice for such backends: *not shipped with Rúnmál; installed by you; the backend's own license terms (including any GPL-3.0 components in its tree) apply to your installation.* The per-backend audit still runs for user-installed backends and its verdict is **displayed as information**; it does not block a user-installed backend.
- The full ruling and its rationale are recorded in `docs/adr/0005-multi-backend-tts-admission.md`; the field evidence is `docs/TTS_ENGINE_SURVEY.md`.

## Status vocabulary

- ✅ **cleared** — exact chosen version/artifact reviewed against project policy.
- 🟡 **candidate** — promising but complete runtime tree not cleared.
- ❌ **rejected by project policy** — known selected artifact/license conflicts with the permissive-only distribution policy.
- 🔄 **reverify** — previously checked but must be checked again for release/version change.

## TTS backend registry (per-backend admission, ADR-0005)

Admission is **per backend**, against that backend's own real installed tree — there is no longer a single TTS path for the gate to bless or condemn.

| Backend key | Class | Upstream | Code / weights license | Admission state |
|---|---|---|---|---|
| `cosyvoice` | **default** (shipped) | CosyVoice 2 (0.5B), FunAudioLLM | Apache-2.0 / Apache-2.0 | ✅ admissible — no eSpeak in the open path; ship the open WeTextProcessing frontend, **exclude** the optional proprietary `ttsfrd` |
| `chatterbox` | **default** (shipped) | chatterbox-tts (Resemble AI) | MIT / MIT | ✅ admissible **only with dependency surgery** — `pykakasi==2.3.0` (GPL-3.0-or-later, Japanese path only) must never enter our tree; Perth pinned to a fixed commit; PerTh watermark ships as upstream (see below) |
| `kitten` | **user-installed** | Kitten TTS (KittenML) | Apache-2.0 / Apache-2.0 | user-installed optional — upstream requires `espeakng-loader` + `phonemizer` (forbidden carriers); audit verdict displayed as information, never shipped by default |
| `piper` | **user-installed** | Piper (OHF-Voice piper1-gpl) | GPL-3.0 / per-voice | user-installed optional — upstream tree carries `piper-phonemize` (forbidden carrier) and the successor codebase is itself GPL-3.0; audit verdict displayed as information, never shipped by default |
| `fake-tts` | test fixture | Rúnmál's own code | Apache-2.0 | deterministic test double; never presented as real speech |
| ~~`kokoro-onnx`~~ | **removed** | Kokoro-82M + Misaki | Apache-2.0 / Apache-2.0 | ❌ **removed from the product** by Volmarr's 2026-10-13 ruling — `misaki[en]` directly requires the forbidden carriers `espeakng-loader` + `phonemizer-fork`; the whole misaki chain leaves the tree |

### Recorded integration facts (default backends)

- **Chatterbox — PerTh watermark:** upstream `generate()` applies the PerTh implicit watermark unconditionally (Perth itself is MIT). Rúnmál ships Chatterbox **as upstream**; synthesized audio from this backend carries that watermark. Recorded here so the fact is never a surprise; removing it would mean patching upstream, which this project does not do silently.
- **Chatterbox — Perth pin:** upstream declares `resemble-perth` as an unpinned git dependency (`@master`). Our curated install pins it to a fixed commit (see `runmal.voice.install` / pyproject notes).
- **Chatterbox — streaming:** upstream has no streaming API (`generate()` returns a whole waveform). Sentence-chunk streaming is built at the Rúnmál seam (`split_text_into_chunks` + per-chunk generate), which is also what keeps barge-in cancellation meaningful for this backend.
- **CosyVoice — frontend:** text normalization uses the open WeTextProcessing frontend. The optional proprietary `ttsfrd` package is **not** installed and must not enter the tree (it would classify *unknown* and fail the default-tree audit).
- **CosyVoice — distribution trap:** CosyVoice is **not** installed from PyPI. The PyPI project named `cosyvoice` (0.0.8, claiming GPL-3.0) is an **unrelated package squatting the name** — never `pip install cosyvoice`. The real CosyVoice ships from the FunAudioLLM GitHub repository; Rúnmál's installer clones it at a pinned commit into the app vendor dir and installs a curated dependency set (see `runmal.voice.install`).

## Candidate stack ledger

| Layer | Candidate | Current Rúnmál state | Required evidence before acceptance |
|---|---|---|---|
| VAD | Silero VAD | ✅ cleared — MIT code + model, ONNX runtime tree audited at Campaign V verification (2026-10-13) | reverify on version change |
| STT | faster-whisper + chosen Whisper weights | ✅ cleared — MIT package tree; Whisper small weights (MIT) verified against the predeclared WER/RTF contract on purplelongship (2026-10-13) | reverify on version change |
| TTS backends | registry above | per-backend — see registry table | per-backend real-tree audit + corpus synthesis + predeclared thresholds (S514) |
| Audio I/O | sounddevice/PortAudio | ✅ cleared — MIT wrapper; PortAudio (MIT-style) license recorded at Campaign V verification | reverify on version change |
| AEC | not selected | 🟡 research | exact runtime/binary license + quality on target route |

## Known caution categories

### eSpeak/eSpeak-NG paths

Do not assume a phonemizer is cleared because the high-level TTS package is permissive. If the selected runtime depends on or bundles eSpeak/eSpeak-NG, inspect the exact upstream licensing and decide against Rúnmál's project policy before S504 acceptance.

### Piper ecosystem

Do not use the name "Piper" as a license conclusion. Different repositories/packages/voices/history may carry different licensing. Review the **exact artifact/version** if reconsidered.

### XTTS / cloning models

Model-weight licenses can impose restrictions independent of inference code. Check exact weight license and commercial/distribution rights before considering a cloning model.

## S504 gate — per-backend admission evidence

S504 cannot pass with only "the package is Apache/MIT" or an equivalent top-level statement — for **each default backend separately**, and the audit runs against the **real installed tree** of that backend's extra.

Acceptance evidence should record, per backend:

```text
Backend key:
  class: default (shipped) / user-installed
  upstream package/version:
  model artifact/version/hash:
  model license:
  runtime dependency lock reviewed (the real installed tree):
  forbidden distributions present: none / list
  phonemizer/G2P path + its license:
  audit verdict (audit_distributions over the real tree):
  corpus synthesis + predeclared thresholds (S514): pass / fail

Verdict: admitted / not admitted
Reviewed date:
Commit:
```

For **user-installed** backends the same evidence block is recorded, but the verdict is **informational**: it is displayed in the settings/audition UI next to the user-install notice and never blocks the user's own installation (scope section above).

## STT backend registry (ADR-0006)

STT admission mirrors TTS: one shipped default, the rest user-downloadable under the same scope line and notice requirement. The forge does **not** pre-claim licenses for user-downloadable STT extras — the per-backend audit's own verdict, computed on the user's real installed tree, is the only license statement the UI makes about them.

| Backend key | Class | Upstream | Forge state |
|---|---|---|---|
| `faster-whisper` | **default** (shipped) | faster-whisper + Whisper small int8 | ✅ cleared — MIT package tree; weights MIT; contract verified on purplelongship (WER 0.1111, RTF 0.8362) |
| `distil-whisper` | user-downloadable | distil-whisper weights via the shipped faster-whisper runtime | registered; one-button = model download; mechanism proof extra for the Campaign V landing |
| `whisper-cpp` | user-downloadable | whisper.cpp (via pywhispercpp) | registered — not forge-verified |
| `openai-whisper` | user-downloadable | OpenAI Whisper reference implementation | registered — not forge-verified |
| `moonshine` | user-downloadable | Moonshine (Useful Sensors) | registered — not forge-verified |
| `parakeet` | user-downloadable | NVIDIA Parakeet (NeMo) | registered — not forge-verified |
| `canary` | user-downloadable | NVIDIA Canary (NeMo) | registered — not forge-verified |
| `vosk` | user-downloadable | Vosk (Kaldi) | registered — not forge-verified |
| `sherpa-onnx-stt` | user-downloadable | sherpa-ONNX STT models | registered — not forge-verified (note: sherpa-ONNX *TTS* Kokoro/Piper paths carry eSpeak data per the survey; STT models are judged by their own audit) |
| `silero-stt` | user-downloadable | Silero STT models | registered — not forge-verified |
| `fake-stt` | test fixture | Rúnmál's own code | deterministic test double |

## Automated gate

Campaign VIII should generate an SBOM/license report from the release environment, but automation supplements manual review for model/voice assets that ordinary Python license scanners may not understand.

A package scanner saying "green" is not proof that separately downloaded weights/assets are cleared.

## Change rule

When any voice dependency/model/voice version changes, return its row to 🔄/🟡 until the release artifact is rechecked.