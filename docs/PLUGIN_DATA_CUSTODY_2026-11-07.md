# P-094 — Plugin data custody (Part VI, Extensions Row)

Roadmap line: *Plugin data custody: a plugin's data is exportable and deletable with the plugin — no hostage state.*

Clean-room: built from the roadmap line and Rúnmál's own contracts only — the P-081 Plugin API v1 citizen pattern, the P-082 sandbox policy, the P-083 manager/ledger, the P-089 durable file-store idiom and its descendants, and each citizen's own inspect/clear roads as banked in P-084..P-093. Base 2b34c9a (P-092 banking record; P-093 banked separately and reconciled by the keeper), migration head 0041. **No migration taken.**

## What landed

`src/runmal/plugins/custody.py` — a first-class P-081 citizen, id `runmal.plugin-custody`, plus two routes on the plugins router:

- capabilities `ui.slots` only; permissions `ui.contribute` only (`chat.write` NOT declared); no events, no prompt hooks; one settings-panel contribution `plugin-custody-panel`;
- sandbox grants EMPTY by construction (`sandbox_grants()` proves it); `register_plugin` only — `build_registry` / `create_app` untouched;
- the citizen itself holds NO data: the custody verbs are module functions (trusted host wiring, the register_plugin trust class), and custody's own export is the honest empty over its universal sections.

## The two verbs

- `export_plugin_data(plugin_id, *, user_id, base_dir, session, instances, registry, manager)` returns ONE document per plugin: `{format: runmal-plugin-custody, custody_version: 1, kind: plugin_data_export, plugin_id, exported_at, app_version, owner_id, manifest, coverage, sections, content_sha256}`. The checksum is the packs canonical-JSON + sha256 idiom over `{plugin_id, owner_id, sections}`; `verify_custody_checksum` recomputes it.
- `delete_plugin_data(...)` (same parameters) deletes the same sections and returns the deletion report `{kind: plugin_data_deletion, deleted_at, sections, content_sha256}` with per-section removed counts. Database deletion is flush-only (the caller commits, the S404 pattern). Deleting what is already gone reports zero counts, never an error.
- A section is NEVER silently omitted. Statuses: `exported` (payload complete) · `empty` (the store exists in principle, holds nothing) · `unavailable` (the access road was not supplied, or the module is absent — the reason is named) · `error` (a durable store is corrupt — the refusal is carried IN the document; the export still stamps and other sections continue). An id with no adapter, no ledger row and no registration raises `UnknownPluginError` (404 over HTTP); other refusals are `CustodyError` (422).

## Coverage, per citizen (from the scout inventory)

- **Durable file stores** (`quick-replies`, `regex-scripts`, `expressions`, `variables`): the payload is the store document VERBATIM, as parsed and schema-checked against the citizen's own `STORE_SCHEMA` — a section cannot silently drop a field the store holds. Needs `user_id`; the path is built from the validated UUID user id alone. Delete removes the owner's file only; other owners' files are never touched (battery-proven byte-identical).
- **Summarise (database)**: ALL `ChatSummary` versions for the owner (ordered chat, version) plus the `kind=summary` memories whose extractor names one of those summaries, with sources. Delete goes through `memory_service.delete_memory` per memory (FTS kept honest) plus a direct delete of the summary rows. Non-summary memories and other owners' rows are never matched.
- **Vector storage (index)**: the plugin's data is its INDEX — doc ids grouped per scope, provenance, and the vectors themselves when the backing store is the enumerable in-memory contract twin. For the sqlite-vec adapter the section states `vectors_not_enumerable` plainly (the founding contract exposes no enumeration) and the index manifest still exports complete: the vectors are rebuildable from the founding memories, which are host data. Delete clears every exported scope through the index.
- **In-memory citizens** (`translate`, `web-search`, `image-generation`, `tts`, `stt`): export is the citizen's CURRENT state via its own inspect surfaces, or an honest empty — nothing here invents persistence these citizens do not have. Delete uses each citizen's own clear roads per chat. Landed P-023 image bytes are character assets — host data, named in the export as `landed_asset_ids` references only; custody deletion never deletes them.
- **Universal sections, for ANY plugin id**: `host_ledger` (the P-083 ledger row verbatim when a manager is supplied) and `registration` (the registry detail view when a registry is supplied). A pack-only plugin (in the ledger, no citizen adapter) is therefore still exportable and deletable: its data IS its ledger row.
- **Custody itself**: stateless; export is the universal sections only.

## The P-083 hook point

`PluginManager.uninstall` alone removes the ledger row + registration and never touched citizen data stores. Custody delete is the verb that makes removal complete: it deletes the data sections first, and when a manager is supplied AND a ledger row exists it finishes through `manager.uninstall`, so no orphan row or registration survives either. When the plugin is a citizen (no row), the delegation is skipped by checking the row first (uninstall would refuse `NotManaged`). Lifecycle for citizens otherwise stays with the registry/manager: custody deletes DATA, and its report says so (`registration: not_applicable`). After a pack plugin's custody delete, the id is completely unknown again and a repeat delete raises `UnknownPluginError` — the unknown-id law, stated here so it is not mistaken for an idempotency break: citizen deletes ARE idempotent.

## Owner scoping (the P-093 law as model)

Deletion only ever touches the named owner's stores: file paths from the validated user id; DB rows filtered by `user_id`; instance sections filtered to the chats (and, for vector scopes, characters) the supplied session proves the owner owns. That filter applies only when BOTH a session and a `user_id` are supplied; with no session the caller is trusted in-process host code operating on its own instances — stated here and in the `delete_plugin_data` docstring, never hidden.

## The P-093 seam (lazy by design)

The `runmal.variables` module is NOT in this slice's base tree (P-093 banked on team-02's branch; the keeper reconciles). Its adapter imports lazily: on this tree the variables section reports `unavailable` ("module … is not present in this build; custody never touches a store it cannot identify"), its manifest stamps as `None`, and its store file is NEVER touched — battery-proven with a planted store file. When the module lands at banking reconciliation the same adapter lights up with zero custody changes: `store_path` / `STORE_SCHEMA` match the banked P-093 module exactly (verified against the banked tree).

## HTTP surface (plugins router, `/api/v1` prefix by mount)

- `GET /plugins/{plugin_id}/custody/export` — owner-scoped export over the roads HTTP can reach: durable files (the request's owner), the database via the request session, the host ledger via the default manager, the registration via the default registry. Live instances are not in the registry (records hold handlers, not instances), so instance sections report `unavailable` with the reason named over HTTP — never a partial export dressed as complete. The in-process road reaches instance state.
- `POST /plugins/{plugin_id}/custody/delete {confirm: true}` — same roads; refuses without the explicit confirm (422) and commits the request session after a database deletion.
- Unknown plugin id → 404; custody refusals → 422 (house `_visible` idiom).

## Honest boundaries

- No migration, no network, no change to any citizen's store format, to `manager.uninstall` itself, or to `build_registry`/`create_app`.
- Custody of founding host data is refused by design: chats/messages, memories at large, and P-023 assets are not plugin data. Where a citizen's data touches host data it is named as a reference (summaries' source messages, landed asset ids), never deleted.
- TTS export carries the citizen's latest results verbatim, including `pcm_b64` audio the citizen itself holds — completeness over size, stated plainly.
- The HTTP road cannot reach live plugin instances (above); host wiring that needs instance custody calls the module functions with `instances=`.
