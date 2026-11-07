# Preset bundles (P-054) — 2026-11-06

Roadmap line (Part IV): *Presets: save/load/share sampler+prompt
bundles; per-character and per-chat overrides.*

## What a bundle is

One validated, saveable unit (`src/runmal/presets/bundles.py`)
gathering everything a preset means in Rúnmál after P-049..P-053:

- `sampler` — the S207/P-052 parameter bag, validated by the
  existing `validate_params` (all 28 canonical keys type/range
  checked; unknown backend keys preserved verbatim).
- `prompt_layout` — a P-049 layout in its normalised complete
  form, or null.
- `instruct_template` / `context_template` — selections:
  `{"kind": "builtin", "name": ...}` (only the name is carried;
  the registry stays the truth), `{"kind": "custom",
  "template": {...}}` (full validated data form), or for context
  templates `{"kind": "story_string", "text": ...}`; null when
  no selection is in play.
- `template_ref` — the legacy S207 reference.
- `prompts` / `prompt_order` — the P-021 carriage, verbatim.
- `extensions` — any other top-level keys of an incoming bundle,
  preserved verbatim through save/load/share. Nothing carried is
  ever silently dropped; malformed KNOWN sections refuse with a
  typed error and store nothing. Normalisation is a fixed point
  and storage is canonical JSON, so load == save, value for value.

## Persistence — migration 0033 (owned by this slice)

The P-049/P-051 notes named layout/template persistence as a
follow-up owning its own migration; P-054 is that follow-up.
`preset_bundles` stores the whole bundle as one canonical JSON
document (an aggregate — splitting it across columns would
invite partial writes that lose carried fields), name unique per
owner. `preset_overrides` assigns one bundle to one character
or chat with a partial delta; unique per (scope, owner).

## Overrides and resolution

Precedence: bundle base < character delta < chat delta. The
sampler merges key-wise — a delta key set to null DELETES the
base key, explicitly. Structural selections replace wholesale
when present (null clears). `GET /presets/resolve` returns the
effective bundle plus the SOURCE of every field (`bundle` /
`character` / `chat`, per sampler key), the applied rows, and
any shadowed row: when a chat assignment names a different
bundle than the character assignment, the chat wins outright and
the character row is reported in `shadowed`, never dropped
silently. No assignment anywhere resolves to an honest null.

## Sharing

`GET /presets/bundles/{id}/share` emits the P-045-style envelope
(`runmal-preset-bundle`, v1): manifest with a SHA-256 over the
canonical normalised bundle, provenance with unknown facts
omitted. Import re-normalises and verifies the checksum before
storing — tampered shares refuse (422); cosmetic re-serialisation
never invalidates. Bare bundle objects import too, reported as
`checksum_verified: false`.

## API

`POST/GET /presets/bundles`, `GET/PATCH/DELETE
/presets/bundles/{id}`, `POST /presets/bundles/import`,
`GET /presets/bundles/{id}/share`, `PUT/GET/DELETE
/presets/overrides/{scope_kind}/{owner_id}`,
`GET /presets/overrides`, `GET /presets/resolve?chat_id=&character_id=`.
Errors follow the house conventions: 422 malformed, 409 name
clash, 404 missing-or-not-yours.

## Carried limitations

- Resolution is a data service + API; wiring the resolved bundle
  into the live generation path is the composer's existing
  explicit-input road (P-049..P-051 resolvers) and is not changed
  here — no pipeline behaviour changes when no bundle is assigned.
- One active bundle assignment per character/chat (unique pair);
  layered multi-bundle stacks are not modelled.
