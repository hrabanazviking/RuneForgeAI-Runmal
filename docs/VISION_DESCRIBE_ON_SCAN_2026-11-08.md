# P-128 - Describe-on-Scan Opt-In (Part VIII, Vision Services)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_
ROADMAP_2026-10-30.md) gives Part VIII only its part-table
line - "VIII | Vision Services | P-117 - P-130" - and no
per-slice entries. This slice scope is therefore DERIVED,
not roadmap-verbatim, from in-tree sources only: P-126's
named-open describe opt-in on the watcher scan road,
P-121's scan no-description bound and attacher seam,
P-126's attach_and_describe atomic pair, P-119 provider
selection, and P-122 custody. The keeper reviews this
derived scope at banking.

Base: 0be09f6 (P-126 banking record). Migration: NONE -
head stays 0041; no new store, no format change -
descriptions ride the existing P-117 store, ingestions
the existing v1 watcher document. Held behind P-127
(watcher history & search, team-03), which banks first;
the expected banking overlap is vision/router.py +
vision/__init__.py additive changes only - this slice
touches neither attachments.py, service.py, selection.py,
nor the P-127 surfaces.

## The reconciliation (P-126's shape, one road over)

P-121's bound as written: scanning generates NO
description. P-126 amended only the HTTP attach road's
form of that invariant and deliberately kept the scan's
bound "exactly". This slice amends the scan road's form,
and only that form:

- scan_watch (the service) is UNCHANGED and still
  generates no description; every service caller keeps
  the old bound exactly. attach_image is unchanged.
- A NEW composition, scan_and_describe, runs the same
  scan with a describing attacher; the HTTP scan road
  calls it only when the request explicitly opts in
  (default off). A plain scan - service or HTTP -
  behaves exactly as P-121 shipped, and its report dict
  stays byte-identical: the "described" key appears only
  on an opt-in scan.

## What landed

Service (src/runmal/vision/watcher.py, additive):

- ScanReport gains described: list[str] (description
  ids, in ingestion order) and describe_requested:
  bool = False. to_dict includes the "described" key
  ONLY when describe_requested is true.
- _default_describing_attacher(data_dir, vision_store,
  *, provider, question) lazily resolves
  attachments.attach_and_describe (the _default_attacher
  idiom; a plain WatchError names the absence when the
  attachments module is missing). The returned callable
  matches the attacher shape, calls attach_and_describe,
  and appends each description id to a shared list it
  exposes as .described.
- scan_and_describe(store, watch, *, vision_store,
  provider=None, question="", attacher=None, now=None)
  -> ScanReport: with no injected attacher it builds the
  describing attacher over store.data_dir; with an
  injected attacher (the test seam) it wraps it - attach
  for the record, then describe_image the same bytes as
  source_kind attachment / source_ref the record's id
  (the exact call the describe road makes); a describe
  failure on the injected path propagates and scan_watch
  names it a refused skip. Atomicity on the production
  path is P-126's own: attach_and_describe rolls the
  just-created attachment back on any describe failure
  and re-raises, so the scan records a named
  "refused: ..." skip and NO ingested record - the file
  is judged fresh by the next scan. provider=None rides
  describe_image's plain unavailable refusal per file
  (every file a named skip, nothing ingested): this
  function never invents a provider - selection is the
  caller's act.

HTTP surface (src/runmal/vision/router.py, additive,
bearer-gated, owner-scoped as every vision road):

- ScanRequest (new, all optional): describe: bool =
  False, describe_question: str = "",
  describe_provider: str | None = None,
  require_semantic: bool = False (the P-126 attach-road
  names for the same fields).
- POST /vision/watch-folders/{watch_id}/scan gains
  body: ScanRequest | None = None - body-less calls
  (every existing client) keep working unchanged. With
  describe off/absent: the P-121 road exactly. With
  describe=True: provider selection runs BEFORE the
  scan (an unknown provider or require_semantic is a
  422 and NOTHING is scanned or ingested - the P-126
  selection-first law), then scan_and_describe with the
  router's VisionStore, the selected provider and the
  question; WatchError / VisionError ride 422 with their
  plain text. The response is the scan report dict,
  which now carries "described".

Package doc (vision/__init__.py): the watcher custody
bullet is followed by the P-128 clause - describe-on-
scan is an explicit opt-in on the scan road only, atomic
per file via P-126, and the scan itself still describes
nothing on its own.

Battery: tests/test_p128_describe_on_scan.py.

## Honesty lines (P-075)

- No opt-in, no description: pinned at the service level
  (scan_watch with a vision store present still stores
  no description row and creates no description file)
  and at the HTTP level (plain and describe=False scans
  return the P-121 report shape with NO "described" key;
  history total stays 0).
- Per-file atomicity: a failing provider makes each
  affected file a named refused skip with NO attachment,
  NO byte file, NO description and NO ingested record;
  a later plain scan ingests the same file fresh.
- Dedupe honesty: already-ingested files are skipped as
  already_ingested and are NOT re-described (the opt-in
  describes what the scan ingests, nothing else); a
  second opt-in scan describes nothing new.
- No fake caption: the opt-in rides the SAME providers
  as the describe road (metadata / deterministic_test);
  require_semantic refuses plainly before any scan and
  ingests nothing; Capabilities.vision stays False.
- Custody is inherited, not new: scan-describe records
  are ordinary attachment-sourced descriptions, so
  deleting the attachment purges them (P-122) and
  forgets the ingested record (P-124), pinned
  end-to-end.
- One question per scan: describe_question applies to
  every file the scan ingests; stated plainly, not
  per-file authored.

## Named open after P-128

A real local semantic caption provider (needs a vision
model + an image-input wire), OCR (needs a real engine),
screen capture, camera flow, watcher scan-history
persistence, vision settings (needs a declared schema),
describe-batch, and non-PNG thumbnails - all still
without an honest in-tree basis beyond what is recorded
here. Only P-129 remains before the P-130 Part VIII
gate.
