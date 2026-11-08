# Vision Watcher Control Parity — P-129 (Part VIII, DERIVED)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_
ROADMAP_2026-10-30.md) gives Part VIII only its part-table
line — "VIII | Vision Services | P-117..P-130" — and no
per-slice entries. This slice's scope is therefore DERIVED,
never roadmap-verbatim, from in-tree sources only (see
hidden_files/P129_SCOUT.md): the P-124 set_enabled
precedent, the watcher scan's consumption of the recursive
flag on every scan, the verified absence of any handle for
that flag, and the P-122/P-124 custody-reporting standard.
P-129 is the last slice before the P-130 Part VIII gate;
it closes a proven gap rather than adding a new surface.

## The gap, proven in-tree

A watch registration carries two behaviour booleans, both
set once at registration and both consumed by every scan:
`enabled` (the scan refuses a disabled watch) and
`recursive` (the scan walks recursively or top-level
only). P-124 gave `enabled` its first handle —
WatchStore.set_enabled plus the PATCH road — precisely
because until then no road could ever change it.

For `recursive`, that sentence was still true at the
P-127 base, verified by grep: `set_recursive` appeared
nowhere in src/ or tests/, and in vision/router.py the
word recursive appeared only in the creation request and
the P-127 history filter. The PATCH road's request model
named enabled only.

The only way to change a live registration's scan depth
was therefore to delete the registration and re-register.
Deletion (WatchStore.remove_watch) destroys the
registration's ingested records — the scan's dedupe
memory — whose loss P-124 proved has behavioural teeth:
the next scan judges every unchanged file fresh and
ingests it again as a duplicate attachment. A one-flag
change cost the owner a full duplicate re-ingestion of
the folder. The battery pins that harm directly
(delete + re-register re-ingests an unchanged file under
a new attachment id) beside the fix (the toggle preserves
the memory and the rescan skips as already_ingested).

The second half shares the same roads: the watch DELETE
road answered `{"deleted": watch.id}` — the id string in
the deleted slot, no id field, and no count of the
ingested records the removal destroyed. Both sibling
delete roads answer the P-122/P-124 shape
(`{"deleted": bool, "id", ...}` plus custody counts —
descriptions_purged and watch_records_forgotten on
attachment delete), under the P-122 honesty line that a
custody deletion is "reported as a count in the response,
never silently". The dedupe-memory loss on watch
deletion is exactly the loss that makes re-registration
expensive, and it was invisible in the response. No
battery pinned the old body (P-121 asserts only status
200 on this road), so bringing it into the part's shape
breaks no pinned contract.

## What lands

Store (src/runmal/vision/watcher.py, additive):

- `WatchStore.set_recursive(watch_id, recursive)` —
  mirrors set_enabled line for line: the named watch's
  flag is replaced, every other field and ALL ingested
  records are preserved, an unknown watch returns None
  and writes nothing.

HTTP (src/runmal/vision/router.py, additive):

- The PATCH road's request model
  (WatchEnabledRequest) now carries both behaviour
  flags as optional: `enabled` and `recursive`. Every
  previously valid body keeps its exact effect
  ({enabled} alone); {recursive} alone and {both} are
  the additive widening. An empty body still answers
  422 — the status P-124's battery pinned for {} — now
  as an explicit plain refusal ("nothing to update:
  name enabled and/or recursive"). Owner-scoped 404s
  are unchanged and change nothing.
- The DELETE road counts the registration's ingested
  records (list_ingested) BEFORE remove_watch and
  answers the sibling shape: `{"deleted": true, "id":
  watch_id, "ingested_records_removed": n}`. What
  deletion destroys is unchanged; what changes is that
  the loss is reported.

Package docstring (vision/__init__.py) and the watcher /
router module docstrings carry the reconciliation.

## Honesty lines (P-075)

- The toggle is non-destructive, and that is its entire
  claim: flipping recursive preserves the dedupe memory,
  so a rescan skips unchanged files as already_ingested
  instead of duplicating them. Nothing here describes,
  captions, moderates, or scans any image.
- Deletion reporting is truthful and scoped: the count
  is the ingested records actually removed; the
  attachments a scan ingested are NOT the watch's and
  are not touched — rows, bytes, and descriptions
  derived from them survive under P-120/P-122 custody
  (pinned end to end). Re-registering the same folder
  for the same chat afterwards is allowed, and its
  first scan re-ingests — the reported loss was real.
- PATCH names behaviour flags only. It cannot retarget
  the registration's path or chat — those are identity
  fields, not behaviour flags, and delete + re-register
  remains their road (now with its cost reported).
- Capabilities.vision stays False; no provider is
  labelled semantic anywhere in this slice.

## Battery

tests/test_p129_watcher_control_parity.py (12 tests) —
store truth (set_recursive round-trip + preservation,
unknown = None + byte-untouched file), scan depth
following the flag at the service level with dedupe
surviving both flips, the delete + re-register
duplication harm pinned as behaviour, the HTTP roads
(PATCH each flag alone and both together, {} 422,
unknown/foreign 404s with no writes, scan depth
following the PATCH end to end with the real attacher),
the DELETE road (truthful count, registration and
records gone, attachments + derived description alive,
zero-count shape, unknown/foreign 404s, honest
re-registration), and the migration head pin (0041).
Migration: NONE — both flags already live in the v1
watcher document; nothing new is persisted.

## Named open after P-129

A real local semantic caption provider (needs a vision
model + an image-input wire), OCR (needs a real engine),
screen capture, and camera flow — all unchanged, all
still without an honest in-tree basis. Watcher
scan-report persistence, vision settings, and
portable-archive inclusion of the vision stores remain
declined on the record in the scout, named open for
their own lines. Describe-on-scan (P-128, team-01) banks
ahead of this slice and is not duplicated here. The
Part VIII runway ends here: P-130, the Part VIII gate,
is next.
