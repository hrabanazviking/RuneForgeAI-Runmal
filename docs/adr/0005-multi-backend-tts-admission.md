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

## Addendum — admission evidence (2026-10-13, Campaign V landing)

Real-tree evidence on purplelongship amended two points of this ADR
and decided both default backends:

1. **CosyVoice is ADMITTED.** Its curated tree (70 distributions)
   audits green and synthesizes the fixed corpus for real. The
   closure was proven by build + synthesis, not import alone; the
   full record is the matrix's admission-evidence block.
2. **Chatterbox is HELD at admission** (a state this ADR did not
   foresee). Dependency surgery (pykakasi/gradio pruning) proved
   insufficient: chatterbox-tts 0.1.7 hard-pins librosa and
   transformers==5.2.0, and transformers 5.x hard-imports
   `soxr` (LGPL-2.1-or-later) whenever librosa is present. Its
   install plan is disabled; the machinery refuses it. Resolution
   requires Volmarr's ruling (user-installed reclassification under
   his scope ruling of 2026-10-13, a patched fork, or removal) —
   the forge does not route around a failed gate.
3. **Correction to point 7 (frontend):** the pinned CosyVoice2
   runtime does not import WeTextProcessing. Its open frontend is
   `wetext`, whose model assets are not anonymously downloadable
   through the pinned modelscope client, so the shipped
   configuration runs with the frontend slot empty — upstream's
   own supported fallback. `ttsfrd` remains excluded, as decided.
4. **The transformers line is a license surface:** CosyVoice's set
   holds upstream's own transformers==4.51.3 pin precisely because
   the 5.x line's soxr behavior makes any librosa-carrying tree
   unshippable. Backend trees are judged with their pinned
   transformers line as part of the evidence from now on.

## Addendum — Chatterbox reclassified user-installed (2026-10-13)

Volmarr ruled at 05:45 EDT: **"Make Chatterbox user-installed —
one-button choice, gate stays pure."**

This addendum supersedes the Chatterbox portions of points 4 and 6
above and resolves the held state recorded in the admission-evidence
addendum:

1. **Chatterbox is a user-installed backend**, in the same class as
   Kitten and Piper. CosyVoice is the sole default-shipped TTS
   backend, and the S504 gate continues to guard only that default
   shipped tree.
2. **Its one-button recipe is the stock upstream tree.** The recipe
   installs `chatterbox-tts==0.1.7` with dependency resolution on:
   no pykakasi/librosa pruning and no curated `--no-deps` surgery.
   A user's own install is the user's own choice.
3. **Its audit verdict is information, never a block.** The verdict
   scopes to the installed dependency closure of the stock recipe
   and is displayed in the backends panel with the existing
   user-install notice. It honestly flags the stock tree's soxr
   (LGPL-2.1-or-later) and pykakasi (GPL-3.0) components.
4. **No binding performance thresholds remain for Chatterbox.**
   The 4.0 s first-audio / 1.0 RTF values declared while it was
   default-class were retired unmeasured when its class changed;
   later measurements are information only. CosyVoice's thresholds
   are unchanged.
5. The PerTh watermark and sentence-chunk streaming facts remain
   as recorded. Under the stock recipe, `resemble-perth` is resolved
   from upstream's declared package requirement rather than the
   retired curated recipe's forge pin.
