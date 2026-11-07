# Sampler surface complete (P-052) — 2026-11-06

Roadmap line: *Sampler surface complete: every common sampler
(temp, top-p/k, min-p, repetition/presence/frequency, DRY,
XTC-class) exposed where the backend supports it, hidden
honestly where not.* Part IV (Prompt & Sampler Depth).

## The gap

The canonical vocabulary stopped at the S301 set of 11 bag
keys. The newer common samplers had no canonical home: a preset
could carry them only as opaque unknown keys that every typed
path (SamplingParams, S310 negotiation, S208 profiles) dropped
-- silently, because they were not even names the tree knew.

## What was built

- `src/runmal/backends/samplers.py` (NEW) -- the complete
  catalogue as DATA: 28 canonical bag keys as SamplerSpec
  (name, group, kind, range, public description) in
  presentation order -- core (temperature, top_p, top_k,
  min_p), cutoff class (typical_p, top_a, tfs_z,
  epsilon_cutoff, eta_cutoff), penalties (repetition, presence,
  frequency), DRY (dry_multiplier, dry_base,
  dry_allowed_length, dry_penalty_last_n,
  dry_sequence_breakers), XTC (xtc_probability,
  xtc_threshold), Mirostat (mirostat_mode, mirostat_tau,
  mirostat_eta), dynamic temperature
  (dynamic_temperature_range, dynamic_temperature_exponent),
  limits (max_tokens, context_length) and controls (stop,
  seed). `sampler_surface(model=None)` renders the surface:
  with a model, supported is the model's DECLARED capability
  truth; without one it is None -- undeclared, never guessed
  (the measured truth table is P-053, not built here).
- `backends/params.py` -- SamplingParams gains the 17 new
  fields with public-semantics validation (DRY base >= 1,
  XTC in [0,1], Mirostat mode 0..2, tau/eta > 0, breakers a
  tuple of non-empty strings); bag round-trip covers all 28
  keys; `with_merged_stops` carries the F3 merge.
- `presets/service.py` -- the canonical preset bag gains the
  same 17 keys with identical ranges (S207 parity).
- `backends/negotiation.py` -- CANONICAL_CONTROLS is now the
  catalogue itself, so controls/clamp/profile can never drift
  from the surface they negotiate.
- `generation/compat.py` -- the S208 profiles account for
  every new key: Ollama maps typical_p, tfs_z and the Mirostat
  trio (its public options carry them); OpenAI lists every new
  key as dropped with a reason; DRY/XTC/top-a/epsilon/eta/
  dynamic-temperature are dropped with reasons on both.
- Backend honesty: the Ollama adapter declares AND forwards
  typical_p, tfs_z, mirostat_mode (-> mirostat),
  mirostat_tau, mirostat_eta via its options dict. No backend
  declares DRY or XTC -- no adapter forwards them today, so
  the surface says so in data and clamp/map paths drop them
  with structured warnings. Aesir and OpenAI-compatible
  UNSUPPORTED_SAMPLERS now account, with SAMPLERS, for all 28
  canonical controls (the F-01/F-02 accounting tests pin it).
- Stop-string merge (P-050 F3, landed here as ordered):
  `merge_stop_strings` -- sampler stops first, template stops
  appended, duplicates removed, empties dropped, order
  preserved; `resolve_sampler_params(params, model,
  template_stops)` merges first, then capability-clamps.

## Migration

NONE. The surface is code/data, no schema. Head stays 0032.

## Carried findings

- F1: tests/test_f01_openai_compat.py hardcoded the
  pre-P-052 canonical set; updated in-slice to derive the
  vocabulary from the catalogue (the thing it pins is the
  accounting, not the old list).
- F2: no router/UI endpoint was added: the surface is
  consumed through the existing negotiation controls_dict
  path. A dedicated samplers endpoint belongs with the UI
  work that renders it.
- F3 (P-053 boundary): per-backend support above is DECLARED
  truth from each adapter's own forwarding code. The measured
  capability-truth table (greying by measured support) is
  P-053 and was not built here.
- F4: tests/test_p009_aesir_readiness.py pinned the exact
  pre-P-052 Aesir UNSUPPORTED set; extended in-slice with
  the 17 new keys (the accounting invariant it guards --
  SAMPLERS | UNSUPPORTED == canonical -- is unchanged).
- F5: the S208 Ollama profile was NOT extended with the
  pre-existing min_p/context_length wire names: P-021 pins
  their dropped behaviour there, and that profile's history
  is not this slice's scope. The Ollama ADAPTER (which does
  forward both) is unchanged in that respect.
