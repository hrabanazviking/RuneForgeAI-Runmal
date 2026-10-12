# Rúnmál Prompt Composer

The Prompt Composer is the only domain that turns persona, lore, memory, examples, history and instructions into model-facing messages. Other subsystems provide structured candidates; they do not secretly append text to the final prompt.

## 1. Slot model

Each candidate slot should carry:

- stable ID/type;
- role (`system`, `user`, `assistant`, provider-supported equivalent);
- content or structured message payload;
- insertion position/order/depth rule;
- priority;
- hard/soft token budget;
- source/provenance references;
- optional character/group scope;
- debug metadata safe for Prompt Trace.

## 2. Baseline order

Default conceptual order:

```text
main/system instruction
persona/card fields
memory nucleus
lorebook-before
retrieved memories
example dialogue
conversation summary + history
lorebook-after
Author's Note/depth injection
post-history instruction
```

A prompt preset may intentionally alter ordering, but changes remain explicit data rather than hidden code branches.

## 3. Response reservation

Before admitting optional prompt material:

1. determine model context limit or conservative configured limit;
2. reserve requested/allowed response tokens;
3. reserve provider/system overhead when known;
4. allocate remaining input budget among slots.

Never fill the entire context with prompt/history and then discover there is no safe response allowance.

## 4. Overflow policy

Overflow behavior is deterministic and versioned.

General policy:

- required system/safety/application contract slots stay unless request is impossible;
- preserve current persona identity/core memory according to configured priorities;
- optional lore/memory follows explicit rank/priority;
- old raw history may be replaced by existing summary before deletion;
- oldest low-priority history is trimmed before recent turns;
- discarded material and reason are visible in Prompt Trace.

Do not silently summarize during the synchronous generation path unless a summary already exists or the policy explicitly allows a pre-generation summarization step with its own failure behavior.

## 5. Lorebook candidates

Lore Service returns structured activated entries including trigger metadata, resolved insertion position, priority and content. Prompt Composer does not reimplement keyword scanning.

Recursive activation must already have terminated safely before slots arrive.

As implemented (S202–S204), the pipeline is three pure stages over the book's entries, in service order (priority descending, then creation order):

1. **Scan** — the last `scan_depth` messages (book-level setting, default 4) are searched for each non-constant entry's primary keys; a primary hit counts only when at least one secondary key also matches, when the entry defines secondary keys. Whole-word and case-sensitivity are per-entry toggles. Disabled and constant entries are not scanned.
2. **Activation** — one tick over the scan hits plus runtime state: `constant` entries always activate; key-hit entries activate unless a `delay_prompts` countdown is merely armed; `sticky_prompts` keeps an entry active after its trigger; `cooldown_prompts` suppresses re-triggering. Entry content may reference sibling entries with `{{lore:Entry Name}}`; references resolve depth-first, cycles and references past the hard depth cap (5) stay literal, and referenced entries activate regardless of keys. Runtime counters live outside the canonical entry definition.
3. **Budget** — activated entries become candidates packed greedily by priority (stable tie-break by entry id) under the book's token budget; seeded probability gates may discard with reason `probability_skip`, overflow with `over_budget`. Discards are data, not errors: they surface in the trace (see §9).

The lorebook editor's **activation preview** (S209) runs this exact pipeline — same functions, the book's stored rows, one tick from a clean runtime state — over author-supplied sample messages, and reports per entry: status (`included` / `discarded` + reason / `not_triggered` / `disabled`), activation path (`constant` / `key` / `sticky` / `delay` / `reference`), matched keys, and token cost. Because preview and production share the pipeline code, a preview verdict is the engine's verdict, not an approximation of it.

## 6. Memory candidates

Memory Service returns only witness-eligible candidates with temporal/status metadata and retrieval scores. Prompt Composer may apply budget/priority but does not bypass witness filtering or revive superseded memories by searching the vector store directly.

## 7. Character-card macros

Supported compatibility macros such as `{{char}}`, `{{user}}` and `{{original}}` are resolved by a defined rendering stage with fixture tests.

Metadata fields such as creator notes do not enter prompt slots merely because they exist in source JSON.

## 8. Token counting

Token count metadata declares quality:

- `exact` — tokenizer/provider exact for selected model;
- `provider` — provider endpoint/service result;
- `estimated` — conservative approximation.

Prompt Trace exposes the quality so a developer does not mistake an estimate for precision.

## 9. Prompt Trace

A trace is an explainability artifact, not the raw secret-bearing provider request.

Example:

```text
Generation G1832
model context: 16384
reserved response: 2048
count quality: exact

INCLUDED
system/main                 438
persona                     912
memory nucleus              327
lore/Folkvangr              611  trigger="Fólkvangr"
memory/M42                  244  rank=2 witness=eligible
history                    4120
Author's Note                82

DISCARDED
lore/Vanir Politics              over lore budget, priority 40
memory/M99                      superseded before composer
history/msg-17                  oldest low-priority trim
```

Trace should include stable IDs so the UI can link to memory/lore source details.

## 10. Trace privacy

Prompt Trace must redact/exclude:

- provider credentials/tokens;
- secret headers;
- internal filesystem secrets;
- bridge bearer tokens;
- hidden values unrelated to actual prompt explanation.

Whether full prompt content is persisted should be a deliberate privacy setting. Metadata-only trace may be safer by default.

## 11. Golden tests

Golden fixtures cover:

- basic persona chat;
- v2/v3 macro behavior;
- lore before/after/depth injection;
- memory witness eligibility;
- output-budget reservation;
- equal-priority deterministic tie-breaking;
- context overflow/history summarization behavior;
- unsupported/estimated token counter;
- group speaker persona selection;
- trace secret-redaction canary.

## 12. Invariant

No extension/backend/lore/memory module gets a side door to mutate the final prompt after the Composer's trace/budget decision. Extensions participate by registering typed slots/hooks that remain visible to the same budgeting and trace system.

## 13. Group speaker selection

Group rooms (S210) hold a roster of member characters and one shared transcript. Every transcript message records its speaker explicitly — the speaking character's id plus a snapshot of its display name — so later membership changes or renames never rewrite who said what. When the Composer builds a group prompt for one participant, that participant's own past messages render as assistant turns, the owner's as user turns, and other participants' as user turns labeled `Name: text`: one shared state, per-persona viewpoint.

Who speaks next is chosen by the room's **speaker policy** (S211), stored on the group with its JSON configuration; per-member knobs are `talkativeness` (0.0–1.0) and `muted`. Mute is absolute in every policy. All policies are deterministic for a fixed seed + state:

- **manual** — only the explicitly designated speaker talks. No designation, an unknown id, or a muted designee yields silence; manual never substitutes.
- **natural** — an @-mentioned unmuted member talks (roster order if several). Otherwise a talkativeness-weighted pick among unmuted members; all-zero weights degrade to a uniform pick; all muted yields silence.
- **list** — cycles a configured id order, skipping departed or muted members; an empty effective order yields silence.
- **pooled** — uniform pick from unmuted members who have not spoken since the pool last reset; the pool resets when it empties.

Policies implement the **director interface** (S212): `select(context) -> character id | None`, plus a `note_selected` hook for stateful policies. Custom directors register by name at runtime and immediately become valid group policy values — no group-service change. The built-in `fake-director` is the deterministic stand-in for a future LLM director: an @-mention wins, otherwise the least-recently-spoken member (never-spoken first, talkativeness and roster order break ties). A real LLM director will implement the same interface behind the same registry.