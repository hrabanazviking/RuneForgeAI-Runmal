# P-084 — Memory Summarise plugin (Part VI, Extensions Row)

Roadmap line: *Memory Summarise plugin: rolling chat summary
into memory (the mirrors' most-loved extension), on the
founding memory stack.*

Clean-room: built from the roadmap line and Rúnmál's own
contracts only — the P-081 Plugin API v1, the P-082 sandbox
policy, and the founding memory stack (S404/Campaign IV).
Base a39e4aac (P-082 banking record), migration head 0041.
**No migration taken** (see "Storage stance" below).

## What landed

`src/runmal/plugins/summarise.py` — the first P-081 citizen
plugin, id `runmal.summarise`: the P-081 slice doc's own
section 1 canonical example made real. Where the example was
parse-shaped only (it declared a UI contribution without the
`ui.slots` capability / `ui.contribute` permission), the
citizen declares the full surface so `register()` accepts it:

- capabilities `chat.events`, `prompt.hooks`, `ui.slots`;
  permissions `chat.read`, `prompt.inject`, `ui.contribute`
  (`chat.write` is NOT declared — it is reserved in v1 and
  this citizen never writes chat messages);
- events `chat.created` (declared, a deliberate no-op),
  `message.created`, `message.edited`, `message.deleted`;
- one slots-stage prompt hook, `summary-slot`;
- one UI contribution, `summary-panel` in `chat.sidebar`;
- settings defaults `{budget_tokens: 1200, keep_recent: 6}`,
  stored verbatim per P-081 and read by the citizen's own
  config (`SummariseConfig`; an explicit config outranks the
  manifest defaults, which outrank the module constants).

## How it works

On a message mutation event the citizen opens its own
session from the host-supplied session factory (the host's
session is committed and closed by dispatch time), resolves
the chat's owner from the chat row, and re-runs the founding
roll — `memory.summarize.roll_summaries` over the chat's
committed history, re-read rather than trusting payload
text, so edits and deletions are summarised as they stand.
The founding semantics govern: nothing folds while summary
+ history fit the budget, already-covered messages never
re-fold, and every new version writes a versioned
`ChatSummary` row plus a `kind='summary'` memory whose
sources are exactly the summarized messages.

The `summary-slot` hook offers the current summary back to
the composer as one system slot (order 4, beside retrieved
memory) headed "Rolling summary of earlier conversation
(extractive; generated from this chat's own messages)". The
host namespaces its id to `runmal.summarise:summary` and
forces provenance `plugin:runmal.summarise`. With no summary
yet — or no chat, or no factory bound — the hook abstains
and composition is unchanged.

`summary_status(session, user_id, chat_id)` returns the
inspectable state (version, summary, source range, the
linked summary memory's id and the summarizer version that
produced it), owner-scoped like every memory read. The same
rows are visible through the founding `/api/v1/memories`
surface with their sources. No new HTTP surface is added.

## Honesty: extractive v1, model-backed by seam only

The shipped summarizer, `ExtractiveSummarizer`
(`extractive-1`, the P-073 house id), is **extractive and
deterministic**: each folded message contributes one segment
(its first ten whitespace-collapsed words) under a count
header, capped at 1600 chars. Because the founding roll
folds incrementally — prior summary plus one new message per
step — a prior summary contributes its segments back rather
than being re-headed (without that recovery the headers nest
and real message heads fall out of the cap; the first
battery run caught exactly that, and it was fixed in-slice).
At the cap the middle is elided instead of the tail being
silently truncated: the first and newest segments are kept
and the dropped count rides in an `[elided N messages]`
marker that the next fold reads back, so the loss is
visible in the text and the header count always spans
every folded message. Every word in a summary comes
from the chat's own messages (or from a prior summary, itself
extractive); no model or backend is called and nothing is
invented. A model-backed summarizer is a drop-in through
`SummariseConfig(summarizer=...)` — any callable with the
S404 seam shape and a `version` attribute — and its version
string is what lands in the memory's extractor record, so
provenance always names the true generator.

One founding-roll consequence, stated plainly: editing a
message that an earlier version already summarized does not
rewrite that version's summary — covered messages never
re-fold, and the prior summary text folds forward. The edit
is reflected in everything summarized after it. Rewriting
frozen summary versions is a founding-stack question, not
this citizen's to change unilaterally.

## Sandbox stance (P-082)

The manifest declares only v1 surface permissions, so the
citizen's derived resource grant set is empty
(`summarise.sandbox_grants()` returns it; the battery pins
it). The citizen has no code path to the network, the files
or secrets. Its database access is the session factory
handed to trusted in-tree registration code — host bootstrap
wiring, not a plugin resource grant (the P-082 honesty
boundary: an API-surface contract for trusted handlers).

## Wiring — and the P-083 reconciliation point

`register_plugin(registry, session_factory, *, config,
enable=False)` is the one-call trusted registration road —
the only registration road in v1. `build_registry` and
`create_app` are deliberately unchanged: P-081's battery
pins the empty boot registry, and **P-083 (plugin manager)
banks before this slice and owns install/enable** — the
manager (or a future one-line `build_registry` change plus
the P-081 pin updates it implies) is what makes this citizen
live in the shipped app. This slice imports and depends on
no unbanked P-083 code; the keeper reconciles liveness at
banking.

## Storage stance

No migration: `chat_summaries` and the memory tables are
founding storage (S404 / Campaign IV). The battery pins
migration head 0041 and `0042` absent.

## Verification

Battery `tests/test_p084_memory_summarise.py` plus neighbours
(P-081, P-082, S404) and the full suite — counts in
`hidden_files/P084_EVIDENCE.md`.
