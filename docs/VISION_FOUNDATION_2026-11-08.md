# P-117 — Vision Foundation + the OpenAPI Fix (Part VIII, Vision Services — opener)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part VIII only its part-table line —
"VIII | Vision Services | P-117 – P-130" — and no per-slice
entries. This slice's scope is therefore DERIVED, not
roadmap-verbatim, from in-tree sources only: the roadmap part
line, the Voxta census (VX-50 vision on request; VX-43 the
last vision description as a template variable), the P-101
opener pattern, the voice JSON-store house pattern, P-053's
provider-truth discipline, P-075's no-content law, and the
sniff truth in assets/imaging.py. The keeper reviews this
derived scope at banking.

Base: 3886cd22 (P-115 banking record). Migration: NONE —
head stays 0041.

## 1. The commissioned fix (P-116 gate finding F2) — FIXED

`app.openapi()` raised `AssertionError: A response class is
needed to generate OpenAPI`, app-wide. Reproduced at slice
start. Root cause: app.py registered the two bare HTML pages
with an explicit `response_class=None` —

    app.get("/memories", response_class=None)(memories_browser_page)
    app.get("/voice", response_class=None)(voice_page)

FastAPI's default response class is a `Default(JSONResponse)`
sentinel; passing None explicitly replaces it with None, and
OpenAPI generation asserts a response class exists. The gate
named the voice page; the memories page carried the
identical defect (same idiom, adjacent lines). Both handlers
already return `HTMLResponse`, and every other HTML route in
the tree declares `response_class=HTMLResponse`. Fix, in
app.py only: import `HTMLResponse` from fastapi.responses and
declare it on both registrations. Small, in-footprint,
pinned by the battery (openapi.json 200 with both paths and
their 200 responses; both pages still serve HTML 200).

## 2. What landed — the vision foundation

New package `src/runmal/vision/`:

- `service.py` — `VisionDescription`, a first-class record
  bound to a chat: source (`asset` id or `inline`), the
  question asked, the description text, provider truth as
  data (provider_id / model / road, P-053), image truth
  (format, dimensions, byte size, sha256 — always sniffed /
  hashed from the actual bytes), and the creation stamp.
  The provider seam is any object with provider_id / model /
  road and `describe(image_bytes, question) -> str`.
  `MetadataVisionProvider` (road `metadata`) is the one real
  provider shipped: its description is built ONLY from
  sniffed truth and says plainly that no semantic caption
  was produced; bytes that do not sniff as an image are
  refused. `describe_image` with no provider raises
  `VisionUnavailableError` — nothing is fabricated and
  nothing is stored (P-075). Persistence is the house JSON
  pattern: `vision_descriptions.json` in the data dir,
  versioned, tolerant load (corrupt reads as empty).
  `last_for_chat` is the VX-50 last-description read
  surface, as data.
- `router.py` — owner-scoped HTTP on /api/v1/vision:
  `POST /vision/describe` (a character asset's bytes — the
  asset must belong to the chat's character — or inline
  base64; bad base64 and non-image bytes are 422, unknown
  or foreign chats 404), `GET /vision/descriptions?chat_id=`,
  `GET /vision/last?chat_id=` (404 when none).
- `__init__.py` — the subsystem map.
- `src/runmal/app.py` — the F2 fix above plus the vision
  router wired under /api/v1 with the local-auth dependency,
  like every sibling.
- Battery: tests/test_p117_vision_foundation.py (15 tests).

## 3. Honest limitations

- The metadata road is NOT a caption: it reports what the
  bytes ARE, never what a picture shows. Semantic caption
  providers (local first, per the house pattern) are later
  Part VIII slices; `Capabilities.vision` still has no
  backend declaring it — the seam here is the vision
  subsystem's own, and wiring backend capability truth into
  provider selection is named open.
- The last description is retrievable as data; the prompt
  composer does not yet consume it as the VX-43/VX-50
  template variable. Named open for a later Part VIII slice.
- No screen capture, folder watcher, camera flow, OCR, or
  image attachments on chat messages in this slice.
- Descriptions are never deleted by chat housekeeping in
  this slice (the store is append/list/last only); custody
  on chat deletion is named open, as voice custody was
  before its own slice.
