# Backend Profiles API — R-02 (2026-11-14)

The windowed-shell redo's first engine slice. Before R-02, the profile
system generation actually resolves through — `src/runmal/backends/
profiles.py` (S306): chat + embedding backends/models, STT/TTS refs, and
the server-side secret store — had **no HTTP router at all**. Its
`create_profile` / `put_secret` had no router callers; only `get_profile`
/ `build_chat_backend` were consumed (by generation, chats, and the
bridge). No client, UI or API, could create the profile generation uses
or store an API key for it. R-02 gives it a door.

## Routes (`/api/v1`, local-credential auth like every engine route)

| Route | Purpose |
|---|---|
| `POST /backend-profiles` | Create (201). Optional write-only `chat_secret` / `embedding_secret` plaintext fields are stored via the secret store at creation and never echoed. |
| `GET /backend-profiles` | List, owner-scoped, name order. |
| `GET /backend-profiles/{id}` | Detail. |
| `PATCH /backend-profiles/{id}` | Partial update (name, backends, models, refs, `config`). Secrets are not patchable here. |
| `DELETE /backend-profiles/{id}` | Delete the profile and, once unreferenced, its secret rows. |
| `PUT /backend-profiles/{id}/chat-secret` | Set/replace the chat API key (body `{"value": …}`). |
| `DELETE /backend-profiles/{id}/chat-secret` | Clear the chat key; idempotent. |
| `PUT /backend-profiles/{id}/embedding-secret` | Set/replace the embedding API key. |
| `DELETE /backend-profiles/{id}/embedding-secret` | Clear the embedding key; idempotent. |
| `GET /backend-profiles/{id}/health` | Probe the profile's chat backend. Failures are data (`ok: false` + plain detail + latency), never a 500. |
| `GET /backend-profiles/{id}/models` | The chat backend's normalized model list (model-picker source). Backend failure answers 502 with the adapter's sanitized taxonomy message. |

Errors follow the house shape: unknown backend / empty name / empty
secret → 422, duplicate name → 409, unknown profile → 404.

## Secrets (INV-023)

Secret values are **write-only**: accepted only in request bodies,
stored only in the `secrets` table via `put_secret`, resolved only
server-side inside `build_chat_backend` / `build_embedding_backend`.
Every response carries references + `has_chat_secret` /
`has_embedding_secret` booleans only. Rotating a secret deletes the
replaced row (unless another profile still references it); clearing a
secret and deleting a profile do the same, so values do not linger
server-side after their profile stops pointing at them. The R-02 tests
assert a canary value appears in **no** response body — create, list,
detail, patch, secret set, health, models, and the streamed `/generate`
output included.

## Legacy `connections` (S211) — retirement, no migration

The S211 `connections` profiles are a separate, older system. Their
data **never drove generation** — generation has always resolved
through backend profiles. R-02 therefore retires them plainly:

- No data is migrated (there is nothing generation could gain from it)
  and no rows or routes are deleted, so existing data is not destroyed.
- The retirement is stated in `connections/service.py`,
  `connections/router.py`, and `backends/profiles.py`.
- The one remaining reader is the per-chat generation manifest, which
  uses the active connection only as a sampler-compatibility label.
- New clients — the desktop shell's Connections page (R-09) above all —
  bind to `/backend-profiles`. The name "connections" is not reused for
  the new API in this slice.

## Bug fixed in-slice

`build_chat_backend` / `build_embedding_backend` ignored a profile's
`config.base_url` for Ollama (chat + embedding) and OpenRouter (chat),
while honouring it for Aesir and OpenAI. A profile pointing at a
non-default Ollama endpoint would silently probe and generate against
the adapter default `http://127.0.0.1:11434`. All backends now honour
`config.base_url` uniformly — which the health/models routes above
depend on to probe the endpoint the profile actually names.

## Verification

`tests/test_r02_backend_profiles.py`: CRUD + validation/conflict/auth,
secret set/replace/clear with canary-never-echoed assertions on every
response, service-level proof that rotated/cleared/deleted secrets are
removed from the store, fake-backend health + model list, unreachable-
Ollama health as `ok: false` data (with a secret on the profile),
legacy-connections separation, and the full round trip:
create → secret → health → `POST /generate` with `profile_id`, answered
by the created profile's own fake backend (`X-Backend-Key: fake`,
streamed text exactly the profile backend's script). The same round
trip is also driven with curl against a locally served app in the
slice's banking evidence.
