# Backend Capability Truth (P-053) — 2026-11-06

Part IV of the Two Mirrors parity roadmap: *sampler controls grey by
measured backend support (Aesir's ledger included) — never fake
sliders.*

## The contract

For every chat backend, every canonical sampler control
(`temperature`, `top_p`, `top_k`, `min_p`, `repetition_penalty`,
`presence_penalty`, `frequency_penalty`, `max_tokens`, `stop`,
`seed`, `context_length`) is in exactly one state, as data:

| State | Meaning | UI behaviour |
|---|---|---|
| `available` | The backend serves the control | Offer it, enabled |
| `greyed` | Canonical, but this backend does not serve it | Show it disabled, with the reason |
| `hidden` | Not a canonical control at all | Never offer it |

A greyed row always carries `reason_code` + `reason` + `source`; an
available row carries its `wire_name`. Nothing is offered on a guess,
and nothing unsupported is ever presented as if it would be honoured
(INV-005, extended from generation time to presentation time).

## Truth sources — and their limits

Rows are judged from the adapters' own published sampler sets,
imported (never copied) by `runmal/backends/capabilities.py`, so the
presentation layer cannot drift from the code that sends requests.
Each row names its provenance in `source`:

- `declared` — the adapter's declaration (fake, ollama, openrouter,
  openai).
- `ledger` — Aesir only: Aesir's published v1 route matrix (P-009
  D2). Aesir's OpenAI chat route — the route this adapter speaks —
  serves `{temperature, top_p, max_tokens, seed}`; its native
  `/v1/generate` route serves the full canonical set. Both ledger
  rows are data (`AESIR_LEDGER`); a truth row names the route it was
  judged against, and the native row is labelled as the ledger's
  record, not a promise this adapter keeps.

No row claims to be *measured*: nothing in this tree probes a live
server for sampler support, so no row says it did.

## Per-backend truth (default models, adapter route for Aesir)

| Backend | Available | Greyed |
|---|---|---|
| fake | temperature, top_p, max_tokens, stop, seed | top_k, min_p, repetition_penalty, presence_penalty, frequency_penalty, context_length |
| ollama | temperature, top_p, top_k, min_p, repetition_penalty, max_tokens, stop, seed, context_length | presence_penalty, frequency_penalty |
| openrouter | temperature, top_p, max_tokens, frequency_penalty, presence_penalty, stop, seed | top_k, min_p, repetition_penalty, context_length |
| aesir | temperature, top_p, max_tokens, seed | top_k, min_p, repetition_penalty, stop, presence_penalty, frequency_penalty, context_length |
| openai | temperature, top_p, max_tokens, frequency_penalty, presence_penalty, stop, seed | top_k, min_p, repetition_penalty, context_length |

## The audit

`capabilities.audit_truth()` returns drift findings (empty = healthy)
across all truth sources: adapter set partitioning, default-model
agreement, S208 profile agreement, and ledger agreement. The
`/debug/backend-capabilities` payload includes the audit, so a
drifted tree is visible in the very payload the UI consumes.

Building this audit found a live drift, fixed in this slice: the
S208 `OLLAMA_PROFILE` dropped `min_p` and `context_length` as
"unknown" although the Ollama adapter declares and honours both
(`min_p`, `num_ctx`). The profile now maps them exactly as the
adapter does, and `OPENAI_PROFILE` names honest reasons for its
unserved `min_p` / `context_length` instead of the generic
unknown-parameter drop.

## API

- `GET /api/v1/debug/backend-capabilities` — matrix for all five
  backends + audit.
- `GET /api/v1/debug/backend-capabilities/{backend_key}` — one
  backend's default-model truth; `?aesir_route=native-generate`
  shows Aesir's ledger native row-set. Unknown backend → 404.

## Relationship to neighbours

- S310 negotiation (`negotiation.clamp_params`) remains the
  generation-time enforcement; P-053 is the presentation-time truth
  and the battery pins that both agree exactly.
- P-052 (sampler surface complete) extends the control vocabulary
  when it banks; because every P-053 row derives from the adapters'
  declared sets, new controls flow through the same accounting as
  soon as adapters declare them — the audit will flag any that are
  declared in one source but not accounted in another.
