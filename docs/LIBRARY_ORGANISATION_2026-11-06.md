# Library organisation (P-024) — 2026-11-06

Roadmap line: *Tags, favourites, and library organisation at card scale (hundreds of cards stay findable)*

## What was built

- Migration 0020: two new tables — `character_organisation` and
  `character_tags` — with no ALTERs to existing tables.
- `src/runmal/library/organise.py` — the organisation service.
  - Tag normalisation rules are applied consistently on every
    read and write path (`normalise_tag` / `normalise_tags`).
  - Organisation is seeded from a card's own tags via the
    canonical card parser, so a card already carrying tags is
    organised from them on first sight.
  - Tag edits rewrite `card_json` through the exporter, so
    unknown fields survive (INV-009).
  - Library listing does its filtering, sorting and pagination
    SQL-side: search (`q`), tag filtering (`any` / `all`),
    favourites-only, and sort order are pushed to the query
    rather than filtered in Python, so hundreds of cards stay
    findable.
  - Service contract: `get_organisation`, `set_tags`,
    `add_tags`, `remove_tag`, `set_favourite`, `list_library`
    and `list_tags`, each scoped to the owning user; an
    organisation view is `{"character_id", "name", "tags",
    "is_favourite"}`.
- `src/runmal/library/router.py` — new routes on the existing
  library router (the P-022 `POST /library/imports` route is
  preserved):
  - `GET /api/v1/library/cards` — query `q`, repeatable `tag`,
    `tag_mode` (`any` / `all`), `favourites_only`, `sort`
    (`name`, `name_desc`, `newest`, `oldest`,
    `favourites_first`), `limit` and `offset`; an invalid
    `sort` or `tag_mode` is a 422.
  - `GET /api/v1/library/tags` — `{"tags": [...]}`.
  - `GET /api/v1/library/cards/{character_id}/organisation`
    — 404 `character not found` when there is no such card.
  - `PUT /api/v1/library/cards/{character_id}/tags` — replace
    the tag set from `{"tags": [...]}`; invalid tags are a
    422, a missing card a 404.
  - `POST /api/v1/library/cards/{character_id}/tags` — add to
    the tag set, same body and errors.
  - `DELETE /api/v1/library/cards/{character_id}/tags/{tag}`
    — remove one (URL-decoded) tag.
  - `PUT /api/v1/library/cards/{character_id}/favourite` —
    set the favourite flag from `{"is_favourite": bool}`.
- `src/runmal/library/__init__.py` re-exports the organise
  service alongside the existing P-022 exports.
- The characters router and service are untouched.

## Test maintenance

- Adding migration 0020 moves the schema head, so the head-revision pins in the existing tests were updated 0019 -> 0020 (tests/test_s103_storage.py, test_s106_characters.py, test_s107_chats.py, test_s201_lorebooks.py, test_s210_group_chats.py, test_s801_archive.py, test_s802_restore.py, and the head test in test_p021_preset_interop.py) - the same maintenance P-021 performed when it added 0019. No assertion was weakened: each still pins the exact head and the exact applied-revision list.

## Not in this slice

- No UI.
- No lorebook tagging — cards only; the roadmap line says
  card scale.
- No collections or folders.
- Duplicate and version work stays P-025.

## Clean-room basis

Shapes rest on P-002's census and public behaviour only.
No SillyTavern or Voxta source was inspected.

## Evidence

Evidence: tests/test_p024_library_organisation.py — counts recorded in the worktree hidden_files/ logs at banking.
