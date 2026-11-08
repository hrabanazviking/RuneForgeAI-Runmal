# P-125 - Attachment History & Search (Part VIII, Vision Services)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part VIII only its part-table line -
"VIII | Vision Services | P-117 - P-130" - and no per-slice
entries. This slice scope is therefore DERIVED, not
roadmap-verbatim, from in-tree sources only: the P-124
scout's standing candidate, the P-122 history/search
discipline, and the P-120 attachment store and roads. The
keeper reviews this derived scope at banking.

Base: f2bb0c2 (P-123 banking record). Migration: NONE -
head stays 0041; the provisional 0042 was eyed only if a
SQL surface proved unavoidable, and the P-120 JSON index
proves it is not. This slice banks AFTER P-124 (watcher
custody & control, complete on team-03), which the keeper
reconciles; P-124 is not duplicated here.

## The weighing (candidates from the scout)

- **Attachment owner-wide history/search - taken.** A
  proven parity gap, verified against the tree: P-122 gave
  vision DESCRIPTIONS an owner-wide history with literal
  search (GET /vision/history, VisionStore.search), while
  P-120 ATTACHMENTS - the images themselves - could still
  be listed only per-chat (GET /vision/attachments requires
  chat_id; the store had no list_for_owner and no search).
  An owner who attached images across many chats could not
  find one again without opening every chat.
- **Semantic caption provider - declined, honestly.** The
  P-119 proof stands: no backend declares
  Capabilities.vision, no vision model or image-input wire
  exists in-tree.
- **OCR - declined, honestly.** No OCR engine exists
  in-tree.
- **Capture / camera - declined.** No capture surface or
  client exists in this server-side tree.
- **Watcher daemon - declined.** The P-121 stance stands:
  a scan is a deliberate operation; no daemon machinery
  exists.
- **Non-PNG thumbnail decoding - declined.** The P-123
  bound stands: the in-tree P-023 engine decodes PNG only.
- **Watcher custody & control - not this slice.** It is
  P-124, complete on team-03 and banking ahead of this
  slice; not duplicated.
- **Watcher scan-history persistence - declined (again).**
  A synchronous operation result with no in-tree consumer
  and no retention law (P-123 scout); unchanged.
- **Vision settings via the P-098 pattern - declined
  (again).** Driven by a P-081 manifest vision does not
  declare; no behaviour waits on stored settings.
- **Describe-on-attach opt-in - declined.** It reverses
  P-120's stated invariant (attaching invents no
  description) and deserves its own reconciliation slice.
- **Search over descriptions-of-attachments from the
  attachment surface - declined.** That text lives in the
  P-122 description store and is already searchable at
  GET /vision/history with source_kind=attachment; a
  second road over the same text duplicates P-122.
- **Bulk export / download-all - declined.** No census
  behaviour names it; invented convenience.

## What landed

Truth layer (src/runmal/vision/attachments.py,
AttachmentStore - additive methods, the v1 index format
unchanged, KNOWN_FORMATS naming the sniffed vocabulary):

- list_for_owner(owner_id) in append order.
- search(owner_id, query, *, chat_id, message_id,
  image_format, limit, offset) -> (page, total): owner
  scoping FIRST (foreign rows are never matched, counted,
  or returned); LITERAL case-insensitive substring matching
  over the filename and the image sha256 ONLY - the two
  text identifiers the record honestly holds; exact
  filters; an unknown image_format is a plain
  AttachmentError; limit clamped 1..200, offset floored
  at 0; total is the full match count before paging.

HTTP surface (src/runmal/vision/router.py, /api/v1/vision,
bearer-gated; unknown OR foreign = 404, existence never
leaks - not even through counts):

- GET /vision/attachments/history?q=&chat_id=&message_id=
  &image_format=&limit=&offset= -> {attachments, total,
  returned, limit, offset, q, chat_id, message_id,
  image_format}. A chat_id filter must name an owned chat
  (404 otherwise, the P-122 history precedent); an unknown
  image_format is 422 via the store refusal. The road is
  declared BEFORE GET /vision/attachments/{attachment_id}
  so the literal segment "history" is not captured as an
  attachment id (the scout's route-shape hazard; the
  battery pins both roads live). The per-chat list road is
  unchanged.

Battery: tests/test_p125_attachment_history_search.py
(17 tests).

## Honesty lines (P-075)

- Search is literal substring matching over the filename
  and the digest - text the record already holds. It ranks
  nothing, embeds nothing, reads no image bytes, and never
  claims semantic recall. The format is an exact filter,
  never search text (pinned by battery).
- No attachment record, byte file, or index field is
  created, altered, or re-derived by this slice; no
  description is created; custody is untouched (P-120 and
  P-122 already own it).

## Named open after P-125

A real local semantic caption provider (needs a vision
model + an image-input wire), OCR (needs a real engine),
screen capture, and camera flow - all unchanged, all still
without an honest in-tree basis. Watcher custody & control
is P-124, banking ahead of this slice.
