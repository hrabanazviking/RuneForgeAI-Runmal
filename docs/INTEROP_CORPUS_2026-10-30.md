# P-005 — Interop Corpus (2026-10-30)

*Real-world-shaped character cards, lorebooks, and presets as test
fixtures — users' content must survive the trip. Corpus at
`tests/fixtures/interop/` (12 fixtures + `manifest.json` +
`make_corpus.py`); acceptance in `tests/test_p005_interop_corpus.py`
(15 tests).*

## Provenance and licences (the roadmap's condition)

The roadmap says "gathered from public user content (licences
respected)". No public corpus of user cards/lorebooks/presets exists
whose licence clearly permits redistribution inside this repository,
and downloading strangers' creative content on an assumption would
violate the very discipline the slice exists to protect. So the
corpus was **authored fresh for Rúnmál by the keeper**: every name,
description, and world is original to this corpus; only the *shapes*
follow the mirrors' public file-format specifications and public
documentation (clean-room law — the same basis as P-002/P-003). The
manifest states this provenance in writing; the fixtures are under
the repository's own licence. If Volmarr later donates real files of
his own, they can join the corpus under the same manifest discipline.

## The corpus (12 fixtures)

- **Cards (5):** v2 rich (full field set, extension zoo —
  talkativeness, depth_prompt, regex scripts, fav, world link —
  embedded character book in the mirror's dict-keyed entries shape,
  long unicode description, unknowns of every JSON type); v3 rich
  (assets array, group-only greetings, nickname, creator version);
  v1 minimal (sparse archive shape); v2 edge (empty values, nulls
  inside string lists, deeply nested unknowns); dual-chunk PNG
  (both `chara` v2 and `ccv3` v3 payloads, as dual-published cards).
- **Lorebooks (3):** world-info full (the documented per-entry
  field set, 3 entries); world-info nulls (explicit null / numeric-
  string numerics, as real exporters leave them); native rich
  (Rúnmál's own shape at full stretch, the round-trip baseline).
- **Presets (2):** mirror text-completion preset (flat sampler keys
  in the mirror's spellings: temp, rep_pen, min_p, tfs, typical_p…)
  and chat-completion preset (sampler keys + prompts[] /
  prompt_order[] structure) — ST-34's shapes, per P-004's handoff.
- **Chat (1) + persona (1):** mirror JSONL chat (metadata header,
  swipes as data) and an exchanged persona file — formats whose
  importers are P-020 / P-018; the corpus pins their well-formedness
  now so those slices build against fixed targets.

The manifest pins sha256 + byte size per fixture; a corpus test
fails if the bytes on disk and the manifest ever disagree, and
`make_corpus.py` regenerates the PNG and refreshes the hashes.

## Measured results (this tree, current code)

- **Cards travel well.** The v2 rich card's unknowns of every JSON
  type and its whole extension zoo survive v2 *and* v3 export round
  trips verbatim; the v3 rich card's assets array, group-only
  greetings, nickname, and creator version survive a v3 round trip;
  the dual-chunk PNG imports as its v3 payload (the parser's
  documented ccv3-first order). ST-02's depth is real where the
  founding road built it.
- **Lorebooks travel thin, now less thin.** World-info mapped fields
  verified; the still-dropped set is pinned exactly in the test
  (23 entry fields: selectiveLogic/selective, useProbability/
  probability, preventRecursion/excludeRecursion/delayUntilRecursion,
  group/groupOverride/groupWeight/useGroupScoring, depth, scanDepth,
  role, vectorized, outletName, automationId, characterFilter,
  triggers, decorators, displayIndex, id, ignoreBudget) plus the
  at-depth position (4) collapsing to before_char. Their homes are
  Part III (P-031–P-038) — a slice that lands one must shrink the
  pinned set in the corpus test deliberately.
- **Presets and chat/persona files have no importer yet** — stated
  plainly, not dressed up: the mirror's preset key spellings ride
  through `validate_params` only as opaque unknowns today (P-021
  owns the real mapping), and the JSONL/persona fixtures are
  well-formedness targets for P-020/P-018.

## Bugs found by the corpus and fixed in this slice

1. **Lorebook import crashed on null numerics** — `parse_import`
   raised a bare `TypeError` (escaping its `ValueError` contract)
   when a world-info or native entry carried an explicit null in
   `order`/`priority`/timed-effect fields, as real files do.
   Fixed with a tolerant coercion (`transfer._as_int`): nulls and
   non-numerics mean the default; numeric strings/floats coerce.
2. **Whole-word flag silently forced on** — world-info import
   hardcoded `whole_word: True`, ignoring the source's
   `matchWholeWords: false`. Now honoured (absent = mirror default).
3. **Timed effects zeroed despite existing on both sides** —
   world-info `sticky`/`cooldown`/`delay` were dropped while the
   native model has exactly those knobs (`*_prompts`). Now mapped.
4. **Card string lists stringified nulls** — a null (or number)
   inside `alternate_greetings`/`tags` became the literal greeting
   `"None"` / tag `"42"` in the normalized card. `_as_str_list` now
   keeps only genuine strings.

## Suite

Full suite re-run this tick on the VM (sanitised proxy env, per the
P-007 standing instruction) — counts recorded in
`CAMPAIGN_STATE.md`. The corpus adds 15 tests over the P-007
baseline of 685 passed / 6 skipped / 0 failed.
