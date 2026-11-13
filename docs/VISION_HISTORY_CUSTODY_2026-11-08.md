# P-122 - Vision Description History, Search & Custody Completion (Part VIII, Vision Services)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part VIII only its part-table line -
"VIII | Vision Services | P-117 - P-130" - and no per-slice
entries. This slice scope is therefore DERIVED, not
roadmap-verbatim, from in-tree sources only: the P-117 store
and road shape, the P-118 custody idiom, the P-119 provider
truth, the P-120 attachment roads, the P-113 custody-coverage
precedent, and the literal-search precedent in chats/search.
The keeper reviews this derived scope at banking.

Base: 5692069 (P-120 banking record). Migration: NONE - head
stays 0041; the provisional 0042 was eyed only if a SQL
surface proved unavoidable, and the P-117 JSON store proves
it is not.

## The weighing (candidates from the scout)

After P-120 banked and with P-121 (folder watcher, team-03)
in flight as the named follow-on, the scout weighed the
remaining Part VIII candidates against the tree:

- **Semantic caption provider - declined, honestly.** The
  P-119 proof stands: no backend declares
  Capabilities.vision, no vision model or image-input wire
  exists in-tree. Nothing here changes that, and no record
  in this slice claims a caption.
- **OCR - declined, honestly.** No OCR engine exists in-tree.
- **Capture / camera - declined.** No capture surface or
  client exists in this server-side tree.
- **Folder watcher - not this slice.** It is P-121, in flight
  on team-03 and banking ahead of this slice; not duplicated.
- **Attachment describe-batch / gallery wiring - declined.**
  Batch describe is a loop over the existing single describe
  with no census behaviour naming it, and there is no gallery
  UI surface in this tree to wire vision into. Invented
  convenience, no grounding.
- **Provider health / truth surfacing - declined.** P-119
  already surfaces the whole provider truth at
  GET /vision/providers. Both shipped providers are local
  pure functions of the bytes; neither has a health signal
  to check, and a health road would re-label P-119 data
  while implying a live dependency that does not exist.
- **Description history/search + custody completion -
  taken.** Two proven gaps share one store: (1) descriptions
  could be listed per chat or read last, but never found
  again across chats - no get-by-id, no owner-wide history,
  no search, no filters; (2) custody had a hole - the store
  had no single-record delete at all, and deleting an
  attachment (P-120) left every description derived from it
  behind, still able to surface as the chat last vision
  description after its source bytes were deleted.

## What landed

Truth layer (src/runmal/vision/service.py, VisionStore -
additive methods, the v1 document format unchanged):

- get(id) and list_for_owner(owner_id) in append order.
- search(owner_id, query, *, chat_id, source_kind,
  provider_road, limit, offset) -> (page, total): owner
  scoping FIRST (foreign rows are never matched, counted,
  or returned); LITERAL case-insensitive substring matching
  over the description text and the question only; exact
  filters; an unknown source_kind is a plain VisionError;
  limit clamped 1..200, offset floored at 0; total is the
  full match count before paging.
- remove(id): single-record custody delete.
- purge_source(source_kind, source_ref) -> count: removes
  every row derived from one source; an empty source_ref
  names no source and purges nothing.

HTTP surface (src/runmal/vision/router.py, /api/v1/vision,
bearer-gated; unknown OR foreign = 404, existence never
leaks - not even through counts):

- GET /vision/history?q=&chat_id=&source_kind=&provider_road=
  &limit=&offset= -> {descriptions, total, returned, limit,
  offset, q, chat_id, source_kind, provider_road}. A chat_id
  filter must name an owned chat (404 otherwise); an unknown
  provider_road is 422 naming the known roads (validated
  against the P-119 catalogue); an unknown source_kind is
  422 via the store refusal.
- GET /vision/descriptions/{description_id} - one record.
- DELETE /vision/descriptions/{description_id} ->
  {deleted, id}. The per-chat last read and the
  {{last_vision_description}} variable follow automatically:
  same store file, read as data by prompt/vision_link.
- DELETE /vision/attachments/{id} gains source custody: the
  response gains descriptions_purged (additive; the existing
  deleted/id fields are unchanged).

Message custody (src/runmal/chats/service.py, inside the
existing guarded P-120 block in delete_message): the message
attachment ids are collected before purge_message, and each
one purges its derived descriptions via purge_source. Chat
deletion needed no new wiring - P-118 already purges all of
the chat description rows. A vision-store failure never
breaks message deletion (the house guarded idiom).

Battery: tests/test_p122_vision_history_custody.py (17 tests).

## Honesty lines (P-075)

- Search is literal substring matching over text the store
  already holds. It ranks nothing, embeds nothing, and never
  claims semantic recall.
- No description text is created, altered, or re-derived by
  this slice; no caption, OCR, or safety claim appears.
- Deleting a description deletes exactly that record;
  deleting an attachment now deletes its derived descriptions
  too, reported as a count in the response, never silently.

## Named open after P-122

A real local semantic caption provider (needs a vision model
+ an image-input wire), OCR (needs a real engine), screen
capture, and camera flow - all unchanged, all still without
an honest in-tree basis. The folder watcher is P-121,
banking ahead of this slice.
