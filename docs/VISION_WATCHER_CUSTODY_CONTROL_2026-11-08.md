# P-124 — Watcher Custody & Control Completion (Part VIII, Vision Services)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_
ROADMAP_2026-10-30.md) gives Part VIII only its part-table
line — "VIII | Vision Services | P-117 – P-130" — and no
per-slice entries. This slice's scope is therefore DERIVED,
not roadmap-verbatim, from in-tree sources only: the P-121
watcher store and roads, the P-120/P-122 attachment custody
roads, the P-113/P-122 custody-completion precedent, and
P-075's no-content law. The keeper reviews this derived
scope at banking.

Base: e0bac3f (P-122 banking record). Migration: NONE —
head stays 0041; the provisional 0042 was eyed only if a
storage need proved unavoidable, and none did: both new
verbs ride the existing watcher JSON store.

## The weighing

Part VIII's remaining runway is P-124..P-129 plus the
P-130 gate. The scout weighed consolidation against new
surfaces and found two proven defects sharing one store,
which outrank both:

- **The dedupe tombstone (custody hole).** P-121's ingested
  records are the scan's dedupe memory, removed only when
  a watch or its chat dies. Deleting an attachment — over
  its own road, or through its message's deletion — left
  the record behind, so the source file skipped as
  already-ingested on every later scan and could never be
  re-ingested while the watch lived. Derived descriptions
  got exactly this fix in P-122; the watcher's records
  were the same hole one store over.
- **The unreachable flag (control hole).** WatchFolder.
  enabled has been refused-by-scan since P-121, yet no
  service verb and no HTTP road could ever change it —
  registration always creates enabled watches, and the
  only disabled watch in the tree was hand-built inside
  the P-121 battery. Half a control with no handle, and
  no single-watch read road to inspect one registration
  without listing its whole chat.

Declined, with reasons: a semantic caption provider (no
backend declares Capabilities.vision, no image wire, no
local model — the P-119 proof, unchanged); OCR (no engine
in-tree); capture/camera (no client surface); a watcher
daemon (no machinery in-tree, the P-121 bound); non-PNG
thumbnail decoding (the P-123 bound); describe-batch
(declined at P-122: a loop over the single describe with
no census behaviour naming it); watcher scan-history
persistence (declined at P-123: the scan report is a
synchronous result; no consumer, no retention law);
vision settings (no declared schema; describe takes its
provider per request); describe-on-attach (reverses
P-120's stated invariant; its own slice if ever);
portable-archive inclusion of the vision stores (the
P-120/P-121 stance — the stores live and die with the
data dir — is a portable-subsystem contract, not a
vision slice); fork/copy carrying vision rows (vision
rows are bound to the chat that produced them; P-120's
copied-message law is the precedent — a fork starts with
no vision rows, stated plainly). Attachment owner-wide
history/search — the P-122 parity gap for the attachment
store — is real and is the named P-125 candidate; it is
not bundled here (one store per slice, the P-122 shape).

## What landed

Truth layer (src/runmal/vision/watcher.py, additive):

- `WatchStore.forget_attachment(attachment_id) -> int` —
  removes every ingested record naming the attachment,
  across all watches, and returns the count. An empty id
  names no attachment and forgets nothing; a no-match
  forget leaves the store file byte-untouched (the P-118
  purge law). Forgetting claims nothing about the source
  file: it still sits in its folder, and the next scan
  judges it fresh.
- `WatchStore.set_enabled(watch_id, enabled)` — replaces
  the registration's enabled flag, preserving every other
  field and all ingested records; None for an unknown
  watch, with no write.

Custody wiring:

- `DELETE /vision/attachments/{id}` (vision/router.py)
  now also forgets the attachment's ingested records;
  the response gains the additive field
  `watch_records_forgotten` (the P-122
  `descriptions_purged` precedent; existing fields
  unchanged).
- `delete_message` (chats/service.py), inside its
  existing guarded P-120/P-122 block, forgets each purged
  attachment's ingested records from the WatchStore on
  the same data dir. A watcher failure never breaks
  message deletion.

Control roads (vision/router.py, additive, bearer-gated,
owner-scoped — unknown OR foreign = 404):

- `GET /vision/watch-folders/{watch_id}` — one
  registration, completing the watch road set.
- `PATCH /vision/watch-folders/{watch_id}` {enabled} —
  the flag's first handle; the P-121 refusal of a
  disabled watch's scan is reachable end to end for the
  first time.

Battery: tests/test_p124_watcher_custody_control.py
(13 tests) — the store verbs, the scan consequence
(skip-forever without forget, re-ingest after it), the
HTTP roads and their 404/422 shapes, and both custody
paths end to end.

## Honesty lines (P-075)

- Forgetting a record deletes bookkeeping only: no file
  is touched, no attachment is recreated, and no scan
  result is promised — a later scan re-judges the actual
  bytes under the usual named-skip law.
- The toggle changes a flag, nothing else: no daemon
  starts or stops (none exists), and a disabled watch's
  registrations and records all survive until deletion.
- Nothing in this slice describes, captions, reads, or
  moderates any image.

## Named open after P-124

A real local semantic caption provider (needs a vision
model + an image-input wire), OCR (needs a real engine),
screen capture, camera flow, a live watcher daemon
(needs machinery), and attachment owner-wide history/
search (the named P-125 candidate) — all unchanged, all
still without an honest in-tree basis beyond what their
own lines state. P-123 (attachment thumbnails, team-02)
banks before this slice; the banking overlap is the
additive router appends only.
