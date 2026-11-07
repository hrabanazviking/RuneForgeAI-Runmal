# P-083 — Plugin manager: local packs + permission cards (Part VI)

Roadmap line: *Plugin manager: install/enable/update from local
packs (Part XII carries them) with permission cards.*

Clean-room: built from the roadmap line, Runmal's own P-045
lorebook-pack discipline, the P-025 collision discipline and the
P-081 plugin contract only. Base 40d77d0 (P-081 banking record).
**No migration taken** — migration head stays 0041 (see "Storage
stance" below).

## The shape of the thing

A local pack is ONE JSON envelope carrying ONE P-081 plugin
manifest as data and nothing else — no code ever travels in a
pack (P-081 section 11 / VX-42). The manager validates the pack,
renders a PERMISSION CARD stating plainly what the plugin asks
for, and installs only when the caller's grant names EXACTLY the
declared permission set. Installs are durable: a ledger file in
the data dir records manifest + grant + enabled flag, and the
registry rehydrates pack plugins at boot. The manager drives
only the P-081 registry verbs; citizens registered by in-tree
code are never manager property.

## Pack format (`runmal.plugins.packs`)

Envelope, strict (unknown keys reject), P-045 discipline:

    {"format": "runmal-plugin-pack", "pack_version": 1,
     "kind": "plugin", "schema": "runmal-p083-plugin-pack-v1",
     "provenance": {...carried verbatim, never interpreted...},
     "plugin": <manifest data, P-081 shape>,
     "content_sha256": <hex>}

`content_sha256` is the SHA-256 of the canonical JSON (sorted
keys, compact separators) of the NORMALISED manifest
(`manifest_to_data` of the parsed manifest) — identity over what
an install would register, never over raw file bytes, so
re-serialising a pack does not mint a false "different plugin".
The canonical plugin-bytes cap is 262,144. `build_pack()` mints
packs; `parse_pack()` validates envelope, manifest and checksum,
raising `PackError` on any defect.

## Permission cards (`runmal.plugins.cards`)

`permission_card(manifest, granted=None, previous=None)` renders
the declared capabilities, permissions (each with a plain-language
effect, a `reserved` flag — `chat.write` is reserved in v1 and
honoured by nothing — and the caller's grant state per row),
events, prompt hooks and UI slots. Honesty notes flag declarations
that are inert in the pack (a permission no declared surface uses,
a reserved permission). For an update, `changes` carries the
diff against the installed manifest: versions, permissions /
capabilities / events added and removed.

## Manager (`runmal.plugins.manager`)

- **Ledger:** `<data_dir>/plugins/installed.json`
  (`RUNMAL_DATA_DIR`-overridable via the service layer), format
  `runmal-plugin-ledger` v1; rows record the normalised manifest,
  content checksum, granted permissions, enabled flag, install /
  update times and the pack provenance subset. Writes are atomic
  (tmp file + replace, the credential-file precedent). A corrupt
  ledger raises `PluginManagerError` loudly at load — never
  silently treated as empty.
- **preview(pack)** writes nothing and returns the verdict:
  action `install | update | duplicate | conflict | invalid`,
  every problem found, and the permission card.
- **install(pack, granted_permissions, enable=False):** full
  validation, then the exact-grant rule (grant set must equal the
  declared set, else `GrantMismatchError`, nothing written), the
  data-only rule (a pack declaring prompt hooks refuses with
  `DataOnlyPackError` — hooks are code and need trusted in-tree
  registration), and duplicate/conflict discipline (exact
  duplicate = `duplicate_exact` no-op report, never a silent
  overwrite; a managed id at another version refuses with "use
  update"; an in-tree id refuses as not pack-managed). The
  registration and the ledger write are atomic: if the ledger
  cannot be written, the registration is rolled back.
- **update(id, pack, granted_permissions):** the pack id must
  match and be pack-managed; the new version must be strictly
  greater (same version + same content = `duplicate_exact`; same
  version + different content = conflict, "bump the version").
  Every check runs before any mutation; the swap disables,
  unregisters, registers the new manifest and restores the
  enabled flag, re-registering the old manifest best-effort if
  the swap fails mid-way. `installed_at` is preserved.
- **uninstall(id):** pack-managed only (in-tree →
  `NotManagedPluginError`; unknown → `KeyError`). Disables first
  if enabled, unregisters, deletes the ledger row.
- **sync_state(id):** follows a registry lifecycle change (the
  router's enable/disable verbs) into the ledger's enabled flag,
  so HTTP enable/disable is as durable as a manager call.
- **rehydrate():** at boot (`service.build_registry`), each
  ledger row is re-registered and re-enabled if flagged. A bad
  row is SKIPPED and named in the problems list — boot never dies
  for one bad plugin, and the skip is never silent. Problems are
  readable via `service.rehydration_problems()` and the
  `GET /plugins/manager` document.

## HTTP surface (house POST-verb idiom)

    POST /plugins/install/preview   {pack} -> preview document
    POST /plugins/install           {pack, granted_permissions, enable?}
                                    -> 201 installed; 200 duplicate_exact
    POST /plugins/{id}/update       {pack, granted_permissions} -> 200
    POST /plugins/{id}/uninstall    -> {outcome, plugin_id, permission_card}
    GET  /plugins/manager           -> {installed, rehydration_problems}
    GET  /plugins/{id}/permission-card

`GET /plugins/manager` is declared before
`GET /plugins/{plugin_id}` so it is never swallowed by the detail
route. DELETE stays absent and `POST /plugins` stays absent — the
P-081 405 pins stand. Error mapping: pack / manifest / grant /
data-only / surface / compatibility / not-managed → 422;
occupied-id conflict → 409; unknown id → 404.

## Storage stance: NO migration (explicit)

Migration head stays 0041; the P-081 battery pins `"0042"` not in
`MIGRATIONS` on this base, and P-082 (banked in parallel) may own
numbers — a file ledger under `data_dir()/plugins/` is the
credential-precedent road and carries zero numbering risk.
Durability scope: manifest + grant + enabled flag + provenance.
Failure logs and handler state stay process-local (P-081 s.7).

## Out of scope

Network/remote packs and signing (Part XII owns transport +
signatures), code-carrying packs, per-chat enablement, settings
interpretation (P-098), conformance listing (P-097), plugin data
custody beyond the ledger row (P-094), frontend UI (cards are API
documents).
