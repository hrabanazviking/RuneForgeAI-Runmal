# Duplicate & version handling (P-025) — 2026-11-06

Roadmap line: *Same-name cards versioned, never silently overwritten*

## What was built

- Migration 0022: three new columns on `characters` —
  `version_no INTEGER NOT NULL DEFAULT 1`, `lineage_id TEXT` (nullable),
  and `content_hash TEXT NOT NULL DEFAULT ''` — with indexes
  `ix_characters_user_lineage` (`user_id`, `lineage_id`) and
  `ix_characters_user_name` (`user_id`, `name`).
- `src/runmal/characters/versioning.py` — the versioning helpers.
  - Identity is the SHA-256 of the export_json v2 stored text, per
    P-022.
  - The hash is always computed live via `effective_content_hash`,
    because `update_character`, the editor, and organise rewrite
    `card_json` without touching the column — the column is a
    creation-time cache only.
  - `effective_lineage_id` falls back to the row's own id for legacy
    rows.
  - `find_name_siblings` finds the non-deleted exact-name siblings.
  - `list_versions` / `get_version` read a lineage back.
- Service create path, in `create_character_from_card`:
  - An exact live-hash match among the same-name live siblings returns
    that sibling unchanged, flagged `DUPLICATE_ATTR` — no row, no
    assets, no commit.
  - Otherwise `version_no` is the maximum version ever in the lineage,
    including deleted rows, plus one, joining the first sibling's
    lineage; a first-of-name starts a lineage rooted at its own id.
  - Row names stay unsuffixed.
- `character_to_dict` gains `version_no`, `lineage_id`, and
  `content_hash` (live).
- Router:
  - `POST /characters` returns 200 with `duplicate_exact: true` for an
    exact duplicate, and 201 otherwise.
  - `GET /characters/{id}/versions` and
    `GET /characters/{id}/versions/{version_no}` — the latter includes
    the card payload.
  - 404 wordings are `character not found` and `version not found`.
- The library/service `_finish_card` adds a `versioned:v<n>` note.
  The P-022 exact and in-batch duplicate refusals are untouched.
- Relaunch fix (team-07, third lead): `GET
  /characters/{id}/versions/{version_no}` now checks the character
  first, so a missing character answers 404 `character not found`
  and only a missing version on an existing character answers 404
  `version not found` (the two wordings above, previously conflated
  in that one handler).

## Test maintenance

- Adding the migration moves the schema head, so the head-revision
  pins in the existing tests were updated 0021 -> 0022 in 9 test
  files. No assertion was weakened: each still pins the exact head.

## Not in this slice

- No UI.
- No restore, merge, or rollback of versions.
- Update, editor, and organise rewrites create no version.
- `duplicate_character` (copy) is unchanged — a separate `(copy)`
  lineage root.
- No dedup across different names in the service path (bulk import's
  digest check is global by its own P-022 design).
- Byte-level provenance is P-029.

## Clean-room basis

Shapes rest on P-002's census and public behaviour only.
No SillyTavern or Voxta source was inspected.

## Carried limitations (honest record)

- If several pre-P-025 legacy rows share one name, each is its own
  lineage; new same-name content joins the earliest live sibling's
  lineage only. The other legacy lineages stay separate (no lineage
  merge exists in this slice).
- Re-importing content identical to a soft-deleted character creates
  a fresh lineage at v1 (deduplication scans live siblings only, by
  design above); the deleted row stays in its own lineage's history.

## Evidence

Evidence: tests/test_p025_character_versions.py — counts recorded in
the worktree hidden_files/ at banking.
