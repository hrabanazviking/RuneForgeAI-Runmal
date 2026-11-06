# Portable archive growth (P-028) — 2026-11-06

Roadmap line: *The `.runmal` archive grows: cards/lorebooks/presets in the portable archive with the same checksum discipline*

## What was built

The S801/S802 portable archive already carried cards, lorebooks
and presets as canonical rows. P-028 audited that claim against
everything Part II added, closed the one real gap, and pinned the
whole claim with round-trip tests.

- **Gap closed — library organisation (P-024) now rides.** The
  `character_tags` and `character_organisation` tables are user
  data (which cards are tagged, which are favourites) that the
  archive silently left behind: a restored library lost every
  tag and favourite. `src/runmal/portable/archive.py` now emits
  one bundled member per organised character,
  `character_library/{character_id}.json`, carrying
  `{"character_id", "tags": [...], "organisation": row|null}`
  (the lorebook bundle pattern: subordinate state with no
  independent identity rides with its parent; a per-tag member
  would have put a user-influenced `tag_key` in a filename).
  Bundles are emitted only for characters that have tags or an
  organisation row. Rows ride the existing generic `row_to_dict`,
  so every P-024 column flows. The manifest gains row counts
  `character_tags` and `character_organisation`, and the
  validator's member shapes gain `character_library` — the same
  per-member SHA-256 checksum discipline as every other member.
- **Restore taught the same step.** `src/runmal/portable/restore.py` gains a `character_library` step immediately after
  `character_assets` (both tables FK to users/characters;
  nothing references them), inserting the organisation row then
  the tags per bundle, with both count keys verified against the
  staged tables like every other kind.
- **Verified already whole (no code change needed):** cards ride
  with their P-025 version fields (`version_no`, `lineage_id`,
  `content_hash`) and `card_json` unknown fields verbatim;
  lorebooks ride with entries (P-019); presets ride with their
  P-021 interop carriage (`source_format`, `interop_json`). The
  battery proves all three field-for-field.
- **Discovered bug, fixed in-slice:** export → restore → export
  was not byte-stable. Tz-aware UTC timestamps export with a
  `+00:00` suffix, SQLite returns them naive, and the re-export
  silently dropped the suffix — the same instant, different
  bytes, different checksum, for every member kind. All Rúnmál
  timestamps are UTC by construction (`_utcnow`), so the
  exporter's `_encode` now states a naive datetime's UTC
  explicitly. The battery's checksum-stability test pins it.

## Compatibility

- **No migration.** Schema head stays **0022**.
- **FORMAT_VERSION stays 1** (the P-023 precedent: purely
  additive member kinds do not bump it). Pre-P-028 archives
  validate and restore unchanged — restore is driven by the
  members and counts present, so absent bundles import as zero
  tags/organisation, which is exactly what those archives hold.
  The battery proves this by stripping the new members from a
  fresh archive and restoring it. New archives are rejected by
  pre-P-028 builds as an unknown member kind (the pre-existing
  P-023 behaviour), never silently half-read.
- Exclusions unchanged: secret values never enter an archive
  (the battery proves a stored secret appears in no member);
  thumbnail bytes stay out — thumbnails are derived state that
  regenerate from the stored original asset bytes on read
  (P-023), and the originals ride.

## Tests

- `tests/test_p028_portable_archive_growth.py` — 10 tests:
  bundle emission (tags-only, organisation-only, both, neither)
  + manifest counts + per-member checksum verification; full
  export → restore → field-diff across characters/tags/
  organisation/lorebooks/entries/presets; tampered bundle
  rejected with staging removed; unmanifested member rejected;
  pre-P-028 archive still restores; owner isolation + secret
  absence; re-export of a restored archive is checksum-
  identical; tampered manifest counts fail restore; malformed
  bundle shape rejected; a duplicate tag inside a bundle fails
  restore with staging removed.
- Neighbours (battery + S801/S802/S808, P-017/P-019/P-021/
  P-022/P-023/P-024/P-025/P-026): 268 passed.
- Full suite: 1174 passed, 4 skipped, 0 failed (= banked base
  1164 + 10 new). Logs in the team worktree `hidden_files/`
  (`p028_battery.log`, `p028_neighbours.log`,
  `p028_fullsuite.log`).

## Not in this slice

- No UI. No change to the full-backup bundle (a different,
  whole-install format; it carries the database file itself).
- Scenarios (P-026) have no database table yet — they are
  file-interop only until Part IX, so there is nothing stored
  for the archive to carry.
- `chat_events` stays out: it is an operational mutation log,
  kin to the derived state the archive policy already excludes.
