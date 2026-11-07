# P-021 — Preset Interop (2026-10-31)

*Part II (Cards & Content Interop): sampler/prompt presets from
ST files imported into Rúnmál's preset system; Part IV gives
them depth. Acceptance in `tests/test_p021_preset_interop.py`
(50 tests), plus the two P-005 corpus pinning tests updated to
assert the real mapping.*

## The measured gap this slice closes

On entry there was **no ST-preset importer at all**: P-005's
corpus pinned both preset fixtures as well-formed and named
P-021 as their home. The mirror's own key spellings (`temp`,
`rep_pen`, `genamt`) rode through `validate_params` as opaque
unknowns — a user importing a community preset got a bag
Rúnmál's canonical consumers (S208 compat filtering, S301
`SamplingParams`, the S306 generation manifest) could not read,
and the chat shape's `prompts`/`prompt_order` had nowhere to
live at all. Two canonical fields the fixtures carry — `min_p`
and `context_length` — were not promoted in S207's canonical
validation either, though S301 already modelled both.

## What was built

`src/runmal/presets/interop.py`:

- `ImportedPreset` — `name`, the canonical parameter bag in
  `params`, `template_ref`, `source_format` (`native`,
  `st-text`, or `st-chat`), the chat shape's `prompts` and
  `prompt_order`, and the complete original object in `raw`.
- `parse_preset(bytes | str | dict)` — defensive import:
  non-UTF-8 bytes, malformed JSON, a non-object, an
  unrecognized flat object, an invalid prompt role, a
  non-list `prompts`, a prompt entry without an identifier,
  a non-boolean `enabled`, and inputs over 8 MiB are each
  rejected with a typed `PresetParseError`, never a bare
  exception. Numeric strings coerce, integral floats coerce
  to ints, booleans are never numbers, and a null mapped
  field is omitted (P-005's discipline).
- Name chain: a `name` key wins, then the text shape's
  `preset` key, then the fallback `Imported preset` (the
  chat fixture is nameless; the API's `?name=` import
  override exists for exactly that case).
- `export_preset(view, format=None)` — export starts from
  the carried `raw` and overlays the current canonical bag
  in the target shape's own spellings, so unknown-but-valid
  fields survive verbatim (INV-009) and keys removed from
  the bag stay removed. Same-shape re-export is a fixed
  point (pinned byte-for-byte in the tests). A target shape
  emits only set keys — no fabricated prompts, order, or
  seed. `PresetFileView` is the stored-preset view the API
  exports from.

### Mapping — text-completion shape (`st-text`)

| File key | Canonical |
|---|---|
| `temp` | `temperature` |
| `top_p` | `top_p` |
| `top_k` | `top_k` |
| `min_p` | `min_p` (promoted: canonical, 0..1) |
| `rep_pen` | `repetition_penalty` |
| `freq_pen` | `frequency_penalty` |
| `presence_pen` | `presence_penalty` |
| `genamt` | `max_tokens` |
| `context_length` | `context_length` (promoted: canonical, int >= 1) |
| `seed` | `seed` (`-1` is the unset sentinel: omitted from the bag, restored on export; `-2` is rejected) |
| `preset` | the preset's name |

`max_context_length` is **not** a source for `context_length`:
a file carrying only it imports with no `context_length` in
the bag (the key itself rides in `raw`).

### Mapping — chat-completion shape (`st-chat`)

| File key | Canonical |
|---|---|
| `temperature` | `temperature` |
| `top_p` | `top_p` |
| `frequency_penalty` | `frequency_penalty` |
| `presence_penalty` | `presence_penalty` |
| `max_tokens` | `max_tokens` (canonical spelling wins; `openai_max_tokens` is only the fallback) |
| `openai_max_context` | `context_length` |
| `prompts` / `prompt_order` | carried intact (below) |

### Carriage (stored, re-exported, not yet modelled)

Imported presets are stored with migration 0019's columns:
`source_format` plus `interop_json` holding
`{"raw": <complete original object>, "prompts": [...],
"prompt_order": [...]}`. `preset_to_dict` surfaces
`source_format`, `prompts`, and `prompt_order`; pre-0019 rows
read as `native` with empty carriage, and the portable
archive includes the new columns with the preset rows.
Carried fields keep their later Part IV homes:

- `prompts` / `prompt_order` (identifiers in order, `enabled`
  flags preserved) → P-049 prompt manager, P-051 context
  templates.
- `logit_bias` → P-060 logit bias & stop sequences.
- DRY (`dry_*`), dynamic temperature (`dynatemp_*`), XTC
  (`xtc_*`), `tfs`, `top_a`, `typical_p`, mirostat,
  smoothing, guidance, grammar and the rest of the mirror's
  sampler surface → P-052 sampler surface complete.
- `model` / `chat_completion_source` → P-062 multi-model
  prompt profiles.

### API

- `POST /presets/import?name=` — import a preset file
  (201; duplicate name 409; unparseable file 422). The
  optional `name` query parameter overrides the file's own
  name chain — the chat shape is nameless by design.
- `GET /presets/{preset_id}/export?format=` — export in the
  preset's source shape by default, or as `native`,
  `st-text`, or `st-chat` on request (404 unknown preset,
  422 unknown format). Both routes require auth, like the
  rest of the preset API.
- The imported bag is real against the existing systems:
  applied to a chat it drives the S306 generation manifest
  (S208 maps `repetition_penalty` to `repeat_penalty` and
  `max_tokens` to `num_predict` for Ollama, and drops
  `min_p`/`context_length` explicitly), and
  `SamplingParams.from_bag` consumes it unchanged. PATCHing
  a stored preset's params does not clear its carried
  prompts.

## Not in this slice

Prompt-manager editing of the carried blocks (P-049),
context-template assembly from them (P-051), the deepened
sampler surface (P-052), logit-bias execution (P-060), and
model-profile switching (P-062) keep their Part IV homes;
this slice is the file interop, the two canonical promotions,
and the lossless carriage those slices will consume.

## Clean-room basis

Own tree only, plus the shapes already logged: P-002's census
of SillyTavern's official public documentation (ST-34) and
P-005's authored corpus fixtures. No mirror source code was
read; no preset file was downloaded; the slice's extra test
presets are authored inline in the test module.
