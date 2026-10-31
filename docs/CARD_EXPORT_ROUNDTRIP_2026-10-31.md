# P-017 — Card Export v2 + v3, Corpus Round-Trips (2026-10-31)

*Part II (Cards & Content Interop), third slice: card export v2 +
v3 — round-trip tests against the P-005 corpus (import → export →
field-diff clean). Acceptance in
`tests/test_p017_card_export_roundtrip.py` (10 tests).*

## The measured gap this slice closes

P-015 and P-016 pinned round trips for the cards they authored,
and P-005 pinned hand-picked fields of the corpus. No test had
ever diffed **every** corpus card against **every** export shape.
This slice's entry probe did exactly that — the five corpus card
fixtures (`card_v1_minimal`, `card_v2_rich`, `card_v2_edge`,
`card_v3_rich`, `card_dual_ccv3.png`) × JSON v2, JSON v3, PNG,
CHARX — and found the export side mostly honest, with two real
defects, both on v3 cards leaving through the v2 door:

1. **A v3 card exported as v2 lost its data-level unknown
   fields.** The exporter's wrapped-envelope branch (P-015) was
   gated on `spec_version == "2"`, so a v3 card fell through to
   the flat path, which preserves only top-level unknowns.
   Corpus proof: `card_v3_rich.json` lost
   `creator_character_version` and `x_corpus_v3_unknown` on a
   JSON v2 export — and on PNG export too, PNG being a v2
   carrier. That is an INV-009 violation: unknown-but-valid
   fields must survive supported round trips. (Normalized
   fields, including the P-016 v3 additions, survived — the
   loss was only in the opaque layer, which is precisely the
   layer no earlier test diffed exhaustively.)
2. **The PNG export carried no v3 payload**, so a v3 card's PNG
   round trip silently downgraded it to v2 — even though real
   cards circulate dual-published (a `chara` v2 chunk and a
   `ccv3` v3 chunk in one PNG; P-005's corpus fixture is one)
   and Rúnmál's importer already prefers `ccv3`.

## The field-diff contract

A round trip is **clean** when, for the imported card and the
card re-imported from its export:

- every normalized field is equal (the diff is taken on the
  normalized model, so the parser's one-time defensive cleaning
  — null members dropped from string lists, per P-005 — is not
  re-judged at export);
- every unknown field survives with its exact value, compared
  **level-agnostically**: a deliberate version conversion may
  move an unknown between the flat level and the `data`
  envelope (the founding convert-up semantics), but may never
  lose, change, or invent one;
- the re-imported spec version is the version the export was
  asked for — JSON v2 → 2, JSON v3 → 3, CHARX → 3 (CHARX is the
  v3 container), PNG → 3 for a v3 card (its `ccv3` chunk) and 2
  otherwise (its `chara` chunk);
- the export is a **fixed point**: exporting the re-imported
  card reproduces the first export byte for byte, in all four
  shapes.

## The fixes

- `export_json`'s wrapped-envelope branch now serves **any**
  wrapped source, not only spec "2": a v3 card exported as v2
  keeps its envelope, its data-level unknowns inside it, its
  top-level unknowns outside it, and its set v3 additions at the
  data level (P-016's only-set rule, unchanged). A flat card's
  export stays flat (P-015's pin, unchanged).
- `export_png` now writes the dual-published shape for a v3
  card: a `chara` chunk (the v2 payload, readable by the widest
  set of tools) **and** a `ccv3` chunk (the v3 payload, which
  Rúnmál's importer already prefers). A non-v3 card's PNG is
  byte-identical to before — `chara` only.

After the fixes the probe reads clean on every cell of the
matrix; the only remaining diffs anywhere are the deliberate
spec-version conversions to the version an export was asked
for. The acceptance tests pin the whole matrix, the fixed-point
property, and both defects by name.

## Clean-room basis

Own tree only: the P-005 corpus (authored fresh for Rúnmál,
provenance in its manifest), the founding exporter/importer,
and the public card specs' already-logged shapes (§1 of the
clean-room log). No mirror source code was read and no card
file was downloaded. Full entry appended to
`docs/CLEAN_ROOM_LOG_2026-10-30.md`.

## Suite

Full suite re-run this tick on the VM (sanitised proxy env, per
the P-007 standing instruction) — counts recorded in
`CAMPAIGN_STATE.md`. This slice adds 10 tests.
