# P-200 - Hub Schema Census (Part XII, The Hub - Sovereign Shape)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part XII only its part-table line -
XII | The Hub, Sovereign Shape | P-187 - P-202 - and no
verbatim P-200 entry exists anywhere in it. This slice
scope is therefore DERIVED, not roadmap-verbatim, from
Runmal own in-tree record only (survey:
hidden_files/P200_SCOUT.md; design:
hidden_files/P200_DESIGN.md):

- Identity in the banked hub estate is measured at
  whole-pack grain (P-195 groups entries by verified
  content checksum) and at value grain (P-199, banking
  ahead of this slice, compares string values for exact
  identity), while structure is measured as counts only:
  P-196 counts every payload node and every dict key,
  P-198 measures every container width, and both discard
  which keys any one object holds together. No banked
  document states how many DISTINCT object shapes
  (key-sets) an estate verified payloads use, how many
  repeat inside one pack or across packs, or how many
  are shared between entries - and it is not derivable
  from any banked document, because no banked document
  carries a key name or a key-set (P-196 returns counts
  only, by law). A hundred lorebook entries with
  different text are one shape.
- P-200 is the last ordinary cell slot of Part XII: the
  Part XI precedent puts the reconciliation battery at
  the second-last slice of a part (P-185 ahead of the
  P-186 gate), so Part XII battery belongs at P-201
  beside the P-202 gate and is declined here as
  premature, exactly as P-199 scout weighed it. The
  cell space is not declared exhausted: this cell
  stands on its own merits in the scout.
- This slice takes that cell in the P-193/P-196/P-199
  shape: a query-free estate aggregate composing the
  banked verified parse roads directly, under P-193
  imported OUTCOMES law and P-188 imported bound,
  measuring the key-set identity of verified payload
  objects.
- Weighed and declined WITH REASONS in the scout:
  string-length distribution and emptiness (new
  statistics over P-193 measured quantity), key-name
  frequency (names are never returned under P-196 law;
  this slice returns no name and no per-key frequency -
  only counts of hashed key-set comparisons, P-199
  in-memory digest discipline), numeric aggregates
  (would return payload values), character-identity
  and distinct-scalar censuses (thinner transpositions
  of P-199 own axis), array element-type signatures
  (a fragment; P-198 already measures arrays),
  depth / breadth distributions (refinements of
  P-196 / P-198), locator-sharing and registration-age
  (derivable from P-187 list), claim decomposition
  (recounts P-189), metadata completeness (derivable
  from P-187 list), synthesis census (measures
  nothing), envelope census (no closed cross-kind
  law), reconciliation battery / part gate (P-201 /
  P-202 own them), signing (no key machinery banked),
  friend-instance exchange (no banked transport), and
  the VX-59 ruled-out forms (central store, catalogue,
  creator profiles).

Base: fd86f6508de147eea65ccaeb9f7a858255130f87 (P-198
banking record; banked P-001..P-198). P-199 (team-01,
hub distinct-content census) banks ahead of this slice
and is NOT in this base; the only files both slices
touch are src/runmal/hub/router.py and
docs/CLEAN_ROOM_LOG_2026-10-30.md (one additive import,
road, docstring lines and log entry each), reconciled
by the keeper at banking. Migration: NONE - head stays
0041, no 0042, battery-pinned.

## The signature law (stated up front)

- Every DICT node in a verified payload is one object
  occurrence. An object shape (signature) is the SET
  of its counted keys - the keys P-196 counts: every
  key except a content_sha256 member, which is
  excluded WHOLE (not a counted key of its parent
  object, and its subtree is never walked - the pack
  identity is not its schema). The set is unordered:
  JSON object member order is not structure. Names are
  exact, never folded. The empty object has the empty
  signature - a shape like any other - and counts.
  Lists and scalars are walked through and are never
  themselves shapes.
- Two objects are the same shape iff their key-sets
  are exactly equal. Comparison is by sha256 digest of
  the canonical encoding (the JSON array of the sorted
  key list, UTF-8), computed in memory only. The
  document carries NO key name, NO per-key frequency
  and NO digest - counts only. A digest of a small
  key-set is a dictionary target for the schema it
  names; carrying one would leak what the law forbids
  returning.

## The document

Schema: runmal-p200-hub-schema-census-v1, from
schema_census_document(entries) in
src/runmal/hub/schema_census.py, served at
GET /hub/schema-census (bearer-gated, owner-scoped,
every census state answers 200 as data).

- The P-187 list document is composed verbatim and
  embedded whole under list.
- Each row is the P-187 entry verbatim plus
  locator_state (judged live), outcome under P-193
  imported OUTCOMES law (parsed / unavailable /
  invalid), verified_content_sha256 (the owning parse
  road own fact; empty for a bare bundle and for any
  non-parsed row; never compared across rows here),
  and - for parsed rows - object_count,
  distinct_shape_count, repeated_shape_count,
  extra_shape_count and shared_shape_count (all zero
  for a non-parsed row), plus error (the owning road
  refusal verbatim; oversize carries this module own
  text, "pack file too large to schema-census").
- Axes: count / entries_considered / parsed_count /
  coverage_complete (count always equals parsed +
  unavailable + invalid); by_outcome zero-filled;
  by_kind_schema zero-filled under HUB_KINDS (per
  kind: entries, parsed, objects, distinct_shapes
  pooled over the kind parsed payloads,
  extra_shapes); total_objects; total_distinct_shapes;
  total_repeated_shapes; total_shared_shapes (always
  at most total_repeated_shapes);
  total_extra_shapes (= total_objects -
  total_distinct_shapes); largest_schema_entry (the
  parsed entry with the greatest distinct_shape_count,
  first in store order on a tie; null when nothing
  parsed); max_browse_bytes; kind_formats; notes.
- census_state under the closed SCHEMA_CENSUS_STATES
  law, judged on the parsed axis: no_entries /
  no_schema / some_schema / all_schema.

## Agreements and fences

- object_count per row necessarily equals P-196
  object_count on the same payload - the same objects,
  counted for identity rather than tallied. That
  agreement is expected, stated, and battery-pinned;
  no other P-196 field (node totals, key totals,
  depth) appears anywhere in this document.
- No P-189 verdict, no P-193 volume field, no P-194
  query axis, no P-195 grouping axis, no P-197 byte
  axis, no P-198 width axis and no P-199 value-identity
  axis appears among this census own fields. Verified
  checksums ride per row as the parse roads own facts,
  as at P-193, and are never compared across rows.

## Honest boundaries

A pure read: the census writes, registers, records,
imports, installs, copies and grants nothing, and
records no history. Its cost is P-196 cost paid once:
every ready pack is read and verified through its own
layer verified parse road under the 16 MiB bound, so
an oversize, corrupt or wrong-kind pack is an invalid
row, never a census failure. Shared counts are
computed over parsed entries only. An entry registered
checksum stays the caller claim and is never upgraded
by being counted beside the verified one. Signing and
friend-instance exchange stay declined - no key or
transport machinery is banked. There is no central
store, no catalogue and no creator profile (VX-59).
No migration: head stays 0041.

Carried items stay untouched: the binding label update
named open at P-186, history retention / bulk clear
(awaiting Volmarr ruling - none invented here), and
unified-search history (presupposes a recording write
this pure read does not make). The Part XII
reconciliation battery stays named open at P-201 and
the part gate at P-202; neither is built here.
