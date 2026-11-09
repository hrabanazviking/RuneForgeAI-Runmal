# P-195 - Hub Duplicate-Content Census (Part XII, The Hub - Sovereign Shape)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part XII only its part-table line -
"XII | The Hub, Sovereign Shape | P-187 - P-202" - and
no verbatim P-195 entry exists anywhere in it. This
slice's scope is therefore DERIVED, not roadmap-verbatim,
from Runmal's own in-tree record only (survey:
hidden_files/P195_SCOUT.md; design:
hidden_files/P195_DESIGN.md):

- Every pack layer's own import road treats the verified
  content checksum as a pack's identity: lorebooks
  (P-045), presets (P-063) and scenarios (P-141) each
  detect an exact duplicate on import by comparing
  content checksums, owner-scoped. The hub, the index
  above those layers, has no such view: an owner can
  register the same pack twice (two copies of one file,
  two locators, two titles - P-187's refusal law covers
  only the identical (owner, kind, locator) triple) and
  no banked document ever says so. P-189 compares each
  entry's CLAIM against its own verified checksum, a
  per-entry verdict - two entries carrying the same
  verified content are invisible to it. P-193 carries
  every parsed row's verified checksum verbatim but its
  axes are content VOLUME; it never groups by that
  checksum. P-194 aggregates one query's unified answer,
  not identity.
- This slice takes that cell, in the P-194 shape (a
  census built over one composed banked document,
  embedded whole, counts summed from its own rows): a
  pure aggregate over P-193's content-census document,
  grouping its rows by verified_content_sha256.
- Weighed and declined WITH REASONS in the scout: a
  reconciliation battery / part gate (premature
  mid-part - the workspace line took its reconciliation
  at P-185, the SECOND-LAST slice of Part XI, ahead of
  its gate; Part XII ends at P-202 and P-196..P-201
  remain to land surfaces such a battery must cover -
  it stays named open beside the gate), a census over
  P-191's content search alone (too thin, the standing
  P-181/P-183/P-184 decline - P-194 carries that ground
  with the matched_by axis added), a search over
  inspection / manifest fields (the envelope is the
  pack's identity papers, excluded from content search
  by P-191's law, and the four kinds' name fields share
  no closed cross-kind law - the names stay readable
  per entry on P-188's browse road), a verdict filter
  over browse / checksum states (P-189 already returns
  every row with those fields verbatim - a filter adds
  a road, not a fact), hub lifecycle depth (P-187's
  remove-then-register law stands), signing /
  attestation (no key machinery is banked),
  friend-instance exchange (no banked pack transport
  exists), and the VX-59 ruled-out forms (central
  store, catalogue, creator profiles).

Base: 90089a8100dd26d7360b80c2bd32b01d367e5688 (P-193
banking record; banked P-001..P-193, PART XII OPEN).
P-194 (team-02, hub unified-search census) banks ahead
of this slice and is NOT in this base; the only file
both slices touch is src/runmal/hub/router.py (one
additive import + one additive road each), reconciled
by the keeper at banking. Migration: NONE - head stays
0041, no 0042, battery-pinned.

## The honesty law (stated up front)

1. ONE composition: P-193's content census is composed
   once, verbatim, and embedded whole as
   `content_census`. Every count in this document is
   summed from THAT document's own rows - no second
   parse, walk or counting law exists here.
2. Identity is verified only: a row's identity is its
   verified_content_sha256 from the composed document,
   and only a NON-EMPTY verified checksum is an
   identity. A row whose verified checksum is empty -
   a bare preset bundle, whose road verifies none, or
   any entry that was not parsed - is UNIDENTIFIED and
   is never grouped: two byte-identical bare bundles
   are NOT declared duplicates, because no identity
   was verified for either.
3. The partition is exact: every entry is exactly one
   of duplicate (verified checksum shared by two or
   more entries), unique (verified checksum its alone)
   or unidentified (no verified checksum), and the
   three counts always sum to the estate count.
4. The claim plays no part: grouping is by the
   verified checksum alone, regardless of kind or of
   the caller's claimed checksum - a wrong claim can
   neither create nor break a group, and being counted
   here never upgrades a claim. Each group's members
   carry their own kinds, so a cross-kind group is
   stated, never hidden.
5. Partiality is P-193's own verdict, carried
   verbatim: parsed_count and coverage_complete ride
   exactly as composed. An estate with unparsed
   entries is censused as partial, never dressed as
   complete.

## What landed

- `src/runmal/hub/duplicate_census.py` (new) - the
  truth layer, two functions in the P-194 shape:
  * `build_duplicate_census(content_census_document)` -
    the pure aggregator: groups the composed
    document's rows by verified_content_sha256
    (groups in first-appearance store order, members
    in store order, each member carrying id, title,
    kind and the row's string counts), sums the
    partition (duplicate / unique / unidentified),
    the distinct verified-content count, the
    redundant-copy count (duplicate entries minus
    duplicate groups), the by-kind axis under
    P-187's closed HUB_KINDS ({entries,
    duplicate_entries} per kind, zero-filled) and
    the largest duplicate group (first in group
    order on a tie; null when no group exists);
    parsed_count and coverage_complete carried
    verbatim from the composed document.
  * `duplicate_census_document(entries)` - composes
    P-193's `content_census_document` VERBATIM over
    the same entry list and returns the aggregator's
    document.
  * The closed `DUPLICATE_CENSUS_STATES` law:
    `no_entries`, `no_duplicates`, `some_duplicates`,
    `all_duplicates` (every entry in the estate a
    member of a duplicate group - by the partition
    law, no unique and no unidentified entry exists),
    judged on the duplicate axis only. Eight standing
    honesty notes ride every document.
- `src/runmal/hub/router.py` - ONE new road:
  GET /hub/duplicate-census, bearer-gated and
  owner-scoped exactly like the content-census road;
  every census state is DATA at 200.
- `tests/test_p195_hub_duplicate_census.py` (new,
  fresh-authored, P-005 discipline) - 19 tests.
- `docs/CLEAN_ROOM_LOG_2026-10-30.md` - +1 entry.

## Honest limitations

1. Identity is the verified CONTENT checksum, exactly
   as the pack layers define it: two registrations of
   one pack exported at different times can carry
   different provenance and still share one content
   checksum - they ARE the same content, and this
   census says so; it does not compare pack files
   byte-for-byte and invents no file identity.
2. A bare preset bundle verifies no checksum on any
   banked road, so bare bundles are always
   unidentified here even when byte-identical. That
   is the honest answer under the banked laws, stated
   on every document, not a gap dressed over.
3. The census pays P-193's full cost (every ready
   pack read and verified under the 16 MiB bound) and
   is a point-in-time judgement: the estate can change
   between this census and any later consumer. The
   registry list (P-187) stays the cheap road.

## Carried forward, named open

- P-194 (team-02) banks in parallel ahead of this
  slice; the keeper reconciles the additive router
  delta (one import + one road each).
- A hub reconciliation battery and the Part XII gate
  stay named open beside the part's end (P-202): the
  workspace line took its reconciliation second-to-
  last (P-185) ahead of its gate (P-186), and this
  part's remaining slices (P-196..P-201) are surfaces
  such a battery must cover.
- A unified-search history surface stays named open:
  it presupposes a recording write and a store that
  no banked slice has taken - it is not a pure-read
  composition.
- A binding label update stays named open
  (bindings.py's own law is unbind-then-bind, never a
  silent in-place update).
- Automatic retention / bulk clear of history awaits
  Volmarr's ruling.
- Signing / attestation and friend-instance exchange
  stay declined (no key or transport machinery is
  banked); the VX-59 ruled-out forms (central store,
  catalogue, creator profiles) stay declined by
  ruling.
