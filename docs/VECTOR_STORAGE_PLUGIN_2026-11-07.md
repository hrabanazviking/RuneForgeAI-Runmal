# P-085 — Vector Storage plugin (Part VI, Extensions Row)

Roadmap line: *Vector Storage plugin: per-chat/character vector memory with the founding sqlite-vec store.*

Clean-room: built from the roadmap line and Runmal's own contracts only — the P-081 Plugin API v1, the P-082 sandbox policy, the founding memory stack (S401/S403/S407) and the P-041 embedding-honesty law. Base 0299f40b (P-083 banking record), migration head 0041. **No migration taken.**

## What landed
`src/runmal/plugins/vector_storage.py` — a first-class P-081 citizen, id `runmal.vector-storage`:
- capabilities `chat.events`, `prompt.hooks`, `ui.slots`; permissions `chat.read`, `prompt.inject`, `ui.contribute` (`chat.write` NOT declared);
- events `chat.created` (declared, deliberate no-op), `message.created`, `message.edited`, `message.deleted`;
- one slots-stage prompt hook `vector-recall`; one UI contribution `vector-panel` in `chat.sidebar`;
- settings defaults `{top_k: 5, min_score: 0.0}` read by `VectorStorageConfig` (strict validation; lenient manifest fallback, the P-084 pattern).

## How it works
`VectorMemoryIndex` wraps any founding `VectorStore` (the sqlite-vec adapter or the in-memory contract twin) under scoped doc ids `chat|<chat_id>|<memory_id>` / `character|<character_id>|<memory_id>`. Scope separation is structural: search over-fetches from the store, then returns only docs whose metadata matches the ONE scope named — a cross-scope doc can never leak, even when its vector scores highest. `forget`, `clear_scope` and `count_scope` are likewise per-scope.

The DB layer works on founding memory rows: `scoped_memories` selects owner-scoped rows with `scope='chat'` + matching `chat_id`, or `scope='character'` + matching `character_id`. `rebuild_scope_index` embeds those rows in ONE batched backend call, clearing the scope first so deleted memories vanish from the index. `search_scoped_memories` embeds the query, auto-rebuilds an empty scope, filters by `min_score`, caps at `top_k`, and returns the inspectable result `{road, provenance, hits}`. `vector_status` reports memory count vs indexed count, provenance and road for one scope — per-chat and per-character state stays separate and inspectable.

On a message mutation event the citizen opens its own session from the host factory, resolves the owner from the chat row, and rebuilds that chat's scope index (read-only over the DB; the index is the store). A vanished chat is a quiet return. The `vector-recall` hook offers one system slot naming the indexed count, road and provider for the context's chat (or character) scope; with nothing indexed — or no factory/index bound — it abstains and composition is unchanged. No new HTTP surface is added.

## Embedding honesty
The default backend is the founding local provider (`local` / `hash-ngram-1`): lexical-semantic, NOT neural, and every result through it is labelled road `lexical_vector`. A configured profile backend (the S304 seam) gives true semantics through the same code and its results are labelled road `vector`, with provenance naming the provider. When embedding fails or is unavailable, search degrades to a keyword scan over the scoped memories and every hit is labelled road `keyword_fallback` with provenance `None` — a keyword fallback is never disguised as a vector hit. An empty query is road `none` with no hits.

## Sandbox stance (P-082)
Only v1 surface permissions are declared, so the derived resource grant set is empty (`sandbox_grants()` returns it; the battery pins it). No network, files or secrets are touched. Store/DB access is host-supplied wiring handed to trusted in-tree registration code, not a plugin resource grant.

## Wiring
`register_plugin(registry, session_factory, *, index, backend, config, enable=False)` is the one-call trusted registration road. `build_registry` and `create_app` are deliberately unchanged (P-081 pins the empty boot registry). P-084 banks before this slice; the keeper reconciles liveness at banking. This slice imports no unbanked code (the P-084 pattern was read as a pattern in team-02's worktree, not imported).

## Storage stance
No migration: the index rides the founding vector-store tables (`vec_spaces`, `vec_ids`, the per-space `vec0` tables) or the in-memory store. The battery pins migration head 0041 and `0042` absent.

## Verification
Battery `tests/test_p085_vector_storage.py` plus neighbours (P-081, P-082, P-083, P-041, S401, S403, S404, S407) and the full suite — counts in `hidden_files/P085_EVIDENCE.md`.
