# Model profiles (P-062) — 2026-11-07

Roadmap: *Multi-model prompt profiles: one chat, swappable model
profiles with their own templates/samplers (the mirrors'
connection profiles, sovereign-shaped).*

A model profile (`runmal.prompt.model_profiles`) binds, as one
swappable unit: a model (`model_id`, optional `backend_key`), its
instruct template selection (P-050), its context template
selection (P-051), its prompt layout (P-049) and its sampler set
(P-052). The selection and sampler shapes are exactly P-054's
bundle shapes, so the vocabularies cannot drift; unknown top-level
keys are preserved under `extensions`; malformed known sections
refuse. Validation is a fixed point and there is **no migration**:
a profile is pure data in the P-049 pattern, supplied per request.
Persisting profiles per owner/chat is a follow-up slice owning
its own migration.

Resolution precedence is per field: explicit per-request value >
profile value > the existing resolvers' own defaults. A profile
naming only a model still receives that model's honest P-050
default template. Every field's source is reported in the
inspect result's `model_profile` echo — metadata only (no prompt
content, no sampler values, no extension values; S214).

Sampler honesty is P-053's: when a profile names a known backend,
its canonical sampler keys are partitioned against that backend's
declared set — offered keys pass, greyed keys are reported with
their truth reasons, non-canonical keys are carried-unknown and
never offered. No backend named means no partition is claimed.

Switching is data: `diff_profiles` (and
`POST /debug/model-profile-diff`) reports what changes between
two profiles and the fixed carries list — history, character,
lorebooks, author's note, post-history instructions — the chat
state no profile governs and a switch never touches. Builtins
(`default`, `chatml-general`, `llama3-instruct`) invent no model
ids; binding a concrete deployment model is user profile data.
`GET /debug/model-profiles` lists them.

Boundary: generation does not route through the composer in this
tree (P-059 scout finding), so profiles govern the
composition/inspection path that exists. Live generation wiring
is a separate future slice and is not claimed here.
