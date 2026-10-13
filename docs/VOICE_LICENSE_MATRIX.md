# Rúnmál Voice License Matrix

Rúnmál's project policy is a permissive-only distributed voice stack. The exact license of **every shipped artifact** matters: application code, Python/native dependencies, model weights, voices, phonemizer data and bundled binaries.

This file is a release/build gate, not legal advice. Re-verify exact versions upstream before adoption/distribution.

## Scope — what the gate guards (Volmarr, 2026-10-13)

> "Backends a user installs themselves are the user's own choice — the gate guards only what Rúnmál ships by default."

This scope line applies **Rúnmál's interoperability principle** (Volmarr, 2026-10-13; full text in `docs/VOICE_ARCHITECTURE.md` §9): *always give the user free-will, choice, trust, but they are responsible for what they add — and we make apps that can play nice with outside tools of whatever kind.* Ship clean lawful defaults; user additions are user choice under user responsibility; design for interop with outside tools of any kind.

- The S504 gate guards the **default shipped tree**: the default install plus the default TTS backends. That tree must audit green against the real installed environment before the voice campaign ships. **As landed (2026-10-13): the shipped default tree is the base install + CosyVoice.** Chatterbox was default-*class* by the original ruling but **held at admission** on real-tree evidence; Volmarr then ruled at 05:45 EDT on 2026-10-13: **"Make Chatterbox user-installed — one-button choice, gate stays pure."** It is therefore recorded below as user-installed, not shipped.
- **User-installed backends are the user's own choice.** For backends in that class (Kitten, Piper, Chatterbox), Rúnmál ships only its own Apache-2.0 adapter code. Installation happens only on the user's explicit per-backend install action — never in the default install. Chatterbox's recipe is its **stock upstream tree**, installed with dependency resolution and no pykakasi/librosa pruning. The settings/audition UI must show an honest notice for such backends: *not shipped with Rúnmál; installed by you; the backend's own license terms (including any GPL-3.0 components in its tree) apply to your installation.* The per-backend audit still runs for user-installed backends and its verdict is **displayed as information**; it does not block a user-installed backend.
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
| `cosyvoice` | **default** (shipped) | CosyVoice 2 (0.5B), FunAudioLLM | Apache-2.0 / Apache-2.0 | ✅ **ADMITTED (2026-10-13)** — real tree audits green (70 distributions, 0 violations); real corpus synthesis on purplelongship; no eSpeak, no soxr, no `ttsfrd` (evidence block below) |
| `chatterbox` | **user-installed** | chatterbox-tts (Resemble AI) | MIT / MIT | **USER-INSTALLED (Volmarr's ruling, 2026-10-13 05:45 EDT)** — stock upstream tree by one-button user action, with no pykakasi/librosa pruning; audit verdict displayed as information and never blocks. Its stock tree is expected to flag `pykakasi` (GPL-3.0) and `soxr` (LGPL-2.1-or-later); real install/synthesis/verdict evidence is recorded below |
| `kitten` | **user-installed** | Kitten TTS (KittenML) | Apache-2.0 / Apache-2.0 | user-installed optional — upstream requires `espeakng-loader` + `phonemizer` (forbidden carriers); audit verdict displayed as information, never shipped by default |
| `piper` | **user-installed** | Piper (OHF-Voice piper1-gpl) | GPL-3.0 / per-voice | user-installed optional — upstream tree carries `piper-phonemize` (forbidden carrier) and the successor codebase is itself GPL-3.0; audit verdict displayed as information, never shipped by default |
| `fake-tts` | test fixture | Rúnmál's own code | Apache-2.0 | deterministic test double; never presented as real speech |
| ~~`kokoro-onnx`~~ | **removed** | Kokoro-82M + Misaki | Apache-2.0 / Apache-2.0 | ❌ **removed from the product** by Volmarr's 2026-10-13 ruling — `misaki[en]` directly requires the forbidden carriers `espeakng-loader` + `phonemizer-fork`; the whole misaki chain leaves the tree |

### Recorded integration facts (registered backends)

- **Chatterbox — PerTh watermark:** upstream `generate()` applies the PerTh implicit watermark unconditionally (Perth itself is MIT). Rúnmál ships Chatterbox **as upstream**; synthesized audio from this backend carries that watermark. Recorded here so the fact is never a surprise; removing it would mean patching upstream, which this project does not do silently.
- **Chatterbox — Perth package:** upstream declares `resemble-perth>=1.0.0` as a package requirement. The retired default-class curated recipe pinned a Perth git commit; the current **stock user-install recipe does not** — pip resolves upstream's declared package, exactly as a user's own stock install would.
- **Chatterbox — streaming:** upstream has no streaming API (`generate()` returns a whole waveform). Sentence-chunk streaming is built at the Rúnmál seam (`split_text_into_chunks` + per-chunk generate), which is also what keeps barge-in cancellation meaningful for this backend.
- **CosyVoice — frontend (corrected by evidence, 2026-10-13):** the pinned CosyVoice2 runtime imports neither WeTextProcessing nor pynini; its open frontend is `wetext`, whose FST assets are served through a modelscope repo endpoint that refuses anonymous access through the pinned modelscope client (the CosyVoice2 model repo itself downloads fine). `wetext` is therefore **not** in the shipped set and the frontend slot stays empty — an upstream-supported configuration ("compatible when no text frontend tool is avaliable"); prose synthesis is unaffected. The proprietary `ttsfrd` is **never** installed. A user with a modelscope token can install `wetext`+`kaldifst` themselves (interoperability principle).
- **CosyVoice — the soxr trap and the transformers line:** librosa **is** required (the vendored Matcha-TTS submodule imports it on the flow path) and ships **without** `soxr`. transformers **5.x** hard-imports `soxr` whenever librosa is present (its `audio_utils`); the set therefore holds upstream's own pin **transformers==4.51.3**, whose `audio_utils` imports librosa only. Verified by `sys.modules` after a real synthesis: `transformers.audio_utils` imported, `soxr` never imported, `soxr` not installed.
- **CosyVoice — torch builds:** the shipped tree uses the self-contained **CPU** torch/torchaudio wheels (BSD-3) from `download.pytorch.org`. The PyPI CUDA builds cannot enter the tree: their `nvidia-*` companion wheels declare **no license metadata at all** (audit "unknown") and torch does not import without them. Consequence: the predeclared performance thresholds (declared for the GPU reference) are **not met on the CPU build** — measured and recorded in `docs/BENCHMARKS.md`, thresholds untouched. GPU torch remains available to users as their own install (interoperability principle).
- **CosyVoice — pins that matter:** `modelscope==1.32.0` (1.40's split hub requires `cryptography`, whose dual-license SPDX sits outside the reviewed set); `ruamel.yaml==0.17.21` (0.18 broke HyperPyYAML's Loader composition); `setuptools==80.9.0` (pyworld imports `pkg_resources`, removed in setuptools ≥81); Matcha-TTS arrives as a git **submodule** — the install machinery initializes submodules (an empty submodule dir was a real build failure).
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

### Admission evidence — recorded 2026-10-13 (purplelongship, uv Python 3.12.13)

```text
Backend key: cosyvoice
  class: default (shipped)
  upstream package/version: FunAudioLLM/CosyVoice git @ 074ca6dc (vendor
    checkout, submodules initialized); CosyVoice2-0.5B via modelscope
  model artifact/version/hash: CosyVoice2-0.5B snapshot (modelscope,
    ~4.5 GB, downloaded by the machinery's warm-up)
  model license: Apache-2.0
  runtime dependency lock reviewed (the real installed tree): YES —
    the curated set in runmal.voice.backends.COSYVOICE_PACKAGES,
    installed in one pass by runmal.voice.install.run_install
  forbidden distributions present: none (no eSpeak carriers, no soxr)
  phonemizer/G2P path + its license: none on the v2 path (frontend
    slot empty — see integration facts)
  audit verdict (audit_distributions over the real tree): PASS —
    70 distributions checked, 0 violations (backend_status, binding)
  corpus synthesis + predeclared thresholds (S514): synthesis PASS
    (3/3 fixed corpus texts, 24 kHz WAVs); performance thresholds
    NOT MET on the shipped CPU build (first-audio p50 18.78 s vs
    1.5 s; RTF p50 6.42 vs 1.0 — thresholds declared for the GPU
    reference and never rewritten; see docs/BENCHMARKS.md)

Verdict: ADMITTED
Reviewed date: 2026-10-13
Commit: surge-c5-tts (Campaign V landing)

Backend key: chatterbox
  class: default-class — HELD at admission
  upstream package/version: chatterbox-tts 0.1.7 (PyPI)
  model license: MIT (code + weights)
  runtime dependency lock reviewed (the real installed tree): YES —
    chatterbox-tts 0.1.7 Requires-Dist: librosa==0.11.0 and
    transformers==5.2.0 are hard pins of the upstream package
  forbidden distributions present: python-soxr (LGPL-2.1-or-later)
    enters mandatorily: transformers 5.2.0's audio_utils hard-imports
    soxr whenever librosa is installed, chatterbox.tts imports
    librosa at module level, and its prompt path calls
    librosa.resample (soxr-backed). Proven on the real tree.
  audit verdict: FAIL-CLOSED — no lawful default-shipped tree exists
    today; the install plan is disabled (enable=False) and the
    machinery refuses installation

Verdict: NOT ADMITTED — held pending Volmarr's ruling (options:
  reclassify as user-installed under his 2026-10-13 scope ruling;
  ship a patched fork; or drop the backend)
Reviewed date: 2026-10-13
```

### Audit fidelity amendments (2026-10-13 — flagged for fellowship review)

The gate's classifier policy (forbidden lists, permissive *set of licenses*) never changed in substance. What changed is the reader's fidelity to how real wheels declare licenses — every amendment below is an attested spelling or a bundled-text fact, each regression-tested:

- The reader takes the declared **License-Expression** (PEP 639), never the raw `License` field when it holds a full license *body* (a PSF body mentioning GPL in prose previously read as *forbidden*; an MIT body as *unknown*).
- SPDX **AND**-compounds are judged per component (every component must be permissive); **WITH**-exception suffixes are stripped; **OR** compounds stay *unknown*.
- Attested spellings of already-accepted licenses added: "Apache 2.0 License", bare "Apache", "BSD 3-Clause License", "3-Clause BSD License", "Public Domain", "CNRI-Python", **0BSD / BSD-0-Clause** (numpy's real expression), **MIT-CMU** (Pillow's declared expression — the CMU variant of the MIT license).
- A `License`-field candidate that names no recognizable license ("Dual License" — python-dateutil) no longer shadows a clear OSI classifier; a candidate carrying a real verdict (e.g. GPL) still always wins over classifiers; banner-rule first lines (`=====`, kiwisolver) are not expressions.
- **Reviewed declarations** (wheels whose metadata declares *nothing* but which bundle their license text as a PEP 639 `License-File`, texts read on purplelongship): `wetextprocessing` → Apache-2.0; `pyworld` → MIT; `wetext` → Apache-2.0. A metadata-silent wheel not on this list still fails as *unknown*.

### Full-environment observations (outside the gate's tree scope — for policy review)

A full-environment audit (every distribution in a developer venv, 120 checked) surfaces items the per-backend trees do not contain. None blocks the S504 gate as scoped in ADR-0005; all are recorded here so the fellowship can rule with eyes open:

- `certifi` (**MPL-2.0**) — present in the base app environment via `httpx` (pre-existing, not a voice dependency). MPL-2.0 is a file-level weak copyleft the classifier leaves *unknown — human review required*. Policy question for the fellowship: accept MPL-2.0 into the reviewed set, or leave the base environment's exposure noted.
- `cffi` (declares **MIT-0**) — arrives via `soundfile`'s normal (with-deps) install; MIT-0 is MIT without the attribution clause. Not in any curated tree (the machinery installs `--no-deps`).
- `greenlet` ("MIT AND PSF-2.0") and `packaging` ("Apache-2.0 OR BSD-2-Clause") — tooling/dev-environment packages; the PSF-2.0 *spelling* and OR-compounds stay *unknown* by the conservative rules above.
- `tqdm` (declares "MPL-2.0 AND MIT") — a `huggingface-hub` dependency (second-order, like certifi/cffi): present in real environments via normal installs, not in the curated tree scope.

## STT backend registry (ADR-0006)

STT admission mirrors TTS: one shipped default, the rest user-downloadable under the same scope line and notice requirement. The forge does **not** pre-claim licenses for user-downloadable STT extras — the per-backend audit's own verdict, computed on the user's real installed tree, is the only license statement the UI makes about them.

| Backend key | Class | Upstream | Forge state |
|---|---|---|---|
| `faster-whisper` | **default** (shipped) | faster-whisper + Whisper small int8 | ✅ cleared — MIT package tree; weights MIT; contract verified on purplelongship (WER 0.1111, RTF 0.8362) |
| `distil-whisper` | user-downloadable | distil-whisper weights via the shipped faster-whisper runtime | ✅ **mechanism proven (2026-10-13)** — one-button install through `run_install` (warm-up model download), real transcription of a fixed Flite corpus item: WER 0.1 against the reference |
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