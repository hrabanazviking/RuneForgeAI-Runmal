# P-081 — Plugin API v1 (Part VI, The Extensions Row opener)

Roadmap line: *Plugin API v1: lifecycle, chat events, prompt
hooks, UI slots — versioned, documented, the Samtal adapter
pattern's kin.*

Clean-room: built from the roadmap line and Runmal's own
contracts only — above all the bridge row's adapter pattern
(S601–S611: a versioned protocol, scoped exact-match grants, a
capability-discovery document, a durable event outbox), turned
inward. Base 192da0d (P-079 banking record), migration head at
base 0041. **No migration taken** (see "Storage stance" below).

This document is the public contract a plugin author codes
against. A blind author needs nothing else: the manifest shape,
the lifecycle, the event catalogue, the hook contracts, the UI
slot registry, the versioning policy, and the v1 limits are all
stated here.

## The shape of the thing

A plugin is **a manifest (data) plus handlers (trusted in-tree
Python callables)**, registered in-process by host/bootstrap
code. There is no dynamic import, no entry-point loading, no
code in a manifest, pack, or HTTP request in v1, and no HTTP
register/install endpoint — installation and packs are P-083's
slice. Plugins live OUTSIDE the core packages: `chats`,
`prompt` and `generation` never grow a branch naming any plugin.

The invariants every surface honours:

- **PLG-01 Chat never dies.** No plugin failure — event, prompt
  hook, UI declaration, lifecycle callback — can fail, roll
  back, or alter the result of a host operation. Failures are
  recorded, never raised through the host path.
- **PLG-02 Manifest is data.** A manifest is JSON-able data and
  round-trips exactly through `manifest_from_data` /
  `manifest_to_data`. No code travels in it.
- **PLG-03 Declared or it does not happen.** A plugin may only
  use a surface it declared, only with the capability +
  permission that surface requires. Undeclared bindings reject
  loudly at registration.
- **PLG-04 Ordering is data.** Dispatch and hook order derive
  only from declared priority + registration order.
- **PLG-05 Traces carry no content.** Plugin echoes and failure
  records are metadata only — plugin ids, hook ids, counts,
  error types. Never prompt text, message text, or exception
  payloads beyond a truncated `str(exc)`.
- **PLG-06 Abstention is free and normal.** A hook returning
  `None` has changed nothing; it is not an error or a warning.
- **PLG-07 Provenance is forced.** Slots a plugin adds carry
  `provenance="plugin:<plugin_id>"` and ids namespaced
  `"<plugin_id>:<local>"`. A plugin cannot forge host
  provenance.

## 1. The manifest

A manifest is a JSON object. Canonical example:

```json
{
  "id": "runmal.summarise",
  "name": "Memory Summarise",
  "version": "1.0.0",
  "api_version": 1,
  "description": "Rolling chat summary into memory.",
  "author": "Rúnmál",
  "capabilities": ["chat.events", "prompt.hooks"],
  "permissions": ["chat.read", "prompt.inject"],
  "events": ["chat.created", "message.created"],
  "prompt_hooks": [
    {"id": "summary-slot", "stage": "slots", "priority": 100}
  ],
  "ui_slots": [
    {"id": "summary-panel", "slot": "chat.sidebar",
     "label": "Summary", "order": 100,
     "payload": {"kind": "panel", "route": "summary"}}
  ],
  "settings": {"schema": {}, "defaults": {}},
  "enabled_by_default": false
}
```

Field rules:

- `id`: `^[a-z0-9][a-z0-9._-]{1,63}$`, unique in the registry.
  The id namespaces slot ids, UI contribution ids, provenance.
- `name`: non-empty, ≤ 120 chars. `version`: strict
  `MAJOR.MINOR.PATCH` numeric triple (pre-release suffixes
  reject in v1). `api_version`: int, REQUIRED — compatibility
  is judged at registration, not parse time; a non-int
  `api_version` is a malformed manifest, a different failure
  class from an incompatible one.
- `description` / `author`: optional strings (default `""`).
- `capabilities`: closed vocabulary — `chat.events`,
  `prompt.hooks`, `ui.slots`, `generation.observe`. Unknown
  names reject. Duplicates collapse, order preserved.
- `permissions`: closed vocabulary — `chat.read` (message text
  may ride in event payloads), `prompt.inject` (slots stage),
  `prompt.modify` (messages stage), `ui.contribute` (UI
  contributions), and `chat.write`, which is RESERVED: in the
  vocabulary so permission cards can name it, but no v1 surface
  honours it — declaring it grants nothing, and plugins cannot
  create, edit or delete messages in v1.
- `events`: names from the catalogue in §3. Requires capability
  `chat.events`; `generation.*` names additionally require
  `generation.observe`.
- `prompt_hooks`: `{id, stage, priority}` — id unique within
  the plugin (`^[a-z0-9][a-z0-9-]{0,39}$`), stage `slots` or
  `messages`, priority int 0..999 (default 100). Requires
  capability `prompt.hooks`; stage `slots` requires permission
  `prompt.inject`, stage `messages` requires `prompt.modify`.
- `ui_slots`: `{id, slot, label, order, payload}` — id unique
  within the plugin, slot from §5, label non-empty ≤ 120,
  order int (default 100), payload a JSON-serializable dict
  whose canonical JSON is ≤ 4096 bytes (enforced at
  registration). Requires capability `ui.slots` + permission
  `ui.contribute`.
- `settings`: optional `{schema: dict, defaults: dict}`, both
  JSON-able dicts, stored verbatim. v1 validates only that they
  are dicts; interpreting them is P-098's contract.
- `enabled_by_default`: bool, default false. Consulted only by
  host bootstrap for in-tree plugins; never self-activating
  over HTTP.
- Unknown top-level keys reject. Extensions are a future API
  version's business, not silent carry.

Handlers are bound at registration as a `PluginHandlers` value
supplied by trusted in-tree code: `on_event` (one callable for
all declared events, or a per-event mapping; sync or async),
`prompt_hooks` (a mapping keyed by declared hook id),
`on_enable` / `on_disable` lifecycle callbacks. Registration
cross-checks: every declared prompt hook id has a handler; a
handler keyed by an undeclared hook id rejects; an event
mapping key outside the declared events rejects; a declared
surface without its capability/permission rejects. Any failure
means registration does not happen — no partial record.

## 2. Lifecycle

States: `discovered`, `registered`, `enabled`, `disabled`,
`errored`.

| From | To | Verb | Actor |
|---|---|---|---|
| discovered | registered | `register()` | trusted in-tree code / host bootstrap only (no HTTP in v1) |
| registered | enabled | `enable()` | owner (HTTP) or bootstrap when `enabled_by_default` |
| enabled | disabled | `disable()` | owner (HTTP) or host shutdown |
| disabled | enabled | `enable()` | owner (HTTP) |
| enabled | errored | — (host only) | the dispatcher itself, on the failure rule |
| errored | disabled | `acknowledge()` | owner (HTTP); clears the failure counter, keeps the log |
| errored | enabled | `enable()` | owner (HTTP); same counter reset, then enable |
| registered / disabled / errored | (gone) | `unregister()` | trusted code only; an enabled plugin must be disabled first |

Anything not listed raises `InvalidPluginTransition` (surfaced
as 422 by the router). A plugin can never transition itself or
another plugin: handlers receive no registry handle.

`on_enable` runs AFTER the record flips to enabled; if it
raises, the enable is undone by the failure rule — the record
lands `errored`, and over HTTP the response is the errored
record, not a 500 (the record IS the report). `on_disable` runs
after the flip to disabled; its failure is recorded but can
never veto the disable.

**Failure rule** (the substrate P-099 refines): every handler
failure appends a failure record `{plugin_id, surface, hook,
error_type, message (truncated to 500 chars), at}` and
increments a consecutive-failure counter; any successful
handler call resets the counter to 0. At **3 consecutive
failures** while enabled, the host flips the plugin to
`errored` and it receives no further dispatch of any kind.
Failures below the limit never affect the current host
operation and never block other plugins.

## 3. Chat events (fire-and-observe)

An event is dispatched only to ENABLED plugins whose manifest
declares its name, in registration order, and only AFTER the
host operation has committed — handlers never observe
rolled-back state and can never roll anything back. Each call
is wrapped individually; dispatch itself never raises. There
is no timeout in v1 (trusted in-tree handlers; timeout
discipline is P-082/P-099).

| Name | Payload (dict) |
|---|---|
| `chat.created` | `{chat_id, character_id\|None, title}` |
| `chat.renamed` | `{chat_id, title}` |
| `chat.deleted` | `{chat_id}` |
| `message.created` | `{chat_id, message_id, role, content?, content_chars}` |
| `message.edited` | `{chat_id, message_id, role, content?, content_chars}` |
| `message.deleted` | `{chat_id, message_id}` |
| `message.swipe_selected` | `{chat_id, message_id, swipe_id}` |
| `generation.before` | `{request_id, backend_key, model_id\|None, chat_id\|None, message_count}` |
| `generation.after` | `{request_id, backend_key, finish_reason, usage\|None}` |
| `generation.failed` | `{request_id, backend_key, error_code, retryable}` |

Content rule: `content` (the message text) is present ONLY
when the receiving plugin declares permission `chat.read`;
otherwise the payload carries `content_chars` and no text.
Per-plugin payloads are built per receiver — redaction is a
payload-construction property, never a handler promise.
Generation events carry metadata only, never prompt or
message text. `generation.before` fires before the backend
stream opens; `model_id` is the backend's declared default
model (the only model identity the generation seam honestly
knows). `chat_id` is threaded in by the callers that generate
FOR a chat (the `/generate` router, the bridge) and stays
null for chat-agnostic callers. Group chats are outside the
v1 catalogue: the group-chat call sites pass
`plugin_events=False` and dispatch nothing.

## 4. Prompt hooks

Two stages, both wired into the one composition choke point,
`inspect_prompt()` — the pipeline every preview, inspect and
generation-from-chat flow passes through. (Direct
`POST /generate` with caller-supplied messages does not
compose and runs NO prompt hooks in v1; it still fires
`generation.*` events.)

A hook receives a context of metadata only — plugin id, hook
id, stage, chat id, character id, model id, API version. No
session, no registry, no credentials: a hook gets data, not
the host.

**Stage `slots`** (pre-compose transform) runs inside
`inspect_prompt` AFTER layout, context-template and budget-
governor slot assembly, immediately BEFORE `compose(...)` —
so hook slots pass through the composer like any other slot
and the composer stays the sole budget authority (a hook slot
can be discarded by budget, visibly, in the trace). The
handler receives the current slots read-only and returns
slots to ADD, or `None` to abstain. Additive only in v1: a
handler cannot remove or mutate host slots or another
plugin's slots. Host post-processing of every returned slot:

- the id is namespaced `"<plugin_id>:<local>"` when it does not
  already carry the plugin's namespace; claiming another
  plugin's or a host namespace is a violation;
- provenance is FORCED to `"plugin:<plugin_id>"`, whatever the
  handler set;
- `required=True` is a violation (plugins cannot force budget
  inclusion);
- the role must be a valid prompt role.

Any violation discards the WHOLE contribution and records a
failure; composition continues.

**Stage `messages`** (post-compose transform) runs after
`compose(...)` and before rendering. `None` abstains; an
iterable REPLACES the message tuple (the `prompt.modify`
surface). Replacement entries must be composed messages with
a valid role; `slot_id` is namespaced to the plugin the same
way (a foreign namespace is a violation, never re-prefixed).
This stage runs after the composer's budget decision, so the
inspect echo reports `messages_added` / `messages_removed`
counts per hook; re-budgeting transformed output is a non-goal
of v1.

Ordering within each stage: priority ASC, then registration
order ASC. Stages always run slots-before-messages. The
ordered plan is introspectable via `prompt_hook_plan(stage)`.

Isolation: each hook call is wrapped alone. An exception, an
invalid return type, or a validation violation discards that
hook's contribution entirely (for `messages`, the pre-hook
tuple flows on), records the failure, and composition
continues with the next hook. With zero enabled plugins, or
all hooks abstaining/failing, the pipeline is byte-identical
to pre-P-081.

The inspect result always gains a `plugins` echo — metadata
only: `{"api_version": 1, "slots_stage": [{plugin_id, hook_id,
outcome: applied|abstained|failed, slots_added}],
"messages_stage": [{plugin_id, hook_id, outcome,
messages_added, messages_removed}]}`. Empty lists when no
plugins ran.

## 5. UI slots

A named registry of contribution points. Adding a slot name
is an API-version event, never a plugin's choice:

- `chat.header` — top of a chat view
- `chat.sidebar` — chat side panel area
- `chat.toolbar` — composer/chat toolbar
- `message.actions` — per-message action row
- `settings.panel` — a panel in the settings area
- `home.panel` — home/library landing area

A contribution IS its manifest `ui_slots` entry — pure data:
`{id, plugin_id, slot, label, order, payload}`. The payload is
an opaque JSON-able dict the host passes through verbatim (v1
payload kinds are conventional, not enforced: `panel {route}`,
`link {href, label}`, `action {action}` — frontend and
P-098-era consumers interpret them). Queries return
contributions sorted by (slot, order ASC, registration order
ASC, id); a contribution's `active` flag is true exactly when
its owning plugin is enabled — disabled and errored owners'
contributions remain queryable with `active: false` and their
owner state attached. A summary reports `{total, active}` for
every slot name, zeros included. Rendering is NOT in v1: no
web UI changes. What ships is the real machinery —
registration, validation, ordering, active-state, and the
read API.

## 6. Versioning + introspection

`PLUGIN_API_VERSION = 1`; `SUPPORTED_API_VERSIONS = {1}`. The
API version is an int major. A future v2 host keeps 1 in the
supported set while it can honour the v1 contracts; removing
a version from the set is the breaking act, and is what the
version exists to make explicit. A manifest's own `version`
plays no part in compatibility.

Compatibility is checked at `register()` ONLY. A manifest
whose `api_version` is not supported is REJECTED with a
`PluginCompatibilityError` carrying `{plugin_id,
plugin_api_version, supported}`: no record, no partial state.
There is deliberately no warn-and-run path in v1.

Introspection — one document teaches a consumer everything v1
speaks (the bridge `/capabilities` pattern turned inward):

```
GET /api/v1/plugins/api
{
  "plugin_api_version": 1, "supported_api_versions": [1],
  "app_version": <runmal version>,
  "events": [...], "capabilities": [...],
  "permissions": [...], "ui_slots": [...],
  "prompt_stages": ["messages", "slots"],
  "failure_limit": 3, "registered": n, "enabled": n
}
```

## 7. HTTP surface

All routes sit under `/api/v1` behind the local credential,
like every other router. Read + lifecycle verbs only:

- `GET /plugins/api` — the introspection document above.
- `GET /plugins` — list rows `{id, name, version, api_version,
  state, capabilities, permissions, events, prompt_hooks:
  count, ui_slots: count, consecutive_failures, last_error}`,
  sorted by id.
- `GET /plugins/{plugin_id}` — the list row + the manifest
  verbatim + the retained failure log (last 20) + this
  plugin's UI contributions + any reserved permissions
  flagged. Unknown id → 404.
- `POST /plugins/{plugin_id}/enable` · `/disable` ·
  `/acknowledge` — the detail row (200). An invalid transition
  → 422. An `on_enable` failure answers 200 with the errored
  record — never a 500.
- `GET /plugins/ui-slots?slot=<name>` — `{slots: summary,
  contributions: [...]}`; an unknown slot name → 422; `slot`
  omitted returns all contributions.

Deliberately ABSENT (the battery pins 404/405):
`POST /plugins` (register/install) and `DELETE /plugins/{id}`.
Registration is trusted in-process code only in v1; P-083
owns install.

## 8. Storage stance

P-081 ships NO migration; the head stays 0041 and the battery
pins it. The registry is process-local, in-memory state (the
tree's own precedents: the backend registry dict, the
generation cancel-token dict). Manifests of in-tree plugins
are re-supplied by their registering code at every boot;
enable/disable state does not survive a restart in v1 — on
boot, registered in-tree plugins start `registered`, and
bootstrap enables exactly those with
`enabled_by_default=true`. Failure logs are likewise
process-local. This is honest v1 scope: nothing a user can
install exists yet (P-083), so there is no user decision for
durability to protect. The durable enable/disable question —
and a provisional migration numbered 0042, enable flags only
— is bequeathed to P-083, the first slice with user-owned
plugin decisions.

## 9. v1 limits (stated plainly)

- No sandbox, timeouts, or resource limits (P-082). Handlers
  are trusted in-tree Python callables.
- No installing, updating, or removing plugins; no pack
  format; no permission-card UI (P-083).
- No citizen plugins ship here (P-084+). The registry boots
  EMPTY — that is the honest state, and the battery pins it.
- `chat.write` is reserved and honoured by no v1 surface.
- No frontend rendering of UI slots; no web UI changes.
- No group-chat plugin events, no plugin-to-plugin
  communication, no plugin-emitted host events, no background
  tasks for plugins, no per-chat enablement (v1 enablement is
  global per install).
- Direct `POST /generate` with caller-supplied messages runs
  no prompt hooks (it does not compose); it still fires
  `generation.*` events.

## 10. Module map

`src/runmal/plugins/` — pure modules, a service layer, one
router (mirrors the bridge/ + prompt/ package idiom):

- `api.py` — version constants + every closed vocabulary. Pure
  data, stdlib only: the audit-friendly single source.
- `manifest.py` — `PluginManifest` / `HookDecl` / `UISlotDecl`
  frozen dataclasses, strict `manifest_from_data` /
  `manifest_to_data`, `ManifestError`, and the registration-
  time surface-requirement cross-checks.
- `events.py` — `PluginEvent`, the payload builders including
  the `chat.read` redaction rule, and the stated mapping from
  plugin event names to the chat service's S107 event
  vocabulary (duplicated values, pinned equal by test — no
  import of the chat service, so no cycle).
- `hooks.py` — `PromptHookContext` (metadata only) and the two
  apply functions for the slots and messages stages.
- `registry.py` — `PluginRegistry`: lifecycle, the failure
  rule, event dispatch, the prompt-hook plan, UI contribution
  queries.
- `service.py` — host glue: `build_registry()` (empty in v1),
  the process-default registry holder, the never-raising
  dispatch helper the host wiring calls, `plugin_api_info`,
  and the record serializers.
- `router.py` — the §7 HTTP surface.
- `__init__.py` — the public surface.

Wiring (minimal, no core branch naming any plugin): `app.py`
builds the registry at `create_app`, installs it as the
service layer's default, mirrors it on `app.state`, and mounts
the router. The chat service dispatches after each listed
operation's commit; the generation service dispatches
before/after/failed around the backend stream; the prompt
inspector runs the two hook stages and always attaches the
`plugins` echo; the prompt router threads the registry from
`app.state` explicitly, and the chat/generation services
reach it through the module-level default-registry holder —
the generation cancel-token precedent — chosen once so every
existing service-level caller stays byte-identical when no
registry is installed.
