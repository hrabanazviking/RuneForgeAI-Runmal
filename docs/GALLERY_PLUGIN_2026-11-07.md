# P-095 — The gallery plugin (2026-11-07)

Roadmap line: "The gallery plugin: chat image gallery with
generation history (Voxta users expect it; ST users bolt it
on — here it's a citizen)." Design: hidden_files/P095_DESIGN.md;
scout: hidden_files/P095_SCOUT.md.

## What shipped

`src/runmal/plugins/gallery.py` — a first-class P-081 citizen
(id `runmal.gallery`) giving every chat a gallery: the images
associated with the chat, listed and inspected with provenance.

- **Citizen shape.** Registered only via `register_plugin`
  (`build_registry` / `create_app` untouched). Capabilities
  `chat.events` + `ui.slots`; permissions `chat.read` +
  `ui.contribute` (`chat.write` reserved, not declared), so the
  P-082 sandbox grant set is empty. One UI contribution: the
  `chat.sidebar` "Chat Gallery" panel. No prompt hooks — gallery
  content is not prompt text. Declared `chat.created` handler is
  a deliberate no-op: entries change only through explicit verbs.
- **Durable generation history.** P-087's ledger is process-local;
  the gallery is its durable home. One JSON document per owner
  (`data_dir()/gallery/<user_id>.json`, P-089 file idiom: atomic
  0600 save, strict re-validation on read, corrupt stores raise
  and are never silently reset). No migration — head stays 0041.
- **Provenance, verbatim.** Three source kinds: `generated`
  (ingested P-087 records keep prompt, prompt source, road,
  provider, model, generation id and sha256; the deterministic
  road stays labelled `deterministic_local`), `asset`
  (a P-023 asset of the chat's bound character, referenced by
  id — bytes never copied), and `attached` (owner-supplied
  bytes). Unlanded generations are stated plainly in the entry
  notes with their landing reason. Ingest is idempotent per
  (chat, generation id); re-syncs report skips.
- **Attach roads.** `attach_asset` refuses plainly when the chat
  has no bound character or the asset is not that character's.
  `attach_image` sniffs bytes first (non-images record nothing);
  bound chats land through P-023 `add_asset` (kind background),
  unbound chats keep bytes in the gallery byte store under the
  honestly labelled `attached_local` road.
- **Inspection.** `gallery_view` enriches asset-backed entries
  live from P-023 (asset status, thumbnail status, has_thumbnail;
  a vanished asset row is stated as `asset_missing`) and reports
  gallery-local byte presence honestly. `gallery_summary` counts
  by source kind and by road. Curation (`update_entry`) touches
  title/notes only — provenance is immutable. `remove_entry`
  removes gallery-local byte files but never touches P-023
  assets; `clear_gallery` is the only emptying verb.
- **Generation import** is pull-based and explicit:
  `import_chat_generations` consumes a bound P-087 citizen
  instance's `history(chat_id)` (host wiring, the P-087 trust
  class) and preserves it durably.

## Honest limitations

- No HTTP routes in this slice: P-094 (plugin data custody) is
  in flight against the shared plugins router on an older base,
  so the gallery ships its service surface + UI contribution
  only (the P-087 citizen likewise ships no router roads).
- The gallery preserves generations it is handed; it does not
  observe P-087 generations it was never shown (P-087 declares
  no generation event, by its own design).
- Gallery-local attachments get no thumbnails: thumbnail facts
  are a P-023 road, and the view labels those entries
  `gallery_local` instead of claiming otherwise.

## Tests

`tests/test_p095_gallery.py` — manifest/registration/sandbox,
store discipline (owner isolation, corrupt-store refusal),
generation preservation (provenance, idempotence, sync
report, refusals), asset/attach roads and refusals, curation,
removal custody, the enriched view, P-087 import (landed and
unlanded), and the migration-head neighbour (0041, no 0042).
Counts are recorded in hidden_files/P095_EVIDENCE.md.
