# P-130 - Part VIII Gate (2026-11-08)

*The Part VIII gate. The filed roadmap gives Part VIII only
its part line - "VIII | Vision Services | P-117 - P-130" -
and no per-slice entries; every Part VIII slice scope is
DERIVED, as each slice doc states plainly. This gate
therefore judges Part VIII against the census its own
banked slice docs declare: the describe roads and the
provider seam, provider selection + capability truth, the
last description reaching the prompt, chat image
attachments, the folder watcher, description history /
search / custody, attachment thumbnails, watcher custody &
control, attachment history & search, the describe-on-
attach and describe-on-scan opt-ins, watcher history &
search, and watcher control parity. Judged only from Part
VIII's banked records, the battery module, and the tester's
logs filed with this slice; no mirror source consulted
(clean-room).*

## Gate verdict

**Part VIII is COMPLETE and the gate PASSES with named
carried items and two findings.** This record claims only
what the battery proves.

Verdict per area: Census PASS, Together PASS, Custody
PASS, Accounting PASS.

Verdict per row:

| Row | Slice | Verdict |
|---|---|---|
| Vision foundation + OpenAPI fix | P-117 | PASS |
| Last description template variable | P-118 | PASS |
| Provider selection + capability truth | P-119 | PASS |
| Chat image attachments | P-120 | PASS |
| Folder watcher | P-121 | PASS |
| Description history, search & custody | P-122 | PASS |
| Attachment thumbnails | P-123 | PASS |
| Watcher custody & control | P-124 | PASS |
| Attachment history & search | P-125 | PASS |
| Describe-on-attach opt-in | P-126 | PASS |
| Watcher history & search | P-127 | PASS |
| Describe-on-scan opt-in | P-128 | PASS |
| Watcher control parity | P-129 | PASS |
| Part VIII gate | P-130 | this gate |

## S1 The gate checklist

| Gate requirement (task census) | Evidence | State |
|---|---|---|
| Provider selection + capability truth | battery A + B + D | DONE HERE |
| Describe roads + history/search/custody | battery B + C | DONE HERE |
| Prompt template variable agrees with the store | battery B | DONE HERE |
| Attachments truth layer + thumbnails + history/search | battery A + B + D | DONE HERE |
| Describe-on-attach opt-in, atomic | battery B + D | DONE HERE |
| Folder watcher end to end | battery B + C | DONE HERE |
| Describe-on-scan opt-in, no re-describe | battery B + D | DONE HERE |
| Watcher control parity (P-129) | battery A + C | DONE HERE |
| Custody purges on chat/message deletion | battery C | DONE HERE |
| Honesty bounds pinned, not loosened | battery D | DONE HERE |
| Measured counts at the gate | S6 of this record, from the tester's logs | DONE HERE |

Part VIII spans P-117..P-130, fourteen slices continuous:
P-117 through P-130, no gaps. Per-slice coverage map:
P-117->A/B/C/D, P-118->A/B, P-119->A/B/D, P-120->A/B/C,
P-121->A/B/C/D, P-122->B/C/D, P-123->A/B/D, P-124->B/C,
P-125->A/B/D, P-126->A/B/C/D, P-127->A/B/D, P-128->B/C/D,
P-129->A/C, P-130->this gate.
No roadmap text was edited.

## S2 "Passes" means, per verdict area

- **Census PASS.** Every P-117..P-129 vision module,
  service function, store method and HTTP road the slice
  docs declare is present: the description service + store,
  the selection catalogue, the attachment store +
  thumbnails + describe-on-attach pair, the watcher store
  + scan + describe-on-scan composition - and the vision
  __init__ module map names them. The P-118 template
  variable last_vision_description stands in the prompt
  registry, and app OpenAPI generation succeeds and names
  the vision roads (the P-116 gate's F2, fixed by P-117,
  re-proved here).
- **Together PASS.** One vision world walks the whole
  part: both provider roads describe into one store whose
  list, last-per-chat, history search and prompt variable
  all state the same last description; a plain attach
  describes nothing, its thumbnail derives on read storing
  nothing, and attachment history finds it by filename and
  by sha256; the describe-on-attach opt-in lands the pair
  atomically (a failing provider rolls the attachment
  back, a semantic refusal stores nothing at all); the
  watcher registers, scans, dedupes an unchanged file,
  ingests a changed file anew, and a plain scan describes
  nothing; the describe-on-scan opt-in lands attachment +
  description pairs and never re-describes an
  already-ingested file; flipping recursive through
  set_recursive changes scan depth while the dedupe
  memory survives the flip.
- **Custody PASS.** The control and custody seams agree
  across slices: the PATCH road moves enabled and/or
  recursive and refuses an empty body 422; a disabled
  watch refuses to scan; the DELETE watch road reports
  {"deleted": true, "id", "ingested_records_removed": n}
  and leaves the ingested attachments under P-120
  custody; deleting an attachment purges its derived
  descriptions AND forgets its watcher records, so the
  same source file ingests anew on the next scan instead
  of skipping forever; chat deletion purges descriptions,
  attachments and watch registrations together while a
  keeper chat's rows all survive; message deletion purges
  the message's attachment, its derived description and
  its watcher record as one chain; single-record remove
  and purge_source are exact to the named source.
- **Accounting PASS.** Every carried item named in S4 is
  pinned by a battery measurement at this gate, at full
  strength: Capabilities.vision is False for every chat
  backend (read live from the adapters' own declarations),
  no catalogue provider is semantic and
  semantic_caption_available is False, a semantic
  requirement never falls back to a non-semantic road,
  no-provider and unknown-provider refusals are plain and
  store nothing, thumbnails are PNG-only and a derivation
  stores nothing, every search in the three stores is
  literal substring over that store's honest text fields
  and owner-scoped first, and the scan report persists
  nothing - no scan-history file, no daemon surface.
  Nothing was loosened to make an area pass.

## S3 The gate world

The battery's world is ZqxGate130, fresh-authored for this
gate (P-005 discipline, no real user files): PNG/JPEG byte
fixtures built in the battery, one owner, chats and a
watched inbox folder created per test under a temp data
dir. Every Part VIII surface is then read against that one
world, so agreement between surfaces is the proof, not any
single surface's word.

## S4 Carried items - named and deliberate

The gate passes with these items carried, not hidden. Each
is exact in the battery module or the banked slices' own
records; this section names them so no later part mistakes
them for clean ground.

- **K1 - A real local semantic caption provider stays
  open.** No backend declares Capabilities.vision, no
  image-input wire and no local vision model exist
  in-tree (P-119 proof, re-measured in battery D). The
  metadata and deterministic_test roads are labelled
  non-semantic everywhere they appear; a semantic
  requirement is refused plainly, never served by
  fallback. Commissioned road: a future provider slice
  that lands a real model + wire behind the P-117 seam
  and only then declares vision truth.
- **K2 - OCR stays open.** No OCR engine exists in-tree;
  no surface claims to read text out of an image.
  Commissioned road: an OCR slice behind a real engine,
  if ever commissioned.
- **K3 - Capture / camera stays open.** No capture
  surface or client exists in this server-side tree.
  Commissioned road: a client-side capture slice, if
  ever commissioned.
- **K4 - A watcher daemon stays open, deliberately.**
  A scan is a deliberate operation (P-121 bound): the
  battery pins that no daemon or background surface
  exists on the watcher module or store. Commissioned
  road: a daemon slice with its own machinery and
  custody story, if ever commissioned.
- **K5 - Non-PNG thumbnails stay open.** The P-023
  engine decodes PNG only; a JPEG attachment's thumbnail
  request is refused plainly naming the bound, and the
  full bytes are never substituted (battery D).
  Commissioned road: a decoder slice for other formats,
  if ever commissioned.
- **K6 - Watcher scan-report persistence stays open.**
  The scan report is a synchronous result; the battery
  pins that a scan leaves no scan or report file behind
  (P-127's stance, declined on the merits by five prior
  scouts: no in-tree consumer, no retention law).
  Commissioned road: a persistence slice only if a
  consumer and a retention law land first.
- **K7 - Vision settings stay open.** Vision declares no
  settings schema and no P-081 manifest; describe takes
  its provider per request and no behaviour waits on
  stored settings (the P-098 pattern does not apply).
  Commissioned road: a settings slice only if a declared
  schema ever lands.
- **K8 - Portable-archive inclusion of the vision stores
  stays open.** The description, attachment and watcher
  stores do not ride the portable archive; that is a
  portable-subsystem contract, not a vision slice
  (declined on the record by the P-126/P-127 scouts).
  Commissioned road: the portable line, if it ever takes
  the vision stores into its footprint.

Also declined on the slices' own records and carried
here without separate rows: describe-batch (a loop over
the single describe with no census behaviour naming it)
and fork-carry of vision rows (the P-120 precedent).

## S5 Findings for the keeper

- **F1 - No new engine defect was found by this gate.**
  Every Part VIII surface produced exactly its promised
  result in the battery. The gate's only correction
  during construction was its own probe error (the
  attachment record's dict nests its image truth under
  an "image" key; the battery first read it flat,
  failed, and was corrected to the banked contract -
  recorded in the slice evidence). Nothing was left
  unfixed in this slice's own files, and no banked code
  was patched by this gate. Commissioned road: none
  required.
- **F2 - The P-116 gate's F2 is verified CLOSED.**
  app.openapi() raised on the Part VII tree; P-117
  fixed it as Part VIII's opener, and this gate's
  battery re-proves OpenAPI generation succeeding and
  naming the vision roads on the merged Part VIII tree
  (battery Area A). Commissioned road: none - closed by
  P-117, regression-pinned by this gate.

## S6 Evidence at the gate

Measured counts, from the tester's logs filed with this
slice (hidden_files/p130_battery.log,
hidden_files/p130_neighbours.log and
hidden_files/p130_fullsuite.log):

- Gate battery: 26 passed, 0 skipped, 0 failed - the one
  P-130 behaviour module: tests/test_p130_part_viii_gate.py
  (26 tests). 4 + 8 + 6 + 6 + 2 = 26 behaviour tests
  (Area A 4, Area B 8, Area C 6, Area D 6, hygiene 2).
- Gate-record module: tests/test_p130_gate_record.py
  (10 tests) - R = 10.
- Neighbours batch as run by the tester: 210 passed,
  1 skipped, 0 failed - the full P-117..P-129 vision
  fence on this gate's base, exactly the P-129 banking
  expectation.
- Full suite: 4597 passed, 5 skipped, 0 failed in
  252.33s on this gate's base (the run collected the
  gate battery; the gate-record module landed while it
  ran and reads 10 passed standalone, so the committed
  tree's suite is 4607 passed, 5 skipped, 0 failed by
  arithmetic - 4571 + 26 + 10 = 4607, exact against the
  P-129 banking confirmation, the battery and R).
- Baseline: the P-129 banking confirmation read 4571
  passed, 5 skipped, 0 failed on the forge tree (forge
  log), with the combined P-117..P-129 vision fence at
  210 passed, 1 skipped, 0 failed.

Migration note: none. This gate adds no migration; the
migration head remains 0041 and no migration was added by
this slice. This slice is committed on yrsa/runmal-team-03
for the keeper to bank in roadmap order.
