# P-088 — Web Search plugin (Part VI, Extensions Row)

Roadmap line: *Web Search plugin: opt-in, per-chat, with
results cited into context (off by default — sovereignty is
the default state).*

Clean-room: built from the roadmap line and Rúnmál's own
contracts only — the P-081 Plugin API v1, the P-082 sandbox
policy, and the banked citizen pattern (P-084 first, P-086
for per-chat configuration). Base 09aa5986 (P-086 banking
record), migration head 0041. **No migration taken** (see
"Storage stance" below). Held behind P-087 in roadmap
order; the keeper banks P-087 first and reconciles.

## What landed

`src/runmal/plugins/web_search.py` — a first-class P-081
citizen plugin, id `runmal.web-search`:

- capabilities `chat.events`, `prompt.hooks`, `ui.slots`;
  permissions `chat.read`, `prompt.inject`, `ui.contribute`
  (`chat.write` is NOT declared — it is reserved in v1 and
  this citizen never writes chat messages);
- events `chat.created` (declared, a deliberate no-op) and
  `chat.deleted` (drops that chat's opt-in and stored
  results). No `message.*` events are declared: no event
  ever triggers a search;
- one slots-stage prompt hook, `web-search-slot`;
- one UI contribution, `web-search-panel` in `chat.sidebar`;
- settings defaults `{max_results: 5}`, read by the
  citizen's own config (`WebSearchConfig`; an explicit
  config outranks the manifest defaults, which outrank the
  module constants).

`build_registry` / `create_app` are unchanged — P-081's
battery pins the empty boot registry. The citizen registers
only through its own `register_plugin` from trusted code.

## Sovereignty: off by default, explicit action only

Per-chat opt-in (`ChatWebSearchConfig`, default
`enabled=False`) lives on the plugin instance, following
the P-086 stance: in memory, lost on restart, stated
plainly. An unknown chat is a disabled chat.

The ONLY road that can invoke a provider is the explicit
`WebSearchPlugin.search(chat_id, query)` action, and its
opt-in check runs first — before the provider is touched
and before the query is even validated. A chat that has
not opted in gets `WebSearchDisabledError`, and the battery
pins that a counting provider records **zero** calls for
a disabled chat: no search, no network-shaped call, no
stored state.

The `web-search-slot` prompt hook never searches. It only
offers an already-fetched result set, and it abstains the
moment the chat's opt-in is off — disabling a chat after a
search stops context injection immediately (the stored set
stays inspectable via `search_status` until cleared or
the chat is deleted).

## Citations into context

Results reach the composer exclusively through
`format_result_set`, which renders a header naming the
provider and road, then one block per result:
`[i] <title> — <url>` followed by the snippet. There is
no rendering path that emits a snippet without its source.
The same pairs are inspectable as data:
`SearchResultSet.to_dict()` exposes `citations` —
1-based rows of `{index, title, url, snippet, provider}`
aligned with the rendering. A result row itself refuses
to exist without a non-empty title and an `http(s)` URL
(`SearchResult` validation), so an uncitable hit is
rejected at the provider seam, never injected.

## Provider seam and honesty

A provider is any object with `search(query, *,
max_results)` (sync or async) or any plain callable of
that shape, returning `SearchResult` rows, mappings, or
`(title, url, snippet)` tuples. Provenance is stamped
honestly: the result set names the provider and road the
labels came from, and a provider failure raises
`WebSearchError` and stores nothing new (a prior result
set survives untouched).

Two providers ship:

- `DeterministicSearchProvider` — the default. Pure
  hash/string work derived from the query;
  provider `deterministic-1`, road `deterministic`. Its
  URLs live on `https://example.invalid/...` (the RFC
  2606 reserved domain, never a real source) and every
  snippet says plainly that it is a deterministic
  placeholder, "not a real web source". Deterministic
  across calls, never disguised as real search.
- `HttpJsonSearchProvider` — the real-web shape:
  provider `http-json`, road `web`. It fills an endpoint
  template (`{query}` URL-quoted, `{max_results}`
  optional) and calls an **injected transport** callable
  expecting a mapping with a `results` list. The provider
  opens no socket itself: the transport IS the network
  road, supplied by the host. Tests inject fake
  transports only — the battery touches no real network.

## Sandbox stance (P-082)

The manifest declares only v1 surface permissions, so the
derived resource grant set is EMPTY (`sandbox_grants()`
proves it). `network.access` is deliberately not part of
the v1 manifest vocabulary, so no v1 manifest can declare
it; like P-086's model access, the provider/transport is
host wiring handed to trusted in-tree registration code,
and the per-chat opt-in above is the gate that wiring is
exercised through.

## Storage stance

No migration. Per-chat config and each chat's latest
result set are in-memory on the plugin instance (the
P-086 pattern) and are lost on restart. The battery pins
migration head 0041 and the absence of 0042.
