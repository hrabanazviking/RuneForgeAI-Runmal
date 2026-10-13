# ADR-0005 — Multi-backend TTS with per-backend license admission

Status: Accepted
Date: 2026-10-13

## Context

S504 selected a single TTS path: independent ONNX inference over
Kokoro-82M with Misaki G2P used without its eSpeak fallback. When the
Campaign V landing ran the license gate against the real installed tree
on purplelongship, the audit failed: `misaki[en]` 0.9.4 directly requires
`espeakng-loader` and `phonemizer-fork` — both forbidden eSpeak-NG
carriers (GPL-3.0) — and misaki declares `Requires-Python <3.13`, so the
declared voice extra cannot install at all in the laptop's Python 3.14
venv. The landing stopped at the gate (Forge-Log 2026-10-13, commit
`a8b06ff`).

A field survey of 25 TTS engines (`docs/TTS_ENGINE_SURVEY.md`) followed.
Its decisive findings: CosyVoice 2 is a clean pass (Apache-2.0 code and
weights, no eSpeak, streaming, cloning); Chatterbox is MIT code+weights
with zero eSpeak but drags a GPL-3.0 dependency (`pykakasi`, Japanese
path only) in a stock install; Kitten TTS and Piper require eSpeak-NG
carriers as shipped upstream.

## Decision (Volmarr, 2026-10-13)

1. **No single-TTS lock-in.** Rúnmál's TTS is multi-backend and
   user-selectable in settings: **Chatterbox, CosyVoice, Kitten, Piper**.
   The backend registry (`runmal.voice.backends`) is extensible by
   design — a future backend (including a first-party one) registers a
   spec; it does not fork the seam.
2. **Kokoro is removed from the product.** The misaki dependency chain
   leaves the tree entirely.
3. **The S504 gate becomes per-backend admission.** Each backend is an
   optional extra, audited on its own real installed tree. A *shipped*
   backend is selectable only if its tree passes the gate.
4. **Gate scope (Volmarr, 2026-10-13):** "Backends a user installs
   themselves are the user's own choice — the gate guards only what
   Rúnmál ships by default." The default shipped tree (default install +
   default backends: **CosyVoice**, and **Chatterbox with pykakasi
   excluded**) must audit green.
5. **Kitten and Piper are user-installed optional backends.** Rúnmál
   ships only its own Apache-2.0 adapter code for them. They are
   selectable in settings; installation happens only on the user's
   explicit per-backend install action, never in the default install.
   The settings/audition UI shows an honest notice for such backends:
   not shipped with Rúnmál, installed by the user, the backend's own
   license terms (including GPL-3.0 components in its tree) apply to the
   user's installation. The per-backend audit still runs for
   user-installed backends and its verdict is displayed as information;
   it does not block a user-installed backend.
6. **Chatterbox integration notes (from the survey):** dependency
   surgery so `pykakasi` is never in our tree (curated `--no-deps`
   install; Perth pinned to a fixed commit — upstream ships it as an
   unpinned git dependency); the PerTh watermark is applied
   unconditionally by upstream `generate()` and ships as upstream —
   recorded here and in the matrix, not silently patched; Chatterbox has
   no native streaming API, so sentence-chunk streaming is built at the
   Rúnmál seam.
7. **CosyVoice integration notes:** ship the open WeTextProcessing
   frontend; the optional proprietary `ttsfrd` frontend is excluded.

## Consequences

- S504's acceptance contract is re-expressed per backend: a backend
  ships when (a) its real installed tree passes the audit (default
  backends) and (b) it synthesizes the fixed corpus under predeclared
  per-backend first-audio/RTF thresholds (S514, declared before
  measurement in `docs/BENCHMARKS.md`).
- The default install's dependency surface grows (torch-class stacks for
  CosyVoice/Chatterbox). The base install is unchanged; the voice
  feature is the default extras set.
- Per-persona voice profiles (S512) reference registry backend keys;
  personas stored against the removed `kokoro-onnx` key resolve through
  the documented fallback to the default voice rather than breaking
  (compatibility-data law).
- User-installed backends move license responsibility to the user by
  explicit, informed action — the UI notice and the informational audit
  verdict are the honesty mechanism, and both are acceptance criteria,
  not decoration.

Detailed contract: `docs/VOICE_LICENSE_MATRIX.md` (admission model and
evidence), `docs/VOICE_ARCHITECTURE.md` §8–§9.
