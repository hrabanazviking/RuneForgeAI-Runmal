# Replacing Kokoro — A Survey of Open TTS Engines for Rúnmál's Voice

**Deliverable for the S504 block.** Authored by Yrsa, 2026-10-13, on Volmarr's order after the
S504 license gate failed the Kokoro path on the real installed tree.
**Status:** research complete; **the engine choice is Volmarr's ruling** — the surge HOLD at S504
stands until he picks. This document surveys; it does not amend the gate, the roadmap, or
`docs/VOICE_LICENSE_MATRIX.md` (whose policy it applies verbatim).

**Method:** every engine's code license and *weights* license were checked separately against
primary sources (project LICENSE files, Hugging Face model cards, PyPI metadata), and every
engine's text-to-phoneme / G2P path was traced for eSpeak-NG entanglement — the trap that killed
Kokoro. Performance figures are vendor/other-hardware numbers classified into RTF *classes*:
**no engine in this survey has a published RTF measured on an RTX 2060** — treat all such
figures as class estimates, not measurements. Anything not verified is listed under
*Could not verify*, not silently dropped.

---

## 1. Why this document exists

Campaign V's landing ran the S504 license audit against the real installed tree on
purplelongship, and it failed (Forge-Log, 2026-10-13 01:36 EDT):

```text
forbidden | espeakng-loader  | eSpeak-NG carrier (GPL-3.0) — rejected by policy
forbidden | phonemizer-fork  | eSpeak-NG carrier (GPL-3.0) — rejected by policy
```

`misaki[en]` 0.9.4 — Kokoro's English phonemizer — directly requires both. Kokoro's weights and
code are Apache-2.0; its *English voice* is not shippable under Rúnmál's law, because the
phonemization path is GPL-3.0 at the heart, not at the edges.

Volmarr's ruling (2026-10-13): **Kokoro is set aside. Survey the whole field properly and post
the findings.** This is that survey.

## 2. The judging law (S504 gate, unchanged)

From `src/runmal/voice/license_audit.py` (branch `surge-c5`) and `docs/VOICE_LICENSE_MATRIX.md`:

- The distributed voice tree is **permissive-only**: Apache-2.0 / MIT / BSD / ISC / PSF / zlib /
  Unlicense / CC0-1.0. MPL-2.0 is excluded from the shipped runtime tree by policy decision.
- **Forbidden outright:** any license marker containing `gpl`, `agpl`, `lgpl`, `copyleft`,
  `noncommercial`, `non-commercial`, or `cc-by-nc`; and these distributions regardless of what
  their metadata claims: `espeakng-loader`, `espeak-ng`, `espeakng`, `phonemizer`,
  `phonemizer-fork`, `piper-phonemize`, `py-espeak-ng`.
- A permissive top-level package does **not** clear its tree — the *installed* tree is audited.
- Unknown/unreviewed licenses fail until reviewed.

And the functional bar from the roadmap (S504, S512, S514):

- Sentence/chunk **streaming** synthesis; a predeclared first-audio latency threshold,
  honestly benchmarked (S514).
- **Per-character voice profiles** (S512) — a voice per persona, selectable without touching
  the chat backend.
- Barge-in (S507): synthesis must be cancellable mid-stream.
- Reference hardware: purplelongship — Ryzen 9 + RTX 2060 Max-Q (6 GB VRAM class).

## 3. Executive verdict

### PASS — license-clean under the gate as written

| Engine | Why it passes | The catch |
|---|---|---|
| **CosyVoice 2** (Alibaba) | Apache-2.0 code **and** weights; no eSpeak in the open path; zero-shot cloning; **bi-directional streaming, vendor-reported 150 ms first packet** — the strongest streaming story in the survey | Ship the open WeTextProcessing frontend, **not** the optional proprietary `ttsfrd`; language strength is zh/en/ja/ko + Chinese dialects |
| **Pocket TTS** (Kyutai) | MIT code; weights CC-BY-4.0 (permissive, attribution — *not* non-commercial); no eSpeak; CPU ~6× real-time, ~200 ms first chunk, streaming by design; cloning from ~5 s | CC-BY-4.0 is **not in the gate's current permissive set** (CC0 is) — needs a one-line policy review by Volmarr; few languages (English-first, ~6–7 later) |
| **Sesame CSM-1B** | Apache-2.0 code and weights; no eSpeak | GPU-serving class; voices are prompt/context-based, not enrollment-based; hard latency numbers sparse in sources |
| **Dia** (Nari Labs) | Apache-2.0 code and weights; no eSpeak; dialogue-native two-speaker model | Heavy (~10 GB VRAM — over a 2060 Max-Q's comfort); repo stale since 2025 |
| **Parler-TTS** (HF) | Apache-2.0 code and weights; no eSpeak | **No true cloning** — voices are text descriptions; CPU far slower than real-time |

### CONDITIONAL — clean only with named engineering or a named ruling

| Engine | Conditions |
|---|---|
| **Chatterbox** (Resemble AI) — *deep dossier in §5* | MIT code, MIT weights, **zero eSpeak** — but a stock install pulls **pykakasi (GPL-3.0)** for Japanese; the PerTh watermark is applied unconditionally (patch the MIT code or accept it); the Perth dependency is an unpinned git `@master`; **no native streaming API** — sentence chunking is integrator work |
| **Orpheus-TTS** (Canopy Labs) | Apache-2.0 on its face, no eSpeak, streaming, cloning — but ~10–12 GB VRAM under vLLM exceeds 2060-class, and whether Llama Community License terms attach to the weights is unresolved |
| **MeloTTS** (MyShell) | MIT code and weights, no direct eSpeak — but its per-language frontends are **not fully audited**; the Japanese path raises the same pykakasi question as Chatterbox |
| **OpenVoice V2** (MyShell) | V2 is MIT (V1 was CC-BY-NC — ship V2 artifacts only); it is a tone-color layer, so its tree inherits whatever base TTS it wraps |
| **Supertonic** (Supertone) | MIT code, extremely fast ONNX — but weights are **OpenRAIL-M** (use restrictions, not plain permissive) and upstream was archived Aug 2026 |

### FAIL — do not ship, however good they sound

- **The eSpeak six** (permissive paint, GPL heart): **Kokoro-82M**, **Piper** (successor
  `piper1-gpl` is literally GPL-3.0), **Zonos**, **NeuTTS Air**, **Kitten TTS**, **StyleTTS 2**
  (its own README admits the GPL phonemizer). All require eSpeak-NG / phonemizer at runtime.
- **Non-commercial weights behind permissive code:** **Spark-TTS** (weights *re-licensed* from
  Apache-2.0 to CC-BY-NC-SA-4.0), **F5-TTS** (CC-BY-NC-4.0), **Fish Speech / OpenAudio**
  (CC-BY-NC-SA-4.0), **XTTS v2** (Coqui Public Model License; code is MPL-2.0 besides),
  **Higgs Audio** (v2 custom community license — *not* Apache as blogs claim; v3 research-NC),
  **IndexTTS 2** (bilibili scale-gated Model Use License).
- **Unverifiable or disputed:** **GPT-SoVITS** (weights license could not be verified at all —
  disqualifying until clarified), **Bark** (MIT vs CC-BY-NC sources conflict; also slower than
  real-time and unmaintained).
- **sherpa-ONNX** is Apache-2.0 itself but statically bundles eSpeak-NG (GPL-3.0), and its
  Kokoro/Piper model bundles ship `espeak-ng-data` — not a clean delivery vehicle for those
  models. Non-eSpeak models through it must be chosen deliberately, per model.

## 4. Summary table

| Engine | Code | Weights | eSpeak in tree | RTF class | Cloning | Verdict |
|---|---|---|---|---|---|---|
| Kokoro-82M | Apache-2.0 | Apache-2.0 | **Yes (GPL-3.0)** | CPU ≫RT | No | Fail as-shipped |
| Piper | MIT → **GPL-3.0** successor | Per-voice, varies | **Yes (GPL-3.0)** | CPU ≫RT | No | Fail |
| **Chatterbox** | **MIT** | **MIT** | No — but **pykakasi GPL-3.0** in default deps | GPU RT; Nano CPU ~3× RT (vendor) | **Yes (~10 s)** | **Conditional** |
| Orpheus-TTS | Apache-2.0 | Apache-2.0 (Llama terms flagged) | No | GPU RT (heavy) | Yes | Conditional |
| Sesame CSM-1B | Apache-2.0 | Apache-2.0 | No | GPU class | Prompt-based | Pass (GPU serving) |
| Zonos | Apache-2.0 (v0.1) | Apache-2.0 | **Yes** | GPU RT | Yes | Fail as-shipped |
| Dia | Apache-2.0 | Apache-2.0 | No | GPU, heavy | Yes (prompt) | Pass; heavy, stale |
| **CosyVoice 2** | **Apache-2.0** | **Apache-2.0** | No (avoid `ttsfrd`) | GPU RT, 150 ms stream | Yes | **PASS — best fit** |
| Parler-TTS | Apache-2.0 | Apache-2.0 | No | GPU RT; CPU ≪RT | No (descriptions) | Pass, no true cloning |
| Spark-TTS | Apache-2.0 | **CC-BY-NC-SA-4.0** | No | GPU RT | Yes | Fail (NC weights) |
| NeuTTS Air | Apache-2.0 | Apache-2.0 | **Yes (GPL-3.0)** | CPU/edge RT | Yes (3 s) | Fail as-shipped |
| **Pocket TTS** | MIT | CC-BY-4.0 | No | CPU ≫RT | Yes (~5 s) | **PASS** (few languages; CC-BY policy line needed) |
| Kitten TTS | Apache-2.0 | Apache-2.0 | **Yes (GPL-3.0)** | CPU ≫RT | No | Fail as-shipped |
| Supertonic | MIT | **OpenRAIL-M** | No | CPU ≫RT | No | Conditional |
| MeloTTS | MIT | MIT | No (frontends unaudited) | CPU ~RT | No | Conditional |
| OpenVoice V2 | MIT (V1 was NC) | MIT | Inherits base TTS | Base-dependent | Yes | Conditional pass (V2 only) |
| GPT-SoVITS | MIT | **Unverified** | Unclear | GPU ≫RT claims | Yes | Fail/unclear |
| F5-TTS | MIT | **CC-BY-NC-4.0** | No | GPU RT; CPU ≪RT | Yes | Fail (NC weights) |
| XTTS v2 | MPL-2.0 | **CPML (non-commercial)** | No | GPU RT; CPU ≪RT | Yes | Fail (NC weights) |
| Bark | MIT (disputed) | MIT vs CC-BY-NC (disputed) | No | Slower than RT | No (presets) | Fail |
| StyleTTS 2 | MIT | Model conditions | **Yes (GPL, per README)** | GPU RT | Yes (style) | Fail as-shipped |
| Fish Speech / OpenAudio | Apache-2.0 vs BSD-3 (disputed) | **CC-BY-NC-SA-4.0** | No | GPU RT | Yes | Fail (NC weights) |
| Higgs Audio | Apache-2.0 | **Custom community / NC** | No | GPU, heavy | Yes | Fail |
| IndexTTS 2 | Custom (bilibili MUA) | Custom (bilibili MUA) | No | GPU RT | Yes | Fail (scale-gated) |
| sherpa-ONNX | Apache-2.0 | Per-model | **Yes for Kokoro/Piper paths** | CPU ≫RT | Per-model | Runtime pass; those paths fail |


---

## 5. Deep dossier — Chatterbox (Resemble AI)

*Volmarr named this one personally. It gets the full lamp.*

### Licensing & phonemization

- **Code license: MIT** — LICENSE file, "Copyright (c) 2025 Resemble AI," unchanged since the
  initial commit (May 28, 2025). Source: github.com/resemble-ai/chatterbox/blob/master/LICENSE
- **Weights: MIT** — the English original, Multilingual V2/V3, and Turbo all sit under
  `license: mit` on their Hugging Face cards. ⚠️ There is **no separate multilingual HF repo**;
  one card (`ResembleAI/chatterbox`) hosts both English and Multilingual checkpoints under the
  single MIT declaration. ⚠️ The six *Single Language Pack* finetune repos linked from the
  README (zh-cmn, es-mx-latam, pt-br, es-es, pt-pt, hi) were **not individually license-checked**.
- **eSpeak/phonemizer: NO — for every language.** The English tokenizer is learned BPE over
  graphemes — *no phonemization at all*. The multilingual tokenizer does script transforms
  only: Chinese Cangjie via `spacy-pkuseg` (MIT), Japanese kanji→hiragana via **pykakasi**,
  Korean Hangul→Jamo in pure Python; the Hebrew (`dicta_onnx`) and Russian
  (`russian_text_stresser`) helpers are lazy imports **not in pyproject** that silently pass
  text through when absent. (Their licenses were not verified; neither installs by default.
  A downstream audit reports `russian-text-stresser` as AGPL/GPL-3 — treat that path as
  forbidden unless re-verified.)
- **⚠️ THE THORN — pykakasi is GPL-3.0 in the default tree.** `chatterbox-tts` 0.1.7's
  pyproject declares `pykakasi==2.3.0` as a **hard dependency**; pykakasi's PyPI metadata reads
  "License: GPL-3.0-or-later" (conda-forge: GPL-3.0-only). It is only *imported* for Japanese
  text, but it is *installed* unconditionally — so a stock `pip install chatterbox-tts` puts a
  GPL-3.0 distribution in the tree and **fails the S504 gate as shipped**. Unlike Kokoro's
  eSpeak — which sits in the English heart — this stone is removable: exclude/replace pykakasi
  (cost: the Japanese path, or reimplement it) and the *installed* tree is honestly clean.
- **PerTh watermark.** The watermarking package (Perth) is itself MIT, but inside Chatterbox it
  is **not optional**: `generate()` applies `PerthImplicitWatermarker` unconditionally as its
  final step — no config flag. Shipping Chatterbox means either accepting an inaudible
  provenance watermark on every generated file, or patching MIT code and maintaining the patch.
  (Patching is license-permitted; it is a maintenance decision, not a legal wall.)
- **Supply-chain flag:** `resemble-perth` is an **unpinned git dependency** (`@master`) in
  pyproject — pin it before any shipped build. `gradio==6.8.0` is also a hard runtime
  dependency (demo UI weight in the shipped tree; its full transitive tree was not audited).
- Other direct deps are clean on their face: torch/torchaudio (BSD-3), transformers/diffusers/
  safetensors (Apache-2.0), librosa (ISC), pyloudnorm (MIT), omegaconf (BSD), spacy-pkuseg (MIT),
  conformer, s3tokenizer, numpy.

### Real-time fitness

- **Family:** Original 500M (English); Multilingual V3 500M (23 languages); **Turbo 350M**
  (English; decoder distilled 10 steps → 1; native paralinguistic tags `[laugh]`, `[chuckle]`,
  `[cough]`); **Nano 110M** (English, Turbo architecture).
- **Streaming: NO native streaming API.** `generate()` returns a complete waveform. Rúnmál's
  S504 sentence/chunk streaming would be integrator-built (synthesize per sentence/clause and
  queue) — workable, and barge-in stays possible at chunk granularity, but first-audio latency
  on long first sentences is the integrator's problem, not the library's.
- **Latency/RTF:** Nano "3× faster than realtime on 8 CPU cores" is a **vendor README claim**.
  Turbo figures (~6× RT, ~75 ms) circulate in press only. ⚠️ The README's "sub-200 ms" refers to
  **Resemble's hosted service, not the open weights** — do not conflate. **No primary VRAM
  figure is published** (README claims only that Turbo uses "less"); Multilingual download ≈ 3 GB
  (secondary source).
- **Cloning:** zero-shot from a reference clip; official examples use a **10 s** clip (code
  truncates decoder conditioning to 10 s, T3 prompt to 6 s). Third-party "5 s suffices" claims
  conflict with the official example — treat 10 s as the documented norm. One reference per
  character = an excellent S512 fit in principle, incl. cross-language cloning in Multilingual V3.
- **Expression:** `exaggeration` and `cfg_weight` controls on Original/Multilingual; paralinguistic
  tags on Turbo/Nano.
- **Languages (23):** ar, da, de, el, en, es, fi, fr, he, hi, it, ja, ko, ms, nl, no, pl, pt,
  ru, sv, sw, tr, zh. (Caveats: ja is the GPL-thorned path; he/ru enhancers are no-ops in a
  default install.)
- **Maintenance:** active — latest commit Jul 21, 2026; ~26.9k stars. ⚠️ Only one GitHub release
  (v0.1.2) exists while pyproject is at 0.1.7 — take versions from PyPI.
- **Quality:** consistently rated above the Kokoro-82M baseline in secondary comparisons;
  Resemble cites blind-preference wins over ElevenLabs Turbo v2.5 / Cartesia Sonic 3
  (vendor-commissioned — treat as vendor claim).

**Chatterbox verdict: CONDITIONAL PASS.** MIT/MIT and eSpeak-free — the strongest *voice* in the
survey for character work — conditional on: (1) pykakasi excluded/replaced in the shipped tree,
(2) a watermark decision (accept PerTh or maintain a patch), (3) Perth pinned, (4) streaming
built at the integration layer, (5) S514 first-audio thresholds predeclared against the chunked
integration, not the library.

## 6. Engine dossiers (compact)

### CosyVoice 2 — Alibaba FunAudioLLM · **PASS, best overall fit**
Apache-2.0 code **and** weights (repo and card agree). No eSpeak in the open path — ⚠️ the
optional proprietary `ttsfrd` frontend must be excluded; ship the open WeTextProcessing
frontend. 0.5B LLM-TTS; **bi-directional streaming with vendor-reported 150 ms first-packet
latency** — the only engine here whose streaming is a headline feature rather than an
integration project. Zero-shot cloning from a short reference; instruct-style control of
emotion/dialect/style. Languages: zh/en/ja/ko + Chinese dialects. Top-tier quality, well above
the Kokoro baseline. Actively maintained.

### Pocket TTS — Kyutai · **PASS (one policy line needed)**
MIT code; weights **CC-BY-4.0** — permissive with attribution, *not* non-commercial; but the
gate's permissive set names CC0, not CC-BY, so under the gate *as written* the weights classify
"unknown/unreviewed" until Volmarr blesses the line. No eSpeak. 100M params; **CPU ~6× real-time
(M4-class measurement)**, ~200 ms first chunk, streaming by design; cloning from ~5 s. English at
launch, ~6–7 languages later. Quality surprisingly good for 100M — near/above its size class.
The sovereign featherweight: this is the one that could plausibly voice the Pi-class future.

### Sesame CSM-1B · **PASS (GPU serving)**
Apache-2.0 code and weights (gated HF repo). No eSpeak. 1B params, GPU-class VRAM. A
*conversational* speech model — takes dialogue context; voice identity comes from audio
prompt/context rather than short-clip enrollment, which suits per-character *consistency* if
each persona carries its own prompt state. Streaming/latency figures sparse in sources
(unverified). Very natural conversational prosody, above Kokoro for dialogue. Llama backbone —
same base-model-license caveat class as Orpheus, less prominently flagged.

### Dia — Nari Labs · **PASS, heavy, stale**
Apache-2.0 code and weights. No eSpeak. 1.6B params, ~10 GB VRAM — too heavy for a 2060 Max-Q
in fp16 comfort. Dialogue-native: `[S1]`/`[S2]` speaker tags + nonverbals (`(laughs)`,
`(sighs)`) — the most "two characters talking" model surveyed. Cloning via 5–10 s prompt.
English-only. Original repo stale since 2025 (a Dia2 was announced Nov 2025). Excellent
dialogue realism when hardware allows.

### Parler-TTS — Hugging Face · **PASS, no true cloning**
Apache-2.0 code and weights. No eSpeak. Mini ~0.6–0.9B, Large ~2.2–2.3B. Voices are
**natural-language descriptions** plus 34 named fixed speakers — per-character *descriptions*,
not voice identity. CPU 7–10× slower than real-time in one benchmark; GPU needed. English-first.
If S512's "voice profile" may be a description rather than an enrolled voice, this passes
everything; if identity matters, it doesn't.

### Orpheus-TTS — Canopy Labs · **CONDITIONAL**
Apache-2.0 code; weights card Apache-2.0 — ⚠️ built on Llama-3.2; downstream audits flag that
Llama Community License obligations may attach to the backbone-derived weights. Unresolved.
No eSpeak (LLM-token based). 3B; ~10–12 GB VRAM under vLLM — heavy for 2060-class. Streaming
yes (~200 ms claimed; ~100 ms with input streaming — vendor claims). Zero-shot cloning +
emotion tags (`<laugh>`…). Expressive, conversational; ~40× Kokoro's size for it.

### MeloTTS — MyShell · **CONDITIONAL**
MIT code and weights. No direct eSpeak dependency — ⚠️ but per-language text frontends pull
components such as pykakasi/MeCab whose licenses were **not fully audited** (the Japanese path
in particular); pykakasi is GPL-3.0 wherever it appears. VITS-based; CPU real-time claimed;
fixed speakers (en/es/fr/zh/ja/ko); no cloning. Repo stale since Dec 2024. English quality
decent, roughly Kokoro-class or below.

### OpenVoice V2 — MyShell · **CONDITIONAL PASS (V2 only)**
MIT since Apr 2024 — ⚠️ **V1 was CC-BY-NC**; ship V2 artifacts only. Not a standalone TTS: a
tone-color converter layered on a base engine (typically MeloTTS), so the shipped tree inherits
the base engine's audit. Cloning from short reference, cross-lingual tone transfer. Good
tone-color fidelity.

### Supertonic — Supertone · **CONDITIONAL**
MIT code; weights **OpenRAIL-M** (use-based restrictions — not plain permissive; the gate has
no OpenRAIL line, so it classifies unreviewed). No eSpeak (ONNX, dictionary-free per vendor).
99M params; CPU RTF ~0.012 on M4 Pro (vendor/secondary) — extremely fast; fixed voices; v3
claims 31 languages. ⚠️ Upstream archived / development ended Aug 2026 — a maintenance dead-end.
Quality ~Kokoro-class.

### Kokoro-82M — hexgrad · **FAIL as-shipped (the incumbent)**
Apache-2.0 code and weights — and the standard Python path phonemizes via misaki →
`phonemizer` + `espeakng-loader` (GPL-3.0); the JS path wraps eSpeak-NG WASM. 82M params;
~330 MB fp32 (~92 MB int8 ONNX). Fixed roster (~54 voices, 8–9 languages), **no cloning**;
speed only control. Very fast (~5× RT on 32-vCPU cloud CPU; ~96× on A10G, secondary
benchmarks). The quality-per-parameter baseline everyone else is measured against. Salvageable
in theory with a dictionary-based non-eSpeak G2P; as shipped, forbidden.

### Piper — Rhasspy → OHF-Voice · **FAIL**
Original repo MIT but **archived Oct 2025**; the successor `piper1-gpl` is **GPL-3.0** — the
name is literal. All paths phonemize via `piper-phonemize` / eSpeak-NG data (GPL-3.0).
Per-voice licenses vary (some restrictive dataset terms) — per-voice audit required regardless.
Tiny VITS voices (~15–90 MB), extremely fast even on Pi-class CPUs, 100+ locales, fixed voices,
no cloning; naturalness below the Kokoro baseline.

### Zonos — Zyphra · **FAIL as-shipped**
v0.1 code+weights Apache-2.0 (⚠️ newer ZONOS2 is MIT — version matters). **Requires a system
`espeak-ng` install for phonemization** — GPL-3.0 at runtime. 1.6B params, ~6 GB+ VRAM;
zero-shot cloning; emotion conditioning vectors; high, expressive quality above Kokoro.
GPU real-time class; CPU not real-time.

### NeuTTS Air — Neuphonic · **FAIL as-shipped**
Code/weights Apache-2.0 on the card — **but requires system eSpeak-NG + `phonemizer`**
(`PHONEMIZER_ESPEAK_*` env vars). 0.5B backbone (~360M active); GGUF edge builds; 3 s reference
cloning; on-device positioning; English. Good quality for size, ~Kokoro-class.

### Kitten TTS — KittenML · **FAIL as-shipped**
Apache-2.0 code and weights — **but requires `phonemizer` + `espeakng-loader` / system
eSpeak-NG**. 15M/40M/80M variants (smallest surveyed); fixed voices; trivially CPU real-time;
English. Quality below Kokoro-82M — the trade for the size.

### StyleTTS 2 · **FAIL as-shipped**
MIT code — but its own README states inference depends on a **GPL-licensed phonemizer package**
not included in the repo, and pretrained-model use conditions apply. ~350M-class; zero-shot
style cloning; English primary; historically excellent (Kokoro's architecture descends from
it). Maintenance slow (2023–2025-era).

### Spark-TTS — SparkAudio · **FAIL (NC weights)**
Code Apache-2.0. ⚠️ **Weights were re-licensed from Apache-2.0 to CC-BY-NC-SA-4.0** — the current
card governs: non-commercial. No eSpeak. 0.5B-class; zero-shot cloning; pitch/speed/style
control tokens; zh/en. Good quality. A warning to the whole field: licenses can move *after*
adoption — pin and archive the license text of anything shipped.

### F5-TTS · **FAIL (NC weights)**
Code MIT; weights **CC-BY-NC-4.0** (Emilia training-data terms) — the classic repo-vs-card
split. No eSpeak. 335M; zero-shot cloning (short reference + reference text); GPU RTF ~0.15
(L20/3090-class); **CPU RTF ~1.9–3.6 — not real-time**. en/zh. Excellent naturalness, above
Kokoro — and unusable here.

### XTTS v2 / Coqui TTS · **FAIL (NC weights)**
Code **MPL-2.0** (excluded from the shipped tree by policy besides). Weights under the **Coqui
Public Model License — non-commercial**. Coqui the company shut down Jan 2024; a community fork
maintains the code. ~470M-class; cloning from ~6 s; 17 languages; GPU RTF ~0.25 (DeepSpeed),
CPU ~1.41. Good cloning, ~Kokoro-class output.

### Fish Speech / OpenAudio — Fish Audio · **FAIL (NC weights)**
⚠️ Code-license disagreement: 1.4 card says BSD-3-Clause, repo presents Apache-2.0. Weights
**CC-BY-NC-SA-4.0** either way. ~1.5B-class (OpenAudio S1); cloning from ~10–15 s; multilingual;
streaming in the serving stack; high quality, above Kokoro.

### Higgs Audio — Boson AI · **FAIL (weights terms)**
Code Apache-2.0. ⚠️ Weights are **not** Apache-2.0 despite widespread blog claims: v2 uses the
custom **Boson Higgs Audio 2 Community License** (`license: other`, ~100k-user gate,
Llama-derived terms); v3 is **research and non-commercial**. ~3B-class v2; expressive,
multi-speaker, cloning; heavy VRAM; en/zh.

### IndexTTS 2 — Bilibili · **FAIL (scale-gated)**
Under the **bilibili Model Use License Agreement** — a separate license is required above
100M MAU or RMB 1B annual revenue. ⚠️ Downstream sources variously mislabel it "Apache,"
"non-commercial," or "research-only"; the primary text is a scale-gated commercial agreement.
Strong zero-shot cloning + explicit emotion control; zh/en; GPU real-time class; among the
best emotional quality surveyed — and incompatible with an unconditional Apache-2.0 ship tree.

### GPT-SoVITS · **FAIL/UNCLEAR (weights license unverified)**
Code MIT. ⚠️ **No clear weights license grant could be found** — downstream NOTICE audits flag
it; treat as unlicensed until clarified. (A Cantonese module file has AGPL-derived source
history — flagged.) No eSpeak (per-language G2P libraries; audit incomplete). Zero/few-shot
cloning + fine-tuning; zh/en/ja/ko/yue; very fast GPU RTF claims (~0.014–0.5, sources disagree
widely). Strong cloning fidelity. Unverifiable licensing is disqualifying for a shipped product.

### Bark — Suno · **FAIL**
⚠️ Sources conflict: most say code+weights MIT; some README copies state CC-BY-NC "due to the
EnCodec dependency," and EnCodec's own weights license is unstated. Unresolved. ~12 GB VRAM
full (~8 GB small); **slow — not real-time**; preset speakers, no true cloning upstream; strong
nonverbals; multilingual; unmaintained since 2023. Characterful but unreliable on long forms.

### sherpa-ONNX — delivery framework · **runtime PASS, Kokoro/Piper paths FAIL**
Own license Apache-2.0. ⚠️ But its shipped native library **statically bundles eSpeak-NG
(GPL-3.0)**, and its Kokoro/Piper model bundles **include `espeak-ng-data` (GPL-3.0)**.
A runtime's license does not launder its cargo: models through sherpa must be selected
per-model, deliberately, avoiding eSpeak-data paths.

---

## 7. The three traps (a field guide, learned the hard way)

1. **eSpeak under permissive paint.** The masthead license is Apache/MIT; the *phonemizer* is
   GPL-3.0. This killed Kokoro, and it kills Piper, Zonos, NeuTTS Air, Kitten TTS, and
   StyleTTS 2 in their standard paths. **Audit the G2P, not the banner.**
2. **Non-commercial weights behind permissive code.** The code says MIT/Apache; the *model card*
   says CC-BY-NC or a custom community license. Spark-TTS, F5-TTS, Fish Speech, XTTS, Higgs,
   IndexTTS 2. **The weights are the product; read their papers separately.**
3. **License drift and disagreement.** Spark-TTS's weights were Apache and *became*
   CC-BY-NC-SA. OpenVoice V1 was NC, V2 is MIT. Piper's MIT original died and its successor is
   GPL. Fish's card and repo disagree on the code license. **Pin the exact artifacts, archive
   their license texts, and re-audit on every version bump** — the S504 gate already does the
   last of these; the survey exists because the first two weren't done before selection.

## 8. Recommendation — for Volmarr's ruling

- **If the priority is the roadmap's letter (streaming first-audio, bilingual future, one
  engine): CosyVoice 2.** The only clean PASS with true streaming (150 ms first packet,
  vendor-reported), cloning, and Apache papers on both code and weights. Cost: front-end
  discipline (no `ttsfrd`), and its language heart is zh/en/ja/ko.
- **If the priority is the voice itself (character cloning quality, 23 languages, the engine
  Volmarr named): Chatterbox — conditional.** Budget the engineering honestly: exclude/replace
  pykakasi, decide the PerTh watermark, pin Perth, build sentence-chunk streaming at the seam,
  predeclare S514 thresholds against that integration. Turbo (350M) is the conversational
  variant; Nano (110M) is the CPU-plausible one.
- **If the priority is sovereignty per gram (CPU-only futures, Pi-class hardware): Pocket TTS** —
  pending Volmarr blessing CC-BY-4.0 weights into the gate's permissive set. It will not do
  23 languages; it will run *anywhere*.

A swap, whichever engine is chosen, means: a successor branch off `surge-c5` replacing the
Kokoro backend behind the existing `TTSBackend` seam (the seam held — this is what it was
for), a `VOICE_LICENSE_MATRIX.md` amendment recording the new path, the S504 audit re-run
against the **real installed tree** of the new path (not its README), S514 thresholds
predeclared before benchmarks, and the full suite green on purplelongship. Nothing in
Campaigns VI–VIII changes.

## 9. Could not verify

- RTX 2060-specific RTF for **every** engine — no published measurements exist.
- Chatterbox: primary-source VRAM figure (none published); Single Language Pack cards'
  individual licenses; `dicta-onnx` license; `russian-text-stresser` primary license;
  full transitive tree under gradio/librosa.
- GPT-SoVITS weights license (no clear grant found anywhere).
- MeloTTS per-language frontend licenses (Japanese path in particular).
- Bark/EnCodec weights licensing (sources conflict).
- Orpheus-TTS / CSM-1B: whether Llama-derived obligations attach to the released weights in
  practice; CSM-1B hard streaming/first-audio latency numbers.
- Chatterbox cloning minimum: official example is a 10 s clip; third-party "5 s" claims
  conflict (code truncates conditioning at 10 s / 6 s).

## 10. Sources

Primary sources were preferred throughout; `[secondary]` marks third-party corroboration.

- Chatterbox: repo, LICENSE, pyproject.toml, tokenizer.py, tts.py, README, releases —
  https://github.com/resemble-ai/chatterbox · cards —
  https://huggingface.co/ResembleAI/chatterbox · https://huggingface.co/ResembleAI/chatterbox-turbo
- Perth (MIT) — https://github.com/resemble-ai/Perth
- pykakasi licensing — https://pypi.org/project/pykakasi/ (metadata: GPL-3.0-or-later) ·
  https://anaconda.org/conda-forge/pykakasi
- spacy-pkuseg (MIT) — https://github.com/conda-forge/spacy-pkuseg-feedstock
- All other engines: the project GitHub repos and Hugging Face model cards named in each
  dossier, read 2026-10-13.
- Cross-check SBOMs/notices `[secondary]`:
  https://github.com/shahfaisalgfg/cc-gen-uitimate/blob/HEAD/THIRD_PARTY_NOTICES.md ·
  https://github.com/bahuleyandr/kural/blob/HEAD/THIRD_PARTY_LICENSES.md ·
  https://github.com/SceneWorks/SceneWorks/pull/1685 ·
  https://github.com/delebash/justvoice/blob/HEAD/docs/plans/2026-10-03-gap-7-more-languages.md

*Survey ends. The gate's law is unchanged; the choice is Volmarr's.*
