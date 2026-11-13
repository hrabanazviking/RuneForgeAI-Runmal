# P-199 - Hub Distinct-Content Census (Part XII, The Hub - Sovereign Shape)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part XII only its part-table line -
XII | The Hub, Sovereign Shape | P-187 - P-202 - and no
verbatim P-199 entry exists anywhere in it. This slice
scope is therefore DERIVED, not roadmap-verbatim, from
Runmal's own in-tree record only (survey:
hidden_files/P199_SCOUT.md; design:
hidden_files/P199_DESIGN.md):

- Every banked identity or volume fact about verified
  payload text sits at one of two grains. P-195 groups
  entries by verified content checksum - identity at
  WHOLE-PACK grain, exact only - so two versions of one
  pack differing in a single entry read there as simply
  unique, and their overlap is nowhere stated. P-193
  counts string-value OCCURRENCES and their characters,
  so a value occurring forty times and forty values
  occurring once read identically there. No banked
  document states how many DISTINCT string values an
  estate holds, how many repeat inside one pack or
  across packs, or how many are shared between entries
  - and none of it is derivable from any banked
  document, because no banked document carries values.
- This slice takes that cell in the P-193/P-196 shape:
  a query-free estate aggregate composing the banked
  verified parse roads directly (as P-193, P-196 and
  P-197 do), under P-193's imported OUTCOMES law and
  P-188's imported bound, comparing the verified
  payloads' string values for exact identity - in
  memory only, by digest, with counts only ever
  entering the document.
- Weighed and declined WITH REASONS in the scout:
  string-length distribution (a new statistic over
  P-193's already-measured quantity - a refinement,
  and the house killed that shape as a recount at
  P-196 scout D), emptiness census (the same
  refinement smaller), key-name frequency (P-196's
  law states key names are never returned, and in
  lorebook-shaped payloads keys can be operator
  data), numeric aggregates (they would return
  payload values as data, breaking the no-content
  law), locator-sharing census (derivable from
  P-187's list, which carries every locator whole;
  shadows P-195 at an unverified layer),
  registration-age census (derivable from the list's
  created_at values, and needs a moving now),
  claim-coverage decomposition (a recount of P-189),
  metadata completeness (derivable from P-187's
  list), a synthesis census over the banked census
  documents (measures nothing - every axis is already
  a fetchable banked document), a census over P-190
  or P-191 alone (standing decline - P-194 carries
  that ground larger), envelope / manifest census
  (no closed cross-kind law banked), reconciliation
  battery / part gate (premature - the workspace line
  took reconciliation at its second-last slice,
  P-185 of Part XI; Part XII's pre-gate position is
  P-201 and its gate P-202, and P-198 was still in
  flight when this slice was scouted), signing (no
  key machinery banked), friend-instance exchange
  (no banked transport), and the VX-59 ruled-out
  forms (central store, catalogue, creator profiles).

Base: 1c18009d5bb3500cb91425afe7d22f8f8ce0e946 (P-197
banking record; banked P-001..P-197 + the commissioned
binding depth/role slice, PART XII OPEN). P-198
(team-03, hub breadth census) banks ahead of this slice
and is NOT in this base; its scout/design were read in
~/runmal-team-03 and both readings of breadth (payload
container widths - its chosen cell - and estate spread)
are ceded to it whole. The only files both slices touch
are src/runmal/hub/router.py and
docs/CLEAN_ROOM_LOG_2026-10-30.md (one additive import +
one additive road + one log entry each), reconciled by
the keeper at banking. Migration: NONE - head stays
0041, no 0042, battery-pinned.

## The identity law (stated up front)

1. The walk is P-191's string walk, carried verbatim
   as P-193 carries it: every STRING VALUE in the
   verified payload (dict values and list items) is an
   occurrence. Dict keys are structure, never values;
   a value under a content_sha256 key is the pack's
   identity, not its content, and its subtree is never
   walked; the pack envelope lives outside the payload
   member and is never walked.
2. Two occurrences are the same value iff the strings
   are EXACTLY equal - no case folding, no whitespace
   normalisation. (The search laws' folding is a search
   law, not an identity law; identity takes the
   checksum law's exactness.) The empty string is a
   value like any other and counts.
3. Comparison is by sha256 digest of the value's UTF-8
   encoding, computed in memory only. Digests are
   retained solely while counting and NEVER appear in
   the document: a digest of a short string is a
   dictionary target, so carrying one would leak what
   the no-content law forbids returning. The document
   carries counts only - never a value, never a digest,
   never an excerpt, never a payload field.
4. No silent omission: every entry ends parsed, or is
   named by its row outcome under P-193's imported
   OUTCOMES law (unavailable - locator not ready;
   invalid - unreadable at read time, over the bound
   with this module's own error text, not valid JSON
   on the bundle road, or the owning road's refusal
   carried verbatim), and coverage_complete carries
   the truth as data: any non-parsed entry makes it
   false, and count always equals parsed plus
   unavailable plus invalid. Shared counts are computed
   over PARSED entries only - a value in one parsed
   entry and one invalid entry is not shared, because
   the invalid entry's values were never verified.

## What the document states

Schema runmal-p199-hub-distinct-content-census-v1,
classified under the closed DISTINCT_CENSUS_STATES law
judged on the parsed axis (no_entries / no_distinct /
some_distinct / all_distinct). The P-187 list document
is composed verbatim and embedded whole. Per parsed
row: string_value_count (occurrences), distinct_value_
count, repeated_value_count (distinct values occurring
at least twice in the row), extra_copy_count
(occurrences beyond the first) and shared_value_count
(the row's distinct values also occurring in at least
one other parsed entry); non-parsed rows carry zeroes
and their outcome. Estate axes: by_outcome (zero-filled
under the imported law); by_kind_distinct (zero-filled
under HUB_KINDS - per kind: entries, parsed,
string_values, distinct_values POOLED over the kind's
parsed payloads, extra_copies); total_string_values
(occurrences over parsed rows - necessarily P-193's
total on the same estate, the stated expected
agreement); total_distinct_values; total_repeated_
values (distinct values occurring at least twice
estate-wide); total_shared_values (distinct values
occurring in at least two parsed entries - always at
most total_repeated_values); total_extra_copies
(total_string_values minus total_distinct_values); and
largest_distinct_entry (the parsed entry with the
greatest distinct_value_count, first in store order on
a tie, null when nothing parsed).

## Distinctness, stated plainly

- P-189 counts browse verdicts and checksum claims;
  this census carries no browse or checksum-match axis.
- P-193 counts occurrences and CHARACTERS (volume);
  this census counts no character anywhere. Its
  occurrence count necessarily equals P-193's
  string-value count on the same estate - the same
  occurrences, counted for identity rather than
  measured for length - and that agreement is expected
  and battery-pinned, as P-196's string node count was.
  The new facts are the identity axes.
- P-194 aggregates one query's answer; this census
  takes no query.
- P-195 groups WHOLE PACKS by verified checksum; this
  census never groups entries and never compares
  verified checksums across rows. Two P-195-unique
  packs sharing most of their text are stated here as
  sharing values, and one pack's internal repetition
  is stated with no P-195 signal at all - both
  battery-pinned on one estate read by both censuses.
- P-196 counts payload structure (nodes, keys, depth),
  P-197 measures file bytes, P-198 measures container
  widths; this census carries no shape, byte or width
  field and never counts a container.

## Roads and boundaries

One new road: GET /hub/distinct-census, bearer-gated
and owner-scoped exactly like the content-census road;
every census state answers 200 as data. The census is
a pure read: it writes nothing, registers nothing,
records no history, imports nothing, installs nothing,
copies nothing and grants nothing. Its cost is P-193's
cost paid once - every ready pack read and verified
through its own layer's parse road under the 16 MiB
bound - plus the in-memory digest counting. An entry's
registered checksum stays the caller's claim and is
never upgraded by being counted beside the verified
one. Signing and friend-instance exchange stay
declined - no key or transport machinery is banked.
There is no central store, no catalogue and no creator
profile here (VX-59). No migration: head stays 0041.
