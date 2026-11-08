# P-092 — Expression/sprite plugin surface (Part VI, Extensions Row)

Roadmap line: *Expression/sprite plugin surface (Part X builds on it).*

Clean-room: built from the roadmap line and Rúnmál's own contracts only — the P-081 Plugin API v1, the P-082 sandbox policy, the P-023 character-asset machinery, and the P-089 durable file-store idiom. Base 62285ae (P-090 banking record), migration head 0041. **No migration taken.**

## What landed

`src/runmal/plugins/expressions.py` — a first-class P-081 citizen, id `runmal.expressions`:

- capabilities `chat.events`, `ui.slots`; permissions `chat.read`, `ui.contribute` (`chat.write` NOT declared — reserved in v1; selections are owner data in the citizen's own store, not chat writes through the plugin API);
- events `chat.created` / `chat.deleted` declared, handler abstains (a chat deletion must never silently delete a character's declared set);
- one UI contribution `expressions-panel` in `chat.sidebar`;
- sandbox grants EMPTY by construction (`sandbox_grants()` proves it); `register_plugin` only — `build_registry` / `create_app` untouched.

## The surface

- **Expression set** — declared per character by its owner: the closed, named set of expressions that character can show, plus an optional default. Entries are `{name (slug), label, asset_id, notes}`; duplicate names reject, a default naming an undeclared entry rejects, unknown keys reject. An empty set is a legal declaration.
- **Sprite binding** — an entry's `asset_id` binds it, by reference only, to one existing P-023 asset. `binding_report` resolves each entry through `assets.service.get_asset` and states the result honestly per entry: `bound`, or `problem` one of `no_asset` / `asset_missing` / `wrong_kind` / `not_stored`, with the P-023 `asset_to_dict` view where an asset exists. Bytes are never read or copied by this citizen.
- **Derivation draft** — `derive_set_from_assets` builds a draft set from the character's stored expression assets (names slugified, collisions suffixed `-2`, `-3` deterministically) and returns it WITHOUT saving: declaration stays an explicit owner act.
- **Selection** — the current expression of one CHAT, chosen from its bound character's set. Choosing an undeclared name refuses loudly before any write. Every selection carries a provenance receipt `{via: expression_plugin, source, actor_user_id, reason, message_id, previous_expression}` with `source` in the closed vocabulary `manual | default | plugin | message`, and appends to a kept history (newest 100). `apply_default` selects the declared default only through its explicit road and never overrides a current selection. `clear_selection` drops the current selection and records the clearing, with the cleared expression named as the record's `previous_expression`.
- **Inspection** — `inspect_state` joins chat → character → set + per-entry bindings + current selection + its binding in one document: the exact read Part X consumes.

## Store

Durable per-user file store, the P-089 idiom: one JSON document at `data_dir()/expressions/<user_id>.json` (`{schema, sets[], selections[], history[]}`), written atomically (tmp sibling, chmod 0o600, replace). A corrupt store raises `ExpressionError` and is never silently reset. Limits: 200 sets per user, 64 entries per set. Single-process store; last-writer-wins across processes (the P-089 standing limitation).

## HTTP surface (plugins router, `/api/v1` prefix by mount)

`GET /expressions/sets?character_id=` · `POST /expressions/sets` (201; the character is verified owner-owned, else 404) · `GET|PUT|DELETE /expressions/sets/{character_id}` · `GET /expressions/sets/{character_id}/bindings` · `POST /expressions/sets/{character_id}/derive` (draft, unsaved) · `GET /expressions/current?chat_id=` · `POST /expressions/select {chat_id, name, source?, reason?, message_id?}` · `POST /expressions/clear {chat_id}` · `GET /expressions/history?chat_id=` · `GET /expressions/inspect?chat_id=`. Errors: invalid payload / undeclared name / chat with no bound character / missing set → 422; unknown character/chat/set/selection → 404.

## Honest boundaries

- **No renderer is invented.** Nothing here draws, composites or displays a sprite; Part X owns rendering and reads sprite bytes through the P-023 roads itself.
- **No automatic detection.** Nothing scans message text to guess an expression. Selection is always an explicit act: the owner (`manual`), a declared default applied through its road (`default`), or a caller naming its source in the closed vocabulary (`plugin` / `message` — `message` means the caller asserts a message motivated the choice).
- No network, no model call, no generation. P-087 may one day land expression sprites through the same `add_asset` road; this slice only binds the P-023 assets that already exist.
- Deleting a set does not rewrite history: past selections stay recorded as what was shown; re-selection refuses until a new set is declared.
