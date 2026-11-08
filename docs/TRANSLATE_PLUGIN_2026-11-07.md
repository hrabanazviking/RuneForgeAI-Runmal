# P-086 — Translate plugin (Part VI, Extensions Row)

Roadmap line: *Translate plugin: messages in/out via local
models by default; provider-pluggable.*

Clean-room: built from the roadmap line and Rúnmál's own
contracts only — the P-081 Plugin API v1, the P-082 sandbox
policy, and the backend / generation seams. Base 0299f40b
(P-083 banking record; P-084 and P-085 bank after it and
are reconciled by the keeper), migration head 0041.
**No migration taken** (see "Storage stance" below).

## What landed

`src/runmal/plugins/translate.py` — the third P-081 citizen
plugin, id `runmal.translate`, pattern P-084
(`runmal.summarise`):

- capabilities `chat.events`, `prompt.hooks`, `ui.slots`;
  permissions `chat.read`, `prompt.modify`, `ui.contribute`
  (`chat.write` is NOT declared — it is reserved in v1 and
  this citizen never creates, edits or deletes messages);
- events `chat.created` (declared, a deliberate no-op),
  `chat.deleted`, `message.created`, `message.edited`,
  `message.deleted`;
- one messages-stage prompt hook, `translate-in`
  (priority 100) — deliberately no slots-stage hook, so
  `prompt.inject` is not declared: translation is a
  transform plus a view, nothing additive to inject;
- one UI contribution, `translation-panel` in
  `chat.sidebar` (payload route `translation`), whose live
  data is `translation_status(chat_id)` /
  `latest_translation(chat_id)`;
- settings defaults `{target_in: en, target_out: en,
  max_chars: 4000}`, read by the citizen's own config
  (`TranslateConfig`; an explicit config outranks the
  manifest defaults, which outrank the module constants,
  and `config_from_manifest` falls back leniently on
  corrupt defaults, the P-084 pattern). Per-chat state is
  a `ChatTranslateConfig` (`enabled`, `in_enabled`,
  `out_enabled`, `source_lang`, `target_in`, `target_out`),
  isolated per chat and unset (disabled) by default.

## The two legal shapes

`chat.write` is reserved and honoured by no v1 surface, so
translation has exactly two legal shapes, and this citizen
uses both:

- **IN:** the `translate-in` hook rewrites user-role
  `ComposedMessage`s in flight at the messages stage — at
  most 8 per composition, each at most `max_chars` long;
  oversize and excess messages pass through verbatim,
  every other role stays byte-identical, and any failed
  step (chat not enabled, IN disabled, source language
  unknown, source == target, translator error) abstains:
  the original composition flows unchanged. Stored
  history is never touched — the battery proves the
  stored original survives an applied translation end to
  end at the inspect choke point.
- **OUT:** on `message.created` the citizen reads the
  payload's assistant `content` (present because the
  manifest declares `chat.read`; absent ⇒ abstain, never
  fetch-and-guess), verifies the chat still exists
  through its own session, translates, and keeps the
  result in an in-memory derived store keyed by
  (chat, message), with the original text snapshot riding
  in the record — the view is inspectable against the
  preserved original, and the stored Message itself never
  changes. `message.edited` / `message.deleted`
  invalidate the derived row (an edit is never
  auto-retranslated from payload text); `chat.deleted`
  clears the chat's config and store. A failed OUT
  translation stores nothing and returns quietly — the
  derived view is best-effort.

## Honesty: deterministic by default, provenance always

The default road is **deterministic and labelled as
such**: `DeterministicTranslator` (`deterministic-1`) is
a tiny authored lexicon (12 English words, with Spanish,
French and German tables) plus a `[deterministic:<target>]`
marker on every cross-language result; unknown words pass
through unchanged, a target with no table still gets the
marker plus pass-through, and same-language input returns
unmarked. It is never presented as real translation.

The model road is provider-pluggable through
`TranslateConfig(translator=...)` / `backend=...`;
`ModelTranslator` drives the generation service exactly
like `chats/continue_impersonate._generate_text`, with
`plugin_events=False` mandatory so translation calls
never recursively dispatch plugin events. Its results
carry true provenance (`road="model"`,
`provider=<backend_key>`, `model=<model_id>`), and an
error event, a non-clean finish or empty output raises
`TranslationError` — partial text is never stored or
returned. A plain callable translator is labelled
`road="custom"`, `provider="callable"`.

Source language is always config/argument, never detected
and never invented: when it is unknown (`None`) every
surface abstains.

## Sandbox stance (P-082)

The manifest declares only v1 surface permissions, so the
citizen's derived resource grant set is empty
(`sandbox_grants()` returns it; the battery pins it). No
network, no `Sandbox.fetch`, no files or secrets. Model
access is host wiring — a `ChatBackend` handed to trusted
registration code — the same trust class as P-084's
`session_factory`.

## Wiring

`register_plugin(registry, session_factory=None, *,
config, enable=False)` is the one-call trusted
registration road — the only registration road in v1.
`build_registry` and `create_app` are deliberately
unchanged: P-081's battery pins the empty boot registry.
The default state is REGISTERED, receiving and
contributing nothing until enabled. With no session
factory bound, the OUT event surface is inert while the
IN hook (in-memory config only) still works and abstains
cleanly.

## Storage stance

No migration: per-chat config and the derived store live
on the plugin instance and are **lost on restart** — the
accepted, stated cost of taking no migration. The
battery pins migration head 0041 and `0042` absent.

## Verification

Battery `tests/test_p086_translate_plugin.py` — 26
passed. Neighbours — P-081 plugin API, P-082 sandbox,
P-083 plugin manager, P-057 post-history, S214 prompt
trace, S215 prompt inspector, P-069
continue/impersonate, S404 summarize: 239 passed; the
banked P-084 / P-085 batteries, run in the forge tree
where their code lives: 50 passed. Full suite: 3575
passed, 4 skipped. Counts are read from the logs in
`hidden_files/P086_EVIDENCE.md`.
