# P-123 — Attachment Thumbnails for Vision Surfaces (Part VIII)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part VIII only its part-table line —
"VIII | Vision Services | P-117 – P-130" — and no per-slice
entries. This slice's scope is therefore DERIVED, not
roadmap-verbatim, from in-tree sources only: the P-023
thumbnail engine in assets/imaging, the P-120 attachment
store and roads, and P-075's no-content law. The keeper
reviews this derived scope at banking.

Base: 3726782 (P-121 banking record). Migration: NONE —
head stays 0041; the provisional 0042 was eyed only if
storage proved unavoidable and is NOT taken (thumbnails
are derived on read; nothing is stored).

## The gap the scout proved

Character assets (P-023) have thumbnails; the images a
vision surface actually lists — P-120 chat attachments —
did not. The only byte road was .../content at full size
(up to the 16 MiB house cap), so any gallery or grid
consumer had to download every full image to render a
list. The engine to close the gap already existed and was
proven (assets/imaging.make_png_thumbnail, pure-stdlib
PNG decode / box-downscale / re-encode); what was missing
was the attachment road riding it.

## Thumbnail honesty — the bound, stated plainly

The engine is PNG-ONLY. It decodes one PNG subset (bit
depth 8, colour types 0/2/3/4/6, non-interlaced) and
returns None outside it. This slice claims exactly that
and no more:

- a JPEG, GIF or WebP attachment gets a plain 422 naming
  the PNG-only bound — the full bytes are NEVER served in
  a thumbnail's place, and no format is re-labelled;
- a PNG outside the decodable subset gets a plain 422
  naming that bound;
- thumbnail availability is a REQUEST-TIME fact: the
  attachment record gains no thumbnail field or claim,
  because an exotic PNG can still be undecodable;
- a thumbnail is a real derived image (decoded pixels,
  box-averaged downscale, re-encoded RGBA PNG) — never
  the source bytes with a thumbnail label.

## What landed

Service (src/runmal/vision/attachments.py, additive):

- `thumbnail_bytes(store, record, max_dim=256)` — derives
  the thumbnail of an attachment's stored bytes through
  make_png_thumbnail and stores NOTHING (no byte file, no
  index change), so P-120 custody (delete / purge_chat /
  purge_message) remains the whole custody story.
  max_dim is bounded 1..1024 (THUMBNAIL_MAX_DIM_LIMIT;
  the default is the P-023 engine's 256). Refusals are
  plain AttachmentErrors naming each bound: max_dim out
  of range, non-PNG format, byte file missing, PNG
  outside the decodable subset. The record's SNIFFED
  format is the gate truth; bytes are never re-guessed.

HTTP (vision/router.py, additive, bearer-gated,
owner-scoped — unknown OR foreign attachment = 404):

- `GET /vision/attachments/{attachment_id}/thumbnail`
  with optional `?max_dim=` → 200 image/png of the
  derived bytes; the byte-file-missing refusal rides
  404, every other refusal rides 422 with its plain text.

Battery: tests/test_p123_attachment_thumbnails.py
(14 tests) — service downscale truth, custom/boundary
max_dim, every refusal class, derivation-stores-nothing
(data-dir listing + index bytes identical), the record's
no-claim pin, the HTTP road (200 shape, 404 unknown and
foreign, 422 non-PNG / bad max_dim / undecodable), and
the migration head pin (0041).

## Declined, with reasons

- **Watcher scan-history persistence**: the P-121 scan
  report is a synchronous operation result delivered to
  its caller by design; no in-tree consumer needs it
  persisted, and persisting it invents an unbounded audit
  collection with no retention law in-tree. Named open.
- **Vision settings via the P-098 pattern**: P-098's
  renderer is driven by a P-081 plugin manifest's declared
  schema; vision is a core subsystem that declares no
  manifest and no settings schema, and describe already
  takes its provider per request — no behaviour waits on
  stored settings. Named open if a declared schema lands.
- **Describe-on-attach opt-in**: reverses P-120's stated
  invariant (attaching generates NO description) and
  couples attach failure modes to provider selection; it
  deserves its own slice and doc reconciliation. Named open.
- **A real semantic caption provider**: no backend
  declares Capabilities.vision, no image wire, no local
  model (P-119 proof, unchanged). Named open.
- **OCR**: no engine in-tree. **Capture / camera**: no
  client surface. **A watcher daemon**: no machinery
  in-tree (P-121 bound). All named open.
- **Thumbnails for non-PNG formats**: needs an in-tree
  decoder for those formats; the engine is PNG-only and
  this slice does not invent one. Named open.

## Honest limitations

- PNG attachments outside the engine's decodable subset
  (interlaced, exotic bit depths) cannot be thumbnailed
  today and refuse plainly; widening the decoder is its
  own slice if ever commissioned.
- Derivation is per-request CPU work with no cache: the
  honest trade for storing nothing. A busy gallery road
  re-derives; a cache would be a storage/custody slice.
- P-122 (description history/search + custody completion,
  team-01) banks before this slice; this slice touches
  neither vision/service.py nor the P-122 roads, so the
  banking overlap is the additive router/__init__ appends
  only.
