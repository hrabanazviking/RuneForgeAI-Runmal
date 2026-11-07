# Structured output — grammar/JSON-mode as a prompt citizen (P-061)

Roadmap line: *Grammar/JSON-mode where backends offer it, as a
prompt citizen (structured replies for bridges/games).*

Before P-061, `Capabilities.structured_output` existed but no
adapter set it True and no chat adapter sent any grammar or JSON
field on any wire. A preset could not ask for a structured reply,
the inspector could not show one, and nothing distinguished "the
backend enforces this shape" from "we hope and parse later".

## What shipped

- `src/runmal/backends/structured.py` — a pure module (no DB, no
  I/O, no HTTP) owning the declaration as data
  (`StructuredOutput`: `off` / `json_object` / `json_schema` /
  `grammar`, strictly validated by `structured_from_data` — a
  field carried by the wrong mode refuses even when present as
  `null`), the per-backend truth rows, the wire payload builders,
  the clamp-style planner, and a client-side validation
  companion. It is deliberately NOT a sampler: it never enters
  `SamplingParams` or the canonical sampler vocabulary.
- Truth, per backend: `openai` / `openrouter` serve both JSON
  modes via `response_format`; `ollama` serves both via the
  top-level `format` field of `/api/chat` (never inside
  `options`). Aesir's JSON modes are greyed `route_not_served`
  (provenance: the P-009 route matrix, which never recorded
  `response_format`); the fake's are greyed `not_declared`
  (scripted text cannot enforce a schema). `grammar` is greyed
  on EVERY current backend with `grammar_not_on_wire` — no wire
  in this tree carries a GBNF field. That is a recorded finding
  of this slice, not a gap to paper over.
- Adapters: `chat_stream` gains a keyword-only `structured=None`
  parameter (base class, all five adapters, the retry layer, and
  `generate_events`). Serving adapters build their field from
  `wire_payload`; `aesir` / `fake` refuse an ACTIVE unserved
  declaration loudly with `InvalidRequest` before any request is
  sent. `Capabilities.structured_output=True` for openai /
  openrouter / ollama only. With `structured=None` every existing
  caller — and every payload — is byte-identical to pre-P-061;
  the retry/generation passthrough passes the keyword only when
  a declaration is in play, so backends written against the old
  signature keep working.
- Planner: `plan_structured` degrades an unserved declaration to
  `None` WITH one structured warning naming the truth row's
  reason code — never silently kept, never silently dropped.
- Validation companion: `validate_reply` checks a finished reply
  on the client side (parse + a documented subset of JSON
  Schema: `type` / `required` / `properties` / `items` /
  `enum`). It is labelled validation everywhere, never
  enforcement; it never repairs a reply (code fences are not
  stripped); a schema using any other constraining keyword is
  `not_validatable` with the keyword named, never `ok`.
- Prompt citizen: `resolve_structured` / `structured_echo` in
  the prompt service (mirroring the P-058 policy pair);
  `inspect_prompt` gains `structured_output=` and ALWAYS carries
  the echo; the router field rides both inspect routes (invalid
  declarations surface as 422) and `GET /debug/structured-modes`
  serves the catalogue + matrix + audit. The echo is metadata
  only — mode, name, strict, and schema/grammar PRESENCE
  booleans; no schema or grammar content ever enters a trace,
  echo, or debug payload (S214).
- Preset bundles (P-054): `structured_output` is a known bundle
  section — validated and normalised like the other structural
  sections, wholesale-replace in merges, `null` override clears,
  carried by share/export.

## Carried limits

- No migration: a declaration is per-request / per-preset data.
  Head stays 0035; the provisional 0036 eyed by both P-060 and
  this slice was taken by neither.
- Per-model variance is not modelled: truth and the capability
  flag are per-BACKEND, so a specific upstream model that cannot
  serve a JSON mode is over-served by the row — the provider's
  own error is the honest failure there.
- No generation-turn wiring beyond passthrough: no chat route or
  bridge caller passes a declaration yet, and `generate_events`
  has no warning channel of its own — planner warnings surface
  to direct callers of `plan_structured` and in the inspector
  echo.
- The landed draft of `structured.py` from the cancelled first
  lead was truncated mid-audit and diverged from the approved
  design in its public names and truth shape; it was rewritten
  to the design by the finisher lead. The divergence is recorded
  in `hidden_files/P061_EVIDENCE.md`.
