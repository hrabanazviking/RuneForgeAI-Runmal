# P-119 — Vision Provider Selection + Capability Truth (Part VIII)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part VIII only its part-table line —
"VIII | Vision Services | P-117 – P-130" — and no per-slice
entries. This slice's scope is therefore DERIVED, not
roadmap-verbatim, from in-tree sources only: P-117's
named-open items (1) semantic caption providers and
(2) Capabilities.vision truth in provider selection, the
P-053 capability-truth discipline, the P-086/P-087 labelled
deterministic-provider pattern, and P-075's no-content law.
The keeper reviews this derived scope at banking.

Base: 6e523e3 (P-117 banking record). Migration: NONE —
head stays 0041.

## Why this shape — the scout's negative

A real semantic caption provider cannot be built honestly
in this tree today: no local vision model, endpoint, or
image payload wire exists anywhere in the adapters (scout:
grep for llava/moondream/caption models across src/ finds
nothing; the Ollama adapter speaks text-only /api/chat), and
every backend's declared Capabilities.vision is False.
Inventing a wire and calling it a captioner would fake the
very capability P-053 exists to keep truthful. What CAN be
built — and what every later semantic slice needs first —
is the selection + truth half. That is this slice.

## What landed

New module `src/runmal/vision/selection.py`:

- **The catalogue as data** — `provider_catalogue()` lists
  every provider that exists (metadata, deterministic_test),
  each with provider_id / model / road, `semantic` and
  `available` flags, and a plain note. Neither provider is
  semantic; `semantic_caption_available()` is False.
- **A deterministic test provider** —
  `DeterministicTestVisionProvider` (provider_id
  `runmal.vision.deterministic-test`, model
  `byte-fingerprint-1`, road `deterministic_test`). Its
  description is a deterministic function of the actual
  bytes (sniffed format/dimensions + size + sha256 in a
  fixed template): same bytes, same text. The text names
  itself a test description and states that no semantic
  caption was produced. It refuses non-images like the
  metadata provider. It is the P-086/P-087 house pattern —
  a real, exercised road a future captioner drops into,
  never a fake captioner in disguise.
- **Backend vision truth** — `backend_vision_truth()` reads
  each chat backend's declared `Capabilities.vision` live
  from its default model via the P-053 road
  (`backends.capabilities.default_model`, imported, never
  copied; lazy import). All five rows are False today,
  source "declared". A backend that one day declares vision
  changes this surface with no edit here.
- **Selection** — `select_provider(requested, *,
  semantic_required=False)`: default is the metadata
  provider (P-117 behaviour preserved); a road name or
  provider_id selects that provider; an unknown name is a
  `VisionProviderError` naming the known roads; a semantic
  requirement raises `VisionUnavailableError` — selection
  never falls back silently to a non-semantic provider.

HTTP (vision/router.py, additive): `POST /vision/describe`
gains optional `provider` and `require_semantic` fields
(refusals ride the existing VisionError → 422 mapping), and
`GET /vision/providers` returns the catalogue, the backend
truth rows, and `semantic_caption_available` — the
inspectable truth surface for the subsystem.

- Battery: tests/test_p119_vision_provider_selection.py
  (16 tests).

## Declined, with reasons

- **A real semantic caption call**: no model/wire exists
  in-tree to call (above). Named open below.
- **Item (4) image attachments on chat messages**: needs
  chat schema/message-shape work (likely a migration); it
  does not complete P-117's seam and is weaker than
  (1)+(2) together. Remains named-open.
- **Declaring Capabilities.vision=True anywhere**: no
  adapter can describe an image today; the flag stays
  False until one honestly can.

## Honest limitations

- Still NO semantic caption anywhere in Rúnmál. The
  selection layer makes that gap explicit, queryable data
  instead of an absence nobody can see — closing it needs
  a real local provider (model + wire) as its own slice.
- The deterministic test provider's text is a fingerprint,
  not a description of content; it shares the metadata
  provider's sniff-only knowledge and says so in its own
  output.
- P-118 (template-variable wiring + chat-deletion custody)
  is a sibling slice in flight; this slice does not touch
  the prompt composer or the store's custody surface, and
  its router edit is additive so the two reconcile cleanly.
