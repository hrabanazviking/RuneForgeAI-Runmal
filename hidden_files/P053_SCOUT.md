# P-053 Scout — Per-backend capability truth (base 6fc65f0)

## Roadmap text
"P-053 Per-backend capability truth: sampler controls grey by measured
backend support (Aesir's ledger included) — never fake sliders."
Part IV. Predecessors: P-051 (context templates), P-052 (sampler surface
complete) bank BEFORE P-053; neither is in base 6fc65f0. P-052 is committed
on team-02 as ed01f90, unbanked — see overlap flags in P053_EVIDENCE.md.

## What exists at 6fc65f0 (verified by reading the tree on purplelongship)

- `backends/params.py` — canonical `SamplingParams` (11 bag keys via
  `to_bag()`: temperature, top_p, top_k, min_p, repetition_penalty,
  presence_penalty, frequency_penalty, max_tokens, stop, seed,
  context_length).
- `backends/models.py` — `Capabilities.supported_samplers` (frozenset of
  canonical bag keys) + `ModelInfo`. No provenance/source, no display
  state, no reason codes.
- `backends/negotiation.py` (S310) — `negotiate_controls` /
  `controls_dict` / `clamp_params` / `profile_from_capabilities` driven
  by DECLARED capabilities only. `ControlDescriptor` carries
  name/kind/supported/detail — but no state (available/greyed/hidden),
  no machine-readable reason code, no source (declared vs ledger vs
  measured), no cross-backend matrix, no API route consumes it.
- Per-adapter sampler declarations (the raw truth, scattered):
  - aesir.py: `SAMPLERS` = {temperature, top_p, max_tokens, seed};
    `UNSUPPORTED_SAMPLERS` = {top_k, min_p, repetition_penalty, stop,
    presence_penalty, frequency_penalty, context_length}; SAMPLERS ∪
    UNSUPPORTED == canonical 11, disjoint. Docstring records the ledger
    fact (P-009 D2): the OpenAI chat route serves only that subset; the
    full canonical set is served on Aesir's native `/v1/generate` route.
    That ledger exists ONLY as prose in the docstring — not as data.
  - openai_compat.py: SAMPLERS (7) + UNSUPPORTED_SAMPLERS (4) ==
    canonical 11, disjoint.
  - ollama.py: SAMPLERS (9) incl. min_p + context_length; NO explicit
    unsupported set (canonical − SAMPLERS = {presence_penalty,
    frequency_penalty}).
  - openrouter.py: SAMPLERS (7); no explicit unsupported set
    (complement = {top_k, min_p, repetition_penalty, context_length}).
  - fake.py: SUPPORTED (5); complement = 6 controls.
- `generation/compat.py` (S208) — static wire profiles for openai +
  ollama ONLY. DRIFT FOUND (defect, fixed in this slice): OLLAMA_PROFILE
  wire_names lacks `min_p` and `context_length` although the Ollama
  adapter declares both in SAMPLERS — through the S208 path min_p is
  dropped as "unknown parameter is not forwarded" and context_length
  likewise, while the adapter's own `_options` honours both
  (min_p→min_p, context_length→num_ctx). Two truth sources disagree =
  a silently lost control. OPENAI_PROFILE similarly lacks explicit
  unsupported reasons for min_p/context_length (they fall into the
  generic "unknown" drop instead of an honest named reason).
- `backends/base.py::filter_params` + negotiation `clamp_params` already
  enforce INV-005 at generation time (unsupported fields cleared with
  warnings). The missing piece is the PRESENTATION truth layer: what
  the UI may offer, greyed, or must not offer — as data, per backend,
  before generation.
- No router exposes controls/capabilities for samplers today
  (prompt/router.py hosts the /debug/* data surfaces, e.g.
  instruct-templates from P-050 — the pattern this slice follows).
- P-008 ledger (docs/BACKEND_PARITY_LEDGER_2026-10-30.md) judges mirror
  backends; Aesir's own route ledger (P-009) is the "Aesir's ledger"
  the roadmap line names.

## Gap P-053 must close
1. One capability-truth module where, per backend+model, EVERY
   canonical sampler control is accounted for exactly once as
   available / greyed (with reason as data) — and non-canonical names
   are hidden (never offered).
2. Truth carries provenance: source (adapter declaration vs Aesir's
   ledger) + reason_code + human reason, all as data.
3. Aesir's ledger as data: both routes (OpenAI chat route subset,
   native /v1/generate full set) with the route a truth row is judged
   against made explicit.
4. A cross-backend matrix + a consistency audit that FAILS LOUD when
   any truth source drifts (adapter sets vs canonical accounting,
   S208 profiles vs adapter declarations).
5. An API surface in the P-050 /debug pattern so the UI renders
   greying from this data and nothing else.
6. Fix the S208 Ollama/OpenAI drift (discovered bug; never left
   unfixed) so all truth sources agree; audit pins the agreement.
