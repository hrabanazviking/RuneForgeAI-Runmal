# P-053 Design — Per-backend capability truth

## Principle
A sampler control is a promise. This slice makes the promise-keeping
data: for every backend, every canonical control is in exactly one
state, decided by the backend's own declaration (or, for Aesir, its
published route ledger) — never by a UI guess, never by provider-name
conditionals in the presentation layer.

## States (as data)
- `available` — the backend declares the control; the UI may offer it
  as an enabled slider/field. reason_code `supported`.
- `greyed` — the control is canonical but the backend does not serve
  it; the UI shows it disabled WITH the reason. reason_codes:
  `route_not_served` (Aesir OpenAI route), `not_declared` (all other
  backends), `profile_not_served` is NOT used — S208 reasons surface
  through the audit, not per-row.
- `hidden` — a name that is not a canonical control at all; it is
  never offered, for any backend. `truth_for_control` reports it with
  reason_code `unknown_control`; it never appears in a model's rows.

## Module: `src/runmal/backends/capabilities.py`
- `CANONICAL_CONTROLS` re-exported from negotiation (single vocabulary).
- `ControlTruth` (frozen dataclass): name, kind ("sampler"), state,
  supported, reason_code, reason, source, wire_name (adapter wire name
  where the adapter publishes one, else the canonical name when
  supported, else None). `to_dict()` JSON-ready.
- `SOURCE_DECLARED = "declared"`, `SOURCE_LEDGER = "ledger"`.
  No row claims "measured": nothing in this tree probes a live server
  for sampler support, so no row may say it did. (Honesty about the
  truth's own provenance is part of the contract.)
- `AESIR_LEDGER`: tuple of `LedgerRoute(route, served, note)` —
  `openai-chat` → aesir.SAMPLERS; `native-generate` → all canonical
  controls. Both notes cite P-009 D2 / the aesir.py binding truth.
- `declared_samplers(backend_key)` / `unsupported_samplers(backend_key)`
  read the ADAPTERS' OWN published sets (imported, never copied), so
  the truth layer cannot drift from the adapters without the audit
  noticing. Backends without an explicit unsupported set derive it as
  canonical − declared; that derivation is itself recorded in the row
  source detail.
- Reason text: adapter-published explanations first (aesir /
  openai_compat UNSUPPORTED membership + ledger notes; S208 profile
  reasons for ollama/openai where they exist), else a plain
  "does not declare" sentence naming backend + model.
- `truth_for_model(model, *, aesir_route="openai-chat")` → rows for a
  ModelInfo (works for ANY model, including ones a profile selects).
  For Aesir models the judged route defaults to the route this
  adapter actually speaks (OpenAI chat); passing
  `aesir_route="native-generate"` shows the ledger's other row-set
  without changing what the adapter will send.
- `truth_for_backend(backend_key)` → rows for the backend's default
  model (constructed offline; adapters do no network at construction).
- `capability_matrix()` → {backend_key: truth_dict} for exactly the
  five CHAT_BACKENDS, in registry order.
- `audit_truth()` → list of drift findings (empty == healthy):
  (a) adapters with explicit SAMPLERS+UNSUPPORTED must partition the
  canonical set exactly (no overlap, no gap); (b) every adapter's
  declared set must equal its default model's supported_samplers;
  (c) each S208 profile's wire+unsupported keys must agree with its
  adapter's declared set (this catches the scout's drift class);
  (d) the Aesir ledger's openai-chat row must equal aesir.SAMPLERS.
- `filter_truth(params, model)` convenience: partitions a bag's keys
  into (offered, greyed) by truth — the sampler layer's pre-flight
  mirror of clamp_params, returning rows not warnings.

## API (P-050 /debug pattern, `src/runmal/prompt/router.py`)
- `GET /debug/backend-capabilities` → `{"backends": [truth_dict...],
  "audit": [...]}` — audit included so a drifted tree is visible in
  the same payload the UI consumes; non-empty audit is data, not a 500.
- `GET /debug/backend-capabilities/{backend_key}` → one truth_dict;
  404 for an unknown backend key. Optional `?aesir_route=` query on
  the single-backend route for the ledger's native row-set.

## Compat drift fix (`src/runmal/generation/compat.py`)
- OLLAMA_PROFILE gains `min_p → min_p` and `context_length → num_ctx`
  wire names (exactly the adapter's own `_OPTION_NAMES`).
- OPENAI_PROFILE gains explicit unsupported reasons for `min_p` and
  `context_length` (named honesty instead of "unknown parameter").
- S208 battery bags don't cover these keys, so existing pins stand;
  the P-053 battery pins the new mappings + the audit agreement.

## No migration. No new dependencies. Adapters untouched.
P-052 overlap: P-052 (team-02 ed01f90, unbanked) extends the sampler
VOCABULARY (DRY/XTC-class). This slice is built against the 11-control
canonical vocabulary at 6fc65f0; when P-052 banks first, the keeper
reconciles by extending CANONICAL_CONTROLS — every P-053 row derives
from the adapters' declared sets, so new controls flow through the
same accounting automatically once adapters declare them. Flagged in
evidence.
