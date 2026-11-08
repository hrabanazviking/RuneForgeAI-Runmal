# P-127 - Watcher History & Search (Part VIII, Vision Services)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part VIII only its part-table line -
"VIII | Vision Services | P-117 - P-130" - and no per-slice
entries. This slice scope is therefore DERIVED, not
roadmap-verbatim, from in-tree sources only: the P-122
history/search discipline, the P-125 parity surface, and
the P-121/P-124 watcher store and roads. The keeper
reviews this derived scope at banking.

Base: f29b712 (P-125 banking record). Migration: NONE -
head stays 0041; the provisional 0042 was eyed only if a
storage need proved unavoidable, and none did: both new
surfaces ride the existing v1 watcher JSON document,
whose format does not change. This slice banks AFTER
P-126 (describe-on-attach opt-in, team-02), which the
keeper reconciles; P-126 is not duplicated here - this
slice touches neither the attach road nor
attachments.py.

## The weighing (candidates from the scout)

- **Watcher owner-wide history/search - taken.** A proven
  parity gap, verified against the tree: P-122 gave vision
  DESCRIPTIONS an owner-wide history with literal search
  (GET /vision/history, VisionStore.search) and P-125 gave
  ATTACHMENTS the same surface (GET
  /vision/attachments/history), while the WATCHER store -
  the third vision store - could be listed only per-chat
  (registrations) and per-watch (ingested records), and
  WatchStore had no search verb at all. An owner who
  registered watches across many chats could not find one
  again without opening every chat, nor find which watch
  ingested a given file without walking every watch.
- **Watcher scan-history persistence - declined (again).**
  The scan REPORT is a synchronous operation result with
  no in-tree consumer and no retention law (P-123 scout;
  re-weighed at P-124, P-125, P-126 - unchanged). This
  slice adds read surfaces over the ingested RECORDS a
  scan already persists as custody data; it persists no
  report and nothing new.
- **Vision settings via the P-098 pattern - declined
  (again).** Driven by a P-081 manifest vision does not
  declare; no declared schema exists in-tree and no
  behaviour waits on stored settings - describe takes
  its provider per request.
- **Portable-archive inclusion of vision stores -
  declined for Part VIII.** The portable archive is a
  SQL-row bundle with manifest-validated member shapes;
  the vision stores are versioned JSON documents + byte
  files that live and die with the data dir by P-120/
  P-121 design. Folding them in is a portable-subsystem
  slice (new member types, validator shapes, restore
  semantics), not a vision slice. Named open for the
  portable line.
- **Semantic caption provider - declined, honestly.**
  The P-119 proof stands: no backend declares
  Capabilities.vision, no vision model or image-input
  wire exists in-tree.
- **OCR - declined, honestly.** No OCR engine exists
  in-tree.
- **Capture / camera - declined.** No capture surface
  or client exists in this server-side tree.
- **Watcher daemon - declined.** The P-121 stance
  stands: a scan is a deliberate operation; no daemon
  machinery exists.
- **Describe-batch - declined.** A loop over the single
  describe with no census behaviour naming it (P-122).
- **Fork/copy carrying vision rows - declined.** Vision
  rows are bound to the chat that produced them;
  P-120's copied-message law is the precedent.

## What landed

Truth layer (src/runmal/vision/watcher.py, WatchStore -
additive methods, the v1 document format unchanged):

- search(owner_id, query, *, chat_id, enabled, recursive,
  limit, offset) -> (page, total): owner scoping FIRST
  (foreign registrations are never matched, counted, or
  returned); LITERAL case-insensitive substring matching
  over the folder path ONLY - the one text identifier a
  registration honestly holds; exact filters; limit
  clamped 1..200, offset floored at 0; total is the full
  match count before paging.
- list_ingested_for_owner(owner_id): every ingested
  record whose watch belongs to the owner, in store
  append order. Ingested records carry no owner field;
  ownership is resolved through the registrations and
  none is invented.
- search_ingested(owner_id, query, *, watch_id, chat_id,
  limit, offset) -> (page, total): owner scoping FIRST
  via watch ownership; LITERAL case-insensitive substring
  matching over the source_path and the sha256 ONLY (the
  P-125 field discipline); exact watch / chat filters -
  a filter naming a foreign watch or chat matches
  nothing at this layer.

HTTP (vision/router.py, additive, bearer-gated,
owner-scoped):

- GET /vision/watch-folders/history?q=&chat_id=&
  enabled=&recursive=&limit=&offset= - declared BEFORE
  the {watch_id} roads so the literal segment is not
  captured as an id (the P-125 precedent); a chat_id
  filter must name an owned chat (404 otherwise, the
  P-122 history precedent). The per-chat list road is
  unchanged.
- GET /vision/watch-folders/ingested/history?q=&
  watch_id=&chat_id=&limit=&offset= - declared before
  the {watch_id} roads likewise; a watch_id filter must
  name an owned watch and a chat_id filter an owned
  chat (404 otherwise).

Battery: tests/test_p127_watcher_history_search.py
(18 tests) - store search truth (owner-first, literal
scope pins for both surfaces, exact filters, paging and
clamps), the ingested owner join, reads-write-nothing,
the HTTP roads (cross-chat listing, query / filters /
paging, 404 filter shapes, owner isolation, end-to-end
scan-to-history), the route-order pins (both history
roads live AND the single-watch + per-watch ingested
roads stay live), the per-chat list unchanged, and the
migration head pin (0041).

## Honesty lines (P-075)

- Search is literal substring matching over text the
  records already hold. It ranks nothing, embeds
  nothing, reads no image bytes, and never claims
  semantic recall. Filters are exact filters, never
  search text (pinned by battery on both surfaces).
- No watch registration, ingested record, or index
  field is created, altered, or re-derived by this
  slice; no scan report is persisted; custody is
  untouched (P-121/P-124 already own it).

## Named open after P-127

A real local semantic caption provider (needs a vision
model + an image-input wire), OCR (needs a real engine),
screen capture, and camera flow - all unchanged, all
still without an honest in-tree basis. Watcher
scan-report persistence, vision settings, and
portable-archive inclusion of the vision stores remain
declined on the record above, named open for their own
lines. The Part VIII runway continues: P-128, P-129,
then the P-130 gate.
