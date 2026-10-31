# P-016 — Character Card v3 Import, The Written Mapping (2026-10-31)

*Part II (Cards & Content Interop), second slice: character card v3
import — the newer spec's additions (assets, creator metadata,
group-only fields) mapped to Rúnmál's model with a written mapping.
Acceptance in `tests/test_p016_card_v3.py` (12 tests).*

## The measured gap this slice closes

The founding importer already *read* v3 files (fields under the
`data` envelope, S104), and P-005 proved the v3 additions travel:
its corpus card's `assets` array, `group_only_greetings`, and
`nickname` survive a v3 export round trip. But they survived only
as **opaque unknowns in `raw`** — no part of Rúnmál could ask a
card for its group greetings, its declared assets, or its creator
metadata, because the normalized model had no fields for them.
This slice gives the v3 additions first-class homes, in the
P-015 pattern.

## The mapping (v3 spec field → normalized model)

All fields live under `data` in the file, as in v2 (P-015's
envelope rule is unchanged). Recognition is **by field name**:
the v3 spec is where these fields are defined, and a v1/v2 file
that carries one gets it normalized rather than left opaque.

| Spec field (`data.…`) | Model field | Type / rule |
|---|---|---|
| `nickname` | `nickname` | string; non-string → `""` |
| `group_only_greetings` | `group_only_greetings` | string list; non-string members dropped, never stringified (P-005 rule) |
| `creator_notes_multilingual` | `creator_notes_multilingual` | string→string mapping; entries with a non-string key or value dropped |
| `source` | `source` | string list, same list rule |
| `creation_date` | `creation_date` | Unix seconds: int, or integral float; bools, strings, and fractional floats are not timestamps → `None` |
| `modification_date` | `modification_date` | same rule |
| `assets` | `asset_refs` | declared asset **descriptors** — see below |

Creator metadata that was already first-class stays so:
`creator` and `character_version` (P-015) are the spec's creator
fields alongside `creator_notes` / `creator_notes_multilingual`.

### Declared assets are descriptors, not bytes

The v3 `assets` array declares assets (`{type, uri, name, ext}` —
icon, emotion, background, …) whose bytes may be embedded in a
CHARX, referenced by `embeded://` URI, or remote. The model's
existing `assets` dict holds embedded **bytes** (CHARX, S113), so
the descriptors land in a separate field, `asset_refs`:

- each entry must be an object; non-object entries are dropped,
  never coerced;
- entries are copied **verbatim** — keys beyond the spec's four
  are the format's own extension room and ride along (INV-009);
- `CharacterCard.find_asset_ref(asset_type=…, name=…)` finds a
  descriptor; `resolve_asset(uri)` still resolves embedded bytes,
  so a declared `embeded://` URI and its bytes meet at call sites
  (pinned by the CHARX round-trip test).

Storage and animation of asset packs are P-023 / Part X — this
slice maps the declarations, it does not build the library.

## Export is the other half of the mapping

- **v3 export** writes the full addition set at the data level:
  the five structural fields always; `creation_date` /
  `modification_date` only when the card carries them — an
  absent timestamp is omitted, never fabricated as `0` or `null`.
- **v2 export** (including PNG, and the character service's
  storage path, which stores through `export_json(card, "2")`)
  writes only the additions that are **set** (differ from their
  defaults), at the same level as the v2 known fields. A v3 card
  stored as v2 therefore keeps its group greetings, nickname,
  source, timestamps, and declared assets; a plain v2 card gains
  no v3 keys.
- Unknown fields at both envelope levels still survive verbatim,
  exactly as P-015 pinned; no existing pin was changed.

## Clean-room basis

Behaviour and format shape only, from public sources: the public
Character Card v3 specification (the `data`-envelope field set
and its v3 additions — `assets`, `nickname`,
`creator_notes_multilingual`, `source`, `group_only_greetings`,
`creation_date`, `modification_date`), already logged in the
clean-room log's §1 founding ledger and exercised by P-005's
authored corpus. No SillyTavern or Voxta source code was read —
neither project is the source of the card spec — and no card file
was downloaded; the test cards are authored fresh in the test
module, P-005's discipline. Full entry appended to
`docs/CLEAN_ROOM_LOG_2026-10-30.md`.

## Suite

Full suite re-run this tick on the VM (sanitised proxy env, per
the P-007 standing instruction) — counts recorded in
`CAMPAIGN_STATE.md`. This slice adds 12 tests.
