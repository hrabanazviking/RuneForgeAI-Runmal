# Logit Bias & Stop Sequences (P-060)

Per-preset, backend-honest. Roadmap Part IV: *Logit bias & stop
sequences: per-preset, backend-honest.*

## What a preset can now carry

Both controls live in the canonical sampler bag, so they ride
S207 presets and P-054 preset bundles (with per-character and
per-chat overrides) with no new storage and no migration:

- `stop` — a list of stop-sequence strings (canonical since
  P-052). Generation halts when the backend produces one.
- `logit_bias` — a JSON object mapping decimal token-id strings
  to bias numbers, e.g. `{"42": 1.5, "7": -2}`. The bias is
  added to that token's logit before sampling; the range is
  -100..100, the range the public OpenAI-shaped wire defines.
  In typed code it is `SamplingParams.logit_bias`, a tuple of
  `(token_id, bias)` pairs kept sorted by token id, so the typed
  form and the bag form are the same value either way round.

Validation is strict at every typed edge (unknown shapes,
duplicate token ids, bool masquerading as a number, biases out
of range all refuse with `ValueError`). The validated value
object and helpers live in `runmal/backends/logit_bias.py`:
`LogitBias`, `plan_text_bias`, `validate_stop_sequences`, and
`resolve_generation_controls`. The entry-count and stop
count/length caps there are local sanity limits of that layer,
named as such — they are not claims about any backend.

## Backend honesty

Support is declared per backend in the P-053 truth table
(`runmal/backends/capabilities.py`), proven from each adapter's
own wire code — a control is available only where the adapter
actually forwards it:

| backend | logit_bias | stop |
| --- | --- | --- |
| OpenAI-compatible | available (wire `logit_bias`) | available |
| OpenRouter | available (wire `logit_bias`) | available |
| Ollama | greyed — its native options publish no logit-bias control | available |
| Aesir (OpenAI chat route) | greyed — not served on that route | greyed — rejected field on that route (P-009 D2) |
| Fake (test) | greyed | available |

Aesir's native `/v1/generate` ledger row previously read as
"the full canonical set" by construction. Since P-060 it
carries one explicit carve-out: it does not claim `logit_bias`,
because the P-009 route matrix never recorded native logit-bias
service and nothing in-tree verifies it. The carve-out is data
(the ledger note names it) and the truth audit pins it.

At generation time, `resolve_generation_controls` merges the
preset's stops with the instruct template's stops under the
P-050 F3 precedent (sampler stops first, template stops
appended, duplicates removed, order preserved), then degrades
the merged parameters to the model's declared capabilities.
An unsupported bias or stop is cleared WITH a structured
warning (`unsupported parameter dropped: logit_bias`) — never
silently dropped, never pretended honoured (INV-005).

## Token ids are never invented

A bias entry names a token id — a number that only a tokenizer
can honestly assign to text. No in-tree tokenizer maps
arbitrary preset text to token ids for these backends, so
text-keyed bias is handled by `plan_text_bias`: entries resolve
ONLY through a token map the caller supplies explicitly. Every
entry that cannot be resolved stays in the plan as an
unresolved record with its reason as data
(`tokenizer_unavailable` with no map, `not_in_token_map` when
the supplied map lacks the text). Nothing guesses an id.

## Import boundary (unchanged by design)

Mirror-shaped preset files keep their foreign `logit_bias`
field in the raw interop carriage, exactly as the P-021/P-030
interop design established: the interop maps decide what
enters the canonical bag for imported files, and P-060 does
not rewrite them. Native presets and bundles carry
`logit_bias` canonically, as above.
