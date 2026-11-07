# Prompt preview (P-059) — 2026-11-07

Roadmap line: *Prompt preview: the exact final prompt (per backend
rendering) inspectable before send — the glass box the Inspector
(Part XIII) also uses.*
Part IV (Prompt & Sampler Depth).

## What was built

- `src/runmal/prompt/preview.py` — the preview as data, built
  from a composition that already happened, nothing more.
  `build_preview(messages, rendered, *, backend_key, model_id)`
  takes ONLY the composed messages plus the `RenderedPrompt`
  that `inspect_prompt` already produced — it never composes
  and never re-renders. There is one composition and one
  render, and the preview reads both as-is, so the preview can
  never drift from the composition it previews (the P-044
  one-source-of-truth pattern: one source, never a second
  counter or renderer beside it).
- `preview_from_composed(composed, rendered, **kwargs)` is the
  convenience helper on the same road: it passes
  `composed.messages` (from an object or a mapping) straight
  to `build_preview` and adds no logic of its own.
- Known backends: `KNOWN_BACKENDS` is the import-time
  snapshot derived from the `backend_key` rows of the
  public `capability_matrix()` in
  `runmal.backends.capabilities`; no provider-name
  literals anywhere in `preview.py` (S706).
  `known_backend_keys()` derives the set fresh from
  that public surface on each call and falls back to
  `KNOWN_BACKENDS` when that surface cannot be built
  (for example, offline), or yields nothing. A test
  pins `KNOWN_BACKENDS` equal to the matrix keys, so
  drift between snapshot and registry fails loud
  instead of silently mislabelling a backend.
- `src/runmal/prompt/inspect.py` — `inspect_prompt` gains
  `include_preview` (default `False`) and `backend_key`
  (default `None`). With the preview on, the result gains a
  `prompt_preview` key built by `build_preview` from the very
  composed messages and the very `RenderedPrompt` that same
  call already computed. See Honesty for what stays unchanged
  when it is off — and what stays unchanged even when it is on.
- `src/runmal/prompt/router.py` — `InspectRequest` gains
  `include_preview` and `backend_key`, carried through the
  existing `POST /debug/prompt-inspect`. A new
  `POST /debug/prompt-preview` forces the preview on and
  returns the full inspect result, so the Part XIII Inspector
  reuses one payload — trace, echoes, and preview together —
  rather than needing a second, differently-shaped response
  to stitch in.

## The payload

`prompt_preview` is a plain JSON-shaped dict:

- `available: True`, `backend_key` and `model_id` echoing the
  selection the preview was built for (either may be `None`
  when none was named).
- `form: "structured_messages"` — the honest name of the form
  a backend actually receives today (see the next section).
- `messages`: one `{role, content, slot_id}` per composed
  message, in composition order. `slot_id` is included when
  the message carries one, else `None`; this is the preview's
  own labelled view, tying each message back to the slot that
  produced it.
- `wire_messages`: one `{role, content}` per composed
  message — exactly the `ChatMessage.to_dict` shape, the
  structured form every chat backend in this tree receives.
  No `slot_id`, no rendering, nothing added.
- `text`: Rúnmál's instruct rendering of the same messages,
  taken as-is from the `RenderedPrompt` — the text produced
  by the one `render_prompt`, never a re-render by the
  preview itself.
- `template_name` and `stop_strings`: also from that same
  `RenderedPrompt`, as data travelling with the render.
- `rendered_tokens`: counted from that same rendered text,
  and equal to the inspect result's own top-level
  `rendered_tokens` for the same call — the same figure, not
  a second count computed by a second road.
- `note`: a plain-language sentence, in the data itself,
  stating which form the backend receives and who applies
  the chat template (see the next section). When a backend
  was named, the note names it; otherwise it speaks of
  backends generally.

## Per-backend honesty

- All five known backends — `fake`, `ollama`, `openrouter`,
  `aesir`, and `openai` — receive structured messages today.
  Their adapters build their wire payloads from the
  structured messages; none of them receives the rendered
  string.
- No backend receives `text`. The rendered string is
  Rúnmál's instruct rendering, shown so the owner can read
  the prompt as one text — but the provider applies its own
  chat template server-side. Labelling the rendered string
  as "what the backend receives" would be false, so the
  payload does not: `form` says `structured_messages`, and
  the `note` field says the same in words — the backend
  receives `wire_messages`; `text` is Rúnmál's rendering of
  the same messages; the provider applies its own template.
  The honesty is in the data, not only in this document.
- An unknown backend is never given an invented rendering.
  If `backend_key` is named and is not in
  `known_backend_keys()`, `build_preview` raises
  `ValueError`, and the router maps that to 422 — on both
  preview routes. A refused name is the honest answer; a
  fabricated per-backend rendering would not be.

## What the preview is not

- The preview is not a capture of a live send. Live
  generation (`/generate`) does not yet route through the
  composer or the inspector, so nothing here claims it does.
  The preview shows exactly what this composition pipeline
  will hand a backend — the composed messages in the
  structured form a backend receives, plus Rúnmál's rendering
  of them — not a recording of a send that happened by
  another road. This carried honesty comes from the P-059
  scout, which found the divergence; the slice documents it
  rather than papering over it.

## Honesty notes

- Opt-in, off by default: `include_preview` defaults to off,
  and with it off the inspector's behaviour is byte-identical
  to pre-P-059 — no `prompt_preview` key, same pipeline, same
  trace. The dedicated `/debug/prompt-preview` route is the
  explicit way to ask for it without setting the flag.
- The S214 trace still carries no content, even when the
  preview is on. `prompt_preview` is a separate top-level key
  beside the trace — a separate, explicit, owner-scoped
  payload — not an extension of the trace itself. Turning the
  preview on does not loosen the trace by one field.
- The author's note follows the same split, deliberately in
  both directions. An active author's note is prompt content,
  so its text appears in the preview's `messages` /
  `wire_messages` when it fires — that is the point of a
  preview: it is prompt content the owner asked to see. It
  still never appears in the trace, in the metadata-only
  `authors_note` echo, or in events, exactly as P-056 held.
  Preview visibility is not a leak into any of those surfaces.
- Counting is one figure, shared: the preview's
  `rendered_tokens` is the inspect call's `rendered_tokens`,
  from the same rendered text by the same estimator — never a
  second counter that could disagree with the first.

## No migration, no stored state

There is no migration in this slice and no stored state.
The preview is a pure read/render over a composition built
for the call that asked for it: nothing is written, nothing
is persisted, and nothing about a preview survives the
response that carries it.

## P-058 note

The token-budget governor (P-058) is not in this slice's
base — it banks immediately before P-059, in roadmap order.
The preview was therefore built without assuming any of its
keys, and composes additively with it when it lands: the
preview adds its own separate top-level key and reuses the
same `rendered_tokens` figure the inspect result already
carries, rather than introducing a second counter that a
governor would then have to reconcile with.

## Clean-room

Built from the roadmap line and Rúnmál's own composer,
renderer, and backend contracts alone; no third-party
prompt-preview implementation was copied or consulted.
