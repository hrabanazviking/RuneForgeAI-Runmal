# P-126 - Describe-on-Attach Opt-In (Part VIII, Vision Services)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_
ROADMAP_2026-10-30.md) gives Part VIII only its part-table
line - "VIII | Vision Services | P-117 - P-130" - and no
per-slice entries. This slice scope is therefore DERIVED,
not roadmap-verbatim, from in-tree sources only: the P-120
attach road and its stated no-description invariant, the
P-119 provider selection layer, the P-117 describe service,
and the P-123 slice's explicit deferral of this candidate
to its own reconciliation slice. The keeper reviews this
derived scope at banking.

Base: f2bb0c2 (P-123 banking record). Migration: NONE -
head stays 0041; the provisional 0042 was eyed only if a
storage shape proved unavoidable, and none changes: both
records ride the existing v1 JSON stores. Held behind
P-124 (watcher custody & control, team-03) and P-125
(attachment history & search, team-01), both banking
ahead; this slice touches neither vision/service.py nor
the watcher/history surfaces.

## The weighing (candidates from the scout)

- **Semantic caption provider - declined, honestly.** The
  P-119 proof stands, re-verified this scout: no backend
  declares Capabilities.vision, no image-input wire, no
  local vision model in-tree. Nothing here changes that,
  and no record in this slice claims a caption.
- **OCR - declined, honestly.** No OCR engine in-tree.
- **Capture / camera - declined.** No capture surface or
  client exists in this server-side tree.
- **Watcher scan-history persistence - declined again.**
  Declined on the merits by the P-123, P-124 and P-125
  scouts (a synchronous operation result with no in-tree
  consumer and no retention law); no new evidence at this
  base. Named open.
- **Vision settings via the P-098 pattern - declined
  again.** P-098 is driven by a P-081 manifest vision does
  not declare; vision has no settings schema in-tree, and
  describe already takes its provider per request - no
  behaviour waits on stored settings. Named open if a
  declared schema ever lands.
- **Describe-batch, portable-archive inclusion, fork/copy
  carrying vision rows - declined**, for the reasons the
  P-122/P-124 scouts recorded; unchanged here.
- **Describe-on-attach opt-in - taken.** The one candidate
  prior slices deferred FOR this reason: P-123's scout
  called it "a real follow-on shape" that "deserves its
  own slice and doc reconciliation" rather than a
  ride-along. This is that slice. Every load-bearing piece
  already exists: attach (P-120), selection with plain
  refusals (P-119), describe persisting source_kind
  "attachment" records (P-117), and the derived-description
  custody that makes such records die with their source
  (P-122).

## The reconciliation

P-120's invariant as written: attaching generates NO
description; describing is a separate explicit call. This
slice amends the HTTP road's form of that invariant, and
only that form:

- attach_image (the service) is UNCHANGED and still
  generates no description. Every service caller - above
  all the P-121 watcher scan, whose own docstring bounds
  scans to generate no description - keeps the old
  invariant exactly.
- The HTTP attach road gains an explicit per-request
  opt-in, default off. A plain attach behaves exactly as
  P-120 shipped: same response shape, no description key,
  nothing described.
- The opt-in is all-or-nothing. Provider selection runs
  BEFORE anything is stored, so a selection refusal (an
  unknown provider, or require_semantic with no semantic
  provider in-tree) stores nothing at all. A describe
  failure after the attach removes the just-created
  attachment (row + byte file) before the refusal rides
  out; describe_image stores nothing on its own failures
  (P-117 law), so no half-state survives.

## What landed

Service (src/runmal/vision/attachments.py, additive):

- attach_and_describe(store, vision_store, *, chat_id,
  owner_id, data, message_id, filename, question,
  provider, now) -> (attachment, description): attach via
  attach_image, then describe the same bytes through
  describe_image with source_kind "attachment" and
  source_ref the new attachment's id - the exact call the
  describe road makes, so the record is indistinguishable
  from a two-call flow's. On any describe exception the
  attachment is removed and the error re-raised.
  provider=None rides the plain unavailable refusal (and
  rolls back): the service never invents a provider.

HTTP surface (src/runmal/vision/router.py, additive,
bearer-gated, owner-scoped as every vision road):

- AttachRequest gains describe (bool, default False),
  describe_question, describe_provider, require_semantic
  (the DescribeRequest names, prefixed where the attach
  road needs the distinction).
- POST /vision/attachments with describe=True: selection
  first (422, nothing stored, on a selection refusal),
  then the atomic pair; attach and describe failures each
  ride 422 with their plain text. Success is 201 with the
  P-120 attachment dict PLUS an additive "description"
  key holding the description record. With describe off
  (or absent) the response is the P-120 dict alone.

Package doc (vision/__init__.py): the attachments bullet
gains the P-126 clause.

Battery: tests/test_p126_describe_on_attach.py (14 tests).

## Honesty lines (P-075)

- No opt-in, no description - pinned at the service level
  (attach_image stores no description row and creates no
  description file) and at the HTTP level (no description
  key, history total 0, last-description road 404).
- No fake caption: the opt-in rides the SAME providers as
  the describe road (metadata / deterministic_test);
  require_semantic refuses plainly today and stores
  nothing; Capabilities.vision stays False; no provider
  is labelled semantic anywhere in this slice.
- Custody is inherited, not new: the opt-in description
  is an ordinary attachment-sourced record, so deleting
  the attachment purges it (pinned end-to-end:
  descriptions_purged == 1), and message/chat deletion
  keeps its P-122 behaviour.
- Rollback leaves no attachment row, no byte file, and
  no description row; the emptied attachments index file
  itself may remain, exactly as after any P-120 remove.

## Named open after P-126

A real local semantic caption provider (needs a vision
model + an image-input wire), OCR (needs a real engine),
screen capture, camera flow, watcher scan-history
persistence, vision settings (needs a declared schema),
describe-batch, non-PNG thumbnails, and a describe opt-in
on the watcher scan road (P-121's no-description bound for
scans stands untouched) - all still without an honest
in-tree basis beyond what is recorded here.
