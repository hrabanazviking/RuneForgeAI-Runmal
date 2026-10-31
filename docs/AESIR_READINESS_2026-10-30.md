# P-009 — Aesir Readiness Check (2026-10-30)

*What Aesir serves today for chat — from Aesir's own ledger — so
parity slices bind to truth, not hope. Rúnmál's side is this tree,
read directly. Aesir's side is Aesir's own versioned statements in
its own repo (see Sources); no Aesir source code was copied and no
feature was redesigned from it — this is a surface-compatibility
check against Aesir's published-in-repo API matrix, the same
clean-room posture as the mirror censuses, applied to Volmarr's
own engine.*

## Headline

**Aesir chat through Rúnmál's adapter is NOT PROVEN live, and as
shipped it would fail against Aesir's real server.** Every proving
test the adapter has ever passed (S701–S706) ran against recorded
fixtures or mock transports; Campaign VII's own close records
"Rúnmál-side only — nothing on Mimir/the Pi was touched"
(`docs/STATUS.md`). No live Aesir server has ever been on the other
end of this adapter. Worse, three adapter assumptions contradict
Aesir's served surface outright (D1, D2, D4 below): the first
request a real deployment sends would be refused. The divergences
are small and repairable, and this ledger flags the repair to the
Part I gate (P-014) as its first recommendation — but no parity
slice may treat "Aesir-ready" as a fact until the repair lands
and a live smoke has run.

## Sources (Aesir's own ledger)

Read 2026-10-30 in the Aesir repo checkout on this VM
(`~/workspace/RuneForgeAI-Project-Aesir`, HEAD `1eed9706`, branch
`platform/cloud-hypervisor-epyc`, tree dirty with unrelated work —
surface claims therefore rest on the versioned documents, not on
working-tree code):

- `docs/API_SUPPORT_MATRIX_V1.md` — the v1 supported subset:
  routes, accepted fields, streaming state (S18/S19), the strict
  Boolean JSON subset (S23), Gemma single-function tool calls
  (S24). The newest versioned API statement in that tree.
- `CAPABILITY_LEDGER.md` — AES-SRV-005/006/008/010 (ledger version
  S19, 2026-09-22): "streaming usage options remain
  unproved/unsupported" (SRV-005); the OpenAI route is "one loaded
  text model, one choice, strict field subset, **no embeddings**
  or general tool-result continuation" (SRV-006); the Ollama
  subset has "no pull/create/delete, **embeddings**, tools,
  multimodal input or remote access" (SRV-008).
- `docs/NATIVE_SERVICE.md` — ports, modes, auth, bounds.
- `docs/CURRENT_STATUS.md` (2026-10-01) — "Embeddings remain
  Ollama" on the Bifröst line; the native service is an
  authenticated loopback `serve` with one loaded model.

Evidence boundary: Aesir work after those documents (the Part II
continuation, the Hailo road) published no v2 API matrix in that
repo, so this check binds to the v1 matrix as Aesir's latest own
statement. If Aesir's surface has moved since S24, this check is
stale in exactly the way its pinning tests are built to expose on
the Rúnmál side, and it must be re-run — it is a readiness check,
not a one-time verdict on Aesir.

## Verdict vocabulary

- **READY** — Rúnmál's assumption matches Aesir's served truth.
- **READY-IF-CONFIGURED** — matches only when the profile's
  `base_url`/secret reference are set to Aesir's real values;
  the shipped default does not match.
- **DIVERGENT** — the assumption contradicts the served truth:
  the request fails, or a declared capability is not honoured.
- **NOT SERVED** — Rúnmál consumes a surface Aesir does not have.
- **UNCONSUMED** — Aesir serves it; Rúnmál does not use it today.
- **NOT PROVEN LIVE** — shapes agree on paper; no live run joins
  them. This qualifier applies to every READY row in this ledger.

## 1. What Rúnmál assumes (from this tree)

The Aesir chat adapter (`src/runmal/backends/aesir.py`, S701/S702):

- `POST {base_url}/chat/completions`, SSE streaming, with
  `stream_options: {"include_usage": true}` sent on **every**
  request; `GET {base_url}/models` for listing and health.
- Default `base_url` is `http://127.0.0.1:8000/v1` (also the
  doctor's assumed default, `diagnostics/doctor.py`); default
  model placeholder `local-model`. Profiles may override
  `base_url` via `config.base_url` and supply a bearer key via a
  secret reference (S306; `tests/test_s701_aesir.py`).
- Declared sampler truth (S702, BACKEND_CONTRACT §12): honours
  temperature, top_p, top_k, min_p,
  repetition_penalty→`repeat_penalty`, max_tokens, stop, seed;
  declares presence/frequency penalty and context_length
  unsupported. `map_params` is the single wire path.
- Parses streamed `usage` into `UsageUpdate`; model entries read
  `id` (required) plus optional `name`, `context_length`,
  `max_output_tokens` (fixtures: `tests/fixtures/backends/
  aesir_models.json`, `aesir_chat.sse`).
- The Aesir embedding backend (`backends/embeddings.py`, S703)
  posts to `{base_url}/embeddings` and degrades through
  `embed_or_fallback` to the FTS contract on any failure.
- The S705 benchmark compares adapters over **recorded streams**
  (`docs/BENCHMARKS.md`), not a live server.

## 2. What Aesir serves (its own matrix, v1)

Loopback only (`127.0.0.1`, no external-listen option), one
resident model, requests serialized, every connection closed
after its response, bearer <redacted> mandatory in native mode and
absent in `--ollama` mode. Generation with a non-resident model
returns 404; catalog visibility does not imply runnable.

| Route | Modes | Notes from the matrix |
|---|---|---|
| `POST /v1/chat/completions` | both | Strict field subset (§3, D2); SSE when `stream:true`: role-delta first, terminal choice with `stop`/`length`, exactly one `data: [DONE]`; **no usage in stream** |
| `POST /v1/completions` | both | Text-completion paradigm, one choice, `usage` in the JSON body |
| `POST /v1/generate` | native | Native route; the **full** sampler set (temperature, top_k, top_p, min_p, repeat_penalty, seed, max_tokens) |
| `GET /v1/models` | both | `data[]` carries only `id`, `object:"model"`, `created`, `owned_by` — no name, no context length, no max output |
| `GET /health`, `/health/live`, `/health/ready` | native | Legacy + schema-v1 liveness/readiness (resident model identity/profile/context) |
| Ollama subset (`/api/chat`, `/api/generate`, `/api/tags`, `/api/ps`, `/api/show`, `/api/version`) | `--ollama` | Options include top_k/min_p/repeat_penalty/seed; `num_ctx` must **equal** the loaded context exactly |
| `POST /v1/embeddings` | — | **Does not exist.** No embeddings route in either mode (SRV-006/008) |
| Vision / multimodal input | — | **Rejected on every generation route** (`images` and multimodal content are refused fields) |

Ports and auth: native `serve` defaults to port **18434**
(`--port` 1024..65535); `--ollama` mode binds **11434**. Chat
bounds: at most 128 messages, text fields at most 64 KiB, POST
body at most **131072** bytes, roles system/user/assistant with
string content only, final message must be from the user.
Context/generation admission failures return **422**; native
errors are `{"error":{"code":N,"message":"..."}}`. Post-header
failures can end a stream **without** a terminal/[DONE] marker —
the matrix instructs clients to treat EOF without the terminal
as incomplete. Two bounded extras exist on the OpenAI routes: a
strict Boolean-only `response_format` subset (S23) and Gemma-4
single-function, zero-argument, non-streaming tool calls (S24).

## 3. The divergences

- **D1 — `stream_options` breaks every chat request. DIVERGENT.**
  The adapter sends `stream_options.include_usage` unconditionally;
  Aesir's chat route lists `stream_options` among **rejected**
  fields (unknown fields fail with 400 before generation). As
  shipped, Rúnmál→Aesir chat cannot complete one request against
  the real server. The fixture suite cannot see this: the recorded
  fixtures were authored to the adapter's assumption.
- **D2 — Sampler overclaim on the OpenAI route. DIVERGENT.**
  Of the adapter's eight declared-honoured controls, Aesir's
  OpenAI chat route accepts only **temperature, top_p,
  max_tokens, seed**. **top_k, min_p, repetition_penalty
  (`repeat_penalty`) and stop are rejected fields** there — so a
  preset that sets any of them passes Rúnmál's own honesty filter
  (the S702 declaration says honoured) and then fails at Aesir.
  Against the real server the S702 declaration is false, which is
  precisely what INV-005 forbids. The full set Rúnmál wants *is*
  served — on the native `/v1/generate` route and in Ollama-mode
  options — just not where the adapter asks for it.
- **D3 — Aesir embeddings are NOT SERVED.** The embedding adapter
  posts to `/v1/embeddings`; no such route exists. Every call
  404s and degrades through `embed_or_fallback` to FTS — memory
  keeps working, honestly degraded, never a crash — but "Aesir
  embeddings" is not a capability any slice may bind to. Aesir's
  own posture agrees: "Embeddings remain Ollama" (its Bifröst
  line); its internal mean-pool extraction has no HTTP route.
- **D4 — The default endpoint reaches nothing. DIVERGENT by
  default, READY-IF-CONFIGURED.** Rúnmál's default
  `127.0.0.1:8000/v1` matches neither Aesir port (18434 native,
  11434 ollama-mode). The profile seam already carries the cure —
  `config.base_url` plus a secret reference for native mode's
  mandatory bearer — so a correctly written profile connects;
  the out-of-box default and the doctor's assumption do not.
- **D5 — Model listing is READY-degraded, with a runnable trap.**
  Aesir's entries carry only `id`; the adapter's optional-field
  reads degrade exactly as designed (display name falls back to
  the id, context/max output become unknown). But the list is
  the **catalog**, while only the **resident** model can
  generate: Rúnmál can offer a model that then 404s at
  generation (mapped honestly to `ModelNotFound`). HAVE-THIN in
  P-004's language; slices must not treat listing as readiness —
  Aesir's `/health/ready` (UNCONSUMED) is the truthful signal.
- **D6 — Incomplete-stream honesty gap. DIVERGENT.** Aesir warns
  that a post-header failure may end the stream with no terminal
  marker and no [DONE]. The adapter yields `Done` after *any*
  clean EOF, [DONE] or not — a truncated stream is
  indistinguishable from success in Rúnmál's event vocabulary.
  (An SSE `error` frame, when Aesir can still send one, *is*
  mapped and raised — that half is READY.)
- **D7 — Long chats exceed Aesir's admission bounds. DIVERGENT
  at scale.** The adapter sends full history unbounded; Aesir
  caps the body at 131072 bytes, 128 messages, 64 KiB per field.
  Short chats fit; the long roleplay chats that are Rúnmál's
  home territory will be refused with 400. Part V (chat surgery)
  and any Aesir-bound history policy must reckon with this.
- **D8 — Error mapping is PARTIAL.** Aesir's 422 (context /
  generation admission) has no case in `map_error`; it falls to
  the message heuristic ("context"+"length"/"maximum") and
  otherwise lands as a generic `ProviderError` instead of
  `ContextOverflow`. HTTP 401/403/404/429/400/5xx and the
  streaming error-object path do map as declared.
- **D9 — UNCONSUMED Aesir surface.** Aesir serves, and Rúnmál
  does not use: `POST /v1/completions` (the text paradigm —
  P-008's WANTED-TEXT now has a concrete served endpoint on
  Volmarr's own engine), the native `/v1/generate` route with
  the full sampler set (the natural cure for D2), the Boolean
  `response_format` subset, Gemma tool calls, and
  `/health/live` + `/health/ready`. None is a defect; each is a
  binding choice a later slice may make knowingly.
- **D10 — A second, unproven interop path exists.** Aesir's
  `--ollama` mode speaks the Ollama subset Rúnmál's *other*
  adapter targets, with wider options than the OpenAI route —
  but its `num_ctx` must equal the loaded context exactly,
  while Rúnmál's Ollama adapter sends `num_ctx` from the
  canonical context_length control. Whether that pair works
  live is **NOT PROVEN**; recorded here so the gate sees the
  option, not as a claim.

What *is* READY (always with NOT PROVEN LIVE attached): the
route shapes themselves (`/v1/chat/completions`, `/v1/models`
exist in both modes, at a `/v1`-rooted base URL as the adapter
assumes); the SSE framing (data: pieces, finish_reason, exactly
one [DONE]) matches the fixture shape the contract suite proves;
the message shape (string role/content) matches; health via
`GET /models` works in both modes; and profile configurability
(base_url + secret reference) covers the port and auth
corrections without new code.

## 4. Summary for priority (P-013) and the gate (P-014)

1. **First recommendation — an Aesir binding repair slice,
   NO HOME in Parts II–VI.** Minimum honest repair: stop sending
   `stream_options`; re-declare the OpenAI-route sampler set to
   the served subset (temperature/top_p/max_tokens/seed) *or*
   rebind the adapter to the native `/v1/generate` route where
   the full set is served; correct the default base URL (or
   stop shipping a default that reaches nothing); map 422;
   require the terminal marker before yielding `Done`. Kin to
   P-008's generic-adapter recommendation — same adapter family,
   same gate. Until it lands, every "Aesir-ready" statement in
   parity work names D1/D2 as its exception.
2. **Embeddings bind to Ollama, never to Aesir** (D3), until
   Aesir publishes an embeddings route in a new matrix version.
3. **No slice may assume** Aesir vision/multimodal, general
   tools, or general structured output; the served subsets are
   the Boolean response_format (S23) and Gemma single-function
   calls (S24), recorded at D9.
4. **The live smoke is owed**: one real Aesir `serve` (resident
   model) + one Rúnmál chat + one model listing, run where
   Aesir runs (purplelongship discipline), is the only evidence
   that can retire NOT PROVEN LIVE. This ledger deliberately
   ran no server; it binds documents to documents and says so.

## 5. F-02 follow-on (2026-10-30, appended — the record above stands)

The P-014 gate homed this ledger's first recommendation as
follow-on **F-02**, and F-02 is banked: `stream_options` is
no longer sent (D1 closed in code), the declared sampler set
is re-declared to the served OpenAI-route subset
{temperature, top_p, max_tokens, seed} (D2 closed in code;
the native-route rebind remains the recorded alternative),
the default base URL is Aesir's native port 18434 at the
adapter, the profile builder, and the doctor (D4 closed),
422 maps to `ContextOverflow` (D8 closed), and a stream
with neither terminal marker nor finish reason raises
instead of yielding `Done` (D6 closed). Resident-model
readiness is surfaced from `/health/ready` at the server
root (D5's truthful signal, VX-19's narrowed home). The D3
binding rule — embeddings bind to Ollama, never to Aesir —
is recorded in the embedding backend's own docstring.
Full record: `docs/AESIR_BINDING_REPAIR_2026-10-30.md`.

**NOT PROVEN LIVE stands, unchanged.** F-02's remaining
completion criterion is the live smoke of §4 point 4, a
purplelongship leg the keeper cannot run. D7 (admission
bounds), D9 and D10 stand as this ledger recorded them.
