# Prompt import/export packs (P-063)

Roadmap line: *Prompt import/export packs (with Part XII sharing).*

## What a pack is

A prompt pack (`src/runmal/presets/packs.py`) gathers many prompt
artefacts into ONE portable JSON file — format `runmal-prompt-pack`,
version 1, schema `runmal-p063-prompt-pack-v1` — that another Runmal
install can verify, inspect, and import piece by piece. Part XII's
sovereign hub (P-187..P-202) carries packs unchanged, exactly as it
carries P-045 lorebook packs; `inspect_pack` is its pre-flight.

Item kinds, each validated and normalised by its own existing
validator: `bundle` (P-054 preset bundle), `preset` (S207 sampler
preset with its P-021 carriage), `instruct_template` (P-050 data
form), `context_template` (P-051 data form), `prompt_layout`
(P-049 data form).

## Integrity and provenance

Every item carries the SHA-256 of the canonical JSON of its
normalised payload; the pack `content_sha256` covers the pack name
plus the normalised item list in carried order — item order is part
of pack identity, and a reordered or altered file refuses.
Cosmetic re-serialisation (whitespace, key order) never invalidates
a pack: identity is over normalised content, never raw bytes.
Provenance follows the P-029 rules: unknown facts are omitted,
never fabricated; it is carried by the pack and the import report,
never stored on a row.

## What import stores — and what it honestly does not

- `bundle` and `preset` items are stored through the existing
  P-054 / S207 services. Import never overwrites: an exact
  duplicate is reported `duplicate_exact` and left unwritten; a
  name collision is stored under `<name> (imported)` (then
  `(imported 2)`, ...) and reported `renamed` under the default
  `on_conflict="create_new"`, or reported `rejected` and left
  unwritten under `on_conflict="reject"`. Outcomes are per item;
  the report is the whole truth.
- `instruct_template`, `context_template` and `prompt_layout`
  items have no library table — P-049/P-050/P-051 each deferred
  that persistence to a migration-owning follow-up that has not
  landed. Import validates them and returns them in the report as
  portable data (`validated_not_stored`, reason
  `no_library_home_p049_p050_p051_deferred_persistence`). They are
  never claimed stored and never silently dropped. A receiver can
  use them per-request or fold them into a bundle today.
- Unknown-field carriage exists exactly where the owning layer
  already provides it: bundle `extensions`, the preset bag and
  `raw` carriage, item `extensions`, pack-level `extensions`.
  Template and layout payloads stay strict per their own
  contracts and refuse unknown keys.

## API

On the presets router: `POST /presets/packs/export` (owned
bundles/presets by id, or all when the id lists are omitted, plus
caller-supplied items), `POST /presets/packs/inspect` (validate +
report, imports nothing), `POST /presets/packs/import`
(`?on_conflict=create_new|reject`).

## Limits and non-claims

Local caps, named as local: 16 MiB pack size, 500 items. No
migration in this slice (head stays 0035): packs are file-layer
artefacts in the P-019/P-045 pattern. A malformed pack — envelope,
version, manifest, any checksum, any item — refuses whole before
any write exists.
